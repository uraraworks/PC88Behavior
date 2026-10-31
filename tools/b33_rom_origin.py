#!/usr/bin/env python3
"""B33: 応答の区間を ROM と照合し、番地だけを記録する。"""
import argparse
import io
import re
import sys

from b32_differing_block import collect

PATTERNS = tuple(re.compile(p) for p in (
    r'length=[0-9]+',
    r'official-in-official-rom offset=(?:[0-9A-F]{4}|none)',
    r'self-in-self-rom offset=(?:[0-9A-F]{4}|none)',
    r'official-in-self-rom offset=(?:[0-9A-F]{4}|none)',
))


def checked(lines):
    return len(lines) == 8 and all(
        PATTERNS[i % 4].fullmatch(line) for i, line in enumerate(lines)
    )


def compare(a, b, official_rom, self_rom):
    left, _ = collect(a)
    right, _ = collect(b)
    count = min(len(left), len(right))
    k = next((i for i in range(count) if left[i] != right[i]), None)
    if k is None or k < 2:
        raise ValueError
    end = k
    while end < count and left[end] != right[end]:
        end += 1
    if end == count:
        raise ValueError
    official_rom, self_rom = official_rom[:0x800], self_rom[:0x800]
    if len(official_rom) != 0x800 or len(self_rom) != 0x800:
        raise ValueError

    def offset(rom, value):
        n = rom.find(value)
        return 'none' if n < 0 else f'{n:04X}'

    lines = []
    for start, stop in ((k, end), (k - 2, k)):
        x, y = left[start:stop], right[start:stop]
        lines.extend((f'length={stop-start}',
                      f'official-in-official-rom offset={offset(official_rom, x)}',
                      f'self-in-self-rom offset={offset(self_rom, y)}',
                      f'official-in-self-rom offset={offset(self_rom, x)}'))
    return lines


def selftest():
    def log(values):
        return io.StringIO('# main\n0 0 0 main IN 0010 ED C000\n' + ''.join(
            f'{i+1} {i+1} 0 main IN 00FC {v:02X} C001\n'
            for i, v in enumerate(values)) +
            '# 取りこぼし: 0件 / 総イベント数: 99件\n# sub\n')

    left = bytes([3, 4, 0xDE, 0xAD, 0xBE, 9])
    right = bytes([3, 4, 0xA1, 0xB2, 0xC3, 9])
    rom1 = bytearray([0x77] * 0x900)
    rom2 = bytearray([0x88] * 0x900)
    rom1[32:35] = left[2:5]
    rom2[32:35] = right[2:5]
    rom1[50:52] = rom2[50:52] = left[:2]
    result = compare(log(left), log(right), rom1, rom2)
    expected = ['length=3', 'official-in-official-rom offset=0020',
                'self-in-self-rom offset=0020', 'official-in-self-rom offset=none',
                'length=2', 'official-in-official-rom offset=0032',
                'self-in-self-rom offset=0032', 'official-in-self-rom offset=0032']
    assert checked(result) and result == expected
    assert all(marker not in '\n'.join(result) for marker in ('DEADBE', 'A1B2C3', 'ED'))
    rom2[32:35] = bytes([0x88] * 3)
    rom2[0x810:0x813] = right[2:5]
    assert compare(log(left), log(right), rom1, rom2)[2].endswith('none')
    rom1[32:35] = bytes([0x77] * 3)
    assert compare(log(left), log(right), rom1, rom2)[1].endswith('none')
    assert not checked(result + ['DEADBE'])
    assert not checked(result[:1] + ['official-in-official-rom offset=DEADBE'] + result[2:])
    for a, b in ((left, left), (left[:-1], right[:-1])):
        try:
            compare(log(a), log(b), rom1, rom2)
        except ValueError:
            pass
        else:
            raise AssertionError
    bad = log(left).getvalue().replace('0 0 0 main', '0 0 main', 1)
    try:
        compare(io.StringIO(bad), log(right), rom1, rom2)
    except ValueError:
        pass
    else:
        raise AssertionError
    faulty = result.copy()
    faulty[1] = 'official-in-official-rom offset=none'
    try:
        assert faulty == expected
    except AssertionError:
        pass
    else:
        raise AssertionError
    print('OK: B33 自己検査')


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError


def main():
    try:
        parser = SafeParser(add_help=False)
        parser.add_argument('--selftest', action='store_true')
        sub = parser.add_subparsers(dest='command', parser_class=SafeParser)
        c = sub.add_parser('compare', add_help=False)
        c.add_argument('official'); c.add_argument('self_log')
        c.add_argument('--official-rom', required=True); c.add_argument('--self-rom', required=True)
        c.add_argument('--id', required=True, choices=['G1']); c.add_argument('--out', required=True)
        args = parser.parse_args()
        if args.selftest and args.command is None:
            selftest()
            return 0
        if args.command != 'compare' or args.selftest:
            raise ValueError
        with open(args.official, encoding='utf-8', errors='replace') as a, \
             open(args.self_log, encoding='utf-8', errors='replace') as b, \
             open(args.official_rom, 'rb') as r1, open(args.self_rom, 'rb') as r2:
            lines = compare(a, b, r1.read(0x800), r2.read(0x800))
        if not checked(lines):
            raise ValueError
        with open(args.out, 'w', encoding='utf-8') as output:
            output.write('\n'.join(lines) + '\n')
        return 0
    except Exception:
        print('エラー', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
