#!/usr/bin/env python3
"""公開D88規則だけから空のN88-BASIC 2Dデータディスクを生成・検査する。

公式媒体は入力しない。形状と初期値はGPL第三者実装QUASI88の公開
``src/image.c`` にある ``d88_append_blank`` / ``d88_write_format`` の
生成規則を機械的に再現する。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

HEADER_SIZE = 32
TRACK_TABLE_COUNT = 164
TRACK_TABLE_SIZE = TRACK_TABLE_COUNT * 4
TRACK_BASE = HEADER_SIZE + TRACK_TABLE_SIZE  # 0x2b0
ALLOCATED_TRACKS = 84
FORMATTED_TRACKS = 80
TRACK_SLOT_SIZE = 0x1600
SECTORS_PER_TRACK = 16
SECTOR_SIZE = 256
SECTOR_HEADER_SIZE = 16
SECTOR_RECORD_SIZE = SECTOR_HEADER_SIZE + SECTOR_SIZE
DISK_SIZE = TRACK_BASE + ALLOCATED_TRACKS * TRACK_SLOT_SIZE

DISK_PROTECT_FALSE = 0x00
DISK_TYPE_2D = 0x00
DISK_DENSITY_DOUBLE = 0x00
DISK_DELETED_FALSE = 0x00
STATUS_NORMAL = 0x00
N_CODE_256 = 0x01

DIRECTORY_TRACK = 37
DIRECTORY_FIRST_SECTOR = 1
DIRECTORY_LAST_SECTOR = 12
DIRECTORY_ENTRY_SIZE = 16
EMPTY_ENTRY = 0xFF


class BlankDiskError(Exception):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sector_data(track: int, sector: int) -> bytes:
    """QUASI88 d88_write_format() の公開初期値を返す。"""
    if track == 37 and sector == 13:
        return bytes(SECTOR_SIZE)
    if track == 37 and sector in (14, 15, 16):
        out = bytearray([0xFF] * 160 + [0x00] * (SECTOR_SIZE - 160))
        out[37 * 2] = 0xFE
        out[37 * 2 + 1] = 0xFE
        return bytes(out)
    return bytes([0xFF]) * SECTOR_SIZE


def sector_header(track: int, sector: int) -> bytes:
    out = bytearray(SECTOR_HEADER_SIZE)
    out[0] = track >> 1
    out[1] = track & 1
    out[2] = sector
    out[3] = N_CODE_256
    struct.pack_into("<H", out, 4, SECTORS_PER_TRACK)
    out[6] = DISK_DENSITY_DOUBLE
    out[7] = DISK_DELETED_FALSE
    out[8] = STATUS_NORMAL
    struct.pack_into("<H", out, 14, SECTOR_SIZE)
    return bytes(out)


def build_disk() -> bytes:
    out = bytearray(DISK_SIZE)
    out[26] = DISK_PROTECT_FALSE
    out[27] = DISK_TYPE_2D
    struct.pack_into("<I", out, 28, DISK_SIZE)
    for track in range(ALLOCATED_TRACKS):
        offset = TRACK_BASE + track * TRACK_SLOT_SIZE
        struct.pack_into("<I", out, HEADER_SIZE + track * 4, offset)
    for track in range(FORMATTED_TRACKS):
        pos = TRACK_BASE + track * TRACK_SLOT_SIZE
        for sector in range(1, SECTORS_PER_TRACK + 1):
            out[pos:pos + SECTOR_HEADER_SIZE] = sector_header(track, sector)
            pos += SECTOR_HEADER_SIZE
            out[pos:pos + SECTOR_SIZE] = sector_data(track, sector)
            pos += SECTOR_SIZE
    return bytes(out)


def track_offset(data: bytes, track: int) -> int:
    return struct.unpack_from("<I", data, HEADER_SIZE + track * 4)[0]


def data_offset(data: bytes, track: int, sector: int) -> int:
    if not 0 <= track < FORMATTED_TRACKS:
        raise BlankDiskError("物理トラック番号が範囲外")
    if not 1 <= sector <= SECTORS_PER_TRACK:
        raise BlankDiskError("セクタ番号が範囲外")
    return (track_offset(data, track) + (sector - 1) * SECTOR_RECORD_SIZE
            + SECTOR_HEADER_SIZE)


def check_structure(data: bytes) -> dict[str, int | str | bool]:
    if len(data) != DISK_SIZE:
        raise BlankDiskError("D88総サイズが固定値と一致しない")
    if data[:26] != bytes(26):
        raise BlankDiskError("D88名または予約領域が0でない")
    if data[26] != DISK_PROTECT_FALSE or data[27] != DISK_TYPE_2D:
        raise BlankDiskError("保護フラグまたは媒体種別が固定値と一致しない")
    if struct.unpack_from("<I", data, 28)[0] != DISK_SIZE:
        raise BlankDiskError("D88ヘッダの総サイズが一致しない")
    for track in range(TRACK_TABLE_COUNT):
        actual = track_offset(data, track)
        expected = (TRACK_BASE + track * TRACK_SLOT_SIZE
                    if track < ALLOCATED_TRACKS else 0)
        if actual != expected:
            raise BlankDiskError("トラックオフセットが固定規則と一致しない")
    for track in range(FORMATTED_TRACKS):
        pos = track_offset(data, track)
        for sector in range(1, SECTORS_PER_TRACK + 1):
            if data[pos:pos + SECTOR_HEADER_SIZE] != sector_header(track, sector):
                raise BlankDiskError("セクタIDが固定規則と一致しない")
            pos += SECTOR_HEADER_SIZE
            if data[pos:pos + SECTOR_SIZE] != sector_data(track, sector):
                raise BlankDiskError("セクタ初期値が固定規則と一致しない")
            pos += SECTOR_SIZE
        slot_end = track_offset(data, track) + TRACK_SLOT_SIZE
        if data[pos:slot_end] != bytes(slot_end - pos):
            raise BlankDiskError("トラック余白が0でない")
    for track in range(FORMATTED_TRACKS, ALLOCATED_TRACKS):
        start = track_offset(data, track)
        if data[start:start + TRACK_SLOT_SIZE] != bytes(TRACK_SLOT_SIZE):
            raise BlankDiskError("未使用トラックが0でない")
    return {
        "structure_ok": True,
        "disk_size": len(data),
        "allocated_tracks": ALLOCATED_TRACKS,
        "formatted_tracks": FORMATTED_TRACKS,
        "sectors_per_track": SECTORS_PER_TRACK,
        "sector_size": SECTOR_SIZE,
        "sha256": sha256(data),
    }


def used_file_entries(data: bytes) -> int:
    used = 0
    for sector in range(DIRECTORY_FIRST_SECTOR, DIRECTORY_LAST_SECTOR + 1):
        start = data_offset(data, DIRECTORY_TRACK, sector)
        block = data[start:start + SECTOR_SIZE]
        for pos in range(0, SECTOR_SIZE, DIRECTORY_ENTRY_SIZE):
            if block[pos] != EMPTY_ENTRY:
                used += 1
    return used


def check_empty(data: bytes) -> dict[str, int | bool]:
    used = used_file_entries(data)
    if used != 0:
        raise BlankDiskError("使用中ファイル項目が0件でない")
    return {"empty_ok": True, "used_file_entries": used,
            "directory_entries": 12 * (SECTOR_SIZE // DIRECTORY_ENTRY_SIZE)}


def inspect(path: Path) -> dict[str, object]:
    try:
        data = path.read_bytes()
    except OSError as ex:
        raise BlankDiskError("媒体を読めない") from ex
    result: dict[str, object] = {"schema": 1}
    result.update(check_structure(data))
    result.update(check_empty(data))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="生成せず、既存の自作媒体を構造・空状態検査する")
    ap.add_argument("path", type=Path)
    args = ap.parse_args()
    try:
        if args.check:
            print(json.dumps(inspect(args.path), ensure_ascii=False, sort_keys=True))
            return 0
        data = build_disk()
        check_structure(data)
        check_empty(data)
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_bytes(data)
        print(json.dumps({"schema": 1, "generated": True,
                          "sha256": sha256(data), "disk_size": len(data)},
                         ensure_ascii=False, sort_keys=True))
        return 0
    except BlankDiskError as ex:
        print(f"不合格: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
