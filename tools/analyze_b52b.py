#!/usr/bin/env python3
"""B52 の読み返しから要求範囲の配置記号だけを出力する。"""
import argparse
import csv
import json
import re
import sys

from analyze_b52 import LENGTHS
from analyze_m6ia_main_sub import MEM_RE

FIELDS = ('row', 'run', 'layout')


def analyze(row, run, lines, pc_range=(0, 0xffff)):
    if row not in range(1, 6) or run not in (1, 2):
        raise ValueError('row or run')
    data = []
    seq = 0
    drops = None
    active = receiving = complete = False
    timeout = False
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
            if a == 0xde00:
                timeout = v != 0
            if a == 0xde03 and v == 0xa5:
                receiving = True
            elif receiving and 0xe000 <= a < 0xe040:
                if a != 0xe000 + len(data):
                    raise ValueError('address')
                data.append(v)
            elif a == 0xde01 and v == 1:
                complete = True
        m = re.search(r'取りこぼし:\s*(\d+)件', line)
        if m:
            drops = int(m[1])
    if drops != 0 or timeout or not complete or len(data) != 64:
        raise ValueError('incomplete')
    length = LENGTHS[row - 1]
    start = 0x20 if row == 4 else 0x10
    payload = [0xa0 + i for i in range(length)]
    layout = []
    for i in range(start, start + length):
        value = data[i]
        # 両方に一致する位置は送信模様を優先する。
        if value in payload:
            layout.append(f'p{payload.index(value)}')
        elif value == (i * 7 + 13) & 255:
            layout.append('b')
        else:
            layout.append('?')
    return [str(row), str(run), ' '.join(layout)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--row', type=int, choices=range(1, 6), required=True)
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
