#!/usr/bin/env python3
"""I/O 列を値を公開せずに比較する。番号は 0 始まり。"""
import argparse
from pathlib import Path
import sys

from b13_sub_fdc import read_events
from b8_io_values import parse_log

START = 76570
SIZE = 132


def read(path):
    events = read_events(path)
    ports = {}
    for pos, (kind, port, value, pc) in enumerate(events):
        if kind == 'OUT':
            ports.setdefault(port, []).append((value, pc, pos))
    with path.open(encoding='utf-8', errors='replace') as f:
        main = parse_log(f)[('IN', '00FC', 'raw')]
    return ports, bytes(item[0][0] for item in main)


def compare(a, b):
    rows = []
    firsts = []
    for port in sorted(a[0].keys() | b[0].keys()):
        left, right = a[0].get(port, []), b[0].get(port, [])
        count = min(len(left), len(right))
        diff = [i for i in range(count) if left[i][0] != right[i][0]]
        first = str(diff[0]) if diff else 'none'
        rows.append(f'port OUT {port:04X} compared={count} differ={len(diff)} first={first} left={len(left)-count} right={len(right)-count}')
        if diff:
            i = diff[0]
            firsts.append((right[i][2], port, i, left[i][1], right[i][1]))
    if firsts:
        _, port, i, lp, rp = min(firsts)
        region = lambda pc: 'hi' if pc >= 0x2000 else 'lo'
        address = lambda pc: f'{pc:04X}' if pc >= 0x2000 else 'lo'
        rows.append(f'first-out-difference: {port:04X} {i} {region(lp)} {region(rp)} {address(lp)} {address(rp)}')
    else:
        rows.append('first-out-difference: none')
    for name, own, other in (('左', a[1], b[1]), ('右', b[1], a[1])):
        block = own[START:START + SIZE]
        for label, haystack in (('self-match', own), ('other-match', other)):
            index = -1
            if len(block) == SIZE:
                index = haystack.find(block)
                if label == 'self-match' and index >= START:
                    index = -1
            rows.append(f'block {name} {label} {index if index >= 0 else "none"}')
    return rows


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('arguments')


def main():
    try:
        parser = Parser()
        parser.add_argument('left', type=Path)
        parser.add_argument('right', type=Path)
        args = parser.parse_args()
        print('\n'.join(compare(read(args.left), read(args.right))))
        return 0
    except Exception:
        print('解析失敗', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
