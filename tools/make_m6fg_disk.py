#!/usr/bin/env python3
"""m6f-g 用の5媒体と10走のシナリオ manifest を生成する。

自作データだけを使い、画面予測器には依存しない。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
import sys

from make_m6fc_blank_disk import build_blank_disk


SECTOR_SIZE = 256
TRACK_COUNT = 164
DIRECTORY_COORDS = tuple((18, 1, r) for r in range(1, 13))
WRITE_MARKER_COORD = (18, 1, 13)
FAT_COORDS = ((18, 1, 14), (18, 1, 15), (18, 1, 16))
RESERVED_UNITS = (74, 75)
ARMS = ("G-P", "G-B", "G-M", "G-Z1", "G-Z2")


def _sector_offsets(image: bytes) -> dict[tuple[int, int, int], int]:
    offsets: dict[tuple[int, int, int], int] = {}
    starts = [struct.unpack_from("<I", image, 32 + i * 4)[0]
              for i in range(TRACK_COUNT)]
    starts = sorted(value for value in starts if value)
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(image)
        pos = start
        while pos < end:
            size = struct.unpack_from("<H", image, pos + 14)[0]
            offsets[(image[pos], image[pos + 1], image[pos + 2])] = pos + 16
            pos += 16 + size
    return offsets


def _available_units() -> list[int]:
    return [unit for unit in range(160) if unit not in RESERVED_UNITS]


def _entry(name: str, file_type: int, units: list[int], value: int) -> dict:
    return {
        "name": name,
        "name_length": len(name),
        "type": file_type,
        "units": units,
        "terminal": 0xC1,
        "content": {"kind": "uniform", "value": value},
        "position": 0,
    }


def _media_definitions() -> dict[str, dict]:
    available = _available_units()
    media = {
        "G-P": {"entries": [_entry("PROGTYPEP", 0xA0, [0], 0x31)]},
        "G-B": {"entries": [_entry("BINARYONE", 0x01, [0], 0x32)]},
        "G-M": {"entries": [
            _entry("MIXED0001", 0x80, [0], 0x41),
            _entry("MIXED0002", 0x00, [1], 0x42),
            _entry("MIXED0003", 0xA0, [2], 0x43),
            _entry("MIXED0004", 0x01, [3], 0x44),
            _entry("MIXED0005", 0x80, [4], 0x45),
        ]},
        "G-Z1": {"entries": [_entry("SIZE00100", 0x80, available[:100], 0x51)]},
        "G-Z2": {"entries": [_entry("SIZE00158", 0x80, available, 0x52)]},
    }
    for media_id, definition in media.items():
        for position, entry in enumerate(definition["entries"]):
            entry["position"] = position
        definition.update({"deleted": [], "first_unused": len(definition["entries"]),
                           "file": f"{media_id}.d88"})
    return media


def build_manifest() -> dict:
    media = _media_definitions()
    arms = [{
        "id": arm,
        "runs": 2,
        "drive1": "reference_boot_copy",
        "drive2": arm,
        "command": "CLS:FILES 2",
        "command_time": "after_boot_complete",
        "final_frame": 8000,
        "events": [],
    } for arm in ARMS]
    return {
        "format": "m6fg-scenario-v1",
        "disk_spec": "l3-disk-format-v4",
        "media_order": list(media),
        "media": media,
        "arms": arms,
    }


def build_disk(definition: dict) -> bytes:
    image = bytearray(build_blank_disk(
        fat_value=0xFF, filler=0xFF,
        sector_fills={WRITE_MARKER_COORD: 0x00},
        fat_positions={74: 0xA0, 75: 0xA0},
    ))
    offsets = _sector_offsets(image)
    directory = bytearray(b"\xFF" * (12 * SECTOR_SIZE))
    for entry in definition["entries"]:
        pos = entry["position"] * 16
        record = bytearray(b"\xFF" * 16)
        record[:9] = entry["name"].encode("ascii").ljust(9, b" ")
        record[9] = entry["type"]
        record[10] = entry["units"][0]
        directory[pos:pos + 16] = record
    for index, coord in enumerate(DIRECTORY_COORDS):
        start = offsets[coord]
        image[start:start + SECTOR_SIZE] = directory[
            index * SECTOR_SIZE:(index + 1) * SECTOR_SIZE]

    fat = bytearray(b"\xFF" * SECTOR_SIZE)
    fat[74] = fat[75] = 0xA0
    for entry in definition["entries"]:
        for current, following in zip(entry["units"], entry["units"][1:]):
            fat[current] = following
        fat[entry["units"][-1]] = entry["terminal"]
    for coord in FAT_COORDS:
        start = offsets[coord]
        image[start:start + SECTOR_SIZE] = fat

    for entry in definition["entries"]:
        value = entry["content"]["value"]
        for unit_index, unit in enumerate(entry["units"]):
            used = entry["terminal"] - 0xC0 if unit_index == len(entry["units"]) - 1 else 8
            for within in range(used):
                linear = unit * 8 + within
                coord = (linear // 32, (linear // 16) % 2, linear % 16 + 1)
                start = offsets[coord]
                image[start:start + SECTOR_SIZE] = bytes([value]) * SECTOR_SIZE
    return bytes(image)


def canonical_json(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=pathlib.Path)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args()
    manifest = build_manifest()
    raw = canonical_json(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    if args.expected_manifest_sha256 is not None and args.expected_manifest_sha256 != digest:
        print("NG manifest_sha256", file=sys.stderr)
        return 1
    targets = [args.output_dir / manifest["media"][item]["file"]
               for item in manifest["media_order"]]
    targets += [args.output_dir / "manifest.json", args.output_dir / "manifest.sha256"]
    if any(path.exists() for path in targets):
        print("NG output_exists", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for media_id in manifest["media_order"]:
        definition = manifest["media"][media_id]
        (args.output_dir / definition["file"]).write_bytes(build_disk(definition))
    (args.output_dir / "manifest.json").write_bytes(raw)
    (args.output_dir / "manifest.sha256").write_text(
        f"{digest}  manifest.json\n", encoding="ascii")
    print(f"manifest_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
