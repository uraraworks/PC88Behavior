#!/usr/bin/env python3
"""東雲と既存 FONT.ROM 生成器から PC-88 漢字 ROM を生成する。"""
import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BDF_DIR = ROOT / 'fonts/shinonome-0.9.11/bdf'


def read_bdf(path, width):
    glyphs = {}
    encoding = None
    lines = iter(path.read_text(encoding='ascii').splitlines())
    for line in lines:
        if line.startswith('ENCODING '):
            encoding = int(line.split()[1])
        elif line.startswith('BBX '):
            if tuple(map(int, line.split()[1:])) != (width, 16, 0, -2):
                raise ValueError(f'{path}: 非対応の BBX: {line}')
        elif line == 'BITMAP':
            rows = [bytes.fromhex(next(lines)) for _ in range(16)]
            if any(len(row) != width // 8 for row in rows):
                raise ValueError(f'{path}: 不正なビットマップ')
            if encoding is not None and encoding >= 0:
                glyphs[encoding] = b''.join(rows)
    return glyphs


def jis_address(code):
    if code < 0x3000:
        return 0, ((code & 0x60) << 7) | ((code & 0x700) << 1) | ((code & 0x1f) << 4)
    if code < 0x5000:
        return 0, ((code & 0x60) << 9) | ((code & 0x1f00) << 1) | ((code & 0x1f) << 4)
    if code < 0x7000:
        return 1, ((code & 0x60) << 9) | ((code & 0xf00) << 1) | ((code & 0x1f) << 4) | (code & 0x2000)
    return 1, ((code & 0x60) << 7) | ((code & 0x700) << 1) | ((code & 0x1f) << 4)


def generate(out, unscii, misaki):
    spec = importlib.util.spec_from_file_location('l2_font', ROOT / 'src/l2_font/make_font_rom.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    font, _ = module.build_font_rom(unscii, misaki)
    roms = [bytearray(0x20000), bytearray(0x20000)]
    for code in range(256):
        if 0x20 <= code <= 0x7f or 0xa0 <= code <= 0xdf:
            continue
        start = ((code << 2) | 0x800) * 2
        roms[0][start:start + 8] = font[(0x800 if code >= 0x80 else 0) + code * 8:(0x800 if code >= 0x80 else 0) + code * 8 + 8]
    for code, glyph in read_bdf(BDF_DIR / 'shnm8x16r.bdf', 8).items():
        if 0x20 <= code <= 0x7f or 0xa0 <= code <= 0xdf:
            roms[0][code * 16:code * 16 + 16] = glyph
    for code, glyph in read_bdf(BDF_DIR / 'shnmk16.bdf', 16).items():
        if not (0x21 <= code >> 8 <= 0x7e and 0x21 <= (code & 0xff) <= 0x7e):
            continue
        bank, address = jis_address(code)
        roms[bank][address * 2:address * 2 + 32] = glyph
    out.mkdir(parents=True, exist_ok=True)
    for i, rom in enumerate(roms, 1):
        (out / f'KANJI{i}.ROM').write_bytes(rom)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'build')
    parser.add_argument('--unscii-hex', type=Path, default=ROOT.parent / 'vendor/unscii/unscii-8.hex')
    parser.add_argument('--misaki-bdf', type=Path, default=ROOT.parent / 'vendor/misaki/misaki_gothic.bdf')
    args = parser.parse_args()
    generate(args.output_dir, args.unscii_hex, args.misaki_bdf)


if __name__ == '__main__':
    main()
