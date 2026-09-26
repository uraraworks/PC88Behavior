#!/usr/bin/env python3
"""m6f-e 用の自作 D88 媒体と、15腕のシナリオ manifest を生成する。

媒体の論理形式は docs/spec/l3-disk-format.md 第3版、内容と腕は
docs/notes/m6f-e-files-display-preregistration.md §4・§5 だけに基づく。
画面予測器・署名器具には依存しない。
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


def _sector_offsets(image: bytes) -> dict[tuple[int, int, int], int]:
    """D88 のセクタデータ先頭を得る（基礎像の書換え専用）。"""
    offsets: dict[tuple[int, int, int], int] = {}
    starts = [struct.unpack_from("<I", image, 32 + i * 4)[0] for i in range(TRACK_COUNT)]
    starts = sorted(value for value in starts if value)
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(image)
        pos = start
        while pos < end:
            size = struct.unpack_from("<H", image, pos + 14)[0]
            offsets[(image[pos], image[pos + 1], image[pos + 2])] = pos + 16
            pos += 16 + size
    return offsets


def _available_units():
    for unit in range(160):
        if unit not in RESERVED_UNITS:
            yield unit


def _entry(name: str, file_type: int, unit_count: int, terminal: int,
           content_value: int, allocator) -> dict:
    units = [next(allocator) for _ in range(unit_count)]
    return {
        "name": name,
        "name_length": len(name),
        "type": file_type,
        "units": units,
        "terminal": terminal,
        "content": {"kind": "uniform", "value": content_value},
    }


def _numbered_entries(prefix: str, count: int) -> list[dict]:
    allocator = _available_units()
    return [
        _entry(f"{prefix}{index:08d}", 0x80 if index % 2 else 0x00,
               1, 0xC1, 0x10 + index, allocator)
        for index in range(1, count + 1)
    ]


def _layout(entries: list[dict], deleted_positions: list[int]) -> dict:
    deleted = set(deleted_positions)
    slots: list[dict] = []
    entry_index = 0
    slot_count = len(entries) + len(deleted)
    markers = iter(("DELONE", "DELTWO", "DELTHREE"))
    for position in range(slot_count):
        if position in deleted:
            slots.append({"position": position, "kind": "deleted", "marker": next(markers)})
        else:
            item = dict(entries[entry_index])
            item["position"] = position
            slots.append({"position": position, "kind": "file", "entry": item})
            entry_index += 1
    return {
        "entries": [slot["entry"] for slot in slots if slot["kind"] == "file"],
        "deleted": [
            {"position": slot["position"], "marker": slot["marker"]}
            for slot in slots if slot["kind"] == "deleted"
        ],
        "first_unused": slot_count,
    }


def _media_definitions() -> dict[str, dict]:
    media: dict[str, dict] = {"L0": _layout([], [])}

    names = ["A", "BC", "DEF", "GHIJ", "KLMNO", "PQRSTU",
             "UVWXYZ1", "ABCDEFGH", "NINECHARS"]
    allocator = _available_units()
    long_entries = [
        _entry(name, 0x80 if index % 2 == 0 else 0x00, 1, 0xC1,
               0x21 + index, allocator)
        for index, name in enumerate(names)
    ]
    # §4.2で型が個別指定されない末尾2件は、直前までの交互列を継続する。
    long_entries.append(_entry("CHAIN10U", 0x00, 10, 0xC1, 0x41, allocator))
    long_entries.append(_entry("LAST8SEC", 0x80, 1, 0xC8, 0x52, allocator))

    media["L1"] = _layout([dict(long_entries[0])], [])
    for count in (4, 5, 6):
        media[f"L{count}"] = _layout(_numbered_entries("B", count), [])
    media["L11"] = _layout(long_entries, [2, 6, 11])
    media["L96"] = _layout(_numbered_entries("Q", 96), [])

    for media_id, name, value in (("D1", "DRIVEONE", 0x61), ("D2", "DRIVETWO", 0x62)):
        media[media_id] = _layout([
            _entry(name, 0x80, 1, 0xC1, value, _available_units())
        ], [])

    for media_id, definition in media.items():
        definition["file"] = f"{media_id}.d88"
    return media


def _arms() -> list[dict]:
    arms: list[dict] = []
    for arm in ("L0", "L1", "L4", "L5", "L6", "L11", "L96"):
        arms.append({
            "id": arm,
            "runs": 2,
            "drive1": "reference_boot_copy",
            "drive2": arm,
            "command": "CLS:FILES 2",
            "command_time": "after_boot_complete",
            "final_frame": 12000 if arm == "L96" else 8000,
            "events": [],
        })

    commands = (
        ("D-omit", "CLS:FILES", "direct"),
        ("D-1", "CLS:FILES 1", "direct"),
        ("D-2", "CLS:FILES 2", "direct"),
        ("D-expr", "CLS:FILES 1+1", "direct"),
        ("E-0", "FILES 0", "error_catcher"),
        ("E-3", "FILES 3", "error_catcher"),
        ("E-str", 'FILES "B:"', "error_catcher"),
    )
    for arm, command, execution in commands:
        arms.append({
            "id": arm,
            "runs": 2,
            "drive1": "D1",
            "drive2": "D2",
            "command": command,
            "execution": execution,
            "command_time": "after_drive1_exchange_confirmed",
            "final_frame": 8000,
            "events": [{
                "kind": "exchange_drive1",
                "from": "reference_boot_copy",
                "to": "D1",
                "time": "after_boot_complete_before_command",
            }],
        })

    arms.append({
        "id": "N-wait",
        "runs": 2,
        "drive1": "reference_boot_copy",
        "drive2": "empty_then_L1",
        "command": "CLS:FILES 2",
        "command_time": "after_boot_complete",
        "final_frame": 4000,
        "events": [{"kind": "insert_drive2", "media": "L1", "frame": 1200}],
    })
    return arms


def build_manifest() -> dict:
    media = _media_definitions()
    return {
        "format": "m6fe-scenario-v1",
        "disk_spec": "l3-disk-format-v3",
        "media_order": list(media),
        "media": media,
        "arms": _arms(),
    }


def _deleted_bytes(marker: str) -> bytes:
    payload = marker.encode("ascii")
    return b"\x00" + (payload * 3)[:15].ljust(15, b"_")


def build_disk(definition: dict) -> bytes:
    """m6f-c の空媒体を基礎に、第3版のディレクトリ・FAT・本体を置く。"""
    image = bytearray(build_blank_disk(
        fat_value=0xFF,
        filler=0xFF,
        sector_fills={WRITE_MARKER_COORD: 0x00},
        fat_positions={74: 0xA0, 75: 0xA0},
    ))
    offsets = _sector_offsets(image)

    directory = bytearray(b"\xFF" * (12 * SECTOR_SIZE))
    for deleted in definition["deleted"]:
        pos = deleted["position"] * 16
        directory[pos:pos + 16] = _deleted_bytes(deleted["marker"])
    for entry in definition["entries"]:
        pos = entry["position"] * 16
        name = entry["name"].encode("ascii")
        record = bytearray(b"\xFF" * 16)
        record[:9] = name.ljust(9, b" ")
        record[9] = entry["type"]
        record[10] = entry["units"][0]
        directory[pos:pos + 16] = record
    for index, coord in enumerate(DIRECTORY_COORDS):
        start = offsets[coord]
        image[start:start + SECTOR_SIZE] = directory[index * SECTOR_SIZE:(index + 1) * SECTOR_SIZE]

    fat = bytearray(b"\xFF" * SECTOR_SIZE)
    fat[74] = fat[75] = 0xA0
    for entry in definition["entries"]:
        units = entry["units"]
        for current, following in zip(units, units[1:]):
            fat[current] = following
        fat[units[-1]] = entry["terminal"]
    for coord in FAT_COORDS:
        start = offsets[coord]
        image[start:start + SECTOR_SIZE] = fat

    for entry in definition["entries"]:
        used_last = entry["terminal"] - 0xC0
        value = entry["content"]["value"]
        for unit_index, unit in enumerate(entry["units"]):
            used_sectors = used_last if unit_index == len(entry["units"]) - 1 else 8
            for within in range(used_sectors):
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
    parser.add_argument("--expected-manifest-sha256", metavar="HEX")
    args = parser.parse_args()

    manifest = build_manifest()
    manifest_bytes = canonical_json(manifest)
    digest = hashlib.sha256(manifest_bytes).hexdigest()
    if args.expected_manifest_sha256 is not None and args.expected_manifest_sha256 != digest:
        print("NG manifest_sha256", file=sys.stderr)
        return 1

    targets = [args.output_dir / manifest["media"][media_id]["file"]
               for media_id in manifest["media_order"]]
    targets += [args.output_dir / "manifest.json", args.output_dir / "manifest.sha256"]
    if any(path.exists() for path in targets):
        print("NG output_exists", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for media_id in manifest["media_order"]:
        definition = manifest["media"][media_id]
        (args.output_dir / definition["file"]).write_bytes(build_disk(definition))
    (args.output_dir / "manifest.json").write_bytes(manifest_bytes)
    (args.output_dir / "manifest.sha256").write_text(
        f"{digest}  manifest.json\n", encoding="ascii"
    )
    print(f"manifest_sha256={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
