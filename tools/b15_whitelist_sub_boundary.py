#!/usr/bin/env python3
"""B15 の記録を検査し、書き込み番地を連続区間に集約する。"""
import argparse
import re
import sys

A = re.compile(r'A ([0-9A-F]{4}) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+)')
W = re.compile(r'W ([0-9A-F]{4}) (rom|ram) ([0-9]+)')


def filter_lines(lines, gid, rom):
    crossings, writes = {}, {'rom': {}, 'ram': {}}
    dropped = 0
    for line in lines:
        line = line.rstrip('\n')
        if not line:
            continue
        a, w = A.fullmatch(line), W.fullmatch(line)
        if a:
            addr = int(a[1], 16)
            nums = tuple(map(int, a.groups()[1:]))
            if addr >= 0x2000 or addr in crossings or nums[0] != nums[1] + nums[2] or nums[3] > nums[1] or nums[4] > nums[1]:
                raise ValueError('不正な A 行')
            crossings[addr] = nums
        elif w:
            addr, source, count = int(w[1], 16), w[2], int(w[3])
            if addr < 0x4000 or not count or addr in writes[source]:
                raise ValueError('不正な W 行')
            writes[source][addr] = count
        else:
            dropped += 1
    out = [f'# 識別子: {gid}', f'# ROM: {rom}']
    out += [f"A {a:04X} " + ' '.join(map(str, v)) for a, v in sorted(crossings.items())]
    for source, entries in writes.items():
        start = end = None
        count = 0
        for addr, n in sorted(entries.items()):
            if end is not None and addr != end + 1:
                out.append(f'W {start:04X}-{end:04X} {source} {count}')
                start = None
                count = 0
            if start is None:
                start = addr
            end = addr
            count += n
        if start is not None:
            out.append(f'W {start:04X}-{end:04X} {source} {count}')
    return out, dropped


def selftest():
    out, n = filter_lines(['A 1000 2 2 0 0 2', 'W 4001 rom 3', 'W 4000 rom 2', 'W 4003 ram 1', 'secret'], 'G1', 'self')
    assert out[2:] == ['A 1000 2 2 0 0 2', 'W 4000-4001 rom 5', 'W 4003-4003 ram 1'] and n == 1
    for lines in (['W 4000 rom 1', 'W 4000 rom 2'], ['A 2000 1 1 0 0 0']):
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
        selftest(); return
    if not args.input or not args.id or not re.fullmatch(r'G[1-9][0-9]*', args.id) or not args.rom:
        p.error('入力、--id、--rom が必要')
    try:
        with open(args.input, encoding='utf-8', errors='replace') as f:
            out, dropped = filter_lines(f, args.id, args.rom)
    except ValueError:
        print('記録が不正です', file=sys.stderr); return 1
    text = '\n'.join(out) + '\n'
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f: f.write(text)
    else:
        sys.stdout.write(text)
    print(f'除外: {dropped} 行', file=sys.stderr)
    return 0

if __name__ == '__main__':
    sys.exit(main())
