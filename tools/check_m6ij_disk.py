#!/usr/bin/env python3
"""生成器の内部関数を使わない m6i-j 媒体・本体検査。"""
from __future__ import annotations

import re

from m6fh_body import BodyError, Image
import m6ij_script as script


def check_body(arm: str, payload: bytes) -> list[str]:
    faults = []
    sectors = 1 if "-S-" in arm else 9
    if not (1 <= len(payload) <= 256 if sectors == 1 else 2049 <= len(payload) <= 2304):
        faults.append("body_length")
    if not payload.endswith(b"\r\n\x1a") or payload.count(b"\x1a") != 1:
        faults.append("body_terminal")
    parts = payload[:-1].split(b"\r\n")
    if not parts or parts[-1] != b"" or any(not re.fullmatch(rb"[1-9][0-9]* (PRINT [0-9]|REM [0-9]+)", p)
                                              for p in parts[:-1]):
        faults.append("body_lines")
    if (len(payload)+255)//256 != sectors:
        faults.append("body_sectors")
    return faults


def inspect(data: bytes, media: str, arm: str) -> list[str]:
    if media not in ("B0", "B1") or arm not in script.ARMS:
        return ["scenario"]
    try:
        image = Image(data)
        if len(image.sectors) != 40*2*16:
            return ["d88_shape"]
        directory = b"".join(bytes(image.sector(18, 1, r)) for r in range(1, 13))
        fat = bytes(image.sector_prefix((18, 1, 14), 160))
        copies = [bytes(image.sector_prefix((18, 1, r), 160)) for r in (15, 16)]
        marker = bytes(image.sector(18, 1, 13))
    except (BodyError, KeyError, ValueError):
        return ["d88_shape"]
    faults = []
    if marker != bytes(256):
        faults.append("marker")
    if any(x != fat for x in copies):
        faults.append("fat_copies")
    if fat[74:76] != b"\xa0\xa0":
        faults.append("reserved")
    expected_entry = (script.name(arm).encode("ascii").ljust(9, b" ") +
                      b"\x00\x0a" + b"\xff"*5)
    if media == "B0":
        if directory != b"\xff"*len(directory):
            faults.append("directory")
    elif directory[:16] != expected_entry or directory[16:] != b"\xff"*(len(directory)-16):
        faults.append("directory")
    for unit in range(160):
        want = 0xa0 if unit in (74, 75) else 0xc1 if media == "B1" and unit == 10 else 0xff
        if fat[unit] != want:
            faults.append("fat"); break
    if media == "B1":
        linear = 10*8
        coord = (linear//32, (linear//16)%2, linear%16+1)
        if bytes(image.sector_prefix(coord, len(script.OLD_BODY))) != script.OLD_BODY:
            faults.append("old_body")
    return sorted(set(faults))
