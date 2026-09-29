#!/usr/bin/env python3
"""m6i-j 用 B0/B1 を自作する。検査は別モジュールで行う。"""
from __future__ import annotations

from make_m6fc_blank_disk import build_blank_disk
from make_m6fj_disk import offsets
from m6ij_script import OLD_BODY, name


def build(media: str, arm: str) -> bytes:
    if media not in ("B0", "B1"):
        raise ValueError("媒体ID")
    image = bytearray(build_blank_disk(fat_value=0xff, filler=0xff,
                                       sector_fills={(18, 1, 13): 0},
                                       fat_positions={74: 0xa0, 75: 0xa0}))
    off = offsets(image)
    if media == "B1":
        image[off[(18, 1, 1)]:off[(18, 1, 1)]+16] = (
            name(arm).encode("ascii").ljust(9, b" ") + b"\x00\x0a" + b"\xff" * 5)
        for r in (14, 15, 16):
            image[off[(18, 1, r)]+10] = 0xc1
        linear = 10 * 8
        pos = off[(linear//32, (linear//16)%2, linear%16+1)]
        image[pos:pos+len(OLD_BODY)] = OLD_BODY
    return bytes(image)
