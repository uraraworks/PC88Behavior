#!/usr/bin/env python3
"""
src/ext_bank/make_ext_rom_banks.py — 拡張ROMバンク(4th ROM)N88_0.ROM〜
N88_3.ROMを組み立てる。

## 出所

根拠は docs/spec/ext-rom-bank.md だけである。各バンクは8KB(0x2000)、
窓(0x6000-0x7FFF)の内容としてそのまま読まれる(第1節)。埋め草はN88.ROM
本体(src/l1_ipl/make_ipl_rom.py の FILL=0x00)と揃える。

段階2の今回は「バンク切り替えの土台」を作るところまでが対象
(docs/spec/ext-rom-bank.md 第0節「位置づけ(実装スコープ)」配置案C)。
各バンクの中身は自己検査用の固定値を返す試験ルーチン1本だけ
(bank0.asm〜bank3.asm)。新しいBASICの機能はまだ置かない。

## 使い方

    python3 src/ext_bank/make_ext_rom_banks.py <出力先ディレクトリ>
"""

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "tools" / "asm"))

import z80text  # noqa: E402

BANK_SIZE = 0x2000  # 8KB。窓(0x6000-0x7FFF)と同じ大きさ
FILL = 0x00         # src/l1_ipl/make_ipl_rom.py の FILL と揃える

BANK_FILES = (
    ("N88_0.ROM", "bank0.asm"),
    ("N88_1.ROM", "bank1.asm"),
    ("N88_2.ROM", "bank2.asm"),
    ("N88_3.ROM", "bank3.asm"),
)


def assemble_bank(asm_path: pathlib.Path) -> bytes:
    asm = z80text.Assembler()
    try:
        code = asm.assemble(asm_path)
    except z80text.AsmError as e:
        raise SystemExit(f"{asm_path.name}: z80text アセンブルエラー: {e}")
    if len(code) > BANK_SIZE:
        raise SystemExit(
            f"{asm_path.name}: バンク(8KB)に収まらない: {len(code)} > {BANK_SIZE}")
    rom = bytearray([FILL] * BANK_SIZE)
    rom[: len(code)] = code
    return bytes(rom)


def build_banks(outdir: pathlib.Path):
    outdir.mkdir(parents=True, exist_ok=True)
    for rom_name, asm_name in BANK_FILES:
        rom = assemble_bank(HERE / asm_name)
        (outdir / rom_name).write_bytes(rom)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", type=pathlib.Path)
    args = ap.parse_args()
    build_banks(args.outdir)
    print(f"生成した: {args.outdir} (N88_0.ROM〜N88_3.ROM 各{BANK_SIZE}バイト)")


if __name__ == "__main__":
    main()
