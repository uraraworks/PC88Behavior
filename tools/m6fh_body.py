#!/usr/bin/env python3
"""m6f-h: D88 のエントリと FAT 鎖をたどり、本体を上限付きで候補照合する。"""
from __future__ import annotations

import json
import mmap
import struct
from pathlib import Path

import m6fh_script as script


class BodyError(ValueError):
    pass


class Image:
    def __init__(self, data: bytes):
        self.data = memoryview(data)
        if len(data) < 688 or struct.unpack_from('<I', data, 28)[0] != len(data):
            raise BodyError("D88外形")
        self.sectors: dict[tuple[int, int, int], tuple[int, int]] = {}
        offsets = sorted(set(struct.unpack_from('<I', data, 32 + 4*i)[0] for i in range(164)) - {0})
        if any(o < 688 or o >= len(data) for o in offsets):
            raise BodyError("トラック表")
        for n, start in enumerate(offsets):
            end = offsets[n+1] if n+1 < len(offsets) else len(data)
            pos = start
            while pos < end:
                if pos + 16 > end:
                    raise BodyError("セクタ見出し")
                size = struct.unpack_from('<H', data, pos+14)[0]
                key = tuple(self.data[pos:pos+3])
                pos += 16
                if size != 256 or pos+size > end or key in self.sectors:
                    raise BodyError("セクタ構造")
                self.sectors[key] = (pos, pos+size)
                pos += size

    def sector(self, c: int, h: int, r: int):
        return self.sector_prefix((c,h,r), 256)

    def sector_prefix(self, coord: tuple[int,int,int], limit: int):
        if not (0 <= limit <= 256):
            raise BodyError('セクタ読取上限')
        try:
            start, _ = self.sectors[coord]
        except KeyError:
            raise BodyError('セクタ欠落') from None
        return self.data[start:start+limit]


def chain(image: Image, name: bytes, allow_empty: bool = False) -> tuple[list[tuple[int,int,int]], int]:
    entry = None
    unused = False
    for r in range(1, 13):
        sector = image.sector(18, 1, r)
        for off in range(0, 256, 16):
            first = sector[off]
            if first == 0xff:
                unused = True
                break
            if first == 0 or first != name[0]:
                continue
            if bytes(sector[off:off+9]).rstrip(b' ') == name:
                entry = bytes(sector[off:off+11])
                break
        if entry is not None or unused:
            break
    if entry is None:
        raise BodyError("エントリなし")
    if entry[9] != 0:
        raise BodyError("G6_種別")
    fat = image.sector(18, 1, 14)[:160]
    if any(fat != image.sector(18, 1, r)[:160] for r in (15, 16)):
        raise BodyError('割り当て表の複製')
    unit = entry[10]
    if allow_empty and unit == 0xff:
        return [], 0
    seen = set()
    units = []
    while True:
        if unit >= 160 or unit in seen:
            raise BodyError("鎖")
        seen.add(unit)
        value = fat[unit]
        units.append(unit)
        if value < 160:
            unit = value
        elif 0xc0 <= value <= 0xc8:  # 0xC0=使ったセクタ数0（空のファイル、m6f-h 1回目で判明）
            used_last = value-0xc0
            break
        else:
            raise BodyError("終端")
    coords = []
    for index, unit in enumerate(units):
        count = used_last if index == len(units)-1 else 8
        for sub in range(count):
            linear = unit*8+sub
            coords.append((linear//32, (linear//16)%2, linear%16+1))
    return coords, len(coords)


def read_bounded(image: Image, coords: list[tuple[int,int,int]], limit: int) -> tuple[bytes,int]:
    """本体から limit バイトだけ読む。最大位置は0始まり、空なら -1。"""
    if limit < 0:
        raise BodyError("読取上限")
    out = bytearray()
    for coord in coords:
        remaining = limit-len(out)
        if remaining <= 0:
            break
        out.extend(image.sector_prefix(coord, min(remaining, 256)))
    return bytes(out), len(out)-1


def compare(image_data: bytes, arm: str) -> dict:
    image = Image(image_data)
    coords, used_sectors = chain(image, script.NAMES[arm], allow_empty=(arm == "H-0"))
    results = {}
    max_pos = -1
    for cid in script.candidate_ids(arm):
        expected = script.predicted(arm, cid)
        # 全候補で予測長+1を上限とする。H-0 EMPTY は本体を読まない。
        limit = 0 if cid == 'EMPTY' else len(expected) + 1
        actual, pos = read_bounded(image, coords, limit)
        max_pos = max(max_pos, pos)
        if cid == 'EMPTY':
            match = used_sectors == 0
            mismatch = None
        else:
            mismatch = next((i for i, (a, b) in enumerate(zip(actual, expected)) if a != b), None)
            if mismatch is None and len(actual) < len(expected):
                mismatch = len(actual)
            match = mismatch is None
            if cid.endswith('_NONE') and match:
                boundary = used_sectors * 256
                if len(expected) == boundary:
                    pass  # 次のバイトは使ったセクタの範囲外。
                elif len(expected) < boundary and len(actual) > len(expected):
                    match = actual[len(expected)] not in (0x1a, 0x00)
                    if not match:
                        mismatch = len(expected)
                else:
                    match = False
        results[cid] = {'match': match, 'first_mismatch': mismatch}
    if arm == 'H-0':
        empty_match = used_sectors == 0 or not (results['1A']['match'] or results['00']['match'])
        results['EMPTY'] = {'match': empty_match and not (results['1A']['match'] or results['00']['match']),
                            'first_mismatch': None}
    return {'candidates': results, 'used_sectors': used_sectors, 'g7_max_position': max_pos,
            'g7_limit': max((len(script.predicted(arm, c)) + (0 if c == 'EMPTY' else 1)) for c in script.candidate_ids(arm)) - 1}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True, type=Path)
    ap.add_argument('--arm', required=True, choices=script.ARMS)
    args = ap.parse_args()
    try:
        # mmap でD88全体をコピーせず、構造位置と上限内の本体位置だけ参照する。
        with args.image.open('rb') as source:
            with mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
                result = compare(mapped, args.arm)
    except (OSError, BodyError, ValueError, BufferError):
        print(json.dumps({'gate': 'NG', 'reason': 'body_read'}))
        return 1
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
