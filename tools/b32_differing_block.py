#!/usr/bin/env python3
"""B32: 最初の差と直前の要求を、ディスク照合後に記録する。"""
import argparse
import itertools
import re
import sys

from b22_differing_replies import ROW, start_position
from b9_sector_coordinates import read_sectors

PATTERNS = [re.compile(p) for p in (
    r'# 識別子: G1', r'first-diff index=[0-9]+ run=[0-9]+',
    r'request same=(?:yes|no) length=[0-9]+ bytes=(?:[0-9A-F]{2}(?: [0-9A-F]{2})*)?',
    r'(?:official|self) body=(?:disk [0-9]+ [0-9]+ [0-9]+ [0-9]+|none)',
    r'(?:official|self) head=[0-9A-F]{2}(?: [0-9A-F]{2}){7}',
)]


def checked(lines):
    return all(any(p.fullmatch(line) for p in PATTERNS) for line in lines)


def collect(stream):
    start = start_position(stream)
    stream.seek(0)
    values, requests = [], []
    current, last = [], []
    running = False
    for line in itertools.islice(stream, start, None):
        if line.strip() == '# sub':
            break
        m = ROW.fullmatch(line.rstrip('\r\n'))
        if not m:
            continue
        direction, port, value = m.group(1), m.group(2).upper(), int(m.group(3), 16)
        if direction == 'OUT' and port == '00FD':
            if not running:
                current = []
            current.append(value)
            last = current
            running = True
        else:
            running = False
        if direction == 'IN' and port == '00FC':
            values.append(value)
            requests.append(tuple(last))
    return bytes(values), requests


def locate(values, k, sectors):
    # 両方の候補を調べられない場合は値を公開しない。
    if len(values) < k + 257:
        raise ValueError
    for shift in (0, 1):
        candidate = values[k + shift:k + shift + 256]
        for (c, h, r), data in sectors.items():
            offset = data.find(candidate)
            if offset >= 0:
                return f'disk {c} {h} {r} {offset}'
    return 'none'


def compare(a, b, sectors, ident):
    left, lr = collect(a)
    right, rr = collect(b)
    count = min(len(left), len(right))
    k = next((i for i in range(count) if left[i] != right[i]), None)
    if k is None:
        raise ValueError
    end = k
    while end < count and left[end] != right[end]:
        end += 1
    if end == count:
        raise ValueError
    # 値の整形に先立ち、両方の照合を完了する。
    official = locate(left, k, sectors)
    self_body = locate(right, k, sectors)
    req = lr[k]
    lines = [f'# 識別子: {ident}', f'first-diff index={k} run={end-k}',
             f'request same={"yes" if req == rr[k] else "no"} length={len(req)} bytes=' +
             ' '.join(f'{v:02X}' for v in req[-64:]),
             f'official body={official}', f'self body={self_body}']
    if official == self_body == 'none':
        lines += ['official head=' + ' '.join(f'{v:02X}' for v in left[k:k+8]),
                  'self head=' + ' '.join(f'{v:02X}' for v in right[k:k+8])]
    return lines


def selftest():
    import io
    import struct

    def log(values, request, marker=0xED):
        events = [('IN', '0010', marker, '1234'), ('IN', '0010', marker, 'C000')]
        events += [('OUT', '00FD', v, 'C001') for v in request]
        events += [('IN', '00FC', v, 'C001') for v in values]
        return io.StringIO('# main\n' + ''.join(
            f'{i} {i} 0 main {d} {p} {v:02X} {pc}\n'
            for i, (d, p, v, pc) in enumerate(events)) +
            '# 取りこぼし: 0件 / 総イベント数: 999件\n# sub\n')

    body = bytes((i * 13 + 7) % 256 for i in range(256))
    image = bytearray(688)
    struct.pack_into('<I', image, 32, 688)
    header = bytearray(16)
    header[:3] = bytes((2, 1, 3))
    struct.pack_into('<H', header, 4, 1)
    struct.pack_into('<H', header, 14, 300)
    image.extend(header + bytes([0xEE] * 11) + body + bytes([0xEE] * 33))
    struct.pack_into('<I', image, 28, len(image))
    sectors = read_sectors(image)
    req = list(range(70))
    left = bytes([0xAA] * 5) + bytes([0xA1]) + body + bytes([0xCC] * 10)
    right = bytes([0xAA] * 5) + bytes(v ^ 0xFF for v in left[5:262]) + bytes([0xCC] * 10)
    result = compare(log(left, req), log(right, req), sectors, 'G1')
    assert checked(result)
    assert result[1] == 'first-diff index=5 run=257'
    assert result[2] == 'request same=yes length=70 bytes=' + ' '.join(f'{v:02X}' for v in req[-64:])
    assert result[3:] == ['official body=disk 2 1 3 11', 'self body=none']
    assert all('ED' not in line and 'head=' not in line for line in result)
    other = compare(log(left, req), log(right, req[:-1]), {(0, 0, 1): bytes([0xEF] * 300)}, 'G1')
    assert checked(other) and 'same=no' in other[2]
    assert other[3:5] == ['official body=none', 'self body=none']
    assert other[5] == 'official head=' + ' '.join(f'{v:02X}' for v in left[5:13])
    assert other[6] == 'self head=' + ' '.join(f'{v:02X}' for v in right[5:13])
    assert all('ED' not in line for line in other)
    assert not checked(result + ['official head=ED'])
    for bad in (log(left, req).getvalue().replace('0 0 0 main', '0 0 main', 1),
                log(left[:20], req).getvalue()):
        try:
            compare(io.StringIO(bad), log(right, req), sectors, 'G1')
        except ValueError:
            pass
        else:
            raise AssertionError
    # 検査側が壊れた結果を拒否することを確認する。
    faulty = result.copy(); faulty[1] = 'first-diff index=6 run=257'
    try:
        assert faulty[1] == 'first-diff index=5 run=257'
    except AssertionError:
        pass
    else:
        raise AssertionError
    print('OK: B32 自己検査')


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        print('1', file=sys.stderr)
        self.exit(1)


def main():
    parser = SafeParser()
    parser.add_argument('--selftest', action='store_true')
    sub = parser.add_subparsers(dest='command')
    c = sub.add_parser('compare')
    c.add_argument('official'); c.add_argument('self_log'); c.add_argument('d88')
    c.add_argument('--id', required=True, choices=['G1']); c.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.selftest and args.command is None:
        selftest()
        return 0
    try:
        if args.command != 'compare' or args.selftest:
            raise ValueError
        with open(args.official, encoding='utf-8', errors='replace') as a, open(args.self_log, encoding='utf-8', errors='replace') as b, open(args.d88, 'rb') as disk:
            sectors = read_sectors(disk.read())
            if not sectors:
                raise ValueError
            lines = compare(a, b, sectors, args.id)
        if not checked(lines):
            raise ValueError
        with open(args.out, 'w', encoding='utf-8') as output:
            output.write('\n'.join(lines) + '\n')
    except Exception:
        print('1', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
