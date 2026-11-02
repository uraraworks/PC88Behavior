#!/usr/bin/env python3
"""B68 の事前登録にある項目だけを出す。"""
import argparse
import json
from pathlib import Path
import re
import sys

from analyze_b12 import CMDS
from b13_sub_fdc import DROP, ROW, read_events
from b38_sub_snapshot_compare import read


def main_events(path):
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    if lines.count('# main') != 1:
        raise ValueError('main')
    events = []
    for line in lines[lines.index('# main') + 1:]:
        m = DROP.fullmatch(line)
        if m:
            if int(m[1]) or int(m[2]) != len(events):
                raise ValueError('drop')
            return events
        if not line or line.startswith('#'):
            continue
        fields = line.split()
        if len(fields) != 8 or fields[3] != 'main' or int(fields[0]) != len(events) + 1:
            raise ValueError('event')
        events.append((fields[4], int(fields[5], 16), int(fields[6], 16), int(fields[7], 16)))
    raise ValueError('end')


def fc_info(log, labels):
    labels = json.loads(Path(labels).read_text())['labels']
    fc = [pc for kind, port, _, pc in main_events(log) if kind == 'IN' and port == 0xfc]
    first = labels['_b68_first_fc']
    positions = [i for i, pc in enumerate(fc) if pc == first]
    if len(positions) > 1:
        raise ValueError('snapshot marker')
    if positions:
        i = positions[0]
        if i != len(fc) - 2 or i > 2:
            raise ValueError('reply')
        # コアの指定値は最初の IN $FC を 0 とする。
        return i, i, len(fc)
    reply_pcs = {labels[k] for k in ('_b68_reply_first', '_b68_reply_second') if k in labels}
    n = sum(pc in reply_pcs for pc in fc)
    if n > 2:
        raise ValueError('reply')
    return n, -1, len(fc)


def reply_count(log, labels):
    return fc_info(log, labels)[0]


def fdc(events):
    writes = [value for kind, port, value, _ in events if kind == 'OUT' and port == 0xfb]
    commands = []
    i = 0
    while i < len(writes):
        if writes[i] & 31 not in CMDS:
            raise ValueError('unknown FDC command')
        name, length = CMDS[writes[i] & 31]
        if i + length > len(writes):
            raise ValueError('incomplete FDC command')
        args = ','.join(str(v) for v in writes[i+1:i+length])
        commands.append(f'{name}({args})')
        i += length
    return ';'.join(commands)


def ram_lines(control, subject, row):
    a, b = read(control)[0], read(subject)[0]
    stamps = {}
    for i in range(len(b)-3):
        if b[i] == 0xa1 and b[i+1] < 40 and b[i+2] < 2 and 1 <= b[i+3] <= 16:
            for offset in range(4):
                stamps[i+offset] = (b[i+1], b[i+2], b[i+3], offset)
    i = 0
    while i < len(b):
        if a[i] == b[i]:
            i += 1
            continue
        start = i
        stamp = stamps.get(i)
        i += 1
        while i < len(b) and a[i] != b[i]:
            next_stamp = stamps.get(i)
            if stamp is None:
                if next_stamp is not None:
                    break
            elif next_stamp != (stamp[0], stamp[1], stamp[2], stamp[3] + i - start):
                break
            i += 1
        desc = '?' if stamp is None else f'{stamp[0]}/{stamp[1]}/{stamp[2]}+{stamp[3]}'
        yield f'row {row} ram {start+0x4000:04X}-{i+0x3fff:04X} {desc}'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('row', type=int, choices=range(1, 9))
    p.add_argument('log', type=Path)
    p.add_argument('control', type=Path)
    p.add_argument('snapshot', type=Path)
    p.add_argument('labels', type=Path)
    p.add_argument('--count-only', action='store_true')
    p.add_argument('--fc-info', action='store_true')
    try:
        a = p.parse_args()
        n, target, total = fc_info(a.log, a.labels)
        if a.fc_info:
            print(target, total)
            return 0
        if a.count_only:
            print(n)
            return 0
        if target < 0:
            print(f'row {a.row} reply={n} timeout=1')
            return 0
        commands = fdc(read_events(a.log))
        lines = [f'row {a.row} fdc={commands}', f'row {a.row} reply={n} timeout={int(a.row != 8 and n < 2)}']
        lines.extend(ram_lines(a.control, a.snapshot, a.row))
        print('\n'.join(lines))
        return 0
    except (OSError, UnicodeError, ValueError, KeyError, IndexError, json.JSONDecodeError):
        print('B68 解析失敗', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
