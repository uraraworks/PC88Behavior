#!/usr/bin/env python3
"""B34 の番地と分類・回数だけを検証し、連続区間にまとめる。"""
import argparse
import re
import sys

ROW = re.compile(r'R ([0-9A-F]{4}) (rom|unwritten|rom-written|ram-written) ([0-9]+)')
CLASSES = ('rom', 'unwritten', 'rom-written', 'ram-written')


def filter_lines(lines, gid, rom):
    entries = {kind: {} for kind in CLASSES}
    dropped = 0
    for line in lines:
        line = line.rstrip('\n')
        if not line:
            continue
        m = ROW.fullmatch(line)
        if not m:
            dropped += 1
            continue
        addr, kind, count = int(m[1], 16), m[2], int(m[3])
        if not count or (addr < 0x2000) != (kind == 'rom') or addr in entries[kind]:
            raise ValueError('不正な R 行')
        entries[kind][addr] = count
    out = [f'# 識別子: {gid}', f'# ROM: {rom}']
    for kind, values in entries.items():
        start = end = None
        total = 0
        for addr, count in sorted(values.items()):
            if end is not None and addr != end + 1:
                out.append(f'R {start:04X}-{end:04X} {kind} {total}')
                start, total = None, 0
            if start is None:
                start = addr
            end, total = addr, total + count
        if start is not None:
            out.append(f'R {start:04X}-{end:04X} {kind} {total}')
    return out, dropped


def selftest():
    out, dropped = filter_lines(['R 0101 rom 2', 'R 0100 rom 3', 'R 5000 ram-written 1', 'secret'], 'G1', 'self')
    assert out[2:] == ['R 0100-0101 rom 5', 'R 5000-5000 ram-written 1'] and dropped == 1
    for lines in (['R 0000 unwritten 1'], ['R 2000 rom 1'], ['R 5000 ram-written 0'], ['R 5000 ram-written 1'] * 2):
        try:
            filter_lines(lines, 'G1', 'self')
        except ValueError:
            continue
        raise AssertionError('不正行を拒否できない')
    print('白リスト自己検査 PASS')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input', nargs='?')
    p.add_argument('--id')
    p.add_argument('--rom', choices=['official', 'self'])
    p.add_argument('--out')
    p.add_argument('--selftest', action='store_true')
    args = p.parse_args()
    if args.selftest:
        selftest(); return 0
    if not args.input or not args.id or not re.fullmatch(r'G[1-9][0-9]*', args.id) or not args.rom:
        p.error('入力、--id、--rom が必要')
    try:
        with open(args.input, encoding='utf-8', errors='replace') as f:
            out, dropped = filter_lines(f, args.id, args.rom)
    except ValueError:
        print('記録が不正です', file=sys.stderr); return 1
    text = '\n'.join(out) + '\n'
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    print(f'除外: {dropped} 行', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
