#!/usr/bin/env python3
"""共通 clock 上の受信位置だけを集計する。番号は 0 始まり。"""
import argparse
from bisect import bisect_left
from collections import Counter
from pathlib import Path
import sys

from b47_pio_handoff import read


def positions(data):
    fc, fd = data
    if len(fc) <= 76827:
        raise ValueError()
    clocks = [event[0] for event in fd]
    return [bisect_left(clocks, event[0]) for event in fc]


def issuer(event):
    pc = event[4]
    return f'{pc:04X}' if pc >= 0x8000 else 'rom'


def summarize(official, selfmade):
    arms = (official, selfmade)
    ks = [positions(data) for data in arms]
    rows = []
    for i in [76300, *range(76560, 76581), 76826, 76827]:
        rows.append(f'at {i} ok={ks[0][i]} sk={ks[1][i]} '
                    f'ok-issuer={issuer(official[0][i])} sk-issuer={issuer(selfmade[0][i])}')
    previous = None
    changes = 0
    for i, (a, b) in enumerate(zip(*ks)):
        difference = a - b
        if difference != previous:
            if changes < 64:
                rows.append(f'offset-change {i} {difference}')
            elif changes == 64:
                rows.append('offset-change more')
            changes += 1
            previous = difference
    for arm, data, k in zip(('OO', 'SS'), arms, ks):
        for name, lo, hi in (('all', 0, len(k) - 1), ('76315-76827', 76315, 76827)):
            counts = Counter(k[i + 1] - k[i] for i in range(lo, hi))
            other = sum(n for step, n in counts.items() if step not in (0, 1, 2))
            rows.append(f'step arm={arm} range={name} 0={counts[0]} 1={counts[1]} 2={counts[2]} other={other}')
        rom = sum(event[4] < 0x8000 for event in data[0][76570:76828])
        rows.append(f'issuer arm={arm} range=76570-76827 rom={rom} ram={258 - rom}')
    return rows


def main():
    try:
        class Parser(argparse.ArgumentParser):
            def error(self, message):
                raise ValueError()
        parser = Parser(add_help=False)
        parser.add_argument('official', type=Path)
        parser.add_argument('selfmade', type=Path)
        args = parser.parse_args()
        print('\n'.join(summarize(read(args.official), read(args.selfmade))))
        return 0
    except Exception:
        return 1


if __name__ == '__main__':
    sys.exit(main())
