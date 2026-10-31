#!/usr/bin/env python3
"""B9: ディスク内容を公開せず、座標と FE ビット差を記録する。"""
import argparse
import bisect
import re
import sys

from b8_io_values import parse_log

PATTERNS = [re.compile(p) for p in (
    r'# 識別子: G1', r'# 腕: (?:OO|OS|SS)',
    r'block [0-9]+ sector [0-9]+ [0-9]+ [0-9]+ matches=[0-9]+',
    r'block [0-9]+ within [0-9]+ [0-9]+ [0-9]+ offset=[0-9]+ matches=[0-9]+',
    r'block [0-9]+ (?:uniform|none)',
    r'fe-bit (?:OS|SS) [0-7] differ=[0-9]+ compared=[0-9]+')]


def checked(lines):
    bad = sum(not any(p.fullmatch(line) for p in PATTERNS) for line in lines)
    if bad:
        print(bad, file=sys.stderr)
    return not bad


def read_sectors(image):
    """先頭のトラック表に記載されたセクタだけを読み取る。"""
    if len(image) < 32 + 4:
        raise ValueError
    total_size = int.from_bytes(image[28:32], 'little')
    image_end = min(total_size, len(image)) if total_size else len(image)
    # 表は最小のオフセットの手前で終わる。その先はトラックの本体なので読まない。
    first = image_end
    table_end = 32
    while table_end < min(first, 32 + 164 * 4) and table_end + 4 <= image_end:
        value = int.from_bytes(image[table_end:table_end + 4], 'little')
        table_end += 4
        if value:
            if value <= 32:
                raise ValueError
            first = min(first, value)
    offsets = sorted(set(int.from_bytes(image[i:i + 4], 'little')
                         for i in range(32, table_end, 4)) - {0})
    if not offsets:
        raise ValueError
    sectors = {}
    for index, start in enumerate(offsets):
        if start < table_end or start >= image_end:
            continue
        end = min(offsets[index + 1] if index + 1 < len(offsets) else image_end, image_end)
        pos = start
        count = None
        seen = 0
        while pos + 16 <= end and (count is None or seen < count):
            if count is None:
                count = int.from_bytes(image[pos + 4:pos + 6], 'little')
                if not count:
                    break
            size = int.from_bytes(image[pos + 14:pos + 16], 'little')
            data_end = pos + 16 + size
            if not size or data_end > end:
                break
            key = tuple(image[pos:pos + 3])
            sectors.setdefault(key, image[pos + 16:data_end])
            pos = data_end
            seen += 1
    return sectors


def coordinates(values, sectors, arm):
    if len(values) < 3840:
        raise ValueError
    # トラックのオフセット順、各トラックの記録順に格納する。
    items = list(sectors.items())
    starts = []
    joined = bytearray()
    for _, data in items:
        starts.append(len(joined))
        joined.extend(data)
    joined = bytes(joined)
    lines = ['# 識別子: G1', f'# 腕: {arm}']
    for index in range(15):
        block = bytes(values[index * 256:(index + 1) * 256])
        prefix = f'block {index}'
        if len(set(block)) == 1:
            lines.append(f'{prefix} uniform')
            continue
        exact = sorted(key for key, data in items if len(data) == 256 and data == block)
        if exact:
            c, h, r = exact[0]
            lines.append(f'{prefix} sector {c} {h} {r} matches={len(exact)}')
            continue
        positions = []
        pos = joined.find(block)
        while pos != -1:
            positions.append(pos)
            pos = joined.find(block, pos + 1)
        if positions:
            i = bisect.bisect_right(starts, positions[0]) - 1
            c, h, r = items[i][0]
            lines.append(f'{prefix} within {c} {h} {r} offset={positions[0] - starts[i]} matches={len(positions)}')
        else:
            lines.append(f'{prefix} none')
    return lines


def fe_bits(oo, os_, ss):
    lines = ['# 識別子: G1']
    for name, other in (('OS', os_), ('SS', ss)):
        count = min(len(oo), len(other))
        for bit in range(8):
            differ = sum(bool((oo[i][0][0] ^ other[i][0][0]) & (1 << bit)) for i in range(count))
            lines.append(f'fe-bit {name} {bit} differ={differ} compared={count}')
    return lines


def read_log(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return parse_log(f)


def selftest():
    import contextlib
    import io
    import struct
    import tempfile
    from pathlib import Path

    a = bytes(range(256))
    b = bytes((i * 7 + 3) % 256 for i in range(300))
    c = bytes((i * 11 + 9) % 256 for i in range(300))
    # トラック順と座標順を逆にし、セクタサイズも混在させる。
    entries = [((2, 0, 3), a), ((1, 0, 2), a), ((3, 1, 1), b), ((3, 1, 2), c), ((4, 0, 1), b), ((4, 0, 2), c)]
    image = bytearray(688)
    struct.pack_into('<I', image, 32, 688)
    for (cyl, head, sector), data in entries:
        header = bytearray(16)
        header[:4] = bytes((cyl, head, sector, 1))
        struct.pack_into('<H', header, 4, len(entries))
        struct.pack_into('<H', header, 14, len(data))
        image.extend(header + data)
    struct.pack_into('<I', image, 28, len(image))
    # 160 件の表で末尾直後の track 0 見出しをオフセットと誤読しない。
    with tempfile.TemporaryDirectory() as tmp:
        disk = Path(tmp) / 'synthetic.d88'
        disk.write_bytes(image)
        sectors = read_sectors(disk.read_bytes())
        real_header = bytearray(672)
        struct.pack_into('<I', real_header, 32, 672)
        real_header.extend(image[688:])
        struct.pack_into('<I', real_header, 28, len(real_header))
        # 表の直後の見出しを小さいオフセットとして読むと、ここで止まるか座標が狂う。
        real_header[672:676] = bytes((16, 0, 0, 0))
        real_sectors = read_sectors(real_header)
        assert (16, 0, 0) in real_sectors and len(real_sectors) == len(sectors)
        real_header[672:676] = image[688:692]
        assert read_sectors(real_header) == sectors
        # 後続像だけにあるブロックが座標に出ないことを確認する。
        later = bytearray(image)
        missing = bytes((i * 13 + 17) % 256 for i in range(256))
        later[image.index(a):image.index(a) + len(a)] = missing
        disk.write_bytes(bytes(image) + bytes(later))
        combined = disk.read_bytes()
        combined_sectors = read_sectors(combined)
        small = bytearray(image)
        struct.pack_into('<I', small, 28, 688)
        # 総サイズより先は別の像とみなして読まない。
        assert read_sectors(small) == {}
        assert read_sectors(image[:-1]) == dict(list(sectors.items())[:-1])
        duplicate = bytearray(image)
        duplicate[688 + 16 + len(a):688 + 16 + len(a) + 3] = bytes(entries[0][0])
        assert read_sectors(duplicate)[entries[0][0]] == a
    shifted = b[100:] + c[:56]
    blocks = [a, shifted, missing, bytes([0xA5]) * 256] + [a] * 11
    def log(fc, fe):
        events = [('IN', '00FC', v, 'C000') for v in fc]
        events += [('IN', '00FE', v, 'C000') for v in fe]
        return ['# main'] + [f'{i} {i} 0 main {d} {p} {v:02X} {pc}' for i, (d, p, v, pc) in enumerate(events)] + ['# 取りこぼし: 0件 / 総イベント数: 0件', '# sub']
    raw = parse_log(log(b''.join(blocks), [0, 0, 3, 4]))
    fc = [item[0][0] for item in raw[('IN', '00FC', 'raw')]]
    out = coordinates(fc, sectors, 'OO')
    expected = ['block 0 sector 1 0 2 matches=2', 'block 1 within 3 1 1 offset=100 matches=2', 'block 2 none', 'block 3 uniform']
    def verify(lines):
        assert lines[2:6] == expected
    verify(out)
    combined_out = coordinates(fc, combined_sectors, 'OO')
    verify(combined_out)
    assert combined_out[4] == 'block 2 none'
    faulty = out.copy(); faulty[2] = 'block 0 sector 2 0 3 matches=2'
    try:
        verify(faulty)
    except AssertionError:
        pass
    else:
        raise AssertionError
    fe = raw[('IN', '00FE', 'collapsed')]
    other = parse_log(log(b'', [1, 2, 4]))[('IN', '00FE', 'collapsed')]
    bits = fe_bits(fe, other, other)
    assert 'fe-bit OS 0 differ=2 compared=3' in bits
    assert 'fe-bit OS 1 differ=0 compared=3' in bits
    assert 'fe-bit OS 2 differ=0 compared=3' in bits
    assert checked(out + bits) and all('A5' not in line for line in out + bits)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert not checked([out[2] + ' A5'])
    assert err.getvalue() == '1\n'
    try:
        parse_log(['# main', '0 0 main IN 00FC A5 C000', '# 取りこぼし: 0件 / 総イベント数: 1件', '# sub'])
    except ValueError:
        pass
    else:
        raise AssertionError
    print('OK: B9 自己検査')


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        print('1', file=sys.stderr)
        self.exit(1)


def main():
    parser = SafeParser()
    parser.add_argument('--selftest', action='store_true')
    sub = parser.add_subparsers(dest='command')
    coord = sub.add_parser('coordinates')
    coord.add_argument('log'); coord.add_argument('d88', nargs='?')
    coord.add_argument('--parse-only', action='store_true')
    coord.add_argument('--arm', choices=['OO', 'OS', 'SS'])
    coord.add_argument('--id', choices=['G1']); coord.add_argument('--out')
    fe = sub.add_parser('fe-bits')
    fe.add_argument('oo'); fe.add_argument('os'); fe.add_argument('ss')
    fe.add_argument('--id', required=True, choices=['G1']); fe.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.selftest and args.command is None:
        selftest()
        return 0
    try:
        if args.command == 'coordinates':
            if args.parse_only:
                path = args.d88 or args.log
            else:
                if not all((args.d88, args.arm, args.id, args.out)):
                    raise ValueError
                path = args.d88
            with open(path, 'rb') as f:
                sectors = read_sectors(f.read())
            if args.parse_only:
                print(f'sectors={len(sectors)} size256={sum(len(data) == 256 for data in sectors.values())}')
                return 0
            raw = read_log(args.log)
            values = [item[0][0] for item in raw[('IN', '00FC', 'raw')]]
            lines = coordinates(values, sectors, args.arm)
        elif args.command == 'fe-bits':
            key = ('IN', '00FE', 'collapsed')
            lines = fe_bits(*(read_log(path)[key] for path in (args.oo, args.os, args.ss)))
        else:
            raise ValueError
        if not checked(lines):
            return 1
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    except (OSError, ValueError, UnicodeError):
        print('1', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
