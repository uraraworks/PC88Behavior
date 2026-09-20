#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_sqr_bank_conform.py — src/ext_bank/bank0.asm EXT_BANK0_SQR_ENTRY
（単精度SQR、docs/spec/l4-program.md 第4.16b節）を実際にZ80として実行し、
tools/l4_mbf_oracle_v10_m9.py の sqr_impl（away丸め版予測器。第4.16b節
「SQRは候補間で差が出ない」ため、実装手順ではなく最終丸め1回だけを
away化した予測器）とバイト単位で突き合わせる照合器。

tools/l4_mbf_conform.py と同じ手段（自作ROMを実際にZ80として実行し、
--mem-write-log で結果を回収する。tools/harness/frontend/q88measure、
自作の試験ROM。公式ROM・private/は一切参照しない）を使う。

## bank0.asmを「そのまま」assembleする（二重実装しない）

EXT_BANK0_SQR_ENTRYのアルゴリズムをこのスクリプト側に書き写すのではなく、
src/ext_bank/bank0.asm を mbf_single.asm・mbf_double.asm と連結して
1本のROM（org 0x0000起点、実機の窓〈0x6000-0x7FFF〉切り替え機構は使わない
——それ自体は tools/ext_bank_selftest.sh が別途検証済み）としてassemble
し、driverが直接 EXT_BANK0_SQR_ENTRY をCALLする。bank0.asm内の
MBF_STOD_ADDR等4つのEQU（常駐部ルーチンの絶対番地）は、
build_main_rom.py --addr と同じ手法（1回目のassembleでラベルの番地を
求め、テキスト置換して2回目でassembleし直す）で解決する。

## 入力の前提

EXT_BANK0_SQR_ENTRYは「0より大きい単精度」だけを入力に想定する
（ゼロ・負はinterp.asm FTNF_DO_SQR側で分岐済み、bank0.asmのコメント
参照）。このため本照合器も乱数ベクタを正の非ゼロ単精度に限定する。
"""

from __future__ import annotations

import argparse
import pathlib
import random
import re
import subprocess
import sys

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

VEC_TABLE_ADDR = 0x7000     # bank0.asmの実測終端より少し先。2026-09-20
                             # 追記: SIN/COS/TAN実装(EXT_BANK0_SIN_ENTRY等、
                             # オフセット0x0200-0x0220台)でbank0.asmが伸び、
                             # 旧値0x6120では実際のコード終端(実測0x64BD
                             # 付近)と衝突して「org が既に書いた領域より
                             # 手前を指している」でアセンブル失敗するように
                             # なった(run_all_selftests.shで発覚)。
                             # tools/l4_sincos_bank_conform.pyの0x6900と
                             # 同じ理由で値を上げる(SQR側は0x6900だと
                             # -n既定値1900がcapを超えるため、0x6900より
                             # 少し詰めた0x6700にする)。
                             # 2026-09-20さらに追記(l4-s7c、親からの指摘):
                             # ATN/EXP/LOG実装(b00bf21)でbank0.asmが
                             # さらに伸び、0x6700でも「org が既に書いた
                             # 領域より手前」で再発した(EQU重複除去の
                             # バグ〔l4_bank_dup_equ.py参照〕でこのエラー
                             # 自体には到達していなかった)。
                             # tools/l4_atnexplog_bank_conform.pyが同じ
                             # bank0.asmに対して既に0x6F00で通っている
                             # ことを踏まえ、さらに余裕を持たせて0x7000に
                             # 上げた(cap=(N88_SIZE-VEC_TABLE_ADDR)/4は
                             # 0x7000で1024、本ファイルが使う最大n=250に
                             # 十分な余裕がある)。
N88_SIZE = 0x8000            # 32KB(実機のROM窓と同じ)。2026-09-20の
                              # デバッグで、48KB(0xC000)にしたところ
                              # n=1536件目から突然「別の固定値が繰り返し
                              # 返る」不一致が発生した——q88measureが
                              # N88.ROMを実機と同じ0x8000までしかROMとして
                              # 読まない(0x8000以降は別のメモリデバイス
                              # 〈VRAM等〉にエイリアスする)ためと判明した。
                              # VEC_TABLE_ADDRをbank0.asm直後まで詰めて
                              # 0x8000以内に収め、実機と同じサイズへ戻した。
DISK_SIZE = 0x0800
OUT_BASE = 0xE000            # 結果格納(RAM)。ROM領域(N88_SIZE)と衝突しない。

ADDR_EQU_NAMES = ("MBF_STOD_ADDR", "MBF_DADD_ADDR", "MBF_DDIV_ADDR", "MBF_DTOS_ADDR")
ADDR_LABELS = {
    "MBF_STOD_ADDR": "MBF_STOD",
    "MBF_DADD_ADDR": "MBF_DADD",
    "MBF_DDIV_ADDR": "MBF_DDIV",
    "MBF_DTOS_ADDR": "MBF_DTOS",
}


def find_core() -> pathlib.Path:
    cands = sorted(VENDOR.glob("quasi88_libretro.*"))
    if not cands:
        raise SystemExit(f"コアが無い: {VENDOR} (tools/setup_harness.sh を先に実行)")
    return cands[0]


def rand_positive_single(rng: random.Random) -> "oracle.GwNum":
    if rng.random() < 0.15:
        exp = rng.choice([1, 2, 3, 4, 126, 127, 128, 129, 130, 253, 254, 255])
    else:
        exp = rng.randint(1, 255)
    mant = rng.randint(0x800000, 0xFFFFFF)
    return oracle.GwNum("single", sign=0, exp=exp, mant=mant)


BOUNDARY_SINGLES = [
    oracle.GwNum.from_fraction(__import__("fractions").Fraction(1), "single"),
    oracle.GwNum.from_fraction(__import__("fractions").Fraction(2), "single"),
    oracle.GwNum.from_fraction(__import__("fractions").Fraction(4), "single"),
    oracle.GwNum.from_fraction(__import__("fractions").Fraction(1, 2), "single"),
    oracle.GwNum("single", sign=0, exp=1, mant=0x800000),      # 最小正
    oracle.GwNum("single", sign=0, exp=255, mant=0xFFFFFF),    # 最大正
    oracle.GwNum("single", sign=0, exp=150, mant=0xFFFFFF),
    oracle.GwNum.from_fraction(__import__("fractions").Fraction(16), "single"),
    oracle.GwNum.from_fraction(__import__("fractions").Fraction(2, 1), "single"),
]


def gen_vectors(n: int, seed: int):
    cap = (N88_SIZE - VEC_TABLE_ADDR) // 4
    if n > cap:
        raise SystemExit(
            f"-n {n} は上限 {cap} を超える(VEC_TABLE_ADDR=0x{VEC_TABLE_ADDR:04X}・"
            f"N88_SIZE=0x{N88_SIZE:04X}、q88measureがROMとして読むのは0x8000まで"
            "——2026-09-20に超えて無言破損を踏んだため上限チェックを追加)")
    rng = random.Random(seed)
    vecs = list(BOUNDARY_SINGLES)
    while len(vecs) < n:
        vecs.append(rand_positive_single(rng))
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
_l4sqr_loop:
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
    CALL EXT_BANK0_SQR_ENTRY
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
    JP NZ,_l4sqr_loop
_l4sqr_done:
    JR _l4sqr_done"""


def driver_prefix(n_vectors: int) -> str:
    # n_vectorsが変わってもテキスト長は変わらない(即値はASCII10進数の
    # 桁数で長さが変わりうる——例えば999→1000で桁が増える。resolve_addrs
    # とbuild_rom で同じn_vectorsを渡す限りは同一になるため実害は無い
    # が、念のためコメントしておく)。
    return DRIVER_PREFIX_TMPL.format(out_base=OUT_BASE, n_vectors=n_vectors)


TAIL_TMPL = """
    org 0x{vec_table_addr:04X}
VEC_TABLE:
    ; (テストデータはこのスクリプトが実行時に追記する)
"""


FAULTS = {
    # 陰性対照: ニュートン法の反復回数を10->1へ削り、収束不足で不一致を
    # 起こす(検出力の確認、docs/notes系の「対照と故障注入の作法」参照)。
    "iter1": ("SQR_ITER_COUNT EQU 10", "SQR_ITER_COUNT EQU 1"),
    # 陰性対照: 2で割る(指数バイト-1)を止め、値が毎回2倍に発散するように
    # 壊す。
    "no_halve": ("    DEC A\n    LD (MBF_DRES_RAM+7),A\n_sqr_skip_halve:",
                 "    LD (MBF_DRES_RAM+7),A\n_sqr_skip_halve:"),
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


def resolve_addrs(driver_prefix: str, mbf_src: str, bank0_src_placeholder: str,
                   workdir: pathlib.Path) -> dict:
    """1回目のassemble(placeholderのまま)でMBF_STOD等の番地を求める。

    重要: mbf_src中のラベル(MBF_STOD等)の番地は「その手前に置かれた
    driverコードの長さ」に依存する。ここで使うdriver_prefixは
    build_rom()が実際に使う本番driverと**同じ長さのテキスト**でなければ
    ならない——ここだけ違う長さのdriver(例: "RET"だけの短いプローブ)を
    使うと、このpassで求めた番地が本番passでは別の番地にズレる
    (実際にこのバグを踏んだ: 最初は"RET"だけの短いプローブで求めた
    番地を本番driverへ渡したところ、mbf_src全体のオフセットがズレて
    MBF_STOD等が全く違う番地を指し、STOD呼び出しが暴走した)。
    """
    tail = TAIL_TMPL.format(vec_table_addr=VEC_TABLE_ADDR)
    probe_text = driver_prefix + "\n\n" + mbf_src + "\n\n" + bank0_src_placeholder + "\n" + tail
    asm_path = workdir / "probe.asm"
    out_bin = workdir / "probe.bin"
    asm_path.write_text(probe_text)
    # z80text.py CLIはラベル表を吐かないので、tools/asm/z80text.pyを直接importして使う。
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


def build_rom(vecs, fault: str | None, workdir: pathlib.Path) -> pathlib.Path:
    mbf_src = MBF_SINGLE_ASM.read_text() + "\n" + MBF_DOUBLE_ASM.read_text()
    bank0_src = load_bank0_src(fault, mbf_src)
    prefix = driver_prefix(len(vecs))
    addrs = resolve_addrs(prefix, mbf_src, bank0_src, workdir)
    bank0_src = patch_bank0(bank0_src, addrs)

    tail = TAIL_TMPL.format(vec_table_addr=VEC_TABLE_ADDR)
    asm_text = prefix + "\n\n" + mbf_src + "\n\n" + bank0_src + "\n" + tail
    asm_path = workdir / "sqr.asm"
    out_bin = workdir / "sqr.bin"
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


def compare(n: int, seed: int, frames: int, fault: str | None, workdir: pathlib.Path):
    vecs = gen_vectors(n, seed)
    romdir = build_rom(vecs, fault, workdir)
    out_len_total = 4 * len(vecs)
    mem = run_and_collect(romdir, out_len_total, workdir, frames)

    mismatches = []
    for i, v in enumerate(vecs):
        base = OUT_BASE + i * 4
        got = bytes(mem.get(base + k, 0) for k in range(4))
        try:
            expected_num = m9.sqr_impl(v)
            s, e, m_ = expected_num.as_single_or_double_pair()
            want = oracle.mbf4_bytes(s, e, m_)
        except Exception as e:  # pragma: no cover
            mismatches.append((i, v, None, got, str(e)))
            continue
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
    ap.add_argument("-n", type=int, default=1600,
                     help="乱数ベクタの数(境界値は別に常に含む)。VEC_TABLE_ADDRから"
                          "N88_SIZE(実機と同じ0x8000)までに収まる上限は約1600件"
                          "(2026-09-20、SIN/COS/TAN追加でbank0.asmが伸びた分だけ"
                          "VEC_TABLE_ADDRを上げたため、既定値も上限内へ下げた。"
                          "--addr等は使わず、bank0.asmの実測終端に合わせて"
                          "VEC_TABLE_ADDRを決めている)")
    ap.add_argument("--seed", type=int, default=20260920)
    ap.add_argument("--frames", type=int, default=None,
                     help="省略時は-nに応じて自動計算(1件あたり約160フレーム、"
                          "実測: n=1900で約300000フレームなら十分)。"
                          "小さすぎるとループ未完了の0埋めを誤って"
                          "「不一致」と報告する(2026-09-20に実際に踏んだ)")
    ap.add_argument("--fault", choices=sorted(FAULTS), default=None,
                     help="陰性対照(検出力の確認、不一致>0が合格)")
    ap.add_argument("--work-dir", type=pathlib.Path, default=None)
    args = ap.parse_args(argv)
    if args.frames is None:
        args.frames = max(2000, args.n * 160)

    import tempfile
    work = args.work_dir
    cleanup = False
    if work is None:
        work = pathlib.Path(tempfile.mkdtemp(prefix="pc88_sqrconform_"))
        cleanup = True
    work.mkdir(parents=True, exist_ok=True)
    try:
        vecs, mismatches = compare(args.n, args.seed, args.frames, args.fault, work)
        ok = report(len(vecs), mismatches, expect_ng=(args.fault is not None))
        sys.exit(0 if ok else 1)
    finally:
        if cleanup:
            import shutil
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
