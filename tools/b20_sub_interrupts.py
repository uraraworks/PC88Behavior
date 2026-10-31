#!/usr/bin/env python3
"""B20 のサブ CPU 割り込みを事前登録済みの項目に集約する。"""
import argparse
from collections import Counter
from pathlib import Path
import re
import sys

ROW = re.compile(r'\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+sub\s+([0-9]+)\s+([0-9]+)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s*')
END = re.compile(r'# 取りこぼし: ([0-9]+)件 / 総イベント数: ([0-9]+)件')
ALLOWED = tuple(map(re.compile, (r'# 識別子: G1', r'# 走: [A-Za-z0-9][A-Za-z0-9_-]*', r'accepted: [0-9]+', r'dropped: [0-9]+', r'int [0-2] [0-9A-F]{4} (?:lo|hi) [1-9][0-9]*')))


def summarize(lines, name):
    active = found = ended = empty = False
    counts = Counter()
    total = dropped = None
    for line in lines:
        line = line.rstrip('\r\n')
        if line == '# sub':
            if found:
                raise ValueError
            active = found = True
            continue
        if not active:
            continue
        if ended:
            if line.strip():
                raise ValueError
            continue
        if line == '# seq    clock   frame  cpu   im  level  ret_pc  handler_pc' or not line:
            continue
        if line == '# (記録されたイベントなし)':
            if empty or counts:
                raise ValueError
            empty = True
            continue
        m = END.fullmatch(line)
        if m:
            dropped, total = map(int, m.groups())
            ended = True
            continue
        m = ROW.fullmatch(line)
        if not m or empty:
            raise ValueError
        im = int(m[4])
        if im not in (0, 1, 2):
            raise ValueError
        counts[(im, m[7].upper(), 'hi' if int(m[6], 16) >= 0x2000 else 'lo')] += 1
    if not found or not ended or total != sum(counts.values()) or (empty != (total == 0)):
        raise ValueError
    out = ['# 識別子: G1', f'# 走: {name}', f'accepted: {total}', f'dropped: {dropped}']
    out += [f'int {im} {handler} {region} {count}' for (im, handler, region), count in sorted(counts.items())]
    if not all(any(p.fullmatch(line) for p in ALLOWED) for line in out):
        raise ValueError
    return out


def selftest():
    header = '# seq    clock   frame  cpu   im  level  ret_pc  handler_pc'
    raw = ['# main', '# sub', header, '0 1 2 sub 1 0 1FFF 0038', '1 2 3 sub 1 0 2000 0038', '# 取りこぼし: 2件 / 総イベント数: 2件']
    out = summarize(raw, 'self-1')
    assert out == ['# 識別子: G1', '# 走: self-1', 'accepted: 2', 'dropped: 2', 'int 1 0038 hi 1', 'int 1 0038 lo 1']
    assert summarize(['# sub', header, '# (記録されたイベントなし)', '# 取りこぼし: 0件 / 総イベント数: 0件'], 'x')[2] == 'accepted: 0'
    for bad in (raw[:-1], raw + ['extra'], raw[:-1] + ['# 取りこぼし: 0件 / 総イベント数: 3件'], raw[:3] + ['秘密'] + raw[3:]):
        try:
            summarize(bad, 'x')
        except ValueError:
            continue
        raise AssertionError
    try:
        summarize(raw, 'bad name')
    except ValueError:
        pass
    else:
        raise AssertionError
    print('OK: B20 自己検査')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--selftest', action='store_true')
    sub = parser.add_subparsers(dest='command')
    cmd = sub.add_parser('summarize')
    cmd.add_argument('input')
    cmd.add_argument('--name', required=True)
    cmd.add_argument('--id', required=True)
    cmd.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.selftest and args.command is None:
        selftest()
    elif args.command == 'summarize' and args.id == 'G1' and not args.selftest:
        with open(args.input, encoding='utf-8') as f:
            out = summarize(f, args.name)
        Path(args.out).write_text('\n'.join(out) + '\n', encoding='utf-8')
    else:
        raise ValueError


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, UnicodeError):
        print('入力または出力を処理できません', file=sys.stderr)
        sys.exit(1)
