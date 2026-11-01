#!/usr/bin/env python3
"""B52d の読み返しを値を出さず配置記号に変換する。"""
import argparse
import csv
import json
import re
import sys

from analyze_b52 import LENGTHS
from analyze_m6ia_main_sub import MEM_RE

FIELDS = ('row', 'run', 'complete', 'timeout', 'count', 'layout', 'before', 'after', 'executed')
BASE = [(i * 7 + 13) & 255 for i in range(64)]
PATTERN = [v for v in range(256) if v not in BASE][:16]
CODE = [0x3e, 0x5a, 0x32, 0x3f, 0x78, 0xc3, 0xc1, 0]


def analyze(row, run, lines, pc_range=(0, 0x10000)):
    if row not in range(1, 9) or run not in (1, 2):
        raise ValueError('row or run')
    data, state = [], {}
    seq, drops = 0, None
    active = receiving = False
    for line in lines:
        m = MEM_RE.match(line)
        if m:
            n, _, pc, addr, value = m.groups()
            seq += 1
            if int(n) != seq:
                raise ValueError('sequence')
            if not pc_range[0] <= int(pc, 16) < pc_range[1]:
                continue
            a, v = int(addr, 16), int(value, 16)
            if a == 0xde04 and v == 0x5a:
                active = True
            if not active:
                continue
            if a in (0xde00, 0xde01):
                state[a] = v
            elif a == 0xde03 and v == 0xa5:
                receiving = True
            elif receiving and 0xe000 <= a < 0xe040:
                if a != 0xe000 + len(data):
                    raise ValueError('address')
                data.append(v)
        m = re.search(r'取りこぼし:\s*(\d+)件', line)
        if m:
            drops = int(m[1])
    if drops != 0:
        raise ValueError('drops')
    length = LENGTHS[row - 1]
    start = 0x20 if row == 4 else 0x11 if row == 8 else 0x10
    payload = CODE if row == 7 else PATTERN[:length]
    layout = []
    for i in range(start, min(start + length, len(data))):
        v = data[i]
        if v in payload:
            layout.append(f'p{payload.index(v)}')
        elif v == BASE[i]:
            layout.append('b')
        else:
            layout.append('?')
    before = sum(data[i] != BASE[i] for i in range(min(start, len(data))))
    after = sum(data[i] != BASE[i] for i in range(start + length, len(data))
                if not (row == 7 and i == 63))
    executed = '-' if row != 7 or len(data) < 64 else str(int(data[63] == 0x5a))
    return [str(row), str(run), str(int(state.get(0xde01) == 1)),
            str(state.get(0xde00, '-')), str(len(data)), ' '.join(layout),
            str(before), str(after), executed]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--row', type=int, choices=range(1, 9), required=True)
    p.add_argument('--run', type=int, choices=(1, 2), required=True)
    p.add_argument('--memlog', required=True)
    p.add_argument('--labels', required=True)
    a = p.parse_args()
    try:
        with open(a.labels) as f:
            labels = json.load(f)['labels']
        with open(a.memlog) as f:
            result = analyze(a.row, a.run, f, (labels['_b52_begin'], labels['_b52_end']))
        w = csv.writer(sys.stdout, delimiter='\t', lineterminator='\n')
        w.writerow(FIELDS)
        w.writerow(result)
    except (ValueError, OSError, KeyError):
        print('解析失敗', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
