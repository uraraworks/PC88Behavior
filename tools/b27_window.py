#!/usr/bin/env python3
"""G1 の窓を値を出さずに比較する。"""
import argparse
from itertools import zip_longest
from pathlib import Path
import re
import sys

from b25_two_bytes import read_events

NAME = r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}'
SEQ = r'seq (?:main|sub) (?:IN|OUT) [0-9A-F]{4} (?:lo|hi) [1-9][0-9]*'
SUMMARY = [re.compile(r'# 識別子: G1'), re.compile(r'# 走: ' + NAME), re.compile(SEQ)]
COMPARISON = [re.compile(r'first-difference: (?:none|[1-9][0-9]*)'),
              re.compile(r'[AB]: (?:missing|' + SEQ + r')')]


def validate(rows, comparison=False):
    patterns = COMPARISON if comparison else SUMMARY
    if any(not any(p.fullmatch(row) for p in patterns) for row in rows):
        raise ValueError('whitelist')
    if comparison:
        if not rows or not patterns[0].fullmatch(rows[0]):
            raise ValueError('structure')
        if rows[0] == 'first-difference: none':
            if len(rows) != 1:
                raise ValueError('structure')
        elif len(rows) != 3 or not rows[1].startswith('A: ') or not rows[2].startswith('B: '):
            raise ValueError('structure')
    elif len(rows) < 3 or not patterns[0].fullmatch(rows[0]) or not patterns[1].fullmatch(rows[1]) or any(not patterns[2].fullmatch(row) for row in rows[2:]):
        raise ValueError('structure')


def summarize(events, name):
    main = events['main']
    start = next((i for i, e in enumerate(main) if 0xC000 <= e[4] <= 0xC0FF), None)
    if start is None:
        start = next((i for i, e in enumerate(main) if e[4] >= 0x8000), None)
    if start is None:
        raise ValueError('start')
    main = main[start:]
    fc = [e for e in main if e[2:4] == ('IN', 0xFC)]
    if len(fc) < 3841:
        raise ValueError('fc')
    # 同一 clock は main を先にし、各 CPU 内の順序を維持する。
    merged = sorted([(e[1], 0, i, 'main', e) for i, e in enumerate(main)] +
                    [(e[1], 1, i, 'sub', e) for i, e in enumerate(events['sub'])])
    first = next(i for i, item in enumerate(merged) if item[3] == 'main' and item[4] is fc[3838])
    last = next(i for i, item in enumerate(merged) if item[3] == 'main' and item[4] is fc[3840])
    groups = []
    for _, _, _, cpu, event in merged[first:last + 1]:
        key = (cpu, event[2], f'{event[3]:04X}', 'lo' if event[4] < (0x8000 if cpu == 'main' else 0x2000) else 'hi')
        if groups and groups[-1][0] == key:
            groups[-1] = (key, groups[-1][1] + 1)
        else:
            groups.append((key, 1))
    return ['# 識別子: G1', f'# 走: {name}'] + [f'seq {" ".join(key)} {count}' for key, count in groups]


def compare(a, b):
    for i, (x, y) in enumerate(zip_longest(a[2:], b[2:], fillvalue='missing'), 1):
        if x != y:
            return [f'first-difference: {i}', f'A: {x}', f'B: {y}']
    return ['first-difference: none']


def selftest():
    import tempfile
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as d:
        log, a, b, out = (Path(d) / x for x in ('log', 'a', 'b', 'out'))
        main_rows = [(i * 10, 'IN', '00FC', 'C001') for i in range(3841)]
        main_rows += [(38385, 'OUT', '00FD', '7FFF'), (38386, 'OUT', '00FD', '8000')]
        main_rows.sort()
        sub_rows = [(38379, 'IN', '00FC', '1FFF'), (38381, 'IN', '00FC', '1FFF'), (38382, 'IN', '00FC', '1FFF'), (38387, 'IN', '00FC', '2000'), (38401, 'OUT', '00FD', '2000')]
        def section(cpu, records):
            return ['# ' + cpu] + [f'{i} {clock} 0 {cpu} {op} {port} A5 {pc}' for i, (clock, op, port, pc) in enumerate(records, 1)] + [f'# 取りこぼし: 0件 / 総イベント数: {len(records)}件']
        raw = '\n'.join(section('main', main_rows) + section('sub', sub_rows)) + '\n'
        log.write_text(raw, encoding='utf-8')
        args = ['summarize', str(log), '--name', 'test', '--id', 'G1', '--out', str(a)]
        assert main(args) == 0
        rows = a.read_text(encoding='utf-8').splitlines()
        assert rows == ['# 識別子: G1', '# 走: test', 'seq main IN 00FC hi 1', 'seq sub IN 00FC lo 2', 'seq main OUT 00FD lo 1', 'seq main OUT 00FD hi 1', 'seq sub IN 00FC hi 1', 'seq main IN 00FC hi 2']
        assert all('A5' not in row for row in rows)
        b.write_text('\n'.join(rows[:-1]) + '\n', encoding='utf-8')
        assert main(['compare', str(a), str(b), '--out', str(out)]) == 0
        assert out.read_text(encoding='utf-8').splitlines() == ['first-difference: 6', 'A: seq main IN 00FC hi 2', 'B: missing']
        assert compare(rows, rows) == ['first-difference: none']
        log.write_text(raw.replace('取りこぼし: 0件', '取りこぼし: 1件', 1), encoding='utf-8')
        a.unlink()
        assert main(args) == 1 and not a.exists()
        log.write_text(raw, encoding='utf-8')
        with patch(__name__ + '.summarize', return_value=rows + ['秘密 A5']):
            assert main(args) == 1 and not a.exists()
    print('自己検査成功')


def main(argv=None):
    parser = argparse.ArgumentParser()
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
    args = parser.parse_args(argv)
    try:
        if args.selftest and args.action is None:
            selftest()
        elif args.action == 'summarize' and not args.selftest:
            rows = summarize(read_events(args.log), args.name)
            validate(rows)
            args.out.write_text('\n'.join(rows) + '\n', encoding='utf-8')
        elif args.action == 'compare' and not args.selftest:
            a = args.a.read_text(encoding='utf-8').splitlines()
            b = args.b.read_text(encoding='utf-8').splitlines()
            validate(a)
            validate(b)
            rows = compare(a, b)
            validate(rows, comparison=True)
            args.out.write_text('\n'.join(rows) + '\n', encoding='utf-8')
        else:
            return 1
        return 0
    except (OSError, UnicodeError, ValueError, IndexError):
        print('解析失敗', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
