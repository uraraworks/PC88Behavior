#!/usr/bin/env python3
"""D88像からIDの (C,H,R) が一致する256バイトのデータ部を取り出す。"""

import argparse
import pathlib
import struct
import sys

D88_HEADER_SIZE = 32
TRACK_COUNT = 164
TRACK_TABLE_OFFSET = D88_HEADER_SIZE
TRACK_TABLE_SIZE = TRACK_COUNT * 4
SECTOR_HEADER_SIZE = 16
EXPECTED_SECTOR_SIZE = 256


class D88Error(ValueError):
    """D88像の構造または要求座標が不正。"""


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


class D88Reader:
    """像を一度だけ走査し、座標からデータ部を引く独立読取器。"""

    def __init__(self, image: bytes):
        self._sectors = {}
        minimum = D88_HEADER_SIZE + TRACK_TABLE_SIZE
        if len(image) < minimum:
            raise D88Error("D88像がヘッダとトラック表より短い")
        declared_size = _u32(image, 28)
        if declared_size != len(image):
            raise D88Error("D88ヘッダの総サイズと実サイズが一致しない")

        track_offsets = [
            _u32(image, TRACK_TABLE_OFFSET + index * 4)
            for index in range(TRACK_COUNT)
        ]
        nonzero_offsets = sorted(set(offset for offset in track_offsets if offset))
        if any(offset < minimum or offset >= len(image) for offset in nonzero_offsets):
            raise D88Error("トラックオフセットがD88像の範囲外")

        for index, start in enumerate(nonzero_offsets):
            end = (nonzero_offsets[index + 1]
                   if index + 1 < len(nonzero_offsets) else len(image))
            pos = start
            sector_count = None
            seen = 0
            while pos < end:
                if pos + SECTOR_HEADER_SIZE > end:
                    raise D88Error("セクタヘッダがトラック境界を越える")
                count = _u16(image, pos + 4)
                size = _u16(image, pos + 14)
                if count == 0 or size == 0:
                    raise D88Error("セクタ数またはデータ長が0")
                if sector_count is None:
                    sector_count = count
                elif count != sector_count:
                    raise D88Error("同一トラック内でセクタ数が一致しない")
                data_start = pos + SECTOR_HEADER_SIZE
                data_end = data_start + size
                if data_end > end:
                    raise D88Error("セクタデータがトラック境界を越える")
                key = (image[pos], image[pos + 1], image[pos + 2])
                if key in self._sectors:
                    raise D88Error("同じ(C,H,R)のセクタが複数ある")
                self._sectors[key] = image[data_start:data_end]
                seen += 1
                pos = data_end
            if sector_count is not None and seen != sector_count:
                raise D88Error("トラック見出しのセクタ数と実数が一致しない")

    def read_sector(self, cyl: int, head: int, sector: int) -> bytes:
        key = (cyl, head, sector)
        if key not in self._sectors:
            raise D88Error("一致セクタ数が1でない: 0")
        payload = self._sectors[key]
        if len(payload) != EXPECTED_SECTOR_SIZE:
            raise D88Error("一致セクタのデータ長が256バイトでない")
        return payload


def read_sector(image: bytes, cyl: int, head: int, sector: int) -> bytes:
    """D88像を直接走査し、指定IDに一致する唯一の256バイトを返す。"""
    return D88Reader(image).read_sector(cyl, head, sector)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=pathlib.Path)
    parser.add_argument("cyl", type=lambda value: int(value, 0))
    parser.add_argument("head", type=lambda value: int(value, 0))
    parser.add_argument("sector", type=lambda value: int(value, 0))
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    try:
        payload = read_sector(args.image.read_bytes(), args.cyl, args.head, args.sector)
    except (OSError, D88Error) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    args.output.write_bytes(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
