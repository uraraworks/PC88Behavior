#!/usr/bin/env python3
"""自作バンクの試験入口と、アセンブラ出力範囲外のFILLを検査する。"""
import json
from pathlib import Path
import sys


def check_bank(data: bytes, ranges: list, bank: int) -> None:
    if len(data) != 0x2000:
        raise ValueError("サイズが8192でない")
    if data[:3] != bytes([0x3E, 0xB0 + bank, 0xC9]):
        raise ValueError("先頭3Bの試験入口が想定と違う")
    covered = bytearray(len(data))
    previous = 0x6000
    for start, end in ranges:
        if not 0x6000 <= previous <= start < end <= 0x8000:
            raise ValueError("出力範囲が不正・重複・順序違反")
        covered[start - 0x6000:end - 0x6000] = b'\x01' * (end - start)
        previous = end
    if not all(covered[:3]):
        raise ValueError("試験入口が出力範囲に含まれない")
    if any(value and not used for value, used in zip(data, covered)):
        raise ValueError("アセンブラ出力範囲外にFILL(0x00)以外のバイトがある")


def main() -> int:
    outdir = Path(sys.argv[1])
    for bank in range(4):
        path = outdir / f'N88_{bank}.ROM'
        try:
            check_bank(path.read_bytes(), json.loads(
                (outdir / 'ext_bank_layout' / f'{path.name}.json').read_text(
                    encoding='utf-8')), bank)
        except (OSError, ValueError, TypeError) as exc:
            print(f'NG: {path.name}: {exc}')
            return 1
    print('OK: バンク4本のサイズ・先頭試験入口・全出力範囲外のFILL')
    return 0


if __name__ == '__main__':
    sys.exit(main())
