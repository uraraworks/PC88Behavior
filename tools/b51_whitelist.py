#!/usr/bin/env python3
"""B51 の行を検証し、短い ROM 読みの番地を伏せる。"""
import argparse
import re
import sys

ROW = re.compile(r'A ([RW]) ([0-9A-F]{4})-([0-9A-F]{4}) (増える|同じ) ([0-9]+) ([0-9]+)')
SHORT = re.compile(r'A R rom-short ([0-9]+) ([0-9]+)')
END = re.compile(r'dropped=([0-9]+) complete=([01])')

def filter_line(line):
    if line == '# 識別子: G1':
        return line
    m = ROW.fullmatch(line)
    if m:
        kind, start, end, direction, count, fc = m.groups()
        a, b, n = int(start, 16), int(end, 16), int(count)
        if n < 1 or not ((direction == '同じ' and a == b) or (direction == '増える' and n > 1 and b - a == n - 1)):
            return None
        if kind == 'R' and a < 0x2000 and n < 16:
            return f'A R rom-short {count} {fc}'
        return line
    m = SHORT.fullmatch(line)
    if m and 0 < int(m[1]) < 16:
        return line
    m = END.fullmatch(line)
    if m and (int(m[1]) == 0) == (m[2] == '1'):
        return line
    return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input'); parser.add_argument('--out')
    args = parser.parse_args()
    output = ['# 識別子: G1']; excluded = 0
    with open(args.input, encoding='utf-8', errors='replace') as src:
        for line in src:
            line = line.rstrip('\n')
            result = filter_line(line)
            if result is None:
                excluded += 1
            elif result != '# 識別子: G1':
                output.append(result)
    text = '\n'.join(output) + '\n'
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as dest: dest.write(text)
    else: sys.stdout.write(text)
    print(f'除外: {excluded} 行', file=sys.stderr)
if __name__ == '__main__': main()
