#!/usr/bin/env python3
"""要求の先頭と受信元の領域、読みの一致数だけを出す。"""
import argparse
from pathlib import Path
import sys
from b47_pio_handoff import ROW, END


def read(path):
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
    if len(fc) <= 76572:
        raise ValueError()
    return sections, fc


def bursts(data):
    sections, fc = data
    main = [e for e in sections['main'] if fc[76569][0] < e[0] < fc[76570][0]
            and e[1:3] in (('OUT', 0xFD), ('OUT', 0xFF), ('IN', 0xFE))]
    # FF の下位 4 ビットが 1 の書き込みで要求を区切る。
    requests, request = [], []
    for event in main:
        request.append(event)
        if event[1:3] == ('OUT', 0xFF) and event[3] & 0x0F == 1:
            requests.append(request)
            request = []
    if request:
        raise ValueError()
    result = []
    for request in requests:
        fdpos = [i for i, e in enumerate(request) if e[1:3] == ('OUT', 0xFD)]
        if not fdpos:
            raise ValueError()
        units = []
        for n, pos in enumerate(fdpos):
            end = fdpos[n + 1] if n + 1 < len(fdpos) else len(request)
            controls = [e[1:3] for e in request[pos + 1:end]]
            if ('OUT', 0xFF) not in controls:
                raise ValueError()
            units.append((pos, end, controls))
        transfers = []
        n = 0
        while n < len(units):
            pos, end, controls = units[n]
            paired = (n + 1 < len(units) and controls[0] == ('OUT', 0xFF)
                      and ('IN', 0xFE) in controls[1:]
                      and units[n + 1][2].count(('OUT', 0xFF)) == 1)
            if paired:
                end = units[n + 1][1]
            transfers.append(('paired' if paired else 'single', request[pos][0],
                              request[end][0] if end < len(request) else request[-1][0] + 1))
            n += 2 if paired else 1
        single = sum(1 for mode, _, _ in transfers if mode == 'single')
        paired = len(fdpos) - single
        shape = '+'.join(part for part in (f'{single}s' if single else '',
                                            f'{paired}p' if paired else '') if part)
        result.append((len(fdpos), shape, request[fdpos[0]][3], transfers))
    return result


def summarize(official, self_data):
    groups = bursts(official)
    rows = [f'burst {i} size={size} shape={shape} head={head:02X}'
            for i, (size, shape, head, _) in enumerate(groups, 1)]
    readers = set()
    for _, _, _, transfers in groups:
        for mode, lo, hi in transfers:
            for e in official[0]['sub']:
                if lo < e[0] < hi and e[1:3] == ('IN', 0xFC):
                    readers.add((mode, 'hi' if e[4] >= 0x2000 else 'lo'))
    for mode in ('single', 'paired'):
        for region in ('hi', 'lo'):
            if (mode, region) in readers:
                rows.append(f'sub-reader {mode} {region}')
    a, b = official[1], self_data[1]
    for delta in range(-8, 9):
        indices = range(max(76572, -delta), min(len(a), len(b) - delta))
        compared = len(indices)
        same = sum(a[i][3] == b[i + delta][3] for i in indices)
        rows.append(f'shift {delta:+d} compared={compared} same={same}')
    return rows


def main():
    try:
        class Parser(argparse.ArgumentParser):
            def error(self, message):
                raise ValueError()
        p = Parser(add_help=False)
        p.add_argument('official', type=Path)
        p.add_argument('self_log', type=Path)
        args = p.parse_args()
        print('\n'.join(summarize(read(args.official), read(args.self_log))))
        return 0
    except Exception:
        return 1


if __name__ == '__main__':
    sys.exit(main())
