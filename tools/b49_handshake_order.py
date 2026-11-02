#!/usr/bin/env python3
"""共通 clock の差と匿名の発行元で受け渡しの順を表す。"""
import argparse
from pathlib import Path
import sys

from b47_pio_handoff import ROW, END


def read(path, offset=None, window=None, tail=0):
    sections = {'main': [], 'sub': []}
    seen, clocks = set(), set()
    current, ended = None, False
    with path.open(encoding='utf-8') as source:
        for line in source:
            line = line.rstrip('\n')
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
            rows = sections[current]
            if ended or not m or m[4] != current or int(m[1]) != len(rows) + 1:
                raise ValueError()
            clock = int(m[2])
            if clock in clocks or (rows and clock <= rows[-1][0]):
                raise ValueError()
            clocks.add(clock)
            rows.append((clock, current, m[5], int(m[6], 16), int(m[7], 16), int(m[8], 16)))
    if seen != {'main', 'sub'} or not ended:
        raise ValueError()
    main = sections['main']
    if window is not None:
        fc = [e for e in main if e[2:4] == ('IN', 0xFC)]
        lo_fc, hi_fc = window
        lo_fc -= offset
        hi_fc -= offset
        if lo_fc < 0 or hi_fc < lo_fc or hi_fc >= len(fc):
            raise ValueError()
        events = sorted(sections['main'] + sections['sub'])
        indices = {e[0]: i for i, e in enumerate(events)}
        lo, hi = indices[fc[lo_fc][0]], indices[fc[hi_fc][0]] + tail
        if hi >= len(events):
            raise ValueError()
        return events[lo:hi + 1]
    start = next((i for i, e in enumerate(main) if 0xC000 <= e[5] <= 0xC0FF), None)
    if start is None:
        start = next((i for i, e in enumerate(main) if e[5] >= 0x8000), None)
    if start is None:
        raise ValueError()
    fc = [e for e in main[start:] if e[2:4] == ('IN', 0xFC)]
    if len(fc) <= 76573:
        raise ValueError()
    events = sorted(sections['main'] + sections['sub'])
    indices = {e[0]: i for i, e in enumerate(events)}
    lo, hi = indices[fc[76568][0]] - 40, indices[fc[76573][0]] + 20
    if lo < 0 or hi >= len(events):
        raise ValueError()
    return events[lo:hi + 1]


def summarize(events, arm):
    if arm not in ('OO', 'SS') or not events:
        raise ValueError()
    issuers, rows = {}, []
    previous_clock = events[0][0]
    previous, count = None, 0
    for clock, cpu, kind, port, value, pc in events:
        key = (cpu, pc)
        if key not in issuers:
            issuers[key] = len(issuers) + 1
        control = (kind, port) in (('IN', 0xFE), ('OUT', 0xFF), ('IN', 0xFF), ('OUT', 0xFE))
        row = f'E {arm} {clock - previous_clock} {cpu} {kind} ${port:02X} {issuers[key]} {value & 15:X}' if control else f'E {arm} {clock - previous_clock} {cpu} {kind} ${port:02X} {issuers[key]} -'
        previous_clock = clock
        if row == previous:
            count += 1
        else:
            if previous is not None:
                rows.append(previous + (f' x{count}' if count > 1 else ''))
            previous, count = row, 1
    rows.append(previous + (f' x{count}' if count > 1 else ''))
    return rows


def main():
    try:
        class Parser(argparse.ArgumentParser):
            def error(self, message):
                raise ValueError()
        parser = Parser(add_help=False)
        parser.add_argument('log', type=Path)
        parser.add_argument('--arm', required=True, choices=('OO', 'SS'))
        parser.add_argument('--offset', type=int)
        parser.add_argument('--window', nargs=2, type=int)
        parser.add_argument('--tail', type=int, default=0)
        args = parser.parse_args()
        if (args.window is None) != (args.offset is None) or args.tail < 0 or (args.window is None and args.tail):
            raise ValueError()
        print('\n'.join(summarize(read(args.log, args.offset, args.window, args.tail), args.arm)))
        return 0
    except Exception:
        return 1


if __name__ == '__main__':
    sys.exit(main())
