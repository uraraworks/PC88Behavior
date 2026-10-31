#!/usr/bin/env python3
"""G1 の要求見出しだけを生ログから抽出する。"""
import argparse
from pathlib import Path
import re
import sys

ROW = re.compile(r'\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{4})\s*')
DROP = re.compile(r'# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件')
NUM = r'(?:0|[1-9][0-9]*)'
PATTERNS = [re.compile(p) for p in (
    r'# 識別子: G1', r'# 走: [A-Za-z0-9][A-Za-z0-9_-]*',
    r'hi-start: (?:yes|no)',
    rf'request {NUM} [0-9A-F]{{2}} length={NUM} (?:before|after)',
    rf'totals before={NUM} after={NUM} bytes={NUM}')]


def scan(path, on_row):
    section = None
    seen = []
    count = 0
    ended = False
    with path.open(encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\r\n')
            if line in ('# main', '# sub'):
                if section is not None and not ended:
                    raise ValueError
                section = line[2:]
                seen.append(section)
                if seen != ['main', 'sub'][:len(seen)]:
                    raise ValueError
                count, ended = 0, False
                continue
            if section is None:
                continue
            m = DROP.fullmatch(line)
            if m:
                if ended or int(m[1]) or int(m[2]) != count:
                    raise ValueError
                ended = True
            elif not line.strip() or line.lstrip().startswith('#'):
                if line.startswith('# 取りこぼし:'):
                    raise ValueError
            else:
                m = ROW.fullmatch(line)
                if ended or not m or m[4] != section or int(m[1]) != count + 1:
                    raise ValueError
                count += 1
                on_row(m)
    if seen != ['main', 'sub'] or not ended:
        raise ValueError


def summarize(path, name):
    boot = first_hi = hi_clock = None
    def locate(m):
        nonlocal boot, first_hi, hi_clock
        pc = int(m[8], 16)
        if m[4] == 'main':
            if boot is None and 0xC000 <= pc <= 0xC0FF:
                boot = int(m[1])
            if first_hi is None and pc >= 0x8000:
                first_hi = int(m[1])
        elif hi_clock is None and pc >= 0x2000:
            hi_clock = int(m[2])
    scan(path, locate)
    start = boot if boot is not None else first_hi
    if start is None:
        raise ValueError
    requests = []
    current = None
    def collect(m):
        nonlocal current
        if m[4] != 'main' or int(m[1]) < start:
            return
        if m[5] == 'IN' and int(m[6], 16) == 0xFC:
            current = None
        elif m[5] == 'OUT' and int(m[6], 16) == 0xFD:
            if current is None:
                current = [m[7].upper(), 0, 0]
                requests.append(current)
            current[1] += 1
            current[2] = int(m[2])
    scan(path, collect)
    rows = ['# 識別子: G1', f'# 走: {name}', f"hi-start: {'yes' if hi_clock is not None else 'no'}"]
    before = after = total = 0
    for i, (first, length, clock) in enumerate(requests, 1):
        total += length
        if hi_clock is None or clock < hi_clock:
            before += 1
            phase = 'before'
        else:
            after += 1
            phase = 'after'
        if phase == 'before' or after <= 8:
            rows.append(f'request {i} {first} length={length} {phase}')
    rows.append(f'totals before={before} after={after} bytes={total}')
    return rows


def validate(rows):
    if any(not any(p.fullmatch(row) for p in PATTERNS) for row in rows):
        raise ValueError


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError


def main(argv=None):
    parser = SafeParser()
    parser.add_argument('--selftest', action='store_true')
    sub = parser.add_subparsers(dest='action', parser_class=SafeParser)
    s = sub.add_parser('summarize')
    s.add_argument('log', type=Path)
    s.add_argument('--name', required=True)
    s.add_argument('--id', required=True, choices=['G1'])
    s.add_argument('--out', required=True, type=Path)
    try:
        args = parser.parse_args(argv)
        if args.selftest and args.action is None:
            selftest()
            return 0
        if args.action != 'summarize' or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.name):
            raise ValueError
        rows = summarize(args.log, args.name)
        validate(rows)
        args.out.write_text(''.join(row + '\n' for row in rows), encoding='utf-8')
        return 0
    except (OSError, UnicodeError, ValueError, IndexError):
        print('解析失敗', file=sys.stderr)
        return 1


def selftest():
    import contextlib
    import io
    import tempfile
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as d:
        path, out = Path(d) / 'log', Path(d) / 'out'
        main_rows = ['1 1 0 main OUT 00FD 99 1234',
                     '2 2 0 main OUT 00FD 11 C000',
                     '3 3 0 main OUT 00FD EE 1234',
                     '4 4 0 main IN 00FC DD 1234']
        for i in range(10):
            main_rows += [f'{5+i*2} {10+i*2} 0 main OUT 00FD 22 1234',
                          f'{6+i*2} {11+i*2} 0 main IN 00FC DD 1234']
        def log(subpc='2000', drop='0'):
            return ('# main\n' + '\n'.join(main_rows) +
                    f'\n# 取りこぼし: {drop}件 / 総イベント数: {len(main_rows)}件\n'
                    f'# sub\n1 10 0 sub IN 00FC CC {subpc}\n'
                    '# 取りこぼし: 0件 / 総イベント数: 1件\n')
        path.write_text(log(), encoding='utf-8')
        rows = summarize(path, 'test')
        validate(rows)
        assert 'request 1 11 length=2 before' in rows
        assert 'request 2 22 length=1 after' in rows and 'request 9 22 length=1 after' in rows
        assert not any(r.startswith('request 10 ') for r in rows)
        assert rows[-1] == 'totals before=1 after=10 bytes=12'
        assert all(not any(x in r for x in ('EE', 'DD', '99', 'CC')) for r in rows)
        path.write_text(log('1FFF'), encoding='utf-8')
        rows = summarize(path, 'test')
        assert rows[2] == 'hi-start: no' and rows[-1] == 'totals before=11 after=0 bytes=12'
        for bad in (log(drop='1'), log().replace('0件 / 総イベント数: 1件', '1件 / 総イベント数: 1件'),
                    log().replace('1 10 0 sub', '1 10 sub')):
            path.write_text(bad, encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()):
                assert main(['summarize', str(path), '--name', 'test', '--id', 'G1', '--out', str(out)]) == 1
            assert not out.exists()
        path.write_text(log(), encoding='utf-8')
        with patch(__name__ + '.summarize', return_value=['request 1 11 length=2 before EE']):
            with contextlib.redirect_stderr(io.StringIO()):
                assert main(['summarize', str(path), '--name', 'test', '--id', 'G1', '--out', str(out)]) == 1
            assert not out.exists()
    print('自己検査成功')


if __name__ == '__main__':
    sys.exit(main())
