#!/usr/bin/env python3
"""m6f-j 合成媒体の独立検査。割り当て表は位置159までしか読まない。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from m6fh_body import BodyError, Image

EXPECTED = {"B0": [], "B1": [("qsa", [10])], "B2": [("qused", list(range(10)))],
            "BP": [], "BF": [("qfull", [x for x in range(160) if x not in (74, 75)])]}


def inspect(data: bytes, media: str) -> list[str]:
    failures: set[str] = set()
    if media not in EXPECTED:
        return ["media_id"]
    try:
        image = Image(data)
        directory = b"".join(image.sector(18, 1, r) for r in range(1, 13))
        fats = [bytes(image.sector_prefix((18, 1, r), 160)) for r in (14, 15, 16)]
        marker = image.sector(18, 1, 13)
    except (BodyError, KeyError, ValueError):
        return ["d88_shape"]
    if fats[0] != fats[1] or fats[0] != fats[2]:
        failures.add("fat_copies")
    fat = fats[0]
    if fat[74:76] != b"\xa0\xa0":
        failures.add("reserved_units")
    if marker != bytes([0x10 if media == "BP" else 0])*256:
        failures.add("write_marker")
    expected = EXPECTED[media]
    if directory[16*len(expected):16*(len(expected)+1)] != b"\xff"*16:
        failures.add("first_unused")
    used: set[int] = set()
    for index, (name, units) in enumerate(expected):
        record = directory[16*index:16*(index+1)]
        if record[:9] != name.encode("ascii").ljust(9, b" "):
            failures.add("entry_name")
        if record[9] != 0:
            failures.add("file_type")
        if record[10] != units[0]:
            failures.add("entry_first_unit")
        if record[11:] != b"\xff"*5:
            failures.add("entry_reserved")
        for pos, unit in enumerate(units):
            if unit in used:
                failures.add("unit_unique")
            used.add(unit)
            want = units[pos+1] if pos+1 < len(units) else (0xc8 if media == "BF" else 0xc1)
            if fat[unit] != want:
                failures.add("chain" if pos+1 < len(units) else "terminal")
    if used.intersection((74, 75)):
        failures.add("reserved_units")
    if any(fat[unit] != 0xff for unit in range(160) if unit not in used and unit not in (74, 75)):
        failures.add("fat_free")
    if media == "B1":
        linear = 10*8
        payload = image.sector_prefix((linear//32, (linear//16)%2, linear%16+1), 13)
        if bytes(payload) != b"10 PRINT 1\r\n\x1a":
            failures.add("body")
    return sorted(failures)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("--media", required=True)
    args = ap.parse_args()
    try:
        failures = inspect(args.image.read_bytes(), args.media)
    except OSError:
        failures = ["input"]
    print(json.dumps({"failures": failures}, separators=(",", ":")))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
