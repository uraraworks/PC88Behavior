#!/usr/bin/env python3
"""B72 のメモリ記録から許可された集計だけを出す。"""
import argparse
import json
import re
import sys
from analyze_m6ia_main_sub import MEM_RE
from make_l3_testdisk import coord_header_pattern


def analyze(row, lines, pc_range):
    length = (2, 128, 2, 2)[row - 1]
    data = []
    state = {}
    active = receiving = False
    sequence = 0
    drops = None
    for line in lines:
        m = MEM_RE.match(line)
        if m:
            n, _, pc, addr, value = m.groups()
            sequence += 1
            if int(n) != sequence:
                raise ValueError('sequence')
            pc, addr, value = int(pc, 16), int(addr, 16), int(value, 16)
            if not pc_range[0] <= pc < pc_range[1]:
                continue
            if addr == 0xde04 and value == 0x5a:
                active = True
            if not active:
                continue
            if addr in (0xde00, 0xde01):
                state[addr] = value
            elif addr == 0xde03 and value == 0xa5:
                receiving = True
            elif receiving and 0xe000 <= addr < 0xe000 + length:
                if addr != 0xe000 + len(data):
                    raise ValueError('address')
                data.append(value)
        m = re.search(r'取りこぼし:\s*(\d+)件', line)
        if m:
            drops = int(m[1])
    if drops != 0 or state.get(0xde01) != 1 or state.get(0xde00) not in (0, 1):
        raise ValueError('incomplete')
    expected = (coord_header_pattern(0xa1, 1, 0, 3) if row == 1 else
                coord_header_pattern(0xa1, 1, 0, 1) if row == 2 else
                bytes((0xff, 0x5a)) if row == 3 else bytes((0xff, 0xff)))
    match = 0
    for actual, want in zip(data, expected):
        if actual != want:
            break
        match += 1
    executed = str(int(len(data) >= 2 and data[1] == 0x5a)) if row == 3 else '-'
    return f'reply={len(data)} match={match} timeout={state[0xde00]} executed={executed}'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--row', type=int, choices=range(1, 5), required=True)
    p.add_argument('--arm', choices=('O', 'S'), required=True)
    p.add_argument('--memlog', required=True)
    p.add_argument('--labels', required=True)
    a = p.parse_args()
    try:
        with open(a.labels) as f:
            labels = json.load(f)['labels']
        with open(a.memlog) as f:
            result = analyze(a.row, f, (labels['_b72_begin'], labels['_b72_end']))
        print(f'row {a.row} {a.arm} {result}')
    except (ValueError, OSError, KeyError, IndexError):
        print('B72 解析失敗', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
