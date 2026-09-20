#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_sincos_bank_conform.py — src/ext_bank/bank0.asm の
EXT_BANK0_SIN_ENTRY/EXT_BANK0_COS_ENTRY/EXT_BANK0_TAN_ENTRY（単精度
SIN/COS/TAN、docs/spec/l4-program.md 第4.16a節）を実際にZ80として実行し、
tools/l4_mbf_oracle_v10_m9.py の sin_impl/cos_impl/tan_impl（`l4-s6g`で
確定した候補M9=範囲縮約単精度化+内部単精度演算すべてaway丸め）とバイト
単位で突き合わせる照合器。

tools/l4_sqr_bank_conform.py と同じ手段・同じ設計（bank0.asmをそのまま
assembleする、公式ROM・private/は一切参照しない、自作の試験ROM＋
tools/harness/frontend/q88measureを使う）を踏襲する。SQRと同じく
bank0.asm内のアルゴリズムをこのスクリプト側に書き写さない
（二重実装しない）。
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

import l4_bank_dup_equ as bank_dup_equ  # noqa: E402
import l4_mbf_oracle_v2 as oracle  # noqa: E402
import l4_mbf_oracle_v10_m9 as m9  # noqa: E402

MBF_SINGLE_ASM = REPO / "src" / "l4_basic" / "mbf_single.asm"
MBF_DOUBLE_ASM = REPO / "src" / "l4_basic" / "mbf_double.asm"
BANK0_ASM = REPO / "src" / "ext_bank" / "bank0.asm"
FRONTEND = REPO / "tools" / "harness" / "frontend" / "q88measure"
VENDOR = REPO.parent / "vendor" / "quasi88-libretro"

# bank0.asmの実測終端よりやや先(SQRのVEC_TABLE_ADDRと同じ考え方。
# SIN/COS/TAN追加分だけbank0.asmが伸びたため、0x6120では足りない
# ——実測して安全側に切り上げた値。q88measureはN88.ROMを実機と同じ
# 0x8000までしかROMとして読まない(0x8000以降は別デバイスにエイリアス
# する、l4_sqr_bank_conform.pyのコメント参照)ため、この余白の中に
# ベクタ表を収める必要がある)。
VEC_TABLE_ADDR = 0x7000     # 2026-09-20追記(l4-s7c、親からの指摘):
                             # ATN/EXP/LOG実装(b00bf21)でbank0.asmが
                             # さらに伸び、旧値0x6900では「org が既に
                             # 書いた領域より手前」で失敗するように
                             # なった(EQU重複除去のバグ〔tools/
                             # l4_bank_dup_equ.py参照〕でこのエラー自体
                             # には到達していなかった)。
                             # tools/l4_atnexplog_bank_conform.pyが同じ
                             # bank0.asmに対して既に0x6F00で通っている
                             # ことを踏まえ、tools/l4_sqr_bank_conform.py
                             # と同じ0x7000に上げた。
N88_SIZE = 0x8000
DISK_SIZE = 0x0800
OUT_BASE = 0xE000

ADDR_LABELS = {
    "MBF_STOD_ADDR": "MBF_STOD",
    "MBF_DADD_ADDR": "MBF_DADD",
    "MBF_DDIV_ADDR": "MBF_DDIV",
    "MBF_DTOS_ADDR": "MBF_DTOS",
    "SIN_ADD_ADDR": "MBF_ADD",
    "SIN_SUB_ADDR": "MBF_SUB",
    "SIN_MUL_ADDR": "MBF_MUL",
    "SIN_DIV_ADDR": "MBF_DIV",
    "SIN_NEG_ADDR": "MBF_NEG",
    "SIN_TRUNC_ADDR": "TRUNC_TO_SINGLE",
}

FUNCS = {
    "sin": ("EXT_BANK0_SIN_ENTRY", m9.sin_impl),
    "cos": ("EXT_BANK0_COS_ENTRY", m9.cos_impl),
    "tan": ("EXT_BANK0_TAN_ENTRY", m9.tan_impl),
}


def find_core() -> pathlib.Path:
    cands = sorted(VENDOR.glob("quasi88_libretro.*"))
    if not cands:
        raise SystemExit(f"コアが無い: {VENDOR} (tools/setup_harness.sh を先に実行)")
    return cands[0]


def rand_single(rng: random.Random) -> "oracle.GwNum":
    sign = rng.choice([0, 1])
    if rng.random() < 0.2:
        # SIN10早期リターン(exp<0o167=119)・微小角近似(exp<0o164=116)・
        # 象限境界付近を狙う小さめの指数バイトも混ぜる。
        exp = rng.choice([1, 50, 100, 110, 114, 115, 116, 117, 118, 119, 120, 128, 129, 130])
    else:
        exp = rng.randint(1, 200)  # あまり大きすぎるとTANのcos(x)=0近辺の
                                     # 判定が支配的になりすぎるため200まで
    mant = rng.randint(0x800000, 0xFFFFFF)
    return oracle.GwNum("single", sign=sign, exp=exp, mant=mant)


def _f(v):
    return oracle.GwNum.from_fraction(Fraction(v), "single")


BOUNDARY_SINGLES = [
    _f(0),
    _f(1),
    _f(-1),
    oracle.GwNum("single", sign=0, exp=1, mant=0x800000),   # 最小正
    oracle.GwNum("single", sign=1, exp=1, mant=0x800000),   # 最小負
    oracle.GwNum("single", sign=0, exp=255, mant=0xFFFFFF),  # 最大正
    oracle.GwNum("single", sign=1, exp=255, mant=0xFFFFFF),  # 最大負
    _f(100), _f(-100), _f(1000000), _f(-1000000),
]
# v3.PI2/TWO_PI(円周・π/2そのもの、象限境界の直近)も対象に含める。
import l4_mbf_oracle_v3 as _v3  # noqa: E402
BOUNDARY_SINGLES += [_v3.PI2, oracle.gw_neg(_v3.PI2), _v3.TWO_PI, oracle.gw_neg(_v3.TWO_PI)]


def gen_vectors(n: int, seed: int):
    rng = random.Random(seed)
    vecs = list(BOUNDARY_SINGLES)
    while len(vecs) < n:
        vecs.append(rand_single(rng))
    return vecs[:n]


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
_l4sc_loop:
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
    DEC BC
    LD A,B
    OR C
    JP NZ,_l4sc_loop
_l4sc_done:
    JR _l4sc_done"""


def driver_prefix(n_vectors: int, entry: str) -> str:
    return DRIVER_PREFIX_TMPL.format(out_base=OUT_BASE, n_vectors=n_vectors, entry=entry)


TAIL_TMPL = """
    org 0x{vec_table_addr:04X}
VEC_TABLE:
    ; (テストデータはこのスクリプトが実行時に追記する)
"""


FAULTS = {
    # 陰性対照: 範囲縮約の乗算をMBF_MULではなくMBF_ADD(全く異なる演算)へ
    # 差し替え、範囲縮約そのものを壊す。
    "wrong_reduce_op": ("CALL SIN_MUL_ADDR      ; MBF_RES = y (away丸め乗算)",
                         "CALL SIN_ADD_ADDR      ; MBF_RES = y (away丸め乗算)"),
    # 陰性対照: SINCN[4](最高位=2πに一致する係数、reduced_spが小さい
    # ほど支配的)の指数バイトを1つ壊す(多項式係数の取り違え)。SINCN[0]
    # (最下位、x^8の係数)の下位バイトを壊す版は、reduced_spが小さい
    # (|x|<0.25程度)ためx^8が実質無視できるほど小さく、全100腕で
    # 不一致0件のまま検出力が無かった(2026-09-20判明。歪みが最終桁の
    # 丸めにすら届かない)。支配的な係数を壊すことで確実に検出させる。
    "bad_coeff": ("SC_SINCN4:\n    DB 0xDB,0x0F,0x49,0x83",
                  "SC_SINCN4:\n    DB 0xDB,0x0F,0x49,0x84"),
    # 陰性対照: SIN10早期リターンの閾値を119から116へ変え、判定境界を壊す。
    "wrong_sin10_threshold": ("CP 119\n    JP NC,_sc_sin_notiny",
                               "CP 116\n    JP NC,_sc_sin_notiny"),
}


def load_bank0_src(fault: str | None, mbf_src: str) -> str:
    text = BANK0_ASM.read_text()
    # EQU重複除去はtools/l4_bank_dup_equ.pyへ集約した(2026-09-20、
    # 経緯は同モジュールのdocstring参照。以前は3照合器へ手書きリストを
    # 複製していたのが退行の原因だった)。
    text = bank_dup_equ.strip_dup_equ(mbf_src, text)
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
    try:
        asm.assemble(asm_path)
    except Exception as e:
        # l4-s7c(2026-09-20、親からの指摘)対応: この1回目のassemble
        # (番地決定のprobe pass)が失敗すると照合が1件も走らないまま
        # 終わってしまい、run_allの表示だけでは「不一致が見つかった」
        # のか「そもそも組み立てが通っていない」のか区別しづらかった。
        # 一言で分かるようにSystemExitで明示する(下のtracebackで詳細
        # は見える)。
        raise SystemExit(
            f"エラー: アセンブル失敗のため照合0件(組み立てエラー、"
            f"番地決定のprobe passで発生): {e}"
        ) from e
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
    bank0_src = load_bank0_src(fault, mbf_src)
    prefix = driver_prefix(len(vecs), entry)
    addrs = resolve_addrs(prefix, mbf_src, bank0_src, workdir)
    bank0_src = patch_bank0(bank0_src, addrs)

    tail = TAIL_TMPL.format(vec_table_addr=VEC_TABLE_ADDR)
    asm_text = prefix + "\n\n" + mbf_src + "\n\n" + bank0_src + "\n" + tail
    asm_path = workdir / "sincos.asm"
    out_bin = workdir / "sincos.bin"
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
    vecs = gen_vectors(n, seed)
    romdir = build_rom(vecs, func, fault, workdir)
    out_len_total = 4 * len(vecs)
    mem = run_and_collect(romdir, out_len_total, workdir, frames)

    mismatches = []
    for i, v in enumerate(vecs):
        base = OUT_BASE + i * 4
        got = bytes(mem.get(base + k, 0) for k in range(4))
        try:
            expected_num = impl(v)
        except m9.GwError as ge:
            # m9.GwErrorを使う理由: このスクリプトは`import l4_mbf_oracle_v2
            # as oracle`(REPO/tools直下からの単純import)だが、
            # l4_mbf_oracle_v10_m9.py自身は`from tools.l4_mbf_oracle_v2
            # import GwError`(パッケージ経由)でimportしており、Pythonの
            # モジュール同一性の都合でoracle.GwErrorとm9.GwErrorは別クラス
            # 扱いになる(2026-09-20、実際にisinstanceが外れてexcept節が
            # 効かず全件「例外」扱いになる不具合を踏んだ)。m9が実際に
            # raiseするクラスそのもの(m9.GwError)で捕まえる。
            # TAN(x)でcos(x)==0(0除算)の場合。MBF_DIVは0除算時に
            # MBF_PACK_OVERFLOW_KEEPSTATUS(mbf_single.asm)でオーバーフロー
            # パターン(符号は分子の符号、仮数全bit1・指数0xFF)を残す
            # ——GwError.residualが同じ値を持つ(tools/l4_mbf_oracle_v2.py
            # gw_binop "/"のZeroDivision処理を参照)ので、それを期待値として
            # 比較する(l4_sqr_bank_conform.pyには無い、SQRが負数を
            # interp.asm側で先に弾くため0除算/エラー経路を持たないのに対し
            # TANは範囲縮約の結果cos(x)がちょうど0になる入力が実在するため)。
            s, e, m_ = ge.residual.as_single_or_double_pair()
            want = oracle.mbf4_bytes(s, e, m_)
            if got != want:
                mismatches.append((i, v, want, got, None))
            continue
        except Exception as e:  # pragma: no cover
            mismatches.append((i, v, None, got, str(e)))
            continue
        s, e, m_ = expected_num.as_single_or_double_pair()
        want = oracle.mbf4_bytes(s, e, m_)
        if got != want:
            mismatches.append((i, v, want, got, None))
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
                print(f"  #{i}: 入力={v.exact()} 期待={want.hex()} 実測={got.hex()}")
    return ok


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--func", choices=sorted(FUNCS), required=True)
    ap.add_argument("-n", type=int, default=600,
                     help="乱数ベクタの数(境界値は別に常に含む)")
    ap.add_argument("--seed", type=int, default=20260920)
    ap.add_argument("--frames", type=int, default=None,
                     help="省略時は-nに応じて自動計算(TANはSIN+COSの2回分の"
                          "計算量なので単位フレーム数を大きめに取る)")
    ap.add_argument("--fault", choices=sorted(FAULTS), default=None,
                     help="陰性対照(検出力の確認、不一致>0が合格)")
    ap.add_argument("--work-dir", type=pathlib.Path, default=None)
    args = ap.parse_args(argv)
    if args.frames is None:
        per = 400 if args.func == "tan" else 250
        args.frames = max(2000, args.n * per)

    import tempfile
    work = args.work_dir
    cleanup = False
    if work is None:
        work = pathlib.Path(tempfile.mkdtemp(prefix="pc88_sincosconform_"))
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
