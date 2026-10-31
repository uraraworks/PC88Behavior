#!/usr/bin/env python3
"""共通 clock で G1 の指定された IN FC 前後を集計する。"""
import argparse
from bisect import bisect_left, bisect_right
from pathlib import Path
import re
import sys

ROW = re.compile(r'\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+([0-9A-Fa-f]{4})\s+[0-9A-Fa-f]{2}\s+([0-9A-Fa-f]{4})\s*')
END = re.compile(r'\s*#\s*取りこぼし:\s*(\d+)件\s*/\s*総イベント数:\s*(\d+)件\s*')
PATTERNS = [re.compile(p) for p in (
    r'# 識別子: G1', r'# 走: [A-Za-z0-9][A-Za-z0-9_-]{0,31}',
    r'fc (?:3839|3840|3841) sub_fd=[0-9]+ last=(?:lo|hi|none) new_fd=[0-9]+ out_ff=[0-9]+ in_fe=[0-9]+')]


def read_events(path):
    sections = {}
    current = None
    ended = False
    main_ended = False
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip() in ('# main', '# sub'):
            current = line.strip()[2:]
            if current in sections or (current == 'main' and 'sub' in sections):
                raise ValueError('section')
            sections[current] = []
            ended = False
        elif current is not None:
            end = END.fullmatch(line)
            if end:
                if ended or int(end[1]) or int(end[2]) != len(sections[current]):
                    raise ValueError('drops or count')
                ended = True
            elif not line.strip() or line.lstrip().startswith('#'):
                continue
            else:
                m = ROW.fullmatch(line)
                if ended or not m or m[4] != current:
                    raise ValueError('row')
                seq, clock, frame = map(int, m.group(1, 2, 3))
                events = sections[current]
                if events and (seq != events[-1][0] + 1 or clock < events[-1][1]):
                    raise ValueError('sequence')
                if not events and seq not in (0, 1):
                    raise ValueError('sequence')
                events.append((seq, clock, m[5], int(m[6], 16), int(m[7], 16)))
        if current is not None and line.strip() == '# sub':
            if 'main' not in sections or not main_ended:
                raise ValueError('end')
        if current == 'main':
            main_ended = ended
    if set(sections) != {'main', 'sub'} or not ended:
        raise ValueError('end')
    return sections


def summarize(events, name):
    main = events['main']
    start = next((i for i, e in enumerate(main) if 0xC000 <= e[4] <= 0xC0FF), None)
    if start is None:
        start = next((i for i, e in enumerate(main) if e[4] >= 0x8000), None)
    if start is None:
        raise ValueError('start')
    main = main[start:]
    fc = [e[1] for e in main if e[2:4] == ('IN', 0xFC)]
    if len(fc) < 3841:
        raise ValueError('fc')
    fd = sorted((e[1], 'lo' if e[4] < 0x2000 else 'hi') for e in events['sub'] if e[2:4] == ('OUT', 0xFD))
    fd_clocks = [e[0] for e in fd]
    ff = sorted(e[1] for e in main if e[2:4] == ('OUT', 0xFF))
    fe = sorted(e[1] for e in main if e[2:4] == ('IN', 0xFE))
    rows = ['# 識別子: G1', f'# 走: {name}']
    for number in (3839, 3840, 3841):
        before, clock = fc[number - 2:number]
        n = bisect_left(fd_clocks, clock)
        count = lambda clocks: max(0, bisect_left(clocks, clock) - bisect_right(clocks, before))
        rows.append(f'fc {number} sub_fd={n} last={fd[n-1][1] if n else "none"} '
                    f'new_fd={count(fd_clocks)} out_ff={count(ff)} in_fe={count(fe)}')
    return rows


def validate(rows):
    if any(not any(p.fullmatch(row) for p in PATTERNS) for row in rows):
        raise ValueError('whitelist')
    if len(rows) != 5 or not PATTERNS[0].fullmatch(rows[0]) or not PATTERNS[1].fullmatch(rows[1]) or [r.split()[1] for r in rows[2:]] != ['3839', '3840', '3841']:
        raise ValueError('structure')


def selftest():
    import tempfile
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as d:
        path, out = Path(d) / 'log', Path(d) / 'out'
        main_rows = [(i * 10, 'IN', '00FC', 'C001') for i in range(3841)]
        main_rows += [(38385, 'OUT', '00FF', 'C001'), (38386, 'IN', '00FE', 'C001')]
        main_rows.sort()
        sub_rows = [(1, 'OUT', '00FD', '1FFF'), (38385, 'OUT', '00FD', '2000')]
        def section(cpu, records):
            return ['# ' + cpu] + [f'{i} {clock} 0 {cpu} {op} {port} A5 {pc}' for i, (clock, op, port, pc) in enumerate(records, 1)] + [f'# 取りこぼし: 0件 / 総イベント数: {len(records)}件']
        raw = '\n'.join(section('main', main_rows) + section('sub', sub_rows)) + '\n'
        path.write_text(raw, encoding='utf-8')
        args = ['summarize', str(path), '--name', 'test', '--id', 'G1', '--out', str(out)]
        assert main(args) == 0
        rows = out.read_text(encoding='utf-8').splitlines()
        assert rows == ['# 識別子: G1', '# 走: test', 'fc 3839 sub_fd=1 last=lo new_fd=0 out_ff=0 in_fe=0', 'fc 3840 sub_fd=2 last=hi new_fd=1 out_ff=1 in_fe=1', 'fc 3841 sub_fd=2 last=hi new_fd=0 out_ff=0 in_fe=0']
        assert all('A5' not in row for row in rows)
        path.write_text(raw.replace('取りこぼし: 0件', '取りこぼし: 1件', 1), encoding='utf-8')
        out.unlink()
        assert main(args) == 1 and not out.exists()
        path.write_text(raw, encoding='utf-8')
        with patch(__name__ + '.summarize', return_value=rows + ['秘密 A5']):
            assert main(args) == 1 and not out.exists()
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
    args = parser.parse_args(argv)
    try:
        if args.selftest and args.action is None:
            selftest()
        elif args.action == 'summarize':
            rows = summarize(read_events(args.log), args.name)
            validate(rows)
            args.out.write_text('\n'.join(rows) + '\n', encoding='utf-8')
        else:
            return 1
        return 0
    except (OSError, UnicodeError, ValueError, IndexError):
        print('解析失敗', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
