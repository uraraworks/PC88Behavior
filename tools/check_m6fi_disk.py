#!/usr/bin/env python3
"""m6f-i のD88を生成器と独立に読み直し、G15の項目別NGを返す。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from check_m6fg_disk import ShapeError, _parse_d88


def inspect_image(image: bytes, doc: dict) -> list[str]:
    failures: set[str] = set()
    try:
        sectors = _parse_d88(image)
    except (ShapeError, ValueError):
        return ["d88_shape"]
    directory = b"".join(sectors[(18, 1, r)] for r in range(1, 13))
    entries = doc["entries"]
    if directory[len(entries) * 16:(len(entries) + 1) * 16] != b"\xff" * 16:
        failures.add("first_unused")
    for entry in entries:
        pos = entry["position"] * 16
        record = directory[pos:pos + 16]
        if record[:9] != entry["name"].encode("ascii").ljust(9, b" "):
            failures.add("entry_name")
        if record[9] != 0 or entry["type"] != 0:
            failures.add("file_type")
        if record[11:] != b"\xff" * 5:
            failures.add("entry_reserved")
    fats = [sectors[(18, 1, r)] for r in (14, 15, 16)]
    if not (fats[0] == fats[1] == fats[2]):
        failures.add("fat_copies")
    fat = fats[0]
    if fat[74:76] != b"\xa0\xa0":
        failures.add("reserved_units")
    if sectors[(18, 1, 13)] != b"\0" * 256:
        failures.add("write_marker")
    owners: set[int] = set()
    duplicates = False
    actual = []
    for entry in entries:
        record = directory[entry["position"] * 16:entry["position"] * 16 + 16]
        units: list[int] = []
        current = record[10]
        seen: set[int] = set()
        terminal = None
        while 0 <= current < 160 and current not in seen:
            seen.add(current)
            units.append(current)
            value = fat[current]
            if 0xC0 <= value <= 0xC8:
                terminal = value
                break
            current = value
        if owners.intersection(units):
            failures.add("unit_unique")
            duplicates = True
        owners.update(units)
        actual.append((entry, units, terminal))
    for entry, units, terminal in actual:
        if terminal is None:
            failures.add("chain")
        elif units != entry["units"] and not duplicates:
            failures.add("chain")
        if terminal is not None and terminal != entry["terminal"]:
            failures.add("terminal")
        if units != entry["units"] or terminal != entry["terminal"]:
            continue
        payload = bytearray()
        for index, unit in enumerate(units):
            count = terminal - 0xC0 if index == len(units) - 1 else 8
            for sub in range(count):
                linear = unit * 8 + sub
                payload.extend(sectors[(linear // 32, (linear // 16) % 2,
                                         linear % 16 + 1)])
        expected = bytes.fromhex(entry["body_hex"])
        if payload[:len(expected) - 1] != expected[:-1]:
            failures.add("body")
        if len(payload) < len(expected) or payload[len(expected) - 1] != 0x1A:
            failures.add("eof_1a")
    expected_used = {unit for entry in entries for unit in entry["units"]}
    for unit in range(160):
        if unit not in expected_used and unit not in (74, 75) and fat[unit] != 0xFF:
            failures.add("fat_free")
            break
    if owners.intersection((74, 75)):
        failures.add("reserved_units")
    return sorted(failures)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--image", type=Path)
    ap.add_argument("--image-dir", type=Path)
    ap.add_argument("--frozen", type=Path,
                    default=Path(__file__).with_name("m6fi_frozen.tsv"))
    args = ap.parse_args()
    try:
        raw = args.manifest.read_bytes()
        doc = json.loads(raw)
        if doc.get("format") != "m6fi-scenario-v1":
            raise ValueError("manifest")
        frozen = dict(row.split("\t") for row in args.frozen.read_text(
            encoding="ascii").splitlines())
        path = args.image or (args.image_dir or args.manifest.parent) / doc["media_file"]
        failures = inspect_image(path.read_bytes(), doc)
        if hashlib.sha256(raw).hexdigest() != frozen["manifest_sha256"]:
            failures.append("manifest_sha256")
        failures = sorted(set(failures))
        print(json.dumps({"failures": failures}, ensure_ascii=True, separators=(",", ":")))
        return 1 if failures else 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        print('{"failures":["input"]}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
