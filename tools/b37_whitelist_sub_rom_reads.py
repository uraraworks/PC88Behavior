#!/usr/bin/env python3
"""B37 の値を含まない行だけを通す。"""
import argparse
import re
import sys

ROW = re.compile(r'W ([0-9]+) ([0-9A-F]{4})-([0-9A-F]{4}) (unwritten|rom-written|ram-written) (増える|同じ) ([0-9]+)')
END = re.compile(r'dropped=([0-9]+) complete=([01])')

def valid(line):
    if line == '# 識別子: G1':
        return True
    m = ROW.fullmatch(line)
    if m:
        a, b, n = int(m[2], 16), int(m[3], 16), int(m[6])
        return a >= 0x4000 and n > 0 and ((m[5] == '同じ' and a == b) or (m[5] == '増える' and n > 1 and b - a == n - 1))
    m = END.fullmatch(line)
    return bool(m and (int(m[1]) == 0) == (m[2] == '1'))

def main():
    p = argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--out')
    args = p.parse_args(); dropped = 0; output = ['# 識別子: G1']
    with open(args.input, encoding='utf-8', errors='replace') as src:
        for line in src:
            line = line.rstrip('\n')
            if line != '# 識別子: G1' and valid(line): output.append(line)
            else: dropped += 1
    text = '\n'.join(output) + '\n'
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as dest: dest.write(text)
    else: sys.stdout.write(text)
    print(f'除外: {dropped} 行', file=sys.stderr)

if __name__ == '__main__': main()
