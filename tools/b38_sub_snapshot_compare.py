#!/usr/bin/env python3
"""生のスナップショットを値を表示せずに比較する。"""
import pathlib
import sys

N = 16384
REGS = ('AF', 'BC', 'DE', 'HL', 'IX', 'IY', 'PC', 'SP',
        'AF1', 'BC1', 'DE1', 'HL1', 'I', 'R', 'IFF', 'IFF2', 'IM', 'HALT')
WRITERS = ('unwritten', 'rom-written', 'ram-written')


def read(path):
    data = pathlib.Path(path).read_bytes()
    if len(data) != 8 + 2 * N + 2 * len(REGS) or data[:8] != b'Q88SNAP1':
        raise ValueError()
    ram, writer, regs = data[8:8+N], data[8+N:8+2*N], data[8+2*N:]
    if any(x >= len(WRITERS) for x in writer):
        raise ValueError()
    return ram, writer, regs


def compare(a, b):
    ar, aw, ag = a
    br, bw, bg = b
    lines = ['# 識別子: G1']
    count = 0
    i = 0
    while i < N:
        if ar[i] == br[i]:
            i += 1
            continue
        start = i
        pair = aw[i], bw[i]
        while i < N and ar[i] != br[i] and (aw[i], bw[i]) == pair:
            i += 1
        count += i - start
        lines.append(f'D {start+0x4000:04X}-{i-1+0x4000:04X} {WRITERS[pair[0]]} {WRITERS[pair[1]]} {i-start}')
    for i, name in enumerate(REGS):
        lines.append(f'REG {name} {"same" if ag[2*i:2*i+2] == bg[2*i:2*i+2] else "differ"}')
    lines.append(f'total differ={count}')
    return lines


def main():
    try:
        if len(sys.argv) != 3:
            raise ValueError()
        lines = compare(read(sys.argv[1]), read(sys.argv[2]))
        print('\n'.join(lines))
    except (OSError, ValueError):
        print('スナップショットを比較できません', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
