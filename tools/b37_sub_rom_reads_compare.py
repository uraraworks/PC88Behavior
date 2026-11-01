#!/usr/bin/env python3
"""濾過済み記録の最初の差のみを表示する。"""
import argparse
import itertools
from b37_whitelist_sub_rom_reads import valid

def main():
    p = argparse.ArgumentParser(); p.add_argument('left'); p.add_argument('right'); a = p.parse_args()
    with open(a.left, encoding='utf-8') as left, open(a.right, encoding='utf-8') as right:
        for i, (x, y) in enumerate(itertools.zip_longest(left, right), 1):
            x = x.rstrip('\n') if x is not None else None
            y = y.rstrip('\n') if y is not None else None
            if (x is not None and not valid(x)) or (y is not None and not valid(y)):
                raise SystemExit('不正な濾過済み記録')
            if x != y:
                print(f'line {i}\nA: {x if x is not None else "missing"}\nB: {y if y is not None else "missing"}')
                return
    print('none')
if __name__ == '__main__': main()
