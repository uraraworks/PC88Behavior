#!/usr/bin/env python3
"""保存後の自作媒体を上限付きで検査する。"""
from __future__ import annotations

from m6fh_body import BodyError, Image, chain, read_bounded
import m6ij_script as script


def inspect(data: bytes, arm: str, media: str) -> bool:
    image = Image(data)
    fat = bytes(image.sector_prefix((18, 1, 14), 160))
    if any(fat != bytes(image.sector_prefix((18, 1, r), 160)) for r in (15, 16)):
        return False
    if fat[74:76] != b"\xa0\xa0" or (media == "B1" and fat[10] != 0xff):
        return False
    coords, sectors = chain(image, script.name(arm).encode("ascii"))
    expected = script.body(arm)
    if sectors != (len(expected)+255)//256:
        return False
    actual, maximum = read_bounded(image, coords, len(expected))
    return actual == expected and maximum == len(expected)-1
