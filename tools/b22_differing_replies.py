#!/usr/bin/env python3
"""B22: 共通範囲の異なる応答だけを記録する。番号は0始まり。"""
import argparse
import itertools
import re
import sys

ROW = re.compile(r'\s*\d+\s+\d+\s+\d+\s+main\s+(IN|OUT)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{4})\s*')
END = re.compile(r'\s*#\s*取りこぼし:\s*(\d+)件\s*/\s*総イベント数:\s*(\d+)件\s*')
PATTERNS = [re.compile(p) for p in (
    r'# 識別子: G1', r'# 比較: [A-Za-z0-9][A-Za-z0-9_-]*-[A-Za-z0-9][A-Za-z0-9_-]*',
    r'compared=[0-9]+ differ=[0-9]+',
    r'diff index=[0-9]+ official=[0-9A-F]{2} self=[0-9A-F]{2} request=(?:[0-9A-F]{2}|none)',
    r'too-many')]


def checked(lines):
    return all(any(p.fullmatch(line) for p in PATTERNS) for line in lines)


def start_position(stream):
    """B8 と同じ開始行を探し、main 節の形式も検査する。"""
    active = found = ended = totals = False
    high = preferred = None
    for number, line in enumerate(stream):
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
        if END.fullmatch(line):
            if totals:
                raise ValueError
            totals = True
        elif not line.strip() or line.lstrip().startswith('#'):
            continue
        else:
            match = ROW.fullmatch(line)
            if not match:
                raise ValueError
            pc = int(match.group(4), 16)
            if high is None and pc >= 0x8000:
                high = number
            if preferred is None and 0xC000 <= pc <= 0xC0FF:
                preferred = number
    if not found or not ended or not totals or high is None:
        raise ValueError
    return preferred if preferred is not None else high


def replies(stream, start):
    request = None
    in_run = False
    for line in itertools.islice(stream, start, None):
        if line.strip() == '# sub':
            break
        match = ROW.fullmatch(line.rstrip('\r\n'))
        if not match:
            continue
        direction, port = match.group(1), match.group(2).upper()
        if direction == 'OUT' and port == '00FD':
            if not in_run:
                request = match.group(3).upper()
            in_run = True
        else:
            in_run = False
        if direction == 'IN' and port == '00FC':
            yield match.group(3).upper(), request


def compare(a, b, name, ident):
    starts = (start_position(a), start_position(b))
    a.seek(0); b.seek(0)
    differences = []
    count = 0
    for left, right in zip(replies(a, starts[0]), replies(b, starts[1])):
        if left[0] != right[0]:
            differences.append((count, left[0], right[0], left[1]))
            if len(differences) > 8:
                return ['too-many']
        count += 1
    lines = [f'# 識別子: {ident}', f'# 比較: {name}',
             f'compared={count} differ={len(differences)}']
    lines.extend(f'diff index={i} official={x} self={y} request={req or "none"}'
                 for i, x, y, req in differences)
    return lines


def selftest():
    import io
    def log(events):
        return io.StringIO('# main\n' + ''.join(
            f'{i} {i} 0 main {d} {p} {v} {pc}\n'
            for i, (d, p, v, pc) in enumerate(events)) +
            '# 取りこぼし: 0件 / 総イベント数: 99件\n# sub\n')
    base = [('IN', '00FC', 'A5', '1234'), ('IN', '0010', '00', 'C000'),
            ('IN', '00FC', 'E7', 'C001'), ('OUT', '00FD', '12', 'C001'),
            ('OUT', '00FD', '34', 'C001')] + [('IN', '00FC', 'A5', 'C001')] * 9
    for n in (0, 2, 8, 9):
        other = list(base)
        for i in range(n):
            other[5 + i] = ('IN', '00FC', '5A', 'C001')
        result = compare(log(base), log(other), 'OO-SS', 'G1')
        assert checked(result)
        if n == 9:
            assert result == ['too-many']
        else:
            assert result[2] == f'compared=10 differ={n}'
            assert len(result) == 3 + n
            assert all('request=12' in line for line in result[3:])
            assert all('E7' not in line for line in result)
    other = list(base); other[2] = ('IN', '00FC', '5A', 'C001')
    result = compare(log(base), log(other), 'OO-SS', 'G1')
    assert result[3].endswith('request=none')
    assert not checked(result + ['diff index=0 official=A5 self=5A request=none LEAK'])
    bad = log(base).getvalue().replace('0 0 0 main', '0 0 main', 1)
    try:
        compare(io.StringIO(bad), log(base), 'OO-SS', 'G1')
    except ValueError:
        pass
    else:
        raise AssertionError
    print('OK: B22 自己検査')


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
    if args.command != 'compare' or args.selftest:
        return 1
    try:
        with open(args.a, encoding='utf-8', errors='replace') as a, open(args.b, encoding='utf-8', errors='replace') as b:
            lines = compare(a, b, args.name, args.id)
        if not checked(lines):
            raise ValueError
        with open(args.out, 'w', encoding='utf-8') as output:
            output.write('\n'.join(lines) + '\n')
    except (ValueError, OSError):
        print('1', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
