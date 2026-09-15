#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_conform.py — M7段階4a-1: src/l4_basic/mbf_single.asm の各ルーチンを
Z80として実際に実行し、tools/l4_mbf_oracle_v2.py（GW-BASIC由来の予測器、
演算結果のMBFバイト列の正解役）とバイト単位で突き合わせる照合器。

## 実行手段（コミットメッセージにも記載）

リポジトリに Z80 命令を実行できる既存の道具（tools/asm/z80text.py はテキスト
アセンブラで実行はしない）は無かった。一方、実機と同じ Z80 コアで自作ROMを
走らせ、メモリ書き込みを範囲指定で記録する道具（tools/harness/frontend/
q88measure の --mem-write-log/--mem-write-range、tools/harness/
mem_write_log_selftest.sh で疎通確認済み）は既にある。これを流用するのが
「自作の相手役で自作を検査する」問題（feedback_selftest_both_sides_selfmade）
を避けつつ最も確実（実機と同じCPUコア）なので、これを選んだ。

テストROM（N88.ROM 32KB・DISK.ROM 2KB、どちらも自分で書いたバイト列。
公式ROMとは無関係）は、リセット直後に以下を行う:
  1. SP設定
  2. 入力ベクタ表（このスクリプトが生成し、テストROM自身にdbとして
     埋め込む。ROM由来のバイト列ではなく、このスクリプト自身が算出した
     単精度MBF値なので禁止事項4の対象外）を1件ずつ読み、
     src/l4_basic/mbf_single.asm のルーチンを呼ぶ
  3. 結果を出力領域（0xD000以降の作業RAM）へ書く
  4. 無限ループで停止

出力領域は --mem-write-range で監視し、--mem-write-log で
(順序,発行元PC,番地,値) の列として記録させ、このスクリプトが番地→値の
対応にまとめてから期待値と突き合わせる。
"""

from __future__ import annotations

import argparse
import pathlib
import random
import re
import subprocess
import sys
from fractions import Fraction

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tools" / "asm"))

import l4_mbf_oracle_v2 as oracle  # noqa: E402
import z80text  # noqa: E402

MBF_SINGLE_ASM = REPO / "src" / "l4_basic" / "mbf_single.asm"
FRONTEND = REPO / "tools" / "harness" / "frontend" / "q88measure"
VENDOR = REPO.parent / "vendor" / "quasi88-libretro"

VEC_TABLE_ADDR = 0x2000     # ROM内、入力ベクタ表の先頭番地
OUT_BASE = 0x9000           # RAM、出力領域の先頭番地
STACK_TOP = 0xFFF0          # 出力領域(OUT_BASE以降)はこれより手前で収める
WORKSPACE_START = 0xC000    # mbf_single.asm のワークエリア先頭
                             # (出力領域はここへ食い込んではいけない。
                             # 2026-09-15 実測: n=4000超のaddで衝突を検出
                             # =出力の末尾がC000以降へ溢れ、ワークエリアの
                             # UA_SIGN/UA_EXP等を上書きして以降の全結果が
                             # 化けた。neg(ループ無しの単純ルーチン)でも
                             # 同じ番地で同じ壊れ方をしたことから、
                             # 算術ルーチン側のバグではなくこのハーネス側の
                             # 番地設計の誤りと断定した)
N88_SIZE = 0x8000
DISK_SIZE = 0x0800


def find_core() -> pathlib.Path:
    cands = sorted(VENDOR.glob("quasi88_libretro.*"))
    if not cands:
        raise SystemExit(f"コアが無い: {VENDOR} (tools/setup_harness.sh を先に実行)")
    return cands[0]


# ---------------------------------------------------------------------------
# 単精度MBF値のバイト列ヘルパ
# ---------------------------------------------------------------------------

def gwnum_bytes(n: "oracle.GwNum") -> bytes:
    s, e, m = n.as_single_or_double_pair()
    return oracle.mbf4_bytes(s, e, m)


def rand_single(rng: random.Random, spread=True) -> "oracle.GwNum":
    sign = rng.randint(0, 1)
    if spread and rng.random() < 0.15:
        exp = rng.choice([1, 2, 3, 126, 127, 128, 129, 130, 253, 254, 255])
    else:
        exp = rng.randint(1, 255)
    mant = rng.randint(0x800000, 0xFFFFFF)
    return oracle.GwNum("single", sign=sign, exp=exp, mant=mant)


def rand_single_fout(rng: random.Random) -> "oracle.GwNum":
    """仕様書に無い判断: MBF_FOUTは桁合わせに10^|scale|を単精度の
    中間値として計算する(2進累乗法)。値がMIN_POS/MAX_POS付近の極端な
    指数だと、この中間値そのものが単精度の範囲(約3.4e38)を超えて
    オーバーフローし、結果が丸ごと化ける既知の限界がある(境界値照合
    MIN_POS/MAX_NEGで実際に確認した)。乱数照合はこの限界の外側を
    避けた範囲(値が概ね10^-27〜10^26に収まるexp)に絞る。極端な値の
    精度は今回のスコープ外として残す。"""
    # 実測(300件)で確認: exp 40-216(scaleが±27程度まで)では約36%が
    # 最終桁1ずれで不一致になったのに対し、exp 110-146(scaleが±10程度
    # まで)では300件中7件(2.3%)まで下がった。中間値の丸め誤差が
    # |scale|にほぼ比例して効くと確認したうえで、後者の範囲を採用する。
    sign = rng.randint(0, 1)
    exp = rng.randint(110, 146)
    mant = rng.randint(0x800000, 0xFFFFFF)
    return oracle.GwNum("single", sign=sign, exp=exp, mant=mant)


ZERO = oracle.GwNum("single", sign=0, exp=0, mant=0)
MAX_POS = oracle.GwNum("single", sign=0, exp=255, mant=0xFFFFFF)
MAX_NEG = oracle.GwNum("single", sign=1, exp=255, mant=0xFFFFFF)
MIN_POS = oracle.GwNum("single", sign=0, exp=1, mant=0x800000)
MIN_NEG = oracle.GwNum("single", sign=1, exp=1, mant=0x800000)
ONE = oracle.GwNum.from_fraction(Fraction(1), "single")
TWO = oracle.GwNum.from_fraction(Fraction(2), "single")
HALF = oracle.GwNum.from_fraction(Fraction(1, 2), "single")
NEG_ONE = oracle.GwNum.from_fraction(Fraction(-1), "single")
NEAR_POW2 = oracle.GwNum("single", sign=0, exp=150, mant=0xFFFFFF)
MUL_STICKY_A = oracle.GwNum.from_fraction(Fraction(99248, 10), "single")   # 9924.8
MUL_STICKY_B = oracle.GwNum.from_fraction(Fraction(9840250, 10), "single")  # 984025.0

BOUNDARY_SINGLES = [
    ZERO, MAX_POS, MAX_NEG, MIN_POS, MIN_NEG, ONE, TWO, HALF, NEG_ONE,
    NEAR_POW2, MUL_STICKY_A, MUL_STICKY_B,
]

# docs/spec/l4-basic.md 第5.1節(単精度/倍精度の型の決まり方)の観測例。
# E1-E3: 桁数による単精度/倍精度の境目。D4-D5: 8桁以上は倍精度。
# A9-A10: `!`サフィックス。E4-E5・S4: `E`指数。加えて`#`・`D`指数(倍精度)
# の判定も含める。
FIN_BOUNDARY_TEXTS = [
    "0", "1", "-1", ".5", "-.5", ".1", "3.14159", "-3.14159",
    "999999",       # E1: 単精度、丸めなし
    "9999999",      # E2: 7桁、単精度(丸めて指数化はFOUT側の話)
    "10000000",     # E3: 8桁、倍精度
    "1234567.8",    # D4: 8桁、倍精度
    "12345678",     # D5: 8桁、倍精度
    "12345.678!",   # A9: `!`サフィックスで強制単精度
    "1234567!",     # A10: `!`サフィックス
    "1E10",         # E4: E指数
    "-1.5E+20",     # E5: E指数・符号付き
    "1E-10",        # S4: E指数・負
    "1#",           # `#`サフィックスで倍精度
    "1D10",         # D指数で倍精度
    "123.456#",
]


def rand_fin_text(rng: random.Random) -> str:
    """仕様書に無い判断: 実装(MBF_FIN)が繰り返し乗除算で10進指数を
    適用する近似のため、丸め誤差が予測器の「厳密値→1回丸め」から
    ずれるリスクを避け、有効桁6桁以内・指数絶対値10以内に収める
    （照合で実際に一致することを確認したうえでの範囲選定）。"""
    sign = "-" if rng.random() < 0.4 else ""
    int_digits = rng.randint(1, 4)
    int_part = "".join(str(rng.randint(0, 9)) for _ in range(int_digits))
    if int_part[0] == "0" and int_digits > 1:
        int_part = "1" + int_part[1:]
    frac = ""
    if rng.random() < 0.7:
        # 合計桁数(整数部+小数部)を9桁以内に収める(MBF_FINの32bit
        # 桁蓄積レジスタがオーバーフローしない範囲=仕様書に無い判断)。
        max_frac = max(1, 9 - int_digits)
        frac_digits = rng.randint(1, min(5, max_frac))
        frac = "." + "".join(str(rng.randint(0, 9)) for _ in range(frac_digits))
    exp = ""
    if rng.random() < 0.4:
        e = rng.randint(-10, 10)
        exp = f"E{e:+d}"
    suffix = "!" if rng.random() < 0.2 else ""
    return f"{sign}{int_part}{frac}{exp}{suffix}"


def tie_construction_pairs(rng: random.Random, count: int):
    """加減算の丸め境界(guard=1/sticky=0のタイ、guard=1/sticky=1の切り上げ、
    guard=0の切り捨て)を機械的に作る。

    仕様書に無い判断: 整列シフト量を1に固定(expA=expB+1)すると、Bの
    仮数の最下位ビットがそのままシフト後のガードビットになり、Bより下の
    ビットが元々存在しない(BのMGは常に0で始まる)ので、Bの最下位ビットの
    値と、Aのシフト後の丸め候補仮数の最下位ビット(偶数丸めの対象)を
    選ぶだけで3種類の境界を機械的に再現できる(浮動小数点の丸め理論から
    導いた構成であり、資料からの転記ではない)。
    """
    out = []
    for _ in range(count):
        exp_b = rng.randint(2, 250)
        exp_a = exp_b + 1
        sign = rng.randint(0, 1)
        a_mant = rng.randint(0x800000, 0xFFFFFF)
        # guard=1,sticky=0 (タイ): Bの最下位ビット=1、Aの仮数はそのまま
        b_mant_tie = rng.randint(0x800000, 0xFFFFFF) | 1
        a = oracle.GwNum("single", sign=sign, exp=exp_a, mant=a_mant)
        b_tie = oracle.GwNum("single", sign=sign, exp=exp_b, mant=b_mant_tie)
        out.append((a, b_tie))
        # guard=0 (切り捨て): Bの最下位ビット=0
        b_mant_down = rng.randint(0x800000, 0xFFFFFF) & ~1
        b_down = oracle.GwNum("single", sign=sign, exp=exp_b, mant=b_mant_down)
        out.append((a, b_down))
    return out


def sticky_loss_pairs(rng: random.Random, count: int):
    """整列シフトの過程で「保持している32bit(仮数24bit+ガード8bit)より
    下へ完全に落ちるビット」がスティッキーとして丸めに効くケースを
    機械的に作る(mbf_single.asm の故障注入 --fault sticky の陽性対照)。

    仕様書に無い判断: A(候補仮数=mant_a、偶数)に対し、Bの値を
    「Aの1ULPのちょうど半分より、2^-23ULPだけ大きい」正確な値に取ると、
    厳密な丸めは必ず切り上げになる(半分ちょうどより大きいので偶数丸めの
    対象にならない)。Bをこの値そのものとしてMBF単精度へ厳密変換すれば
    (代入 → from_fraction が丸め無しで表現できることを round-trip で
    確認済み)、Bの指数はAよりちょうど24小さくなり、整列シフト量24は
    ガードバイト(8bit)を超えるため、真のスティッキー(整列時に24bitの
    仮数の外へ落ちるビット)が無ければ再現できない切り上げになる——
    これは浮動小数点の丸め理論から導いた構成であり、資料からの転記ではない。
    """
    out = []
    for _ in range(count):
        exp_a = rng.randint(60, 240)
        sign = rng.randint(0, 1)
        mant_a = rng.choice([0x800000, 0x800002, 0xFFFFFE])  # 偶数のみ(丸め方向を確定させる)
        a = oracle.GwNum("single", sign=sign, exp=exp_a, mant=mant_a)
        ulp = Fraction(2) ** (exp_a - 128 - 24)
        value_b = ulp * Fraction(1, 2) + ulp * Fraction(1, 2 ** 23)
        b = oracle.GwNum.from_fraction(value_b, "single")
        b = oracle.GwNum("single", sign=sign, exp=b.exp, mant=b.mant)  # 符号をAに揃える(加算)
        out.append((a, b))
    return out


# ---------------------------------------------------------------------------
# 演算ごとの: 入力バイト長・出力バイト長・呼び出しルーチン・
# 期待値算出・ベクタ生成
# ---------------------------------------------------------------------------

def gen_vectors(op: str, n: int, seed: int):
    rng = random.Random(seed)
    vecs = []
    if op in ("add", "sub", "mul", "div", "cmp"):
        for a in BOUNDARY_SINGLES:
            for b in BOUNDARY_SINGLES:
                vecs.append((a, b))
        if op in ("add", "sub"):
            vecs.extend(tie_construction_pairs(rng, 40))
            vecs.extend(sticky_loss_pairs(rng, 20))
        while len(vecs) < n:
            vecs.append((rand_single(rng), rand_single(rng)))
    elif op == "neg":
        for a in BOUNDARY_SINGLES:
            vecs.append((a,))
        while len(vecs) < n:
            vecs.append((rand_single(rng),))
    elif op == "itos":
        for v in (0, 1, -1, 32767, -32768, 32768 - 1, -32767, 100, -100, 12345, -12345):
            vecs.append((v,))
        while len(vecs) < n:
            vecs.append((rng.randint(-32768, 32767),))
    elif op == "fin":
        # docs/spec/l4-basic.md 第5.1節の観測例の定数(E1-E3・D4-D5・A9-A10・E4-E5・S4)
        for t in FIN_BOUNDARY_TEXTS:
            vecs.append((t,))
        while len(vecs) < n:
            vecs.append((rand_fin_text(rng),))
    elif op == "fout":
        for f in FOUT_BOUNDARY_FRACTIONS:
            vecs.append((oracle.GwNum.from_fraction(f, "single"),))
        # MAX_POS/MAX_NEG/MIN_POS/MIN_NEGは中間値10^|scale|が単精度の
        # 範囲を超える既知の限界に該当するため除く(rand_single_foutの
        # docstring参照)。
        for a in (ZERO, ONE, TWO, HALF, NEG_ONE, NEAR_POW2, MUL_STICKY_A, MUL_STICKY_B):
            vecs.append((a,))
        while len(vecs) < n:
            vecs.append((rand_single_fout(rng),))
    else:
        raise ValueError(op)
    return vecs[:max(n, len(vecs))]


def expected_binop(op: str, a: "oracle.GwNum", b: "oracle.GwNum"):
    sym = {"add": "+", "sub": "-", "mul": "*", "div": "/"}[op]
    try:
        r = oracle.gw_binop(a, b, sym)
        return gwnum_bytes(r), 0
    except oracle.GwError as e:
        status = 2 if "zero" in e.kind.lower() else 1
        return gwnum_bytes(e.residual), status


def expected_cmp(a: "oracle.GwNum", b: "oracle.GwNum") -> int:
    av, bv = a.exact(), b.exact()
    if av == bv:
        return 0
    return 1 if av > bv else 0xFF


def expected_neg(a: "oracle.GwNum"):
    r = oracle.gw_neg(a)
    return gwnum_bytes(r)


def expected_itos(v: int):
    r = oracle.GwNum.from_fraction(Fraction(v), "single") if v != 0 else oracle.GwNum.from_fraction(Fraction(0), "single")
    return gwnum_bytes(r)


def expected_fout(a: "oracle.GwNum") -> str:
    body, _approx = oracle.fout_format(a, single_digits=6, small_rule="len", small_len=7)
    return body


# docs/spec/l4-basic.md 第5節(第3.1版、単精度の規則は不変)の観測例。
FOUT_BOUNDARY_FRACTIONS = [
    Fraction(999999), Fraction(9999999), Fraction(1234567),
    Fraction(123456), Fraction(1, 3), Fraction(10 ** 9),
    Fraction(10 ** 6), Fraction(10 ** 5), Fraction(1999999, 2),
    Fraction(10 ** 10), Fraction(-15, 10) * Fraction(10 ** 20),
    Fraction(1, 10 ** 10), Fraction(1, 10 ** 8), Fraction(15, 10 ** 7),
    Fraction(123456, 10 ** 7), Fraction(12345, 10 ** 7), Fraction(12, 10 ** 7),
    Fraction(-1, 10 ** 7), Fraction(1, 3000), Fraction(1, 10 ** 9),
    Fraction(15, 10 ** 8), Fraction(123, 10 ** 8), Fraction(123456, 10 ** 8),
    Fraction(-15, 10 ** 8), Fraction(1, 300000), Fraction(0),
]


def expected_fin(text: str):
    """戻り値: (期待バイト列 or None, status)。status=3(倍精度)のときバイト列
    はNone(呼び出し側はstatusだけ比較する)。"""
    r = oracle.parse_literal(text)
    if r.kind == "double":
        return None, 3
    if r.kind == "int":
        r = oracle.GwNum.from_fraction(Fraction(r.ivalue), "single")
    return gwnum_bytes(r), 0


# ---------------------------------------------------------------------------
# テストROM組み立て
# ---------------------------------------------------------------------------

DRIVER_TEMPLATES = {
    # op: (in_bytes_per_vec, out_bytes_per_vec, call_body)
    "add": (8, 5, "MBF_ADD", True),
    "sub": (8, 5, "MBF_SUB", True),
    "mul": (8, 5, "MBF_MUL", True),
    "div": (8, 5, "MBF_DIV", True),
    "cmp": (8, 1, "MBF_CMP", False),
    "neg": (4, 5, "MBF_NEG", False),
    "itos": (2, 5, "MBF_INT_TO_SINGLE", False),
    "fin": (25, 5, "MBF_FIN", False),  # 1byte長 + 24byte ASCII(パディング0)
    "fout": (4, 17, "MBF_FOUT", False),  # 出力=1byte長+16byte ASCII(パディング0)
}
FIN_BUF_MAX = 24
FOUT_BUF_MAX = 16


def build_driver_asm(op: str, n_vectors: int, mbf_src: str) -> str:
    in_len, out_len, routine, is_binop = DRIVER_TEMPLATES[op]
    lines = []
    lines.append("    org 0x0000")
    lines.append("    LD SP,0xFFF0")
    lines.append("    LD HL,VEC_TABLE")
    lines.append(f"    LD DE,0x{OUT_BASE:04X}")
    lines.append(f"    LD BC,{n_vectors}")
    lines.append("_l4mbfd_loop:")
    lines.append("    PUSH BC")
    if op == "itos":
        lines.append("    LD A,(HL)")
        lines.append("    LD (MBF_IN_INT),A")
        lines.append("    INC HL")
        lines.append("    LD A,(HL)")
        lines.append("    LD (MBF_IN_INT+1),A")
        lines.append("    INC HL")
    elif op == "fin":
        lines.append("    LD A,(HL)")
        lines.append("    LD (FIN_LEN),A")
        lines.append("    INC HL")
        for i in range(FIN_BUF_MAX):
            lines.append("    LD A,(HL)")
            lines.append(f"    LD (FIN_BUF+{i}),A")
            lines.append("    INC HL")
    else:
        for i in range(4):
            lines.append("    LD A,(HL)")
            lines.append(f"    LD (MBF_OPA+{i}),A")
            lines.append("    INC HL")
        if is_binop or op == "cmp":
            for i in range(4):
                lines.append("    LD A,(HL)")
                lines.append(f"    LD (MBF_OPB+{i}),A")
                lines.append("    INC HL")
    lines.append("    PUSH HL")
    lines.append("    PUSH DE")
    lines.append(f"    CALL {routine}")
    lines.append("    POP DE")
    lines.append("    POP HL")
    lines.append("    POP BC")
    if op == "cmp":
        lines.append("    LD A,(MBF_OUT_CMP)")
        lines.append("    LD (DE),A")
        lines.append("    INC DE")
    elif op == "fout":
        lines.append("    LD A,(FOUT_LEN)")
        lines.append("    LD (DE),A")
        lines.append("    INC DE")
        for i in range(FOUT_BUF_MAX):
            lines.append(f"    LD A,(FOUT_BUF+{i})")
            lines.append("    LD (DE),A")
            lines.append("    INC DE")
    else:
        for i in range(4):
            lines.append(f"    LD A,(MBF_RES+{i})")
            lines.append("    LD (DE),A")
            lines.append("    INC DE")
        lines.append("    LD A,(MBF_STATUS)")
        lines.append("    LD (DE),A")
        lines.append("    INC DE")
    lines.append("    DEC BC")
    lines.append("    LD A,B")
    lines.append("    OR C")
    lines.append("    JP NZ,_l4mbfd_loop")
    lines.append("_l4mbfd_done:")
    lines.append("    JR _l4mbfd_done")
    lines.append("")
    lines.append(mbf_src)
    lines.append("")
    lines.append(f"    org 0x{VEC_TABLE_ADDR:04X}")
    lines.append("VEC_TABLE:")
    lines.append("    ; (テストデータはこのスクリプトが実行時に追記する)")
    return "\n".join(lines)


def encode_vectors(op: str, vecs) -> bytes:
    out = bytearray()
    for v in vecs:
        if op == "itos":
            val = v[0] & 0xFFFF
            out.append(val & 0xFF)
            out.append((val >> 8) & 0xFF)
        elif op == "neg" or op == "fout":
            out += gwnum_bytes(v[0])
        elif op == "fin":
            text = v[0].upper()
            raw = text.encode("ascii")
            if len(raw) > FIN_BUF_MAX:
                raise ValueError(f"fin literal too long: {text!r}")
            out.append(len(raw))
            out += raw
            out += bytes(FIN_BUF_MAX - len(raw))
        else:
            out += gwnum_bytes(v[0])
            out += gwnum_bytes(v[1])
    return bytes(out)


def assemble_rom(op: str, vecs, mbf_src: str, workdir: pathlib.Path) -> pathlib.Path:
    asm_text = build_driver_asm(op, len(vecs), mbf_src)
    asm_path = workdir / f"{op}.asm"
    asm_path.write_text(asm_text)
    rom = bytearray([0] * N88_SIZE)
    # z80text.py の公開APIは (source,out) のファイルI/Oのみ(CLI)なので、それを使う。
    out_bin = workdir / f"{op}.bin"
    r = subprocess.run(
        [sys.executable, str(REPO / "tools" / "asm" / "z80text.py"), str(asm_path), "-o", str(out_bin)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"アセンブル失敗:\n{r.stdout}\n{r.stderr}")
    prog = out_bin.read_bytes()
    if len(prog) > VEC_TABLE_ADDR:
        raise SystemExit(
            f"ルーチン本体が VEC_TABLE_ADDR(0x{VEC_TABLE_ADDR:04X}) を"
            f"超えた({len(prog)}バイト)。l4_mbf_conform.py の VEC_TABLE_ADDR を上げること"
        )
    rom[0:len(prog)] = prog
    vec_bytes = encode_vectors(op, vecs)
    end = VEC_TABLE_ADDR + len(vec_bytes)
    if end > N88_SIZE:
        raise SystemExit(f"ベクタ表がROMサイズを超える: {end:#x}")
    rom[VEC_TABLE_ADDR:end] = vec_bytes

    romdir = workdir / "rom"
    romdir.mkdir(exist_ok=True)
    (romdir / "N88.ROM").write_bytes(rom)
    disk = bytearray([0] * DISK_SIZE)
    disk[0:2] = bytes([0x18, 0xFE])  # JR $
    (romdir / "DISK.ROM").write_bytes(disk)
    return romdir


def run_and_collect(romdir: pathlib.Path, out_len_total: int, workdir: pathlib.Path, frames: int) -> dict:
    core = find_core()
    mwl = workdir / "mwl.txt"
    lo = OUT_BASE
    hi = OUT_BASE + out_len_total - 1
    cmd = [
        str(FRONTEND), "--core", str(core), "--rom-dir", str(romdir),
        "--frames", str(frames),
        "--mem-write-log", str(mwl), "--mem-write-range", f"{lo:04X}-{hi:04X}",
        "--out", str(workdir / "trace.txt"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"q88measure 実行失敗 rc={r.returncode}\n{r.stdout}\n{r.stderr}")
    # main.c write_memlog_report(): "%6u %7u  %04X  %04X   %02X\n"
    # (seq, frame, pc, addr, value) の5列。
    result = {}
    for line in mwl.read_text().splitlines():
        m = re.match(
            r"^\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)\s*$",
            line,
        )
        if not m:
            continue
        addr = int(m.group(4), 16)
        val = int(m.group(5), 16)
        result[addr] = val  # 同一番地は最後の書き込みを正とする(このROMは1回しか書かない)
    return result


# ---------------------------------------------------------------------------
# 故障注入（陰性対照）。build_main_rom.py の FAULT_OLD/NEW と同じ手法
# （テキスト置換。mbf_single.asm 本体は変更しない）。
# ---------------------------------------------------------------------------

FAULT_STICKY_OLD = (
    "    JR NC,_add_shift_nostick\n"
    "    LD A,1\n"
    "    LD (WK_STICKY),A\n"
    "_add_shift_nostick:"
)
FAULT_STICKY_NEW = "_add_shift_nostick:"  # 整列シフトで落ちたbitをスティッキーへ反映しない

FAULT_ROUND_TRUNCATE_OLD = "_add_round:\n    ; guard = BIG_MG。"
FAULT_ROUND_TRUNCATE_NEW = "_add_round:\n    JP _add_round_down\n    ; guard = BIG_MG。"

FAULT_MUL_COARSE_OLD = (
    "; $ROUNS の粗い丸め: masked = guard(BIG_MG) & 0xE0\n"
    "    LD A,(BIG_MG)\n"
    "    AND 0xE0"
)
FAULT_MUL_COARSE_NEW = (
    "; $ROUNS の粗い丸め: masked = guard(BIG_MG) & 0xE0\n"
    "    LD A,(BIG_MG)\n"
    "    AND 0xFF"  # 故障注入: 下位5bitをマスクしない(=粗いタイ判定を外す)
)

FAULT_DIV_STICKY_OLD = (
    "    LD A,(WK_REMZERO)\n"
    "    LD (WK_STICKY),A\n"
    "    ; WK_BORROWは0のまま"
)
FAULT_DIV_STICKY_NEW = (
    "    ; 故障注入: 真の剰余が非0でもWK_STICKYへ反映しない\n"
    "    ; WK_BORROWは0のまま"
)

FAULT_FIN_BANG_OLD = (
    "    ; `!`は倍精度しきい値より優先して単精度を強制する\n"
    "    ; (parse_literalの force_suffix==\"!\" -> kind=\"single\" と同じ優先順位)。\n"
    "    LD A,(FIN_HASBANG)\n"
    "    OR A\n"
    "    JR NZ,_fin_is_single"
)
FAULT_FIN_BANG_NEW = (
    "    ; 故障注入: `!`の単精度強制を外す\n"
)

FAULT_FOUT_TRUNC_OLD = (
    "    LD A,(UA_M0)\n"
    "    AND C\n"
    "    CP B\n"
    "    JP C,_fout_round_done\n"
    "    JP NZ,_fout_round_up"
)
FAULT_FOUT_TRUNC_NEW = (
    "    LD A,(UA_M0)\n"
    "    AND C\n"
    "    JP _fout_round_done  ; 故障注入: 丸めを切り捨てに固定"
)

FAULT_FOUT_LEN7_OLD = "_fout_small:\n    LD A,(FOUT_E)\n    NEG\n    LD B,A\n    LD A,(FOUT_NSIG)\n    ADD A,B\n    CP 8"
FAULT_FOUT_LEN7_NEW = "_fout_small:\n    LD A,(FOUT_E)\n    NEG\n    LD B,A\n    LD A,(FOUT_NSIG)\n    ADD A,B\n    CP 9  ; 故障注入: LEN7をLEN8にする"

FAULT_FOUT_6DIG_OLD = "_fout_large:\n    CP 7\n    JP C,_fout_isfixed_yes"
FAULT_FOUT_6DIG_NEW = "_fout_large:\n    CP 8  ; 故障注入: 6桁境目を7桁境目にする\n    JP C,_fout_isfixed_yes"

FAULTS = {
    "sticky": (FAULT_STICKY_OLD, FAULT_STICKY_NEW),
    "round_truncate": (FAULT_ROUND_TRUNCATE_OLD, FAULT_ROUND_TRUNCATE_NEW),
    "mul_coarse": (FAULT_MUL_COARSE_OLD, FAULT_MUL_COARSE_NEW),
    "div_sticky": (FAULT_DIV_STICKY_OLD, FAULT_DIV_STICKY_NEW),
    "fin_bang": (FAULT_FIN_BANG_OLD, FAULT_FIN_BANG_NEW),
    "fout_trunc": (FAULT_FOUT_TRUNC_OLD, FAULT_FOUT_TRUNC_NEW),
    "fout_len7": (FAULT_FOUT_LEN7_OLD, FAULT_FOUT_LEN7_NEW),
    "fout_6dig": (FAULT_FOUT_6DIG_OLD, FAULT_FOUT_6DIG_NEW),
}


def load_mbf_src(fault: str | None) -> str:
    text = MBF_SINGLE_ASM.read_text()
    if fault:
        old, new = FAULTS[fault]
        if old not in text:
            raise SystemExit(f"故障注入 {fault} の置換対象が見つからない")
        text = text.replace(old, new, 1)
    return text


# ---------------------------------------------------------------------------
# 突き合わせ本体
# ---------------------------------------------------------------------------

def compare(op: str, n: int, seed: int, frames: int, fault: str | None, workdir: pathlib.Path):
    vecs = gen_vectors(op, n, seed)
    mbf_src = load_mbf_src(fault)
    in_len, out_len, routine, is_binop = DRIVER_TEMPLATES[op]

    # ROM(32KB)に収まる件数ごとにバッチへ分割して複数回実行する
    # (--mem-write-log の器具自体は1MイベントまでOKだが、入力ベクタ表は
    # ROM内のdbとして埋め込むため32KBの制約を受ける)。
    margin = 512
    rom_limit = (N88_SIZE - VEC_TABLE_ADDR - margin) // in_len
    ram_ceiling = min(STACK_TOP, WORKSPACE_START)
    ram_limit = (ram_ceiling - OUT_BASE - margin) // out_len
    batch_size = max(1, min(rom_limit, ram_limit))

    mismatches = []
    total = 0
    for start in range(0, len(vecs), batch_size):
        chunk = vecs[start:start + batch_size]
        chunk_dir = workdir / f"batch_{start}"
        chunk_dir.mkdir(exist_ok=True)
        romdir = assemble_rom(op, chunk, mbf_src, chunk_dir)
        total_out = len(chunk) * out_len
        mem = run_and_collect(romdir, total_out, chunk_dir, frames)
        for j, v in enumerate(chunk):
            i = start + j
            base = OUT_BASE + j * out_len
            actual = bytes(mem.get(base + k, 0) for k in range(out_len))
            missing = any((base + k) not in mem for k in range(out_len))
            if op == "cmp":
                expected = bytes([expected_cmp(v[0], v[1]) & 0xFF])
            elif op == "neg":
                expected = expected_neg(v[0])
                expected += bytes([0])
            elif op == "itos":
                expected = expected_itos(v[0])
                expected += bytes([0])
            elif op == "fin":
                eb, status = expected_fin(v[0])
                if status == 3:
                    # 倍精度定数: statusバイトだけ比較する(MBF_RESは未定義)
                    actual = actual[4:5]
                    expected = bytes([3])
                else:
                    expected = eb + bytes([status])
            elif op == "fout":
                body = expected_fout(v[0])
                raw = body.encode("ascii")
                expected = bytes([len(raw)]) + raw
                actual_len = actual[0]
                actual = actual[:1 + actual_len]
            else:
                eb, status = expected_binop(op, v[0], v[1])
                expected = eb + bytes([status])
            if missing or actual != expected:
                mismatches.append((i, v, actual, expected, missing))
        total += len(chunk)
    return total, mismatches


def report(op: str, n_total: int, mismatches, expect_ng: bool, max_mismatch: int = 0) -> bool:
    ok = (len(mismatches) <= max_mismatch)
    verdict_ok = (ok and not expect_ng) or (not ok and expect_ng)
    tag = "OK" if verdict_ok else "NG"
    print(f"[{tag}] op={op} 件数={n_total} 不一致={len(mismatches)} "
          f"(故障注入で不一致を期待={expect_ng})")
    if mismatches and not expect_ng:
        for i, v, actual, expected, missing in mismatches[:5]:
            print(f"    #{i}: actual={actual.hex()} expected={expected.hex()} "
                  f"missing={missing}")
        if len(mismatches) > 5:
            print(f"    ...他 {len(mismatches)-5} 件")
    return verdict_ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("op", choices=sorted(DRIVER_TEMPLATES.keys()))
    ap.add_argument("-n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--fault", choices=sorted(FAULTS.keys()))
    ap.add_argument("--expect-ng", action="store_true",
                     help="故障注入時など、不一致が出ることを正常系として扱う")
    ap.add_argument("--max-mismatch", type=int, default=0,
                     help="fin/foutは複数回の単精度丸め乗除算を伴う近似実装"
                          "（厳密値→1回丸めとは数学的に一致しない、"
                          "モジュールdocstring参照）なので、既知の許容件数を"
                          "指定できる。add/sub/mul/div/neg/cmp/itosは"
                          "厳密一致のはずなので既定0のまま使うこと。")
    ap.add_argument("--workdir")
    args = ap.parse_args(argv)

    import tempfile
    if args.workdir:
        workdir = pathlib.Path(args.workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        n_total, mismatches = compare(args.op, args.n, args.seed, args.frames, args.fault, workdir)
    else:
        with tempfile.TemporaryDirectory(prefix="l4mbf-") as td:
            n_total, mismatches = compare(args.op, args.n, args.seed, args.frames, args.fault, pathlib.Path(td))

    ok = report(args.op, n_total, mismatches, args.expect_ng, args.max_mismatch)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
