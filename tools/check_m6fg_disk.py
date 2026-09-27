#!/usr/bin/env python3
"""m6f-g の自作媒体を、生成器から独立に像から読み直して検査する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import struct
import sys


SECTOR_SIZE = 256
TRACK_COUNT = 164
MINIMUM_SIZE = 32 + TRACK_COUNT * 4
DIRECTORY_COORDS = tuple((18, 1, r) for r in range(1, 13))
FAT_COORDS = ((18, 1, 14), (18, 1, 15), (18, 1, 16))
VALID_TYPES = (0x00, 0x01, 0x80, 0xA0)


class ShapeError(ValueError):
    pass


def _parse_d88(image: bytes) -> dict[tuple[int, int, int], bytes]:
    if len(image) < MINIMUM_SIZE or struct.unpack_from("<I", image, 28)[0] != len(image):
        raise ShapeError("size")
    if image[26] != 0 or image[27] != 0:
        raise ShapeError("disk_header")
    offsets = [struct.unpack_from("<I", image, 32 + i * 4)[0]
               for i in range(TRACK_COUNT)]
    active = offsets[:80]
    if any(value == 0 for value in active) or any(offsets[80:]):
        raise ShapeError("track_table")
    if active[0] != MINIMUM_SIZE or active != sorted(active) or len(set(active)) != 80:
        raise ShapeError("track_offsets")
    sectors: dict[tuple[int, int, int], bytes] = {}
    for physical, start in enumerate(active):
        end = active[physical + 1] if physical + 1 < 80 else len(image)
        pos = start
        seen = 0
        while pos < end:
            if pos + 16 > end:
                raise ShapeError("sector_header")
            c, h, r, n = image[pos:pos + 4]
            count = struct.unpack_from("<H", image, pos + 4)[0]
            size = struct.unpack_from("<H", image, pos + 14)[0]
            if (c, h) != (physical // 2, physical % 2) or n != 1 or count != 16:
                raise ShapeError("sector_id")
            if image[pos + 6:pos + 14] != b"\x00" * 8 or size != SECTOR_SIZE:
                raise ShapeError("sector_shape")
            data_start = pos + 16
            data_end = data_start + size
            if data_end > end or (c, h, r) in sectors:
                raise ShapeError("sector_bounds")
            sectors[(c, h, r)] = image[data_start:data_end]
            pos = data_end
            seen += 1
        if seen != 16 or pos != end:
            raise ShapeError("sector_count")
    expected = {(c, h, r) for c in range(40) for h in range(2) for r in range(1, 17)}
    if set(sectors) != expected:
        raise ShapeError("coordinates")
    return sectors


def _directory(sectors: dict) -> bytes:
    return b"".join(sectors[coord] for coord in DIRECTORY_COORDS)


def _record(directory: bytes, position: int) -> bytes:
    return directory[position * 16:(position + 1) * 16]


def _chain(start: int, fat: bytes) -> tuple[list[int], int | None]:
    units: list[int] = []
    seen: set[int] = set()
    current = start
    while 0 <= current < 160 and current not in seen:
        units.append(current)
        seen.add(current)
        value = fat[current]
        if 0xC1 <= value <= 0xC8:
            return units, value
        current = value
    return units, None


def inspect_image(image: bytes, definition: dict) -> list[str]:
    failures: set[str] = set()
    try:
        sectors = _parse_d88(image)
    except (ShapeError, struct.error):
        return ["d88_shape"]
    directory = _directory(sectors)
    entries = definition["entries"]
    expected_records = {_record(directory, entry["position"]) for entry in entries}
    for coord, payload in sectors.items():
        if coord in DIRECTORY_COORDS:
            continue
        if any(payload[offset:offset + 16] in expected_records
               for offset in range(0, SECTOR_SIZE, 16)):
            failures.add("directory_location")
            break
    if _record(directory, definition["first_unused"]) != b"\xFF" * 16:
        failures.add("first_unused")

    names: list[str | None] = []
    for entry in entries:
        record = _record(directory, entry["position"])
        expected_name = entry["name"].encode("ascii")
        if (entry["name_length"] != len(expected_name)
                or not 1 <= entry["name_length"] <= 9
                or record[:9] != expected_name.ljust(9, b" ")):
            failures.add("name_length")
        try:
            names.append(record[:entry["name_length"]].decode("ascii"))
        except UnicodeDecodeError:
            failures.add("name_length")
            names.append(None)
        if record[9] != entry["type"] or record[9] not in VALID_TYPES:
            failures.add("file_type")
        if record[11:16] != b"\xFF" * 5:
            failures.add("entry_reserved")
    if names != [entry["name"] for entry in entries]:
        failures.add("entry_order")

    fats = [sectors[coord] for coord in FAT_COORDS]
    if not (fats[0] == fats[1] == fats[2]):
        failures.add("fat_copies")
    fat = fats[0]
    if fat[74] != 0xA0 or fat[75] != 0xA0:
        failures.add("reserved_units")

    owners: dict[int, int] = {}
    actual: list[tuple[list[int], int | None]] = []
    for entry in entries:
        units, terminal = _chain(_record(directory, entry["position"])[10], fat)
        actual.append((units, terminal))
        for unit in units:
            owners[unit] = owners.get(unit, 0) + 1
    duplicate = any(value > 1 for value in owners.values())
    if duplicate:
        failures.add("unit_unique")
    expected_used: set[int] = set()
    for entry, (units, terminal) in zip(entries, actual):
        expected = entry["units"]
        expected_used.update(expected)
        if not duplicate and units != expected:
            failures.add("chain")
        if terminal != entry["terminal"]:
            failures.add("terminal")
    if 74 in expected_used or 75 in expected_used:
        failures.add("reserved_units")
    for unit in range(160):
        if unit not in expected_used and unit not in (74, 75) and fat[unit] != 0xFF:
            failures.add("fat_free")
            break
    if sectors[(18, 1, 13)] != b"\x00" * SECTOR_SIZE:
        failures.add("write_marker")
    for entry in entries:
        value = entry["content"]["value"]
        for unit_index, unit in enumerate(entry["units"]):
            used = entry["terminal"] - 0xC0 if unit_index == len(entry["units"]) - 1 else 8
            for within in range(used):
                linear = unit * 8 + within
                coord = (linear // 32, (linear // 16) % 2, linear % 16 + 1)
                if sectors[coord] != bytes([value]) * SECTOR_SIZE:
                    failures.add("body")
                    break
    return sorted(failures)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=pathlib.Path)
    parser.add_argument("--image-dir", type=pathlib.Path)
    parser.add_argument("--media")
    parser.add_argument("--image", type=pathlib.Path)
    parser.add_argument("--sha256-file", type=pathlib.Path,
                        default=pathlib.Path(__file__).with_name("m6fg_frozen.tsv"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        raw = args.manifest.read_bytes()
        manifest = json.loads(raw)
        if manifest.get("format") != "m6fg-scenario-v1":
            raise ValueError("manifest形式")
        frozen = dict(line.split("\t") for line in
                      args.sha256_file.read_text(encoding="ascii").splitlines())
        failures: dict[str, list[str]] = {}
        if hashlib.sha256(raw).hexdigest() != frozen["manifest_sha256"]:
            failures["manifest"] = ["manifest_sha256"]
        if args.media is not None:
            if args.image is None or args.media not in manifest["media"]:
                raise ValueError("媒体指定")
            failures[args.media] = inspect_image(
                args.image.read_bytes(), manifest["media"][args.media])
        else:
            image_dir = args.image_dir or args.manifest.parent
            for media_id in manifest["media_order"]:
                definition = manifest["media"][media_id]
                failures[media_id] = inspect_image(
                    (image_dir / definition["file"]).read_bytes(), definition)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"NG input {type(exc).__name__}", file=sys.stderr)
        return 2
    failures = {key: value for key, value in failures.items() if value}
    if args.json:
        print(json.dumps({"failures": failures}, ensure_ascii=True, sort_keys=True))
    elif failures:
        for media_id, labels in failures.items():
            print(f"NG {media_id} {','.join(labels)}")
    else:
        print("OK")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
