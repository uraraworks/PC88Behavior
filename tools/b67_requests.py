#!/usr/bin/env python3
"""窓内の要求を先頭バイトと形だけに変換する。"""
import argparse
from pathlib import Path
import sys
from b47_pio_handoff import ROW, END
from b39_sub_reg_compare import read as read_reg


def read(path):
    sections = {'main': [], 'sub': []}
    seen, clocks = set(), set()
    current, ended = None, False
    complete = True
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
            if ended or int(m[2]) != len(sections[current]):
                raise ValueError()
            complete &= int(m[1]) == 0
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
        rows.append((clock, m[5], int(m[6], 16), int(m[7], 16)))
    if seen != {'main', 'sub'} or not ended:
        raise ValueError()
    return sections, complete


def requests(main, offset, arm, window):
    groups, group = [], []
    fc = offset
    for event in main:
        kind, port, value = event[1:]
        if (kind, port) == ('IN', 0xFC):
            fc += 1
        if (kind, port) not in (('OUT', 0xFD), ('OUT', 0xFF), ('IN', 0xFE)):
            continue
        if (kind, port) == ('OUT', 0xFF) and value & 15 == 1:
            if any(e[1:3] == ('OUT', 0xFD) for e, _ in group):
                groups.append(group)
            group = []
        group.append((event, fc))
    if any(e[1:3] == ('OUT', 0xFD) for e, _ in group):
        groups.append(group)
    rows = []
    for group in groups:
        positions = [i for i, (e, _) in enumerate(group) if e[1:3] == ('OUT', 0xFD)]
        units = []
        for i, pos in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(group)
            controls = [e[1:3] for e, _ in group[pos + 1:end]]
            if ('OUT', 0xFF) not in controls:
                raise ValueError()
            units.append(controls)
        single = paired = i = 0
        while i < len(units):
            controls = units[i]
            pair = (i + 1 < len(units) and controls[0] == ('OUT', 0xFF)
                    and ('IN', 0xFE) in controls[1:]
                    and units[i + 1].count(('OUT', 0xFF)) == 1)
            if pair:
                paired += 2
            else:
                single += 1
            i += 2 if pair else 1
        shape = '+'.join(x for x in (f'{single}s' if single else '', f'{paired}p' if paired else '') if x)
        first, count = group[positions[0]]
        # 要求開始の区切りより前の FC 数。区切りが窓外なら先頭書込時を使う。
        count = group[0][1] if group[0][0][1:3] == ('OUT', 0xFF) else count
        rows.append(f'req {arm} {window} {len(rows)+1} head={first[3]:02X} size={len(positions)} shape={shape} fc={count}')
    return rows


def main():
    try:
        class Parser(argparse.ArgumentParser):
            def error(self, message):
                raise ValueError()
        p = Parser(add_help=False)
        p.add_argument('log', type=Path)
        p.add_argument('--sub-reg-log', required=True, type=Path)
        p.add_argument('--arm', required=True, choices=('O', 'S'))
        p.add_argument('--window', required=True, type=int)
        a = p.parse_args()
        sections, complete = read(a.log)
        reg = read_reg(a.sub_reg_log)
        if complete:
            offset = len(reg['F']) - sum(e[1:3] == ('IN', 0xFC) for e in sections['main'])
            if offset < 0:
                raise ValueError()
            rows = requests(sections['main'], offset, a.arm, a.window)
            if rows:
                print('\n'.join(rows))
        return 0
    except Exception:
        return 1


if __name__ == '__main__':
    sys.exit(main())
