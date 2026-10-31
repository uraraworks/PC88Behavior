#!/usr/bin/env python3
"""B8 の値を公開せずに比較する。番号は 0 始まり。"""
import argparse
import re
import sys

ROW = re.compile(r'\s*\d+\s+\d+\s+\d+\s+main\s+(IN|OUT)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{4})\s*')
END = re.compile(r'\s*#\s*取りこぼし:\s*(\d+)件\s*/\s*総イベント数:\s*(\d+)件\s*')
PORTS = [('IN', '00FC', 'raw'), ('OUT', '00FD', 'raw'),
         ('IN', '00FE', 'collapsed'), ('OUT', '00FF', 'collapsed')]
PATTERNS = [re.compile(p) for p in (
    r'# 識別子: G1', r'# 比較: [A-Za-z0-9][A-Za-z0-9_-]*-[A-Za-z0-9][A-Za-z0-9_-]*',
    r'port (?:IN|OUT) [0-9A-F]{4} (?:raw|collapsed) compared=[0-9]+ differ=[0-9]+ first=(?:[0-9]+|none) left=[0-9]+ right=[0-9]+',
    r'first-difference: (?:none|(?:IN|OUT) [0-9A-F]{4} [0-9]+)')]


def checked(lines):
    bad = sum(not any(p.fullmatch(line) for p in PATTERNS) for line in lines)
    if bad:
        print(bad, file=sys.stderr)
    return not bad


def parse_log(lines):
    active = found = ended = False
    totals = None
    rows = []
    for line in lines:
        line = line.rstrip('\r\n')
        if line.strip() == '# main':
            if found:
                raise ValueError
            active = found = True
            continue
        if active and line.strip() == '# sub':
            ended = True
            break
        if not active:
            continue
        m = END.fullmatch(line)
        if m:
            if totals is not None:
                raise ValueError
            totals = m.groups()
        elif not line.strip() or line.lstrip().startswith('#'):
            continue
        else:
            m = ROW.fullmatch(line)
            if not m:
                raise ValueError
            direction, port, value, pc = m.groups()
            rows.append((direction, port.upper(), int(value, 16), int(pc, 16)))
    if not found or not ended or totals is None:
        raise ValueError
    start = next((i for i, row in enumerate(rows) if 0xC000 <= row[3] <= 0xC0FF), None)
    if start is None:
        start = next((i for i, row in enumerate(rows) if row[3] >= 0x8000), None)
    if start is None:
        raise ValueError
    result = {p: [] for p in PORTS}
    for position, (direction, port, value, pc) in enumerate(rows[start:]):
        for key in PORTS:
            if (direction, port) == key[:2]:
                item = (value, 'hi' if pc >= 0x8000 else 'lo')
                seq = result[key]
                if key[2] == 'raw' or not seq or seq[-1][0] != item:
                    seq.append((item, position))
    return result


def compare(a, b, name, ident):
    lines = [f'# 識別子: {ident}', f'# 比較: {name}']
    firsts = []
    for key in PORTS:
        left, right = a[key], b[key]
        count = min(len(left), len(right))
        differences = [i for i in range(count) if left[i][0] != right[i][0]]
        first = str(differences[0]) if differences else 'none'
        if differences:
            firsts.append((right[differences[0]][1], key, differences[0]))
        lines.append(f'port {" ".join(key)} compared={count} differ={len(differences)} first={first} left={len(left)-count} right={len(right)-count}')
    if firsts:
        _, key, index = min(firsts)
        lines.append(f'first-difference: {key[0]} {key[1]} {index}')
    else:
        lines.append('first-difference: none')
    return lines


def selftest():
    import contextlib
    import io
    def log(events):
        return ['# main'] + [f'{i} {i} 0 main {d} {p} {v} {pc}' for i, (d, p, v, pc) in enumerate(events)] + ['# 取りこぼし: 0件 / 総イベント数: 9件', '# sub']
    events = [('IN', '0010', 'AA', 'C000'), ('IN', '00FC', 'A5', 'C001'),
              ('OUT', '00FD', 'A5', '1234'), ('IN', '00FE', 'A5', 'C001'),
              ('OUT', '00FF', 'A5', 'C001')]
    a = parse_log(log(events))
    out = compare(a, a, 'A-B', 'G1')
    assert checked(out) and out[-1] == 'first-difference: none' and all('A5' not in s for s in out)
    for index, key in enumerate(PORTS, 1):
        changed = events.copy()
        d, p, _, pc = changed[index]
        changed[index] = (d, p, '5A', pc)
        result = compare(a, parse_log(log(changed)), 'A-B', 'G1')
        assert 'differ=1 first=0' in result[index + 1]
        assert result[-1] == f'first-difference: {key[0]} {key[1]} 0'
    repeated = events[:4] + [events[3]] + events[4:]
    assert compare(a, parse_log(log(repeated)), 'A-B', 'G1')[-1] == 'first-difference: none'
    changed = repeated.copy(); changed[4] = ('IN', '00FE', '5A', 'C001')
    assert 'right=1' in compare(a, parse_log(log(changed)), 'A-B', 'G1')[4]
    extra = events + [events[1]]
    assert 'left=1' in compare(parse_log(log(extra)), a, 'A-B', 'G1')[2]
    assert 'right=1' in compare(a, parse_log(log(extra)), 'A-B', 'G1')[2]
    changed = events.copy(); changed[1] = ('IN', '00FC', '5A', 'C001'); changed[4] = ('OUT', '00FF', '5A', 'C001')
    changed[1], changed[4] = changed[4], changed[1]
    assert compare(a, parse_log(log(changed)), 'A-B', 'G1')[-1] == 'first-difference: OUT 00FF 0'
    assert parse_log(log([('IN', '00FC', '5A', '1234')] + events)) == a
    hi = events.copy(); hi[2] = ('OUT', '00FD', 'A5', '9000')
    assert 'differ=1' in compare(a, parse_log(log(hi)), 'A-B', 'G1')[3]
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert not checked(out + [out[2] + ' A5'])
    assert err.getvalue() == '1\n'
    try:
        parse_log(['# main', '0 0 main IN 00FC A5 C000', '# 取りこぼし: 0件 / 総イベント数: 1件', '# sub'])
    except ValueError:
        pass
    else:
        raise AssertionError
    print('OK: B8 自己検査')


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        print('1', file=sys.stderr)
        self.exit(1)


def main():
    parser = SafeParser()
    parser.add_argument('--selftest', action='store_true')
    sub = parser.add_subparsers(dest='command')
    c = sub.add_parser('compare')
    c.add_argument('a'); c.add_argument('b')
    c.add_argument('--name', required=True); c.add_argument('--id', required=True, choices=['G1'])
    c.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.selftest and args.command is None:
        selftest(); return 0
    if args.command != 'compare':
        return 1
    try:
        with open(args.a, encoding='utf-8', errors='replace') as f:
            a = parse_log(f)
        with open(args.b, encoding='utf-8', errors='replace') as f:
            b = parse_log(f)
        lines = compare(a, b, args.name, args.id)
        if not checked(lines):
            return 1
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    except (ValueError, OSError):
        print('1', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
