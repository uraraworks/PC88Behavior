#!/usr/bin/env python3
"""生成器と独立した番地・BDF の検査、および陰性対照。"""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / 'tools/make_kanji_rom.py'
BDF = ROOT / 'fonts/shinonome-0.9.11/bdf'


def glyph(path, code):
    text = path.read_text(encoding='ascii')
    for block in text.split('STARTCHAR ')[1:]:
        lines = block.splitlines()
        if f'ENCODING {code}' in lines:
            start = lines.index('BITMAP') + 1
            return bytes.fromhex(''.join(lines[start:start + 16]))
    raise AssertionError(f'字形なし: {code:x}')


def verify(directory):
    rom1 = (directory / 'KANJI1.ROM').read_bytes()
    rom2 = (directory / 'KANJI2.ROM').read_bytes()
    assert len(rom1) == len(rom2) == 131072
    # 独立に固定した JIS とワードアドレス。第2水準も検査する。
    for code, address, rom in [(0x3021, 0x6010, rom1), (0x3441, 0xa810, rom1),
                               (0x3b7a, 0xf7a0, rom1), (0x5021, 0x4010, rom2)]:
        assert rom[address * 2:address * 2 + 32] == glyph(BDF / 'shnmk16.bdf', code), hex(code)
    assert rom1[0x41 * 16:0x42 * 16] == glyph(BDF / 'shnm8x16r.bdf', 0x41)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        a, b, bad = (Path(tmp) / x for x in ('a', 'b', 'bad'))
        for target in (a, b):
            subprocess.run([sys.executable, str(GEN), '--output-dir', str(target)], check=True)
        verify(a)
        for name in ('KANJI1.ROM', 'KANJI2.ROM'):
            assert (a / name).read_bytes() == (b / name).read_bytes()
        spec = importlib.util.spec_from_file_location('generator', GEN)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        original = mod.jis_address
        mod.jis_address = lambda code: (lambda p: (p[0], (p[1] + 16) & 0xffff))(original(code))
        mod.generate(bad, ROOT.parent / 'vendor/unscii/unscii-8.hex', ROOT.parent / 'vendor/misaki/misaki_gothic.bdf')
        try:
            verify(bad)
        except AssertionError:
            pass
        else:
            raise AssertionError('陰性対照を検出できなかった')
    print('自己検査成功（陰性対照は期待どおり失敗）')


if __name__ == '__main__':
    main()
