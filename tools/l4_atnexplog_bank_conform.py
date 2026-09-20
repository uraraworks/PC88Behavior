#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_atnexplog_bank_conform.py — src/ext_bank/bank0.asm の
EXT_BANK0_ATN_ENTRY/EXT_BANK0_EXP_ENTRY/EXT_BANK0_LOG_ENTRY（単精度
ATN/EXP/LOG、docs/spec/l4-program.md 第4.16b節）を実際にZ80として実行し、
tools/l4_mbf_oracle_v10_m9.py の atn_impl/exp_impl/log_impl（`l4-s6h`で
確定したround-half-away丸め）とバイト単位で突き合わせる照合器。

tools/l4_sincos_bank_conform.py と同じ手段・同じ設計（bank0.asmをそのまま
assembleする、公式ROM・private/は一切参照しない、自作の試験ROM＋
tools/harness/frontend/q88measureを使う）を踏襲する。bank0.asm内の
アルゴリズムをこのスクリプト側に書き写さない（二重実装しない）。

MBF_STATUS(0=正常/1=オーバーフロー)もMBF_RESと一緒に読み出して照合する
——EXPはオーバーフロー時にMBF_RESを明示的な値へ書かない(interp.asm側は
VAL_CHECK_MBF_STATUSでMBF_STATUSしか見ないため、この設計はSIN/COS/TAN・
SQRと同じ「呼び出し元が実際に見る場所だけを合わせる」方針に従う)。

LOG は x<=0 の判定を interp.asm 側(FTNF_DO_LOG)が呼び出し前に行う設計
なので、この照合器はx>0のベクタしか生成しない(バンク側はx>0前提)。
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

import l4_mbf_oracle_v2 as oracle  # noqa: E402
import l4_mbf_oracle_v3 as v3  # noqa: E402
import l4_mbf_oracle_v10_m9 as m9  # noqa: E402

MBF_SINGLE_ASM = REPO / "src" / "l4_basic" / "mbf_single.asm"
MBF_DOUBLE_ASM = REPO / "src" / "l4_basic" / "mbf_double.asm"
BANK0_ASM = REPO / "src" / "ext_bank" / "bank0.asm"
FRONTEND = REPO / "tools" / "harness" / "frontend" / "q88measure"
VENDOR = REPO.parent / "vendor" / "quasi88-libretro"

# bank0.asmの実測終端よりやや先(SIN/COS/TANのVEC_TABLE_ADDRと同じ考え方。
# ATN/EXP/LOG追加分だけbank0.asmがさらに伸びたため、SIN/COS/TAN照合器の
# 0x6900では足りない——実測して安全側に切り上げた値)。
VEC_TABLE_ADDR = 0x6F00
N88_SIZE = 0x8000
DISK_SIZE = 0x0800
OUT_BASE = 0xE000
OUT_STRIDE = 5  # MBF_RES(4byte) + MBF_STATUS(1byte)

ADDR_LABELS = {
    "SIN_ADD_ADDR": "MBF_ADD",
    "SIN_SUB_ADDR": "MBF_SUB",
    "SIN_MUL_ADDR": "MBF_MUL",
    "SIN_DIV_ADDR": "MBF_DIV",
    "SIN_NEG_ADDR": "MBF_NEG",
    "SIN_TRUNC_ADDR": "TRUNC_TO_SINGLE",
    "MBF_STOD_ADDR": "MBF_STOD",
    "MBF_DADD_ADDR": "MBF_DADD",
    "MBF_DDIV_ADDR": "MBF_DDIV",
    "MBF_DTOS_ADDR": "MBF_DTOS",
    "AEL_ADD_ADDR": "MBF_ADD",
    "AEL_SUB_ADDR": "MBF_SUB",
    "AEL_MUL_ADDR": "MBF_MUL",
    "AEL_DIV_ADDR": "MBF_DIV",
    "AEL_NEG_ADDR": "MBF_NEG",
    "AEL_CMP_ADDR": "MBF_CMP",
    "AEL_TRUNC_ADDR": "TRUNC_TO_SINGLE",
    "AEL_ITOS_ADDR": "MBF_INT_TO_SINGLE",
}

FUNCS = {
    "atn": ("EXT_BANK0_ATN_ENTRY", m9.atn_impl),
    "exp": ("EXT_BANK0_EXP_ENTRY", m9.exp_impl),
    "log": ("EXT_BANK0_LOG_ENTRY", m9.log_impl),
}


def find_core() -> pathlib.Path:
    cands = sorted(VENDOR.glob("quasi88_libretro.*"))
    if not cands:
        raise SystemExit(f"コアが無い: {VENDOR} (tools/setup_harness.sh を先に実行)")
    return cands[0]


def _f(v):
    return oracle.GwNum.from_fraction(Fraction(v), "single")


def rand_single_general(rng: random.Random, sign_choices=(0, 1), exp_range=(1, 200)) -> "oracle.GwNum":
    sign = rng.choice(sign_choices)
    exp = rng.randint(*exp_range)
    mant = rng.randint(0x800000, 0xFFFFFF)
    return oracle.GwNum("single", sign=sign, exp=exp, mant=mant)


# ---------------------------------------------------------------------
# ATN: 0付近・±1付近・大きい値を含む乱数+境界値。
# ---------------------------------------------------------------------
ATN_BOUNDARY = [
    _f(0), _f(1), _f(-1), _f(2), _f(-2),
    v3.TAN_PI12, oracle.gw_neg(v3.TAN_PI12),
    v3.SQRT3, oracle.gw_neg(v3.SQRT3),
    oracle.GwNum("single", sign=0, exp=1, mant=0x800000),
    oracle.GwNum("single", sign=1, exp=1, mant=0x800000),
    oracle.GwNum("single", sign=0, exp=255, mant=0xFFFFFF),
    oracle.GwNum("single", sign=1, exp=255, mant=0xFFFFFF),
    oracle.GwNum("single", sign=0, exp=129, mant=0x800000),  # ちょうど1.0(need_pi2境界)
    _f(100), _f(-100), _f(1000000), _f(-1000000),
]


def atn_vectors(n: int, rng: random.Random):
    vecs = list(ATN_BOUNDARY)
    while len(vecs) < n:
        if rng.random() < 0.3:
            # 0付近(exp小さめ)
            exp = rng.randint(1, 30)
        elif rng.random() < 0.6:
            # ±1付近(need_pi2/need_pi6の分岐境界)
            exp = rng.randint(125, 132)
        else:
            exp = rng.randint(1, 200)
        vecs.append(rand_single_general(rng, exp_range=(exp, exp)))
    return vecs[:n]


# ---------------------------------------------------------------------
# EXP: 溢れ境界・負の大きい値・0付近を含む乱数+境界値。
# ---------------------------------------------------------------------
EXP_BOUNDARY = [
    _f(0), _f(1), _f(-1), _f(2), _f(-2),
    _f(10), _f(-10), _f(50), _f(-50),
    _f(88), _f(-88),  # exp(88)は単精度でほぼ境界(log2(e)*88≈127付近)
    _f(-7),  # l4-s6h・第9版で確定済みの既知の1腕(16桁目のみ食い違い)
    oracle.GwNum("single", sign=0, exp=1, mant=0x800000),   # 最小正
    oracle.GwNum("single", sign=1, exp=1, mant=0x800000),   # 最小負
    oracle.GwNum("single", sign=0, exp=255, mant=0xFFFFFF),  # 最大正(確実にOverflow)
    oracle.GwNum("single", sign=1, exp=255, mant=0xFFFFFF),  # 最大負(確実に0)
]


def exp_vectors(n: int, rng: random.Random):
    vecs = list(EXP_BOUNDARY)
    while len(vecs) < n:
        r = rng.random()
        if r < 0.25:
            # y.exp>=0o210(136)の境界付近を狙う: x*LOG2E~2^8。
            # LOG2Eの指数は0x81なのでx自体の指数を135-136付近に振る。
            exp = rng.randint(133, 138)
        elif r < 0.5:
            # y.exp<0o150(104)の境界(1.0を返す)付近。
            exp = rng.randint(95, 105)
        elif r < 0.75:
            exp = rng.randint(1, 60)
        else:
            exp = rng.randint(1, 200)
        vecs.append(rand_single_general(rng, exp_range=(exp, exp)))
    return vecs[:n]


# ---------------------------------------------------------------------
# LOG: 1付近・非常に小さい値・大きい値を含む乱数+境界値(x>0のみ)。
# ---------------------------------------------------------------------
LOG_BOUNDARY = [
    _f(1), _f(2), _f(Fraction(1, 2)),
    oracle.GwNum("single", sign=0, exp=1, mant=0x800000),   # 最小正
    oracle.GwNum("single", sign=0, exp=255, mant=0xFFFFFF),  # 最大正
    oracle.GwNum("single", sign=0, exp=129, mant=0x800001),  # 1.0にごく近い(>1側)
    oracle.GwNum("single", sign=0, exp=128, mant=0xFFFFFF),  # 1.0にごく近い(<1側)
    _f(10), _f(100), _f(1000000),
]


def log_vectors(n: int, rng: random.Random):
    vecs = list(LOG_BOUNDARY)
    while len(vecs) < n:
        r = rng.random()
        if r < 0.3:
            exp = rng.randint(126, 132)  # 1.0付近
        elif r < 0.6:
            exp = rng.randint(1, 20)  # 非常に小さい
        elif r < 0.8:
            exp = rng.randint(200, 255)  # 大きい
        else:
            exp = rng.randint(1, 255)
        vecs.append(rand_single_general(rng, sign_choices=(0,), exp_range=(exp, exp)))
    return vecs[:n]


VECTOR_GENS = {"atn": atn_vectors, "exp": exp_vectors, "log": log_vectors}


def gen_vectors(func: str, n: int, seed: int):
    rng = random.Random(seed)
    return VECTOR_GENS[func](n, rng)


def encode_vectors(vecs) -> bytes:
    out = bytearray()
    for v in vecs:
        s, e, m = v.as_single_or_double_pair()
        out += oracle.mbf4_bytes(s, e, m)
    return bytes(out)


DRIVER_PREFIX_TMPL = """    org 0x0000
    DI
    LD SP,0xFFF0
    LD HL,VEC_TABLE
    LD DE,0x{out_base:04X}
    LD BC,{n_vectors}
_l4ael_loop:
    PUSH BC
    LD A,(HL)
    LD (MBF_OPA),A
    INC HL
    LD A,(HL)
    LD (MBF_OPA+1),A
    INC HL
    LD A,(HL)
    LD (MBF_OPA+2),A
    INC HL
    LD A,(HL)
    LD (MBF_OPA+3),A
    INC HL
    PUSH HL
    PUSH DE
    CALL {entry}
    POP DE
    POP HL
    POP BC
    LD A,(MBF_RES)
    LD (DE),A
    INC DE
    LD A,(MBF_RES+1)
    LD (DE),A
    INC DE
    LD A,(MBF_RES+2)
    LD (DE),A
    INC DE
    LD A,(MBF_RES+3)
    LD (DE),A
    INC DE
    LD A,(MBF_STATUS)
    LD (DE),A
    INC DE
    DEC BC
    LD A,B
    OR C
    JP NZ,_l4ael_loop
_l4ael_done:
    JR _l4ael_done"""


def driver_prefix(n_vectors: int, entry: str) -> str:
    return DRIVER_PREFIX_TMPL.format(out_base=OUT_BASE, n_vectors=n_vectors, entry=entry)


TAIL_TMPL = """
    org 0x{vec_table_addr:04X}
VEC_TABLE:
    ; (テストデータはこのスクリプトが実行時に追記する)
"""


FAULTS = {
    # 陰性対照(ATN): 係数破壊。ATNC2[3](=1.0、_polyx_evalの最終段)の
    # 指数バイトを1つ壊す。
    "atn_bad_coeff": ("AEL_ATNC2_3:\n    DB 0x00,0x00,0x00,0x81",
                       "AEL_ATNC2_3:\n    DB 0x00,0x00,0x00,0x82"),
    # 陰性対照(ATN): need_pi6分岐条件(MBF_OUT_CMPが1=A>Bのときだけ真)を
    # 逆転させる(CPで1と比較する箇所を0と比較=常に成立しない条件へ)。
    "atn_wrong_branch": ("LD A,(MBF_OUT_CMP)\n    CP 1\n    JP NZ,_ael_atn_no_pi6",
                          "LD A,(MBF_OUT_CMP)\n    CP 0\n    JP NZ,_ael_atn_no_pi6"),
    # 陰性対照(EXP): 係数破壊。EXPCN6(=1.0、最高位係数)を壊す。
    "exp_bad_coeff": ("AEL_EXPCN6:\n    DB 0x00,0x00,0x00,0x81",
                       "AEL_EXPCN6:\n    DB 0x00,0x00,0x00,0x82"),
    # 陰性対照(EXP): オーバーフロー閾値(0o210=136)を壊す。
    "exp_wrong_threshold": ("CP 136\n    JP C,_ael_exp_check_small",
                             "CP 120\n    JP C,_ael_exp_check_small"),
    # 陰性対照(LOG): 係数破壊。LOGP0を壊す。
    "log_bad_coeff": ("AEL_LOGP0:\n    DB 0x9A,0xF7,0x19,0x83",
                       "AEL_LOGP0:\n    DB 0x9A,0xF7,0x19,0x84"),
    # 陰性対照(LOG): LN2を壊す(最終乗算の定数取り違え)。
    "log_bad_ln2": ("AEL_LN2:\n    DB 0x18,0x72,0x31,0x80",
                     "AEL_LN2:\n    DB 0x18,0x72,0x31,0x81"),
}


DUP_EQU_LINES = (
    "MBF_OPA EQU 0xC000",
    "MBF_OPB EQU 0xC004",
    "MBF_RES EQU 0xC008",
    "MBF_STATUS EQU 0xC00C",
    "MBF_IN_INT EQU 0xC00D",
    "MBF_OUT_CMP EQU 0xC00F",
)


def load_bank0_src(fault: str | None) -> str:
    text = BANK0_ASM.read_text()
    for line in DUP_EQU_LINES:
        old = line + "\n"
        if text.count(old) == 1:
            text = text.replace(old, "", 1)
    if fault:
        old, new = FAULTS[fault]
        if old not in text:
            raise SystemExit(f"故障注入 {fault} の置換対象が見つからない")
        if text.count(old) != 1:
            raise SystemExit(f"故障注入 {fault} の置換対象が一意でない")
        text = text.replace(old, new, 1)
    return text


def assemble(text: str, out_bin: pathlib.Path, asm_path: pathlib.Path):
    asm_path.write_text(text)
    r = subprocess.run(
        [sys.executable, str(REPO / "tools" / "asm" / "z80text.py"), str(asm_path), "-o", str(out_bin)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"アセンブル失敗:\n{r.stdout}\n{r.stderr}")
    return out_bin.read_bytes()


def resolve_addrs(prefix: str, mbf_src: str, bank0_src_placeholder: str,
                   workdir: pathlib.Path) -> dict:
    tail = TAIL_TMPL.format(vec_table_addr=VEC_TABLE_ADDR)
    probe_text = prefix + "\n\n" + mbf_src + "\n\n" + bank0_src_placeholder + "\n" + tail
    asm_path = workdir / "probe.asm"
    asm_path.write_text(probe_text)
    sys.path.insert(0, str(REPO / "tools" / "asm"))
    import z80text  # noqa: E402
    asm = z80text.Assembler()
    asm.assemble(asm_path)
    addrs = {}
    for eq_name, label in ADDR_LABELS.items():
        addr = asm.labels.get(label)
        if addr is None:
            raise SystemExit(f"ラベルが見つからない: {label}")
        addrs[eq_name] = addr
    return addrs


def patch_bank0(text: str, addrs: dict) -> str:
    for eq_name, addr in addrs.items():
        old = f"{eq_name} EQU 0x1787"
        if old not in text:
            raise SystemExit(f"{eq_name}の置換対象が見つからない")
        if text.count(old) != 1:
            raise SystemExit(f"{eq_name}の置換対象が一意でない")
        text = text.replace(old, f"{eq_name} EQU 0x{addr:04X}")
    return text


def build_rom(vecs, func: str, fault: str | None, workdir: pathlib.Path) -> pathlib.Path:
    entry, _ = FUNCS[func]
    mbf_src = MBF_SINGLE_ASM.read_text() + "\n" + MBF_DOUBLE_ASM.read_text()
    bank0_src = load_bank0_src(fault)
    prefix = driver_prefix(len(vecs), entry)
    addrs = resolve_addrs(prefix, mbf_src, bank0_src, workdir)
    bank0_src = patch_bank0(bank0_src, addrs)

    tail = TAIL_TMPL.format(vec_table_addr=VEC_TABLE_ADDR)
    asm_text = prefix + "\n\n" + mbf_src + "\n\n" + bank0_src + "\n" + tail
    asm_path = workdir / "atnexplog.asm"
    out_bin = workdir / "atnexplog.bin"
    prog = assemble(asm_text, out_bin, asm_path)
    if len(prog) > VEC_TABLE_ADDR:
        raise SystemExit(
            f"ルーチン本体がVEC_TABLE_ADDR(0x{VEC_TABLE_ADDR:04X})を超えた"
            f"({len(prog)}バイト)")

    rom = bytearray([0] * N88_SIZE)
    rom[0:len(prog)] = prog
    vec_bytes = encode_vectors(vecs)
    end = VEC_TABLE_ADDR + len(vec_bytes)
    if end > N88_SIZE:
        raise SystemExit(f"ベクタ表がROMサイズを超える: {end:#x} > {N88_SIZE:#x}")
    rom[VEC_TABLE_ADDR:end] = vec_bytes

    romdir = workdir / "rom"
    romdir.mkdir(exist_ok=True)
    (romdir / "N88.ROM").write_bytes(rom)
    disk = bytearray([0] * DISK_SIZE)
    disk[0:2] = bytes([0x18, 0xFE])
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
        result[addr] = val
    return result


def compare(func: str, n: int, seed: int, frames: int, fault: str | None, workdir: pathlib.Path):
    _, impl = FUNCS[func]
    vecs = gen_vectors(func, n, seed)
    romdir = build_rom(vecs, func, fault, workdir)
    out_len_total = OUT_STRIDE * len(vecs)
    mem = run_and_collect(romdir, out_len_total, workdir, frames)

    mismatches = []
    for i, v in enumerate(vecs):
        base = OUT_BASE + i * OUT_STRIDE
        got_res = bytes(mem.get(base + k, 0) for k in range(4))
        got_status = mem.get(base + 4, 0)
        try:
            expected_num = impl(v)
        except m9.GwError as ge:
            # EXPのオーバーフロー(引数が大きすぎる/2^nyのげたが255超)。
            # bank0.asm AEL_EXP_IMPLはこの経路でMBF_RESを明示的な値へ
            # 書かない(interp.asm FTNF_DO_EXPもMBF_STATUSしか見ない)ため、
            # MBF_STATUS==1だけを照合する(MBF_RESは比較対象外)。
            if got_status != 1:
                mismatches.append((i, v, "status=1", f"status={got_status}", None))
            continue
        except Exception as e:  # pragma: no cover
            mismatches.append((i, v, None, got_res, str(e)))
            continue
        if got_status != 0:
            mismatches.append((i, v, "status=0", f"status={got_status}", None))
            continue
        s, e, m_ = expected_num.as_single_or_double_pair()
        want = oracle.mbf4_bytes(s, e, m_)
        if got_res != want:
            mismatches.append((i, v, want, got_res, None))
    return vecs, mismatches


def report(n_total: int, mismatches, expect_ng: bool) -> bool:
    n_mis = len(mismatches)
    if expect_ng:
        ok = n_mis > 0
        print(f"[fault] {n_mis}/{n_total} 件不一致 (期待: 不一致>0) -> {'OK' if ok else 'NG'}")
    else:
        ok = n_mis == 0
        print(f"{n_total}件中 不一致{n_mis}件 -> {'OK' if ok else 'NG'}")
        for i, v, want, got, err in mismatches[:10]:
            if err:
                print(f"  #{i}: 例外 {err} (入力={v.exact()})")
            else:
                want_s = want if isinstance(want, str) else want.hex()
                got_s = got if isinstance(got, str) else got.hex()
                print(f"  #{i}: 入力={v.exact()} 期待={want_s} 実測={got_s}")
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--func", choices=sorted(FUNCS), required=True)
    ap.add_argument("-n", type=int, default=1500,
                     help="乱数ベクタの数(境界値は別に常に含む)")
    ap.add_argument("--seed", type=int, default=20260920)
    ap.add_argument("--frames", type=int, default=None,
                     help="省略時は-nに応じて自動計算")
    ap.add_argument("--fault", choices=sorted(FAULTS), default=None,
                     help="陰性対照(検出力の確認、不一致>0が合格)")
    ap.add_argument("--work-dir", type=pathlib.Path, default=None)
    args = ap.parse_args(argv)
    if args.frames is None:
        args.frames = max(2000, args.n * 300)

    import tempfile
    work = args.work_dir
    cleanup = False
    if work is None:
        work = pathlib.Path(tempfile.mkdtemp(prefix="pc88_atnexplogconform_"))
        cleanup = True
    work.mkdir(parents=True, exist_ok=True)
    try:
        vecs, mismatches = compare(args.func, args.n, args.seed, args.frames, args.fault, work)
        ok = report(len(vecs), mismatches, expect_ng=(args.fault is not None))
        sys.exit(0 if ok else 1)
    finally:
        if cleanup:
            import shutil
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
