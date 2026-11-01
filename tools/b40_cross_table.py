#!/usr/bin/env python3
"""B39 の記録を順に読み、値を伏せた移行表を作る。"""
import pathlib
import re
import sys

NAMES = ('A', 'F', 'B', 'C', 'D', 'E', 'H', 'L', 'IX', 'IY', 'SP',
         "A'F'", "B'C'", "D'E'", "H'L'", 'I', 'IFF', 'IFF2', 'IM', 'HALT')


def read(path):
    crosses = []
    fc = 0
    with pathlib.Path(path).open(encoding='ascii') as f:
        if f.readline() != 'Q88REG1\n':
            raise ValueError('不正な記録')
        for line in f:
            if line == 'END\n':
                if f.read(1):
                    raise ValueError('不正な記録')
                return crosses
            p = line.split()
            if len(p) == 19 and p[0] in ('C', 'F') and all(re.fullmatch(r'[0-9A-F]{4}', x) for x in p[1:]):
                row = tuple(int(x, 16) for x in p[1:])
                if p[0] == 'F':
                    fc += 1
                else:
                    if row[6] < 0x2000:
                        raise ValueError('不正な記録')
                    regs = tuple(v for x in row[:4] for v in (x >> 8, x & 255)) + row[4:6] + row[7:12] + (row[12],) + row[14:18]
                    crosses.append((row[6], fc, regs))
            elif not (len(p) == 3 and p[0] == 'O' and p[1] in ('R', 'I') and re.fullmatch(r'[0-9A-F]{4}', p[2]) and int(p[2], 16) >= 0x2000):
                raise ValueError('不正な記録')
    raise ValueError('不完全な記録')


def compare(a, b):
    lines = ['# 識別子: G1', f'count {len(a)} {len(b)}']
    for i in range(max(len(a), len(b))):
        if i >= len(b):
            pc, fc, _ = a[i]
            lines.append(f'LEFT {i} {pc:04X} {fc}')
        elif i >= len(a):
            pc, fc, _ = b[i]
            lines.append(f'RIGHT {i} {pc:04X} {fc}')
        else:
            pc1, fc1, r1 = a[i]
            pc2, fc2, r2 = b[i]
            names = ','.join(n for n, x, y in zip(NAMES, r1, r2) if x != y) or 'none'
            lines.append(f'C {i} {pc1:04X} {pc2:04X} {fc1} {fc2} {names}')
    return lines


def main():
    try:
        if len(sys.argv) != 3:
            raise ValueError('引数が不正')
        lines = compare(read(sys.argv[1]), read(sys.argv[2]))
        print('\n'.join(lines))
        return 0
    except Exception:
        print('比較できません', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
