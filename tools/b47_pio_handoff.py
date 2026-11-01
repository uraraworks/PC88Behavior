#!/usr/bin/env python3
"""共通 clock を使い、I/O 値を外に出さず受け渡しを集計する。"""
import argparse
from bisect import bisect_left
from pathlib import Path
import re
import sys

ROW = re.compile(r'\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s+([0-9A-Fa-f]{4})\s*')
END = re.compile(r'# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件')


def read(path):
    sections = {'main': [], 'sub': []}
    seen = set()
    current = None
    ended = False
    clocks = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        if line in ('# main', '# sub'):
            if current is not None and not ended:
                raise ValueError()
            current = line[2:]
            if current in seen:
                raise ValueError()
            seen.add(current)
            ended = False
            continue
        if current is None:
            continue
        m = END.fullmatch(line)
        if m:
            if ended or int(m[1]) or int(m[2]) != len(sections[current]):
                raise ValueError()
            ended = True
            continue
        if not line.strip() or line.startswith('#'):
            continue
        m = ROW.fullmatch(line)
        if ended or not m or m[4] != current or int(m[1]) != len(sections[current]) + 1:
            raise ValueError()
        clock = int(m[2])
        rows = sections[current]
        # seq は CPU 別。clock が欠落、重複、逆行した記録では前後を決めない。
        if clock in clocks or (rows and clock <= rows[-1][0]):
            raise ValueError()
        clocks.add(clock)
        rows.append((clock, m[5], int(m[6], 16), int(m[7], 16), int(m[8], 16)))
    if seen != {'main', 'sub'} or not ended:
        raise ValueError()
    main = sections['main']
    start = next((i for i, e in enumerate(main) if 0xC000 <= e[4] <= 0xC0FF), None)
    if start is None:
        start = next((i for i, e in enumerate(main) if e[4] >= 0x8000), None)
    if start is None:
        raise ValueError()
    fc = [e for e in main[start:] if e[1:3] == ('IN', 0xFC)]
    fd = [e for e in sections['sub'] if e[1:3] == ('OUT', 0xFD)]
    return fc, fd


def summarize(data, arm):
    fc, fd = data
    if arm not in ('OO', 'SS') or len(fc) <= 76570:
        raise ValueError()
    times = [e[0] for e in fd]
    comparisons = []
    for e in fc:
        pos = bisect_left(times, e[0])
        comparisons.append((pos, pos > 0 and e[3] == fd[pos - 1][3]))
    rows = [f'arm {arm} fc={len(fc)} sub-fd-out={len(fd)}']
    for name, lo, hi in [('all', 0, len(fc)), ('76315-76827', 76315, 76828), ('76570-76827', 76570, 76828)]:
        valid = [(i, comparisons[i][1]) for i in range(lo, min(hi, len(fc))) if comparisons[i][0] > 0]
        different = [i for i, same in valid if not same]
        rows.append(f'latest arm={arm} range={name} compared={len(valid)} same={sum(s for _, s in valid)} first-differ={different[0] if different else "none"}')
    prev = next_ = neither = 0
    for i in range(76570, min(76828, len(fc))):
        pos, same = comparisons[i]
        if not pos or same:
            continue
        value = fc[i][3]
        if pos >= 2 and value == fd[pos - 2][3]:
            prev += 1
        elif pos < len(fd) and value == fd[pos][3]:
            next_ += 1
        else:
            neither += 1
    rows.append(f'stale arm={arm} range=76570-76827 prev={prev} next={next_} neither={neither}')
    pc = fc[76570][4]
    rows.append(f'main-pc arm={arm} index=76570 {pc:04X}' if pc >= 0x8000 else f'main-pc arm={arm} index=76570 rom')
    return rows


def main():
    try:
        class Parser(argparse.ArgumentParser):
            def error(self, message):
                raise ValueError()
        p = Parser(add_help=False)
        p.add_argument('log', type=Path)
        p.add_argument('--arm', required=True, choices=['OO', 'SS'])
        a = p.parse_args()
        print('\n'.join(summarize(read(a.log), a.arm)))
        return 0
    except Exception:
        return 1


if __name__ == '__main__':
    sys.exit(main())
