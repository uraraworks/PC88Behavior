#!/usr/bin/env python3
"""本文の各256バイト先頭の刻印と余分のバイトだけを記録する。"""
import argparse
import csv
import io
import json
import re
import sys
from analyze_m6ia_main_sub import MEM_RE
from judge_b26 import FIELDS, LENGTHS, PHASES, load

BASE = {1: 0xe000, 2: 0xef10, 3: 0xef20}

def analyze(row, run, lines, pc_range=(0, 0x10000)):
    data = {p: [] for p in PHASES[row-1]}
    timeouts = {p: '-' for p in data}
    state = {}; seq = 0; drops = None; active = False; finished = False; phase = None
    for line in lines:
        m = MEM_RE.match(line)
        if m:
            n, _, pc, addr, value = m.groups(); seq += 1
            if int(n) != seq: raise ValueError('sequence')
            a, v = int(addr, 16), int(value, 16)
            if not pc_range[0] <= int(pc, 16) < pc_range[1] or finished: continue
            if a == 0xde04 and v == 0x5a: active = True
            if not active: continue
            if a in (0xde00, 0xde01):
                state[a] = v
                if a == 0xde01 and v == 1: finished = True
            elif a == 0xde03:
                if v not in data or timeouts[v] != '-': raise ValueError('phase')
                phase = v; timeouts[v] = '0'
            elif a == 0xde05:
                if v != phase: raise ValueError('timeout')
                timeouts[v] = '1'
            elif phase is not None and BASE[phase] <= a < BASE[phase] + (LENGTHS[row-1] if phase == 1 else 0) + 4:
                if a != BASE[phase] + len(data[phase]): raise ValueError('address')
                data[phase].append(v)
        m = re.search(r'取りこぼし:\s*(\d+)件', line)
        if m: drops = int(m[1])
    if drops != 0: raise ValueError('drops')
    body = data.get(1, [])[:LENGTHS[row-1]]
    stamps = []
    for start in range(0, len(body), 256):
        block = body[start:start+4]
        stamps.append(','.join(map(str, block[1:])) if len(block) == 4 and block[0] == 0xa1 else 'other')
    extras = []
    for p in PHASES[row-1]:
        values = data[p][LENGTHS[row-1] if p == 1 else 0:]
        extras.append(';'.join(f'{v:02X}' for v in values) or '-')
    return [str(row), str(run), str(int(state.get(0xde01) == 1)), str(state.get(0xde00, '-')), str(len(body)), ';'.join(stamps) or '-', '|'.join(str(0 if x == '-' else len(x.split(';'))) for x in extras), '|'.join(extras), '|'.join(timeouts[p] for p in PHASES[row-1])]

def main():
    p = argparse.ArgumentParser(); p.add_argument('--row', type=int, choices=range(1, 8), required=True); p.add_argument('--run', type=int, choices=(1, 2), required=True); p.add_argument('--memlog', required=True); p.add_argument('--labels', required=True); a = p.parse_args()
    try:
        with open(a.labels, encoding='utf-8') as f: labels = json.load(f)['labels']
        with open(a.memlog, encoding='utf-8') as f: values = analyze(a.row, a.run, f, (labels['_b26_begin'], labels['_b26_end']))
        out = io.StringIO(newline=''); w = csv.writer(out, delimiter='\t', lineterminator='\n'); w.writerow(FIELDS); w.writerow(values); load([io.StringIO(out.getvalue())]); sys.stdout.write(out.getvalue())
    except (ValueError, OSError, IndexError, KeyError): print('解析失敗', file=sys.stderr); return 2
    return 0
if __name__ == '__main__': sys.exit(main())
