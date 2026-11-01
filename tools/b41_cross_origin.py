#!/usr/bin/env python3
"""移行元を腕ごとの番号に置き換えて出力する。"""
import pathlib
import re
import sys

HEX = re.compile(r'[0-9A-F]{4}\Z')


def read(path):
    crosses = []
    pending = None
    with pathlib.Path(path).open(encoding='ascii') as f:
        if f.readline() != 'Q88REG1\n':
            raise ValueError('記録形式')
        for line in f:
            if line == 'END\n':
                if pending is not None or f.read(1):
                    raise ValueError('記録形式')
                return crosses
            p = line.split()
            if pending is not None:
                if len(p) != 3 or p[0] != 'X' or not all(HEX.fullmatch(x) for x in p[1:]):
                    raise ValueError('記録形式')
                origin, sp = (int(x, 16) for x in p[1:])
                crosses.append((pending, origin, sp))
                pending = None
            elif len(p) == 19 and p[0] in ('C', 'F') and all(HEX.fullmatch(x) for x in p[1:]):
                row = tuple(int(x, 16) for x in p[1:])
                if p[0] == 'C':
                    if row[6] < 0x2000:
                        raise ValueError('記録形式')
                    pending = row
            elif len(p) == 3 and p[0] == 'O' and p[1] in ('R', 'I') and HEX.fullmatch(p[2]) and int(p[2], 16) >= 0x2000:
                pass
            else:
                raise ValueError('記録形式')
    raise ValueError('記録形式')


def render(arm, crosses):
    origins = {}
    lines = []
    for i, (r, pc, sp) in enumerate(crosses):
        if pc not in origins:
            origins[pc] = len(origins) + 1
        delta = (r[7] - sp + 32768) % 65536 - 32768
        delta = str(delta) if -4 <= delta <= 4 else 'other'
        yes = lambda x: 'yes' if x else 'no'
        lines.append(f'O {arm} {i} {r[6]:04X} {origins[pc]} {delta} {yes(r[2] == 0)} {yes(r[2] == r[3])} {yes(r[2] == r[1])}')
    return lines


def main():
    try:
        if len(sys.argv) != 3:
            raise ValueError('引数')
        lines = ['# 識別子: G1'] + render('OO', read(sys.argv[1])) + render('SS', read(sys.argv[2]))
        print('\n'.join(lines))
        return 0
    except Exception:
        print('変換できません', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
