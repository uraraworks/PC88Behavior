#!/usr/bin/env python3
"""m6i-a の腕専用ROMを作る（エミュレータは起動しない）。

通常の ``src/build_main_rom.py`` が生成する自作ROM一式を土台にする。
A1では既知READのRだけを2へ変え、A5では定常ループから呼ぶ一回入口だけを
測定用200回ラッパへ差し替える。配布構成やsub ROMのソースは変更しない。
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys


REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import src.build_main_rom as build  # noqa: E402


SECTOR_OLD = "    LD A,001h                   ; 位置5=R 1"
SECTOR_NEW = "    LD A,002h                   ; 位置5=R 2（A1測定ビルド）"

BOOT_OLD = """MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    XOR A
    CALL MAIN_SUB_READ_KNOWN
    RET
"""

# E010-E03A は測定ビルドだけの観測域。値はmemlogから解析器だけが読み、
# 標準出力へは一致真偽・件数・SHA-256しか出さない。
BOOT_A5 = """MAIN_SUB_READ_BOOT_ONCE:
    LD A,(MAIN_SUB_BOOT_DONE)
    OR A
    RET NZ
    LD A,001h
    LD (MAIN_SUB_BOOT_DONE),A
    LD HL,00C8h
    LD (M6IA_REPEAT_LEFT),HL
_m6ia_repeat_loop:
    CALL M6IA_BANK_PROBE_PRE

    ; G8で凍結する保存対象 AF/BC/DE/HL/IX/IY に既知値を置く。
    ; Aは入口引数bit0=0を兼ねる。snapshot自身は全対を復元して戻る。
    LD BC,01234h
    LD DE,05678h
    LD HL,09ABCh
    LD IX,01357h
    LD IY,02468h
    XOR A
    SCF
    CALL M6IA_SNAPSHOT_PRE
    CALL MAIN_SUB_READ_KNOWN
    CALL M6IA_SNAPSHOT_POST

    CALL M6IA_BANK_PROBE_POST
    LD A,001h
    LD (M6IA_ITERATION_DONE),A
    LD HL,(M6IA_REPEAT_LEFT)
    DEC HL
    LD (M6IA_REPEAT_LEFT),HL
    LD A,H
    OR L
    JR NZ,_m6ia_repeat_loop
    LD A,001h
    LD (M6IA_REPEAT_DONE),A
    RET

; PUSH順の12バイトをそのまま前後スナップショットへ写す。
; メモリ上の順序は IY,IX,HL,DE,BC,AF（各little endian）。
M6IA_SNAPSHOT_PRE:
    PUSH AF
    PUSH BC
    PUSH DE
    PUSH HL
    PUSH IX
    PUSH IY
    LD HL,00000h
    ADD HL,SP
    LD DE,M6IA_REG_PRE
    LD BC,0000Ch
    LDIR
    POP IY
    POP IX
    POP HL
    POP DE
    POP BC
    POP AF
    RET

M6IA_SNAPSHOT_POST:
    PUSH AF
    PUSH BC
    PUSH DE
    PUSH HL
    PUSH IX
    PUSH IY
    LD HL,00000h
    ADD HL,SP
    LD DE,M6IA_REG_POST
    LD BC,0000Ch
    LDIR
    POP IY
    POP IX
    POP HL
    POP DE
    POP BC
    POP AF
    RET

; 既存の窓外中継 EXT_BANK_CALL と各バンク自身の識別返値を使う。
; 呼出し前後の0x71/0x32も別に保存し、解析器が各200組を比較する。
M6IA_BANK_PROBE_PRE:
    IN A,(071h)
    LD (M6IA_PORT71_PRE),A
    IN A,(032h)
    LD (M6IA_PORT32_PRE),A
    LD A,000h
    LD HL,06000h
    CALL EXT_BANK_CALL
    LD (M6IA_BANK_PRE+0),A
    LD A,001h
    LD HL,06000h
    CALL EXT_BANK_CALL
    LD (M6IA_BANK_PRE+1),A
    LD A,002h
    LD HL,06000h
    CALL EXT_BANK_CALL
    LD (M6IA_BANK_PRE+2),A
    LD A,003h
    LD HL,06000h
    CALL EXT_BANK_CALL
    LD (M6IA_BANK_PRE+3),A
    RET

M6IA_BANK_PROBE_POST:
    IN A,(071h)
    LD (M6IA_PORT71_POST),A
    IN A,(032h)
    LD (M6IA_PORT32_POST),A
    LD A,000h
    LD HL,06000h
    CALL EXT_BANK_CALL
    LD (M6IA_BANK_POST+0),A
    LD A,001h
    LD HL,06000h
    CALL EXT_BANK_CALL
    LD (M6IA_BANK_POST+1),A
    LD A,002h
    LD HL,06000h
    CALL EXT_BANK_CALL
    LD (M6IA_BANK_POST+2),A
    LD A,003h
    LD HL,06000h
    CALL EXT_BANK_CALL
    LD (M6IA_BANK_POST+3),A
    RET

M6IA_REG_PRE        EQU 0E010h ; 12 bytes
M6IA_REG_POST       EQU 0E01Ch ; 12 bytes
M6IA_PORT71_PRE     EQU 0E028h
M6IA_PORT32_PRE     EQU 0E029h
M6IA_PORT71_POST    EQU 0E02Ah
M6IA_PORT32_POST    EQU 0E02Bh
M6IA_BANK_PRE       EQU 0E02Ch ; 4 bytes
M6IA_BANK_POST      EQU 0E030h ; 4 bytes
M6IA_ITERATION_DONE EQU 0E034h
M6IA_REPEAT_DONE    EQU 0E035h
M6IA_REPEAT_LEFT    EQU 0E036h ; 2 bytes
"""


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label}の差し替え対象が一意でない")
    return text.replace(old, new)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("outdir", type=pathlib.Path)
    ap.add_argument("--arm", required=True,
                    choices=("A0", "A1", "A2", "A3", "A4-cont", "A4-pair", "A5"))
    ap.add_argument("--work-dir", required=True, type=pathlib.Path)
    args = ap.parse_args()

    args.work_dir.mkdir(parents=True, exist_ok=True)
    fault = {
        "A3": "--inject-main-sub-wait-fault",
        "A4-cont": "--inject-main-sub-cont-fault",
        "A4-pair": "--inject-main-sub-pair-fault",
    }.get(args.arm)
    base_cmd = [sys.executable, str(REPO / "src" / "build_main_rom.py"),
                str(args.outdir), "--enable-main-sub-read"]
    if fault:
        base_cmd.append(fault)
    subprocess.run(base_cmd, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)

    kwargs = {
        "enable_main_sub_read": True,
        "inject_main_sub_wait_fault": args.arm == "A3",
        "inject_main_sub_cont_fault": args.arm == "A4-cont",
        "inject_main_sub_pair_fault": args.arm == "A4-pair",
    }
    combined = build.build_combined_asm(args.work_dir, 0, False, **kwargs)
    generated = args.work_dir / "main_sub_read_gen.asm"
    text = generated.read_text(encoding="utf-8")
    if args.arm == "A1":
        text = replace_once(text, SECTOR_OLD, SECTOR_NEW, "A1 R=2")
    if args.arm == "A5":
        text = replace_once(text, BOOT_OLD, BOOT_A5, "A5 200回ラッパ")
    generated.write_text(text, encoding="utf-8")

    rom, asm = build.assemble(combined, args.work_dir)
    (args.outdir / "N88.ROM").write_bytes(rom)
    link_size = asm.labels["MAIN_SUB_LINK_END"] - asm.labels["MAIN_SUB_LINK_START"]
    print(f"arm={args.arm}")
    print(f"main_sub_link_size={link_size}")
    print(f"main_sub_link_limit={build.MAIN_SUB_LINK_MAX_SIZE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
