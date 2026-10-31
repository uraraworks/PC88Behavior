#!/usr/bin/env python3
"""サブの入力値を非公開のまま比較する。番号は入力列では0始まり。"""
import argparse
from pathlib import Path
import re
import sys

from analyze_b12 import CMDS
from b13_sub_fdc import read_events

PATTERNS = [re.compile(p) for p in (
    r'# 識別子: G1',
    r'port IN [0-9A-F]{4} (?:raw|collapsed) compared=[0-9]+ differ=[0-9]+ first=(?:[0-9]+|none) left=[0-9]+ right=[0-9]+',
    r'first-difference: (?:none|IN [0-9A-F]{4} [0-9]+ fdc=[0-9]+)')]


def sequences(events):
    # B13 と同じ全 OUT FB 列でコマンドの先頭を数える。
    writes = [(i, value) for i, (kind, port, value, pc) in enumerate(events)
              if kind == 'OUT' and port == 0xFB]
    starts = []
    i = 0
    while i < len(writes):
        starts.append(writes[i][0])
        length = CMDS.get(writes[i][1] & 31, ('unknown', 1))[1]
        if i + length > len(writes):
            raise ValueError('incomplete')
        i += length
    result = {}
    fdc = 0
    for pos, (kind, port, value, pc) in enumerate(events):
        if fdc < len(starts) and starts[fdc] == pos:
            fdc += 1
        if kind != 'IN' or pc < 0x2000:
            continue
        seq = result.setdefault(port, [])
        if port not in (0xFE, 0xFA) or not seq or seq[-1][0] != value:
            seq.append((value, pos, fdc))
    return result


def compare(a, b):
    rows = ['# 識別子: G1']
    firsts = []
    for port in sorted(a.keys() | b.keys()):
        left, right = a.get(port, []), b.get(port, [])
        count = min(len(left), len(right))
        diff = [i for i in range(count) if left[i][0] != right[i][0]]
        first = str(diff[0]) if diff else 'none'
        mode = 'collapsed' if port in (0xFE, 0xFA) else 'raw'
        rows.append(f'port IN {port:04X} {mode} compared={count} differ={len(diff)} first={first} left={len(left)-count} right={len(right)-count}')
        if diff:
            index = diff[0]
            firsts.append((right[index][1], port, index, right[index][2]))
    if firsts:
        _, port, index, fdc = min(firsts)
        rows.append(f'first-difference: IN {port:04X} {index} fdc={fdc}')
    else:
        rows.append('first-difference: none')
    return rows


def validate(rows):
    if any(not any(p.fullmatch(row) for p in PATTERNS) for row in rows):
        raise ValueError('whitelist')


def selftest():
    import contextlib
    import io
    import tempfile
    from unittest.mock import patch

    def log(events):
        return '# main\n# 取りこぼし: 0件 / 総イベント数: 0件\n# sub\n' + ''.join(
            f'{i} {i * 10} 0 sub {kind} {port:04X} {value:02X} {pc:04X}\n'
            for i, (kind, port, value, pc) in enumerate(events, 1)) + f'# 取りこぼし: 0件 / 総イベント数: {len(events)}件\n'

    events = [('OUT', 0xFB, 8, 0x1000), ('IN', 0xFB, 0xA5, 0x2000),
              ('IN', 0xFE, 0xA5, 0x2000), ('IN', 0xFE, 0xA5, 0x2000),
              ('OUT', 0xFB, 8, 0x2000), ('IN', 0xFA, 0xA5, 0x2000),
              ('IN', 0xFB, 0xA5, 0x1FFF), ('IN', 0xFC, 0xA5, 0x2000)]
    with tempfile.TemporaryDirectory() as directory:
        a, b, out = (Path(directory) / n for n in ('a', 'b', 'out'))
        a.write_text(log(events), encoding='utf-8')
        changed = events.copy()
        changed[1] = ('IN', 0xFB, 0x5A, 0x2000)
        changed[-1] = ('IN', 0xFC, 0x5A, 0x2000)
        b.write_text(log(changed), encoding='utf-8')
        assert main(['compare', str(a), str(b), '--id', 'G1', '--out', str(out)]) == 0
        result = out.read_text(encoding='utf-8')
        assert 'port IN 00FB raw compared=1 differ=1 first=0' in result
        assert 'port IN 00FE collapsed compared=1 differ=0' in result
        assert result.endswith('first-difference: IN 00FB 0 fdc=1\n')
        assert 'A5' not in result and '5A' not in result
        changed[1], changed[-1] = changed[-1], changed[1]
        b.write_text(log(changed), encoding='utf-8')
        assert main(['compare', str(a), str(b), '--id', 'G1', '--out', str(out)]) == 0
        assert out.read_text(encoding='utf-8').endswith('first-difference: IN 00FC 0 fdc=1\n')
        assert sequences(read_events(a))[0xFA][0][2] == 2
        assert len(sequences(read_events(a))[0xFB]) == 1
        b.write_text(log(events).replace('総イベント数: 8件', '総イベント数: 9件'), encoding='utf-8')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert main(['compare', str(a), str(b), '--id', 'G1', '--out', str(out)]) == 2
        assert 'A5' not in err.getvalue() and '5A' not in err.getvalue()
        out.unlink()
        with patch(__name__ + '.compare', return_value=['secret A5']):
            with contextlib.redirect_stderr(err):
                assert main(['compare', str(a), str(a), '--id', 'G1', '--out', str(out)]) == 2
        assert not out.exists() and 'A5' not in err.getvalue()
    print('自己検査成功')


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError('arguments')


def main(argv=None):
    parser = SafeParser()
    parser.add_argument('--selftest', action='store_true')
    sub = parser.add_subparsers(dest='action')
    c = sub.add_parser('compare')
    c.add_argument('a', type=Path)
    c.add_argument('b', type=Path)
    c.add_argument('--id', required=True, choices=['G1'])
    c.add_argument('--out', required=True, type=Path)
    try:
        args = parser.parse_args(argv)
        if args.selftest and args.action is None:
            selftest()
            return 0
        if args.action != 'compare' or args.selftest:
            raise ValueError('action')
        rows = compare(sequences(read_events(args.a)), sequences(read_events(args.b)))
        validate(rows)
        args.out.write_text(''.join(row + '\n' for row in rows), encoding='utf-8')
        return 0
    except (OSError, UnicodeError, ValueError, IndexError):
        print('解析失敗', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
