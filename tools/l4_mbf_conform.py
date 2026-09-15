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

VEC_TABLE_ADDR = 0x1000     # ROM内、入力ベクタ表の先頭番地
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
}


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
    lines.append("    JR NZ,_l4mbfd_loop")
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
        elif op == "neg":
            out += gwnum_bytes(v[0])
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

FAULTS = {
    "sticky": (FAULT_STICKY_OLD, FAULT_STICKY_NEW),
    "round_truncate": (FAULT_ROUND_TRUNCATE_OLD, FAULT_ROUND_TRUNCATE_NEW),
    "mul_coarse": (FAULT_MUL_COARSE_OLD, FAULT_MUL_COARSE_NEW),
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
            else:
                eb, status = expected_binop(op, v[0], v[1])
                expected = eb + bytes([status])
            if missing or actual != expected:
                mismatches.append((i, v, actual, expected, missing))
        total += len(chunk)
    return total, mismatches


def report(op: str, n_total: int, mismatches, expect_ng: bool) -> bool:
    ok = (len(mismatches) == 0)
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

    ok = report(args.op, n_total, mismatches, args.expect_ng)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
