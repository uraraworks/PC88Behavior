#!/usr/bin/env python3
"""固定長の出来事列を値を公開せず比較する。番号は 0 始まり。"""
import argparse
from collections import deque
from itertools import zip_longest
from pathlib import Path
import struct
import sys

RECORD = struct.Struct('<cHHBQ')
MAGIC = b'Q88EVT1\n'


def records(path):
    with Path(path).open('rb') as f:
        if f.read(len(MAGIC)) != MAGIC:
            raise ValueError('invalid record')
        while True:
            data = f.read(RECORD.size)
            if not data:
                return
            if len(data) != RECORD.size:
                raise ValueError('invalid record')
            kind, pc, addr, value, fc = RECORD.unpack(data)
            if kind not in (b'R', b'W', b'I', b'O'):
                raise ValueError('invalid record')
            yield kind.decode('ascii'), pc, addr, value, fc


def compare(left, right):
    previous = deque(maxlen=16)
    counts = [0, 0]
    first = None
    for index, (a, b) in enumerate(zip_longest(records(left), records(right))):
        counts[0] += a is not None
        counts[1] += b is not None
        if first is None:
            fields = [name for i, name in enumerate(('kind', 'pc', 'addr', 'value'))
                      if a is None or b is None or a[i] != b[i]]
            if fields:
                def show(row, i):
                    if row is None:
                        return '-'
                    if i in (1, 2):
                        return f'{row[i]:04X}'
                    return str(row[i])
                first = (index, fields, a, b, list(previous))
            elif a is not None:
                previous.append((index, a[0], a[1], a[2]))
    rows = [f'count {counts[0]} {counts[1]}']
    if first is None:
        rows.append('first-diff none')
    else:
        index, fields, a, b, history = first
        def fmt(row, i):
            if row is None:
                return '-'
            return f'{row[i]:04X}' if i in (1, 2) else str(row[i])
        rows.append(f"first-diff {index} {','.join(fields)} " +
                    ' '.join(fmt(row, i) for i in (0, 1, 2, 4) for row in (a, b)))
        rows.extend(f'before {n} {kind} {pc:04X} {addr:04X}' for n, kind, pc, addr in history)
    return rows


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('arguments')


def main():
    try:
        parser = Parser()
        parser.add_argument('left')
        parser.add_argument('right')
        args = parser.parse_args()
        print('\n'.join(compare(args.left, args.right)))
        return 0
    except Exception:
        print('解析失敗', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
