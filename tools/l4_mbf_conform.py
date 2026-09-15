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
MBF_DOUBLE_ASM = REPO / "src" / "l4_basic" / "mbf_double.asm"
FRONTEND = REPO / "tools" / "harness" / "frontend" / "q88measure"
VENDOR = REPO.parent / "vendor" / "quasi88-libretro"

VEC_TABLE_ADDR = 0x5000     # ROM内、入力ベクタ表の先頭番地
                             # (M7段階4b-1: mbf_double.asm連結でコード本体が
                             # 0x2000を超えたため0x5000へ引き上げた)
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


def gwnum8_bytes(n: "oracle.GwNum") -> bytes:
    s, e, m = n.as_single_or_double_pair()
    return oracle.mbf8_bytes(s, e, m)


def rand_double(rng: random.Random, spread=True) -> "oracle.GwNum":
    """M7段階4b-1: rand_singleの倍精度版。指数バイトは単精度と同じ8bit・
    同じバイアスを共有する(mbf_double.asmヘッダコメント参照)ので範囲は同じ、
    仮数だけ56bitへ広げる。"""
    sign = rng.randint(0, 1)
    if spread and rng.random() < 0.15:
        exp = rng.choice([1, 2, 3, 126, 127, 128, 129, 130, 253, 254, 255])
    else:
        exp = rng.randint(1, 255)
    mant = rng.randint(1 << 55, (1 << 56) - 1)
    return oracle.GwNum("double", sign=sign, exp=exp, mant=mant)


def rand_double_fout(rng: random.Random) -> "oracle.GwNum":
    """rand_single_foutの倍精度版。予測器側の10^39以上スケール未対応
    (expected_dfout_or_none参照)を避けるため、指数を安全域(概ね
    10^-27〜10^27相当)に絞る(仕様書に無い判断)。境界(MIN_POS_D/
    MAX_POS_D等)はBOUNDARY_DOUBLESで別途「オーバーフローせず動くか」
    だけを確認する。"""
    sign = rng.randint(0, 1)
    if rng.random() < 0.15:
        exp = rng.choice([40, 41, 42, 126, 127, 128, 129, 130, 213, 214, 215])
    else:
        exp = rng.randint(40, 215)
    mant = rng.randint(1 << 55, (1 << 56) - 1)
    return oracle.GwNum("double", sign=sign, exp=exp, mant=mant)


ZERO_D = oracle.GwNum("double", sign=0, exp=0, mant=0)
MAX_POS_D = oracle.GwNum("double", sign=0, exp=255, mant=(1 << 56) - 1)
MAX_NEG_D = oracle.GwNum("double", sign=1, exp=255, mant=(1 << 56) - 1)
MIN_POS_D = oracle.GwNum("double", sign=0, exp=1, mant=1 << 55)
MIN_NEG_D = oracle.GwNum("double", sign=1, exp=1, mant=1 << 55)
ONE_D = oracle.GwNum.from_fraction(Fraction(1), "double")
TWO_D = oracle.GwNum.from_fraction(Fraction(2), "double")
HALF_D = oracle.GwNum.from_fraction(Fraction(1, 2), "double")
NEG_ONE_D = oracle.GwNum.from_fraction(Fraction(-1), "double")
NEAR_POW2_D = oracle.GwNum("double", sign=0, exp=150, mant=(1 << 56) - 1)

BOUNDARY_DOUBLES = [
    ZERO_D, MAX_POS_D, MAX_NEG_D, MIN_POS_D, MIN_NEG_D, ONE_D, TWO_D, HALF_D,
    NEG_ONE_D, NEAR_POW2_D,
]


def tie_construction_pairs_d(rng: random.Random, count: int):
    """tie_construction_pairsの倍精度版(56bit仮数)。"""
    out = []
    for _ in range(count):
        exp_b = rng.randint(2, 250)
        exp_a = exp_b + 1
        sign = rng.randint(0, 1)
        a_mant = rng.randint(1 << 55, (1 << 56) - 1)
        b_mant_tie = rng.randint(1 << 55, (1 << 56) - 1) | 1
        a = oracle.GwNum("double", sign=sign, exp=exp_a, mant=a_mant)
        b_tie = oracle.GwNum("double", sign=sign, exp=exp_b, mant=b_mant_tie)
        out.append((a, b_tie))
        b_mant_down = rng.randint(1 << 55, (1 << 56) - 1) & ~1
        b_down = oracle.GwNum("double", sign=sign, exp=exp_b, mant=b_mant_down)
        out.append((a, b_down))
    return out


def sticky_loss_pairs_d(rng: random.Random, count: int):
    """sticky_loss_pairsの倍精度版(56bit仮数、整列シフト量56)。"""
    out = []
    for _ in range(count):
        exp_a = rng.randint(60, 240)
        sign = rng.randint(0, 1)
        mant_a = rng.choice([1 << 55, (1 << 55) + 2, (1 << 56) - 2])
        a = oracle.GwNum("double", sign=sign, exp=exp_a, mant=mant_a)
        ulp = Fraction(2) ** (exp_a - 128 - 56)
        value_b = ulp * Fraction(1, 2) + ulp * Fraction(1, 2 ** 55)
        b = oracle.GwNum.from_fraction(value_b, "double")
        b = oracle.GwNum("double", sign=sign, exp=b.exp, mant=b.mant)
        out.append((a, b))
    return out


def rand_single(rng: random.Random, spread=True) -> "oracle.GwNum":
    sign = rng.randint(0, 1)
    if spread and rng.random() < 0.15:
        exp = rng.choice([1, 2, 3, 126, 127, 128, 129, 130, 253, 254, 255])
    else:
        exp = rng.randint(1, 255)
    mant = rng.randint(0x800000, 0xFFFFFF)
    return oracle.GwNum("single", sign=sign, exp=exp, mant=mant)


def rand_single_fout(rng: random.Random) -> "oracle.GwNum":
    """M7追記(2026-09-15): MBF_FOUTを倍精度(DBL_TABLE、10^0-10^38を
    DBL_MUL/DBL_DIVで適用、38を超える分は分割)経由のGW手順に作り直し、
    旧実装(単精度の2進累乗法でオーバーフローしていた)の限界を解消した
    ため、安全域への限定(旧:exp 110-146)をやめ、指数の全範囲(1-255、
    rand_singleと同じ「15%の確率で極端な指数を選ぶ」構成)を使う。

    ただし exp byte が概ね1-19(値が10^-33より小さい、6桁化に10^39以上
    を掛ける必要がある領域)は、Z80側は倍精度の分割適用で溢れずに動く
    ものの、予測器(tools/l4_mbf_oracle_v2.py)側が10^39以上を倍精度定数
    として表現できずOverflowErrorになる別の既知の限界がある(報告済み、
    予測器修正は担当外)。厳密一致で照合できるのはexp>=20からなので、
    乱数照合の母集団はそちらを使う(exp 1-19はcompare()側で境界値
    MIN_POS/MIN_NEGとして別途「オーバーフローせず動くか」だけ確認する)。
    """
    sign = rng.randint(0, 1)
    if rng.random() < 0.15:
        exp = rng.choice([20, 21, 22, 126, 127, 128, 129, 130, 253, 254, 255])
    else:
        exp = rng.randint(20, 255)
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
    # M7(REP01)追記(2026-09-15): _fin_scale_nonzeroの反復(10.0倍/S01倍)
    # 回数=|SCALE|の境界を機械的に踏む値。指数の上下限近く(単精度は
    # おおよそ1E-38〜1E+38)・7桁定数(9999999は上にある)・`!`・e+/e-の
    # 大小・小数点以下の桁数・先頭0の小数を意図的に混ぜる
    # (仕様書に無い判断、REP01実装担当が選定)。
    "1E38", "-1E38", "9.99999E37", "1E-38", "1E-37", "-1E-38",
    "3.4E38", "3.4E38!", "1.2E-38#",           # 単精度の実用上限/下限近辺
    "1.234567E30", "1.234567E-30",              # 7桁の仮数部+E指数
    "1E+30", "1E-30", "1e+05", "1e-05",         # e+/e-の大小(小さい方)
    "0.0001", "-0.0001", "0.00001234",          # 先頭0の小数
    "123.456789", "-0.000123456",               # 小数点以下の桁数が多い
    "5E0", "5E-0", "5E+0",                      # 指数0(符号の有無違い)
]


def rand_fin_text(rng: random.Random) -> str:
    """仕様書に無い判断: 合計桁数(整数部+小数部)は9桁以内、指数絶対値は
    10以内に収める。前者はMBF_FINの32bit桁蓄積レジスタ(FIN_ACC)が
    オーバーフローしない範囲、後者は単精度の実用範囲(指数絶対値が
    大きいとオーバーフロー/アンダーフローになりやすい)という実装上の
    制約に基づく選定であり、予測器との丸めの一致・不一致とは無関係
    （2026-09-15: 以前はここに「丸め誤差が予測器の『厳密値→1回丸め』
    からずれるリスクを避ける」という記述があったが、それは予測器側の
    バグ(parse_literalのfin_algo="gw"がCSDの丸めを再現していなかった)
    が原因で、実装(mbf_single.asm)ではなかった。原因特定・修正済み
    （tools/l4_mbf_oracle_v2.py parse_literal・l4_mbf_conform.py
    expected_fin のコメント参照）なので、桁数レンジを狭める理由は
    もう無い）。"""
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


# M7段階4b-2: 倍精度FIN(DREP10A)の境界値。いずれもmbf_single.asm
# MBF_FINが倍精度と判定する形(数字8桁以上・`#`・`d`指数)。
# docs/spec/l4-basic.md 5.1.2節・5.3節・5.4節・5.5節の観測例の打鍵文字列
# そのもの(画面本文ではなく自分で指定した打鍵文字列なので禁止事項7の
# 対象外)を流用し、1e-38付近・16桁ちょうど・半端・17桁以上の整数・
# `#`付き小数・`d`指数の各境界を踏む。
DFIN_BOUNDARY_TEXTS = [
    "0#", "1#", "-1#", ".5#", "12345678",          # 単純な倍精度定数
    "1D10",                                         # W2
    "12345678901234#",                              # W3
    "123456789012345#",                             # G1(15桁、E=14)
    "123456789012345.6#",                           # G8(16有効桁)
    "1234567890123456#",                            # G3(16桁ちょうど、E=15)
    "1D15",                                          # G5(16桁ちょうど)
    "1D16",                                          # C2(17桁相当、E=16)
    "1D17",                                          # C3
    "99999999999999995#",                            # G10(丸めで18桁相当)
    "12345678901234567#",                             # C4(17桁の定数)
    "123456789012345678",                             # 18桁の整数(#なしでも桁数で倍精度)
    "1.234567890123456D-2",                           # L6(k=1)
    "1.23456789012345D-3",                            # M2(k=2)
    "1.2345678901234D-3",                             # Q10(k=2,s=14)
    "1.5D-14",                                        # M8(k=13)
    "1D-15",                                          # L1(k=14ぎりぎり)
    "1.5D-15",                                        # L3(k=14、k+s=16ぎりぎり)
    "2D-16",                                          # Q6(k=15、指数境界)
    "1.5D-16",                                        # L4(k=15)
    "1.23D-15",                                       # M3
    "1D-38", "1.5D-38", "9.99999999999999D-39",       # 1e-38付近
    "1D38", "-1D38",                                  # 指数上限付近
    "1234567890123456.5#",                            # 16桁目の半端(丸め)
    "2000000000000000.5#",                            # 同上(0→1側)
    "9007199254740992.5#",                            # 同上(16桁目が偶数)
    "-1234567890123456.5#",                           # 負の半端
    "60487647593824219489241",  # 桁の積み上げ(×10)過程の20-21桁目で
                                 # 実際にタイになる例(乱数探索で確認、
                                 # --fault dfin_round_evenの検出力の根拠)
]


def rand_dfin_text(rng: random.Random) -> str:
    """rand_fin_textの倍精度版。合計桁数8-20桁・指数絶対値38以内に
    収める(倍精度の実用範囲、仕様書に無い判断)。`#`か`d`指数のどちらか
    (または両方の元になる長い整数)で必ず倍精度と判定されるようにする。"""
    # FIN_BUF_MAX(24byte)に収まるよう、桁数・指数桁を絞る(仕様書に無い
    # 判断): sign(1)+int(9)+dot(1)+frac(6)+exp記号(4)+suffix(1)=22以内。
    sign = "-" if rng.random() < 0.4 else ""
    int_digits = rng.randint(1, 9)
    int_part = "".join(str(rng.randint(0, 9)) for _ in range(int_digits))
    if int_part[0] == "0" and int_digits > 1:
        int_part = "1" + int_part[1:]
    frac = ""
    total_digits = int_digits
    if rng.random() < 0.7 and total_digits < 15:
        frac_digits = rng.randint(1, min(6, 15 - total_digits))
        frac = "." + "".join(str(rng.randint(0, 9)) for _ in range(frac_digits))
        total_digits += frac_digits
    use_d = rng.random() < 0.5
    exp = ""
    if use_d or rng.random() < 0.3:
        e = rng.randint(-38, 38)
        letter = "D" if use_d else "E"
        exp = f"{letter}{e:+d}"
    # 8桁未満・E指数・#なしだと単精度と判定されてしまうので、その場合は
    # #を強制する(倍精度専用opの契約=必ず倍精度と判定される文字列)。
    force_hash = total_digits < 8 and not (use_d and exp)
    suffix = "#" if force_hash else ""
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
    elif op == "dfin":
        for t in DFIN_BOUNDARY_TEXTS:
            vecs.append((t,))
        while len(vecs) < n:
            vecs.append((rand_dfin_text(rng),))
    elif op in ("dadd", "dsub", "dmul", "ddiv", "dcmp"):
        for a in BOUNDARY_DOUBLES:
            for b in BOUNDARY_DOUBLES:
                vecs.append((a, b))
        if op in ("dadd", "dsub"):
            vecs.extend(tie_construction_pairs_d(rng, 40))
            vecs.extend(sticky_loss_pairs_d(rng, 20))
        while len(vecs) < n:
            vecs.append((rand_double(rng), rand_double(rng)))
    elif op == "dneg":
        for a in BOUNDARY_DOUBLES:
            vecs.append((a,))
        while len(vecs) < n:
            vecs.append((rand_double(rng),))
    elif op == "itod":
        for v in (0, 1, -1, 32767, -32768, 32768 - 1, -32767, 100, -100, 12345, -12345):
            vecs.append((v,))
        while len(vecs) < n:
            vecs.append((rng.randint(-32768, 32767),))
    elif op == "stod":
        for a in BOUNDARY_SINGLES:
            vecs.append((a,))
        while len(vecs) < n:
            vecs.append((rand_single(rng),))
    elif op == "dtos":
        for a in BOUNDARY_DOUBLES:
            vecs.append((a,))
        while len(vecs) < n:
            vecs.append((rand_double(rng),))
    elif op == "fout":
        for f in FOUT_BOUNDARY_FRACTIONS:
            vecs.append((oracle.GwNum.from_fraction(f, "single"),))
        # M7追記(2026-09-15): MBF_FOUTを倍精度(DBL_TABLE)経由のGW手順に
        # 作り直し、単精度の2進累乗法によるオーバーフローを解消したため、
        # MAX_POS/MAX_NEGは境界値集合に戻す(コメントに残す=戻した根拠)。
        # MIN_POS/MIN_NEGはZ80側はオーバーフローせず動くが、予測器側が
        # OverflowErrorになる既知の限界が別に残っている
        # (expected_fout_or_none参照、報告済み)。厳密一致は検査できない
        # ものの「クラッシュ・オーバーフローせず何か返すか」は検査したい
        # ので境界値集合に含め、compare側でNone分岐として扱う。
        for a in (ZERO, ONE, TWO, HALF, NEG_ONE, NEAR_POW2, MUL_STICKY_A, MUL_STICKY_B,
                  MAX_POS, MAX_NEG, MIN_POS, MIN_NEG):
            vecs.append((a,))
        while len(vecs) < n:
            vecs.append((rand_single_fout(rng),))
    elif op == "dfout":
        for f in DFOUT_BOUNDARY_FRACTIONS:
            vecs.append((oracle.GwNum.from_fraction(f, "double"),))
        # fout(単精度)と同じ理由でMAX_POS_D/MAX_NEG_Dは境界値集合に含め、
        # MIN_POS_D/MIN_NEG_Dは予測器側の既知の限界(expected_dfout_or_none)
        # によりNone分岐で「オーバーフローせず動くか」だけ確認する。
        for a in (ZERO_D, ONE_D, TWO_D, HALF_D, NEG_ONE_D, NEAR_POW2_D,
                  MAX_POS_D, MAX_NEG_D, MIN_POS_D, MIN_NEG_D):
            vecs.append((a,))
        while len(vecs) < n:
            vecs.append((rand_double_fout(rng),))
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


def expected_dbinop(op: str, a: "oracle.GwNum", b: "oracle.GwNum"):
    sym = {"dadd": "+", "dsub": "-", "dmul": "*", "ddiv": "/"}[op]
    try:
        r = oracle.gw_binop(a, b, sym)
        return gwnum8_bytes(r), 0
    except oracle.GwError as e:
        status = 2 if "zero" in e.kind.lower() else 1
        return gwnum8_bytes(e.residual), status


def expected_dcmp(a: "oracle.GwNum", b: "oracle.GwNum") -> int:
    av, bv = a.exact(), b.exact()
    if av == bv:
        return 0
    return 1 if av > bv else 0xFF


def expected_dneg(a: "oracle.GwNum"):
    r = oracle.gw_neg(a)
    return gwnum8_bytes(r)


def expected_itod(v: int):
    r = oracle.GwNum.from_fraction(Fraction(v), "double") if v != 0 else oracle.GwNum.from_fraction(Fraction(0), "double")
    return gwnum8_bytes(r)


def expected_stod(a: "oracle.GwNum"):
    r = oracle.force_to_double(a)
    return gwnum8_bytes(r)


def expected_dtos(a: "oracle.GwNum"):
    try:
        r = oracle.force_to_single(a)
        return gwnum_bytes(r), 0
    except oracle.GwError as e:
        return gwnum_bytes(e.residual), 1


def expected_fout(a: "oracle.GwNum") -> str:
    # M7追記(2026-09-15): MBF_FOUTがGW手順($FOTNV+「0.5を足して切り捨て」)
    # へ作り直された(mbf_single.asm該当コメント参照)ため、予測器も
    # fout_algo="gw"(_significant_digits_gw、docs/spec/l4-basic.md 5.3節の
    # タイの丸め方向と一致)に合わせる。single_digits/small_rule/small_len
    # は従来どおり(6桁・LEN7則)。
    body, _approx = oracle.fout_format(
        a, single_digits=6, small_rule="len", small_len=7, fout_algo="gw"
    )
    return body


def expected_fout_or_none(a: "oracle.GwNum"):
    """expected_foutのラッパ。MIN_POS/MIN_NEG近傍(単精度の指数byteが
    概ね1-19、6桁化に10^39以上を掛ける必要がある領域)では
    tools/l4_mbf_oracle_v2.py の_pow10_as_double/encode_mbf自体が
    OverflowErrorになり予測値を計算できない(倍精度MBFの指数byteが
    単精度と同じ8bit・bias+128を共有するため、10^39以上はそもそも
    倍精度定数として表現できない=予測器側の既知の未対応領域。
    報告済み、予測器修正は担当外のためここでは触らない)。
    この領域はNoneを返し、呼び出し側は「オーバーフローせず何らかの
    出力を返したか」だけを検査する(厳密な文字列一致は検査できない)。
    """
    try:
        return expected_fout(a)
    except OverflowError:
        return None


def expected_dfout(a: "oracle.GwNum") -> str:
    """M7段階4b-2: 倍精度FOUTの正解役。n88=True(oracle.fout_format)で
    倍精度=16桁・rstar則・大きい側しきい値16を一括指定し、
    fout_algo="gw"(単精度MBF_FOUTと同じ$FOTNV+「0.5を足して切り捨て」)
    を使う。"""
    body, _approx = oracle.fout_format(a, n88=True, fout_algo="gw")
    return body


def expected_dfout_or_none(a: "oracle.GwNum"):
    """expected_dfoutのラッパ。expected_fout_or_noneと同じ理由
    (MIN_POS_D/MAX_POS_D近傍で予測器側の10^39以上スケール未対応の
    OverflowErrorが起きうる)でNoneを返すことがある。"""
    try:
        return expected_dfout(a)
    except OverflowError:
        return None


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

# M7段階4b-2: docs/spec/l4-basic.md 5.3〜5.5節(倍精度)の観測例のうち
# 値そのもの(打鍵文字列ではなくFraction)を境界に使う。DFOUTはFIN経由
# ではなくGwNumを直接渡すため、5.1.2節の定数読み取りとは独立に検査できる。
DFOUT_BOUNDARY_FRACTIONS = [
    Fraction(1, 3), Fraction(0),
    Fraction(1234567890123456), Fraction(1234567890123456) * 10,
    Fraction(123456789012345), Fraction("123456789012345.6"),
    Fraction(12345678901234567), Fraction(10 ** 15), Fraction(10 ** 16),
    Fraction(1, 70), Fraction(1, 700), Fraction(1, 3000),
    Fraction("1.2345678901234e-3"), Fraction("1.5e-14"),
    Fraction(1, 10 ** 15), Fraction("1.5e-15"), Fraction(2, 10 ** 16),
    Fraction("1.5e-16"), Fraction("1.23e-15"),
    Fraction("1.234567890123456e-2"),
    Fraction("1234567890123456.5"), Fraction("2000000000000000.5"),
    Fraction("9007199254740992.5"), Fraction("-1234567890123456.5"),
    Fraction("1e-38"), Fraction("1.5e-38"), Fraction("1e38"), Fraction("-1e38"),
]


def expected_fin(text: str):
    """戻り値: (期待バイト列 or None, status)。status=3(倍精度)のときバイト列
    はNone(呼び出し側はstatusだけ比較する)。

    fin_algo="rep01"を使う(2026-09-15、M7): docs/spec/l4-basic.md
    第3.6版5.1.1節「単精度の定数の読み取り(FIN)」の推定REP01
    (ユーザー判断により実装を進める規則)。l4-s4i・l4-s4j実測57件中55件を
    再現する規則で、以前使っていた"gw"(倍精度56bit経由・$CSD1回丸め、
    $FINE/MDPTENの実際の手順の再現)は対照C6(l4-s4i)・4腕(l4-s4j)で
    実測と食い違うことが分かったため置き換えた
    (詳細はdocs/spec/l4-basic.md 5.1.1節「観測」、
    tools/l4_mbf_oracle_v2.py parse_literal内の該当コメント参照)。

    REP01は指数の絶対値ぶん10.0/S01を1回ずつ掛ける反復なので、境界値
    (1E38・1E-38付近)ではparse_literalがOverflowError由来のGwErrorを
    投げる。mbf_single.asm側もMBF_MUL(WK_MUL_ROUNDMODE=1)が同じ境界で
    オーバーフロー検出しMBF_STATUS=1を返す設計なので、ここでも
    status=1・残留値($INFPD/$INFMD相当)を返して合わせる
    (expected_binopと同じ扱い)。
    """
    try:
        r = oracle.parse_literal(text, fin_algo="rep01")
    except oracle.GwError as e:
        return gwnum_bytes(e.residual), 1
    if r.kind == "double":
        return None, 3
    if r.kind == "int":
        r = oracle.GwNum.from_fraction(Fraction(r.ivalue), "single")
    return gwnum_bytes(r), 0


def expected_dfin(text: str):
    """M7段階4b-2: 倍精度FIN(DREP10A)の正解役。dfin_algo="drep10a"
    (tools/l4_mbf_oracle_v2.py parse_literal、oracle_v2_selftestで
    tools/l4_dmodels.py drep10a_v2と乱数1万件バイト一致を確認済み)。
    戻り値: (期待8byteバイト列, status)。
    """
    try:
        r = oracle.parse_literal(text, dfin_algo="drep10a")
    except oracle.GwError as e:
        return gwnum8_bytes(e.residual), 1
    if r.kind != "double":
        # 契約外(dfin opの照合ベクタは倍精度と判定される文字列だけを
        # 使うため通常は起きない)。Z80側のフォールバック
        # (SINGLE_TO_DOUBLE、厳密)と同じ変換を予測側でも行う。
        r = oracle.force_to_double(r)
    return gwnum8_bytes(r), 0


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
    # M7段階4b-1: 倍精度(以下、in/outとも8byte倍精度+statusを基本とする)。
    "dadd": (16, 9, "MBF_DADD", True),
    "dsub": (16, 9, "MBF_DSUB", True),
    "dmul": (16, 9, "MBF_DMUL", True),
    "ddiv": (16, 9, "MBF_DDIV", True),
    "dcmp": (16, 1, "MBF_DCMP", False),
    "dneg": (8, 9, "MBF_DNEG", False),
    "itod": (2, 9, "MBF_ITOD", False),
    "stod": (4, 9, "MBF_STOD", False),
    "dtos": (8, 5, "MBF_DTOS", False),
    # M7段階4b-2: 倍精度FIN(DREP10A)。入力はfinと同じ1byte長+24byte ASCII、
    # 出力はdadd等と同じ8byte倍精度+status。
    "dfin": (25, 9, "MBF_DFIN", False),
    # M7段階4b-2: 倍精度FOUT。入力8byte倍精度、出力=1byte長+24byte ASCII。
    "dfout": (8, 25, "MBF_DFOUT", False),
}
FIN_BUF_MAX = 24
FOUT_BUF_MAX = 16
DFOUT_BUF_MAX = 24  # M7段階4b-2: 指数表記(桁.仮数15桁D+nn)の最大長に余裕を見た


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
    elif op == "fin" or op == "dfin":
        lines.append("    LD A,(HL)")
        lines.append("    LD (FIN_LEN),A")
        lines.append("    INC HL")
        for i in range(FIN_BUF_MAX):
            lines.append("    LD A,(HL)")
            lines.append(f"    LD (FIN_BUF+{i}),A")
            lines.append("    INC HL")
    elif op == "itod":
        # M7段階4b-1: MBF_ITODの入力もMBF_IN_INT(mbf_single.asmと共有)を使う。
        lines.append("    LD A,(HL)")
        lines.append("    LD (MBF_IN_INT),A")
        lines.append("    INC HL")
        lines.append("    LD A,(HL)")
        lines.append("    LD (MBF_IN_INT+1),A")
        lines.append("    INC HL")
    elif op == "stod":
        # 単精度4byteをMBF_OPA(mbf_single.asmと共有)へ。
        for i in range(4):
            lines.append("    LD A,(HL)")
            lines.append(f"    LD (MBF_OPA+{i}),A")
            lines.append("    INC HL")
    elif op in ("dtos", "dneg", "dfout"):
        # 倍精度8byteをMBF_DOPAへ。
        for i in range(8):
            lines.append("    LD A,(HL)")
            lines.append(f"    LD (MBF_DOPA+{i}),A")
            lines.append("    INC HL")
    elif op in ("dadd", "dsub", "dmul", "ddiv", "dcmp"):
        for i in range(8):
            lines.append("    LD A,(HL)")
            lines.append(f"    LD (MBF_DOPA+{i}),A")
            lines.append("    INC HL")
        for i in range(8):
            lines.append("    LD A,(HL)")
            lines.append(f"    LD (MBF_DOPB+{i}),A")
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
    elif op == "dcmp":
        lines.append("    LD A,(MBF_DOUT_CMP)")
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
    elif op == "dfout":
        lines.append("    LD A,(DFOUT_LEN)")
        lines.append("    LD (DE),A")
        lines.append("    INC DE")
        for i in range(DFOUT_BUF_MAX):
            lines.append(f"    LD A,(DFOUT_BUF+{i})")
            lines.append("    LD (DE),A")
            lines.append("    INC DE")
    elif op == "dtos":
        # 結果は単精度4byte(MBF_RES、mbf_single.asmと共有)+status。
        for i in range(4):
            lines.append(f"    LD A,(MBF_RES+{i})")
            lines.append("    LD (DE),A")
            lines.append("    INC DE")
        lines.append("    LD A,(MBF_STATUS)")
        lines.append("    LD (DE),A")
        lines.append("    INC DE")
    elif op in ("dadd", "dsub", "dmul", "ddiv", "dneg", "itod", "stod", "dfin"):
        # 結果は倍精度8byte(MBF_DRES)+status。
        for i in range(8):
            lines.append(f"    LD A,(MBF_DRES+{i})")
            lines.append("    LD (DE),A")
            lines.append("    INC DE")
        lines.append("    LD A,(MBF_STATUS)")
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
        if op == "itos" or op == "itod":
            val = v[0] & 0xFFFF
            out.append(val & 0xFF)
            out.append((val >> 8) & 0xFF)
        elif op == "neg" or op == "fout" or op == "stod":
            out += gwnum_bytes(v[0])
        elif op == "dneg" or op == "dtos" or op == "dfout":
            out += gwnum8_bytes(v[0])
        elif op == "fin" or op == "dfin":
            text = v[0].upper()
            raw = text.encode("ascii")
            if len(raw) > FIN_BUF_MAX:
                raise ValueError(f"fin literal too long: {text!r}")
            out.append(len(raw))
            out += raw
            out += bytes(FIN_BUF_MAX - len(raw))
        elif op in ("dadd", "dsub", "dmul", "ddiv", "dcmp"):
            out += gwnum8_bytes(v[0])
            out += gwnum8_bytes(v[1])
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
    "; $ROUNS の粗い丸め: masked = guard(BIG_MG) & 0xE0 (既定、$FMULS忠実再現)\n"
    "    LD A,(BIG_MG)\n"
    "    AND 0xE0"
)
FAULT_MUL_COARSE_NEW = (
    "; $ROUNS の粗い丸め: masked = guard(BIG_MG) & 0xE0 (既定、$FMULS忠実再現)\n"
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

# M7(REP01)追記(2026-09-15): docs/spec/l4-basic.md 5.1.1節REP01の陽性対照。
# fin_exact: 「1手ごとの丸めを最後の1回にまとめる」(EXACT相当)。
# _fin_scale_nonzero の先頭を、mbf_single.asm に残置してある
# _fin_scale_nonzero_EXACT_FAULT(倍精度56bit経由・DBL_MUL/DBL_DIVを
# 1回だけ掛ける/割ってからDBL_TO_SINGLE_CSDで単精度へ1回だけ丸める、
# REP01置き換え前の旧実装)へ無条件でJPさせる。
FAULT_FIN_EXACT_OLD = (
    "_fin_scale_nonzero:\n"
    "    CALL FIN_ACC_TO_SINGLE_AWAY\n"
    "    CALL FIN_COPY_RES_TO_OPA\n"
)
FAULT_FIN_EXACT_NEW = (
    "_fin_scale_nonzero:\n"
    "    ; 故障注入: 1手ごとの丸めをやめ、最後に1回だけ丸める(EXACT相当)\n"
    "    JP _fin_scale_nonzero_EXACT_FAULT\n"
    "    CALL FIN_ACC_TO_SINGLE_AWAY\n"
    "    CALL FIN_COPY_RES_TO_OPA\n"
)

# fin_rep10: 「0.1を掛ける代わりに10で割る」(REP10相当)。負の正味指数の
# 反復だけを対象に、単精度に丸めたS01との乗算をMBF_DIVによる10.0での
# 除算へ差し替える。
FAULT_FIN_REP10_OLD = (
    "_fin_rep01_use_s01:\n"
    "    CALL FIN_SET_OPB_S01\n"
    "    CALL MBF_MUL_HALFUP\n"
)
FAULT_FIN_REP10_NEW = (
    "_fin_rep01_use_s01:\n"
    "    ; 故障注入: 0.1を掛ける代わりに10で割る(REP10相当)\n"
    "    CALL FIN_SET_OPB_TEN\n"
    "    CALL MBF_DIV\n"
)

# M7追記(2026-09-15): FOUTがGW手順(倍精度$FOTNV+ガードビットのみの
# 「0.5を足して切り捨て」)へ作り直された(mbf_single.asm該当コメント
# 参照)ため、丸め判定の位置がUA_M0のビットマスク方式からFOUT_DGUARD
# (シフトで最後に落ちたビット1つだけ)方式に変わった。旧FAULT_FOUT_TRUNCの
# OLD文字列(UA_M0を直接マスクする書き方)はもう存在しないので、新しい
# 丸めコードを対象に書き直した。
FAULT_FOUT_TRUNC_OLD = (
    "    LD A,(FOUT_DGUARD)\n"
    "    OR A\n"
    "    JP Z,_fout_round_done\n"
    "    LD A,(FOUT_INT0)\n"
    "    INC A"
)
FAULT_FOUT_TRUNC_NEW = (
    "    LD A,(FOUT_DGUARD)\n"
    "    OR A\n"
    "    JP _fout_round_done  ; 故障注入: 丸めを切り捨てに固定\n"
    "    LD A,(FOUT_INT0)\n"
    "    INC A"
)

# 故障注入: 「丸めるとちょうど半分になる値は絶対値の大きい側へ丸める」
# (docs/spec/l4-basic.md 第5.3節、偶数丸めではない)という仕様に反し、
# 偶数丸め(タイは結果の最下位ビットが奇数の時だけ切り上げる)にする
# 陰性対照。正しい実装はガードビット(FOUT_DGUARD)1つだけで切り上げを
# 決めるが、この故障注入はさらに結果のLSBの偶奇を見て、LSBが偶数に
# なる側へ倒す(sticky情報が無いため「ちょうど半分」と「半分を超える」
# を区別できない粗い偶数丸めだが、正しい実装とは系統的に異なる結果に
# なるので陰性対照として機能する)。
FAULT_FOUT_ROUND_EVEN_OLD = FAULT_FOUT_TRUNC_OLD
FAULT_FOUT_ROUND_EVEN_NEW = (
    "    LD A,(FOUT_DGUARD)\n"
    "    OR A\n"
    "    JP Z,_fout_round_done\n"
    "    LD A,(FOUT_INT0)\n"
    "    BIT 0,A  ; 故障注入: 偶数丸め(LSBが奇数の時だけ切り上げ)\n"
    "    JP Z,_fout_round_done\n"
    "    LD A,(FOUT_INT0)\n"
    "    INC A"
)

FAULT_FOUT_LEN7_OLD = "_fout_small:\n    LD A,(FOUT_E)\n    NEG\n    LD B,A\n    LD A,(FOUT_NSIG)\n    ADD A,B\n    CP 8"
FAULT_FOUT_LEN7_NEW = "_fout_small:\n    LD A,(FOUT_E)\n    NEG\n    LD B,A\n    LD A,(FOUT_NSIG)\n    ADD A,B\n    CP 9  ; 故障注入: LEN7をLEN8にする"

FAULT_FOUT_6DIG_OLD = "_fout_large:\n    CP 7\n    JP C,_fout_isfixed_yes"
FAULT_FOUT_6DIG_NEW = "_fout_large:\n    CP 8  ; 故障注入: 6桁境目を7桁境目にする\n    JP C,_fout_isfixed_yes"

# M7段階4b-1: 倍精度(mbf_double.asm)の陰性対照。
FAULT_DSTICKY_OLD = (
    "    JP NC,_dadd_shift_nostick\n"
    "    LD A,1\n"
    "    LD (DWK_STICKY),A\n"
    "_dadd_shift_nostick:"
)
FAULT_DSTICKY_NEW = "_dadd_shift_nostick:"  # 整列シフトで落ちたbitをスティッキーへ反映しない

FAULT_DROUND_TRUNCATE_OLD = "_dadd_round:\n    ; guard = DBIG_MG。"
FAULT_DROUND_TRUNCATE_NEW = "_dadd_round:\n    JP _dadd_round_down\n    ; guard = DBIG_MG。"

FAULT_DMUL_STICKY_OLD = (
    "    LD A,(DPR5)\n"
    "    OR C\n"
    "    LD C,A\n"
    "    LD A,(DPR4)\n"
    "    OR C\n"
    "    LD C,A\n"
    "    LD A,(DPR3)\n"
    "    OR C\n"
    "    LD C,A\n"
    "    LD A,(DPR2)\n"
    "    OR C\n"
    "    LD C,A\n"
    "    LD A,(DPR1)\n"
    "    OR C\n"
    "    LD C,A\n"
    "    LD A,(DPR0)\n"
    "    OR C\n"
    "    JP NZ,_dmulc_round_up"
)
FAULT_DMUL_STICKY_NEW = (
    "    XOR A  ; 故障注入: DPR5..DPR0のstickyを捨てる\n"
    "           ; (LD A,0はZ80のフラグを変えないためNZ判定に効かず、\n"
    "           ; 無故障とほぼ同じ挙動になってしまう。XOR Aでなければ\n"
    "           ; ならない——最初XOR Aと書かず0件不一致になり気づいた)\n"
    "    JP NZ,_dmulc_round_up"
)

FAULT_DDIV_STICKY_OLD = (
    "    LD A,(WK_DREMZERO)\n"
    "    OR C\n"
    "    JP NZ,_ddiv_round_up"
)
FAULT_DDIV_STICKY_NEW = (
    "    LD A,C  ; 故障注入: 真の剰余(WK_DREMZERO)を無視する\n"
    "    JP NZ,_ddiv_round_up"
)

# M7段階4b-2: 倍精度FIN(DREP10A)の陰性対照。乗算(桁の×10適用)のタイ判定
# を狙う——事前の乱数探索(200件試行)で「60487647593824219489241」を
# 積み上げる過程の20-21桁目に実際にタイが発生することを確認済み
# (除算÷10側は乱数探索20万件でタイが1件も見つからず、10進の桁を10で
# 割って56bit境界にちょうど乗るのは非常に稀と判断し、乗算側を対象にした)。
FAULT_DFIN_ROUND_EVEN_OLD = (
    "    ; 真のタイ。WK_DROUND_MODE=1(MBF_DMUL_AWAY)なら常に切り上げ。\n"
    "    LD A,(WK_DROUND_MODE)\n"
    "    OR A\n"
    "    JP NZ,_dmulc_round_up\n"
)
FAULT_DFIN_ROUND_EVEN_NEW = (
    "    ; 故障注入: WK_DROUND_MODE(AWAY指定)を無視し常に偶数丸めにする\n"
)

FAULT_DFIN_DIV_AS_MUL_OLD = (
    "_dfin_scale_neg_loop:\n"
    "    LD HL,DBL_CONST_TEN\n"
    "    LD DE,MBF_DOPB\n"
    "    LD BC,8\n"
    "    LDIR\n"
    "    CALL MBF_DDIV_AWAY\n"
)
FAULT_DFIN_DIV_AS_MUL_NEW = (
    "_dfin_scale_neg_loop:\n"
    "    LD HL,DBL_CONST_TENTH  ; 故障注入: 真の÷10ではなく丸めた0.1の乗算にする\n"
    "    LD DE,MBF_DOPB\n"
    "    LD BC,8\n"
    "    LDIR\n"
    "    CALL MBF_DMUL_AWAY\n"
)

# M7段階4b-2: 倍精度FOUTの陰性対照。
FAULT_DFOUT_ROUND_EVEN_OLD = (
    "    LD A,(WK_DFOUT_GUARD)\n"
    "    OR A\n"
    "    JP Z,_dfout_round_done\n"
    "    LD A,(DFOUT_INT)\n"
    "    INC A\n"
    "    LD (DFOUT_INT),A\n"
)
FAULT_DFOUT_ROUND_EVEN_NEW = (
    "    LD A,(WK_DFOUT_GUARD)\n"
    "    OR A\n"
    "    JP Z,_dfout_round_done\n"
    "    LD A,(DFOUT_INT)\n"
    "    BIT 0,A  ; 故障注入: 偶数丸め(LSBが奇数の時だけ切り上げ)\n"
    "    JP Z,_dfout_round_done\n"
    "    LD A,(DFOUT_INT)\n"
    "    INC A\n"
    "    LD (DFOUT_INT),A\n"
)

FAULT_DFOUT_K14_OLD = (
    "    LD A,(WK_DFOUT_K)\n"
    "    CP 15\n"
    "    JP NC,_dfout_isfixed_no\n"
    "_dfout_isfixed_yes:"
)
FAULT_DFOUT_K14_NEW = (
    "    ; 故障注入: k<=14の条件を外す\n"
    "_dfout_isfixed_yes:"
)

FAULTS = {
    "sticky": (FAULT_STICKY_OLD, FAULT_STICKY_NEW),
    "round_truncate": (FAULT_ROUND_TRUNCATE_OLD, FAULT_ROUND_TRUNCATE_NEW),
    "mul_coarse": (FAULT_MUL_COARSE_OLD, FAULT_MUL_COARSE_NEW),
    "div_sticky": (FAULT_DIV_STICKY_OLD, FAULT_DIV_STICKY_NEW),
    "fin_bang": (FAULT_FIN_BANG_OLD, FAULT_FIN_BANG_NEW),
    "fin_exact": (FAULT_FIN_EXACT_OLD, FAULT_FIN_EXACT_NEW),
    "fin_rep10": (FAULT_FIN_REP10_OLD, FAULT_FIN_REP10_NEW),
    "fout_trunc": (FAULT_FOUT_TRUNC_OLD, FAULT_FOUT_TRUNC_NEW),
    "fout_round_even": (FAULT_FOUT_ROUND_EVEN_OLD, FAULT_FOUT_ROUND_EVEN_NEW),
    "fout_len7": (FAULT_FOUT_LEN7_OLD, FAULT_FOUT_LEN7_NEW),
    "fout_6dig": (FAULT_FOUT_6DIG_OLD, FAULT_FOUT_6DIG_NEW),
    "dsticky": (FAULT_DSTICKY_OLD, FAULT_DSTICKY_NEW),
    "dround_truncate": (FAULT_DROUND_TRUNCATE_OLD, FAULT_DROUND_TRUNCATE_NEW),
    "dmul_sticky": (FAULT_DMUL_STICKY_OLD, FAULT_DMUL_STICKY_NEW),
    "ddiv_sticky": (FAULT_DDIV_STICKY_OLD, FAULT_DDIV_STICKY_NEW),
    "dfin_round_even": (FAULT_DFIN_ROUND_EVEN_OLD, FAULT_DFIN_ROUND_EVEN_NEW),
    "dfin_div_as_mul": (FAULT_DFIN_DIV_AS_MUL_OLD, FAULT_DFIN_DIV_AS_MUL_NEW),
    "dfout_round_even": (FAULT_DFOUT_ROUND_EVEN_OLD, FAULT_DFOUT_ROUND_EVEN_NEW),
    "dfout_k14": (FAULT_DFOUT_K14_OLD, FAULT_DFOUT_K14_NEW),
}


def load_mbf_src(fault: str | None) -> str:
    # M7段階4b-1: mbf_double.asmはDA_*/DB_*・DBL_MUL/DBL_DIV・
    # DBL_TO_SINGLE_CSD・SINGLE_TO_DOUBLE・MBF_UNPACK_A・MBF_STATUS等、
    # mbf_single.asmのシンボルを直接呼ぶ前提なので、連結して1つのアセンブル
    # 単位として渡す(mbf_double.asmヘッダコメント参照)。
    text = MBF_SINGLE_ASM.read_text() + "\n" + MBF_DOUBLE_ASM.read_text()
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
            elif op == "dcmp":
                expected = bytes([expected_dcmp(v[0], v[1]) & 0xFF])
            elif op == "neg":
                expected = expected_neg(v[0])
                expected += bytes([0])
            elif op == "dneg":
                expected = expected_dneg(v[0])
                expected += bytes([0])
            elif op == "itos":
                expected = expected_itos(v[0])
                expected += bytes([0])
            elif op == "itod":
                expected = expected_itod(v[0])
                expected += bytes([0])
            elif op == "stod":
                expected = expected_stod(v[0])
                expected += bytes([0])
            elif op == "dtos":
                eb, status = expected_dtos(v[0])
                expected = eb + bytes([status])
            elif op in ("dadd", "dsub", "dmul", "ddiv"):
                eb, status = expected_dbinop(op, v[0], v[1])
                expected = eb + bytes([status])
            elif op == "dfin":
                eb, status = expected_dfin(v[0])
                expected = eb + bytes([status])
            elif op == "fin":
                eb, status = expected_fin(v[0])
                if status == 3:
                    # 倍精度定数: statusバイトだけ比較する(MBF_RESは未定義)
                    actual = actual[4:5]
                    expected = bytes([3])
                else:
                    expected = eb + bytes([status])
            elif op == "fout":
                body = expected_fout_or_none(v[0])
                actual_len = actual[0]
                actual = actual[:1 + actual_len]
                if body is None:
                    # MIN_POS/MIN_NEG近傍: 予測器が計算不能(expected_fout_or_none
                    # 参照)。溢れずに何か出力したか(長さが16バイトの枠に収まり、
                    # 長さバイト自体が矛盾していないか)だけを確認する。
                    if missing or actual_len > 16:
                        mismatches.append((i, v, None, actual))
                    continue
                raw = body.encode("ascii")
                expected = bytes([len(raw)]) + raw
            elif op == "dfout":
                body = expected_dfout_or_none(v[0])
                actual_len = actual[0]
                actual = actual[:1 + actual_len]
                if body is None:
                    if missing or actual_len > DFOUT_BUF_MAX:
                        mismatches.append((i, v, None, actual))
                    continue
                raw = body.encode("ascii")
                expected = bytes([len(raw)]) + raw
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
