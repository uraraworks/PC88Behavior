#!/usr/bin/env python3
"""サブの I/O 記録から事前登録済みの項目だけを出力する。"""
import argparse
from collections import Counter
from pathlib import Path
import re
import sys

from analyze_b12 import CMDS

NAMES = '|'.join(sorted({v[0] for v in CMDS.values()} | {'unknown'}))
DATA = {'read_track', 'write_data', 'read_data', 'write_deleted_data',
        'read_deleted_data', 'scan_equal', 'scan_low_or_equal', 'scan_high_or_equal'}
NUM = r'(?:0|[1-9][0-9]*)'
BYTE = r'(?:0|[1-9][0-9]?|1[0-9]{2}|2[0-4][0-9]|25[0-5])'
FDC = rf'fdc {NUM} (?:{NAMES}) (?:lo|hi) (?:- - - - -|{BYTE} {BYTE} {BYTE} {BYTE} {BYTE})'
COUNT = rf'count (?:{NAMES}) (?:lo|hi) {NUM}'
PORT = rf'port (?:IN|OUT) [0-9A-F]{{4}} (?:lo|hi) {NUM}'
ROW = re.compile(r'\s*(\d+)\s+(\d+)\s+(\d+)\s+sub\s+(IN|OUT)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{4})\s*')
DROP = re.compile(r'# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件')


def read_events(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    sections = [i for i, line in enumerate(lines) if line == '# sub']
    if len(sections) != 1:
        raise ValueError('section')
    # main 側も欠落していれば記録全体の完全性を保証できない。
    drops = [DROP.fullmatch(line) for line in lines if line.startswith('# 取りこぼし:')]
    if len(drops) != 2 or any(not m or int(m[1]) for m in drops):
        raise ValueError('drops')
    events = []
    done = False
    for line in lines[sections[0] + 1:]:
        if DROP.fullmatch(line):
            if int(DROP.fullmatch(line)[2]) != len(events):
                raise ValueError('count')
            done = True
            break
        if not line or line.startswith('#'):
            continue
        m = ROW.fullmatch(line)
        if not m or int(m[1]) != len(events) + 1:
            raise ValueError('row')
        events.append((m[4], int(m[5], 16), int(m[6], 16), int(m[7], 16)))
    if not done:
        raise ValueError('end')
    return events


def summarize(events):
    ports = Counter((kind, f'{port:04X}', 'lo' if pc < 0x2000 else 'hi')
                    for kind, port, value, pc in events)
    writes = [(value, pc) for kind, port, value, pc in events if kind == 'OUT' and port == 0xFB]
    counts = Counter()
    rows = []
    i = 0
    number = 0
    while i < len(writes):
        value, pc = writes[i]
        name, length = CMDS.get(value & 31, ('unknown', 1))
        if i + length > len(writes):
            raise ValueError('incomplete')
        region = 'lo' if pc < 0x2000 else 'hi'
        counts[name, region] += 1
        number += 1
        args = [writes[i + j][0] for j in (2, 3, 4, 5, 6)] if name in DATA else ['-'] * 5
        if number <= 400:
            rows.append(f"fdc {number} {name} {region} {' '.join(map(str, args))}")
        i += length
    rows += [f'count {name} {region} {n}' for (name, region), n in sorted(counts.items())]
    rows += [f'port {kind} {port} {region} {n}' for (kind, port, region), n in sorted(ports.items())]
    return rows


def validate(rows, comparison=False):
    patterns = [FDC, COUNT, PORT]
    if comparison:
        patterns = [rf'first-difference: (?:none|{NUM})', FDC, r'(?:A|B): (?:missing|' + FDC + ')']
    if any(not any(re.fullmatch(p, row) for p in patterns) for row in rows):
        raise ValueError('whitelist')


def load_summary(path):
    rows = path.read_text(encoding='utf-8').splitlines()
    validate(rows)
    fdc = [r for r in rows if r.startswith('fdc ')]
    if len(fdc) > 400 or any(int(row.split()[1]) != i for i, row in enumerate(fdc, 1)):
        raise ValueError('sequence')
    return fdc


def compare(a, b):
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else 'missing'
        y = b[i] if i < len(b) else 'missing'
        if x != y:
            return [f'first-difference: {i + 1}', f'A: {x}', f'B: {y}']
    return ['first-difference: none']


def selftest():
    import tempfile
    from unittest.mock import patch
    events = []
    for opcode, (name, length) in CMDS.items():
        events.extend(('OUT', 0xFB, value, 0x1FFF if j == 0 else 0x2000)
                      for j, value in enumerate([opcode] + list(range(1, length))))
    rows = summarize(events)
    for i, (opcode, (name, length)) in enumerate(CMDS.items()):
        assert rows[i] == f"fdc {i+1} {name} lo " + ('2 3 4 5 6' if name in DATA else '- - - - -')
    rows = summarize([('OUT', 0xFB, 8, 0x1FFF)] + [('OUT', 0xFB, 8, 0x2000)] * 400 + [('IN', 0x1234, 0xAB, 0xCDEF)])
    validate(rows)
    assert len([r for r in rows if r.startswith('fdc ')]) == 400
    assert 'count sense_interrupt hi 400' in rows and 'count sense_interrupt lo 1' in rows
    assert 'port IN 1234 hi 1' in rows and not any('AB' in r or 'CDEF' in r for r in rows)
    try:
        validate(rows + ['fdc 1 secret AB CDEF'])
        raise AssertionError('whitelist')
    except ValueError:
        pass
    assert compare(['fdc 1 sense_interrupt lo - - - - -'], [])[-1] == 'B: missing'
    assert compare([], []) == ['first-difference: none']
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'log'
        base = '# main\n# 取りこぼし: 0件 / 総イベント数: 0件\n# sub\n1 0 0 sub OUT 00FB 08 1FFF\n# 取りこぼし: 0件 / 総イベント数: 1件\n'
        p.write_text(base, encoding='utf-8')
        assert len(read_events(p)) == 1
        for bad in (base.replace('0件 / 総イベント数: 1件', '1件 / 総イベント数: 1件'), base.replace('1 0 0 sub', '2 0 0 sub'), base.replace('総イベント数: 1件', '総イベント数: 2件')):
            p.write_text(bad, encoding='utf-8')
            try:
                read_events(p)
                raise AssertionError('drops')
            except ValueError:
                pass
        with patch(__name__ + '.summarize', return_value=['fdc 1 secret AB CDEF']):
            p.write_text(base, encoding='utf-8')
            out = Path(d) / 'out'
            assert main(['summarize', str(p), '--name', 'test', '--id', 'G1', '--out', str(out)]) == 2
            assert not out.exists()
    print('自己検査成功')


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('arguments')


def main(argv=None):
    parser = SafeParser()
    parser.add_argument('--selftest', action='store_true')
    sub = parser.add_subparsers(dest='action')
    s = sub.add_parser('summarize')
    s.add_argument('log', type=Path)
    s.add_argument('--name', required=True)
    s.add_argument('--id', required=True, choices=['G1'])
    s.add_argument('--out', required=True, type=Path)
    c = sub.add_parser('compare')
    c.add_argument('a', type=Path)
    c.add_argument('b', type=Path)
    c.add_argument('--out', required=True, type=Path)
    try:
        args = parser.parse_args(argv)
        if args.selftest and args.action is None:
            selftest()
            return 0
        if args.action == 'summarize':
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,32}', args.name):
                raise ValueError('name')
            rows = summarize(read_events(args.log))
            validate(rows)
        elif args.action == 'compare':
            rows = compare(load_summary(args.a), load_summary(args.b))
            validate(rows, comparison=True)
        else:
            raise ValueError('action')
        args.out.write_text(''.join(row + '\n' for row in rows), encoding='utf-8')
        return 0
    except (OSError, UnicodeError, ValueError, IndexError):
        print('解析失敗', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
