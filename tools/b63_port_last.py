#!/usr/bin/env python3
"""main の OUT をポート別に数え、最終値の一致だけを出す。"""
import sys
from b8_io_values import ROW, END


def read(path):
    ports = {}
    found = ended = False
    totals = None
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.rstrip('\r\n')
            if not found:
                if line.strip() == '# main':
                    found = True
                continue
            if line.strip() == '# sub':
                ended = True
                break
            m = END.fullmatch(line)
            if m:
                if totals is not None:
                    raise ValueError
                totals = tuple(map(int, m.groups()))
            elif not line.strip() or line.lstrip().startswith('#'):
                continue
            else:
                m = ROW.fullmatch(line)
                if not m or totals is not None:
                    raise ValueError
                direction, port, value, _ = m.groups()
                if direction == 'OUT':
                    p = int(port, 16) & 255
                    count, _ = ports.get(p, (0, None))
                    ports[p] = (count + 1, int(value, 16))
    if not found or not ended or totals is None or totals[0]:
        raise ValueError
    return ports


def compare(a, b):
    lines = []
    for port in sorted(a.keys() | b.keys()):
        ac, av = a.get(port, (0, None))
        bc, bv = b.get(port, (0, None))
        last = 'none' if not ac or not bc else ('same' if av == bv else 'differ')
        lines.append(f'port {port:02X} out-count={ac} {bc} last={last}')
    return lines


def main():
    if len(sys.argv) != 3:
        return 1
    try:
        lines = compare(read(sys.argv[1]), read(sys.argv[2]))
    except (OSError, ValueError):
        print('ログを読み取れません', file=sys.stderr)
        return 1
    print('\n'.join(lines), end='\n' if lines else '')
    return 0


if __name__ == '__main__':
    sys.exit(main())
