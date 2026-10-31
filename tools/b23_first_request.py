#!/usr/bin/env python3
"""G1 の最初の要求だけを生ログから抽出する。"""
import argparse
from pathlib import Path
import re
import sys

from b14_request_headers import SafeParser, scan

NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]*')
PATTERNS = tuple(re.compile(p) for p in (
    r'# 識別子: G1', r'# 走: [A-Za-z0-9][A-Za-z0-9_-]*',
    r'first-run length=10(?: [0-9A-F]{2}){10}',
    r'length=(?:0|[1-9][0-9]*)'))


def summarize(path, name):
    boot = first_hi = None
    def locate(m):
        nonlocal boot, first_hi
        if m[4] != 'main':
            return
        pc = int(m[8], 16)
        if boot is None and 0xC000 <= pc <= 0xC0FF:
            boot = int(m[1])
        if first_hi is None and pc >= 0x8000:
            first_hi = int(m[1])
    scan(path, locate)
    start = boot if boot is not None else first_hi
    if start is None:
        raise ValueError
    values = []
    length = 0
    started = ended = False
    def collect(m):
        nonlocal started, ended, length
        if m[4] != 'main' or int(m[1]) < start or ended:
            return
        if m[5] == 'IN' and int(m[6], 16) == 0xFC:
            if started:
                ended = True
        elif m[5] == 'OUT' and int(m[6], 16) == 0xFD:
            started = True
            length += 1
            if length <= 10:
                values.append(m[7].upper())
    scan(path, collect)
    rows = ['# 識別子: G1', f'# 走: {name}']
    rows.append('first-run length=10 ' + ' '.join(values) if length == 10
                else f'length={length}')
    return rows


def validate(rows):
    if any(not any(p.fullmatch(row) for p in PATTERNS) for row in rows):
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
        if args.selftest or args.action != 'summarize' or not NAME.fullmatch(args.name):
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
        def log(n):
            events = [('OUT', '00FD', 'EE', '1234')]
            events += [('OUT', '00FD', f'{i:02X}', 'C000' if i == 0 else '1234') for i in range(n)]
            events += [('IN', '00FC', 'DD', '1234'), ('OUT', '00FD', 'CC', '1234'),
                       ('IN', '00FC', 'BB', '1234')]
            lines = [f'{i} {i} 0 main {op} {port} {value} {pc}'
                     for i, (op, port, value, pc) in enumerate(events, 1)]
            return ('# main\n' + '\n'.join(lines) +
                    f'\n# 取りこぼし: 0件 / 総イベント数: {len(lines)}件\n'
                    '# sub\n1 1 0 sub IN 00FC AA 2000\n'
                    '# 取りこぼし: 0件 / 総イベント数: 1件\n')
        for n in (10, 9, 11):
            path.write_text(log(n), encoding='utf-8')
            assert main(['summarize', str(path), '--name', 'test', '--id', 'G1', '--out', str(out)]) == 0
            rows = out.read_text(encoding='utf-8').splitlines()
            expected = 'first-run length=10 ' + ' '.join(f'{i:02X}' for i in range(10)) if n == 10 else f'length={n}'
            assert rows == ['# 識別子: G1', '# 走: test', expected]
        out.unlink()
        for broken in (log(10).replace('取りこぼし: 0件', '取りこぼし: 1件', 1),
                       log(10).replace('1 1 0 sub', '1 1 sub')):
            path.write_text(broken, encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()):
                assert main(['summarize', str(path), '--name', 'test', '--id', 'G1', '--out', str(out)]) == 1
            assert not out.exists()
        with patch(__name__ + '.summarize', return_value=['# 識別子: G1', '# 走: test', 'length=9 CC']):
            with contextlib.redirect_stderr(io.StringIO()):
                assert main(['summarize', str(path), '--name', 'test', '--id', 'G1', '--out', str(out)]) == 1
            assert not out.exists()
    print('自己検査成功')


if __name__ == '__main__':
    sys.exit(main())
