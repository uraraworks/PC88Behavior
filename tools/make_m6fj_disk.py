#!/usr/bin/env python3
"""第5版の規則だけから m6f-j の5媒体を作る。予測器には依存しない。"""
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

from make_m6fc_blank_disk import build_blank_disk
import m6fj_script as script

MEDIA = ("B0", "B1", "B2", "BP", "BF")


def offsets(image: bytes) -> dict[tuple[int, int, int], int]:
    starts = sorted(x for x in (struct.unpack_from("<I", image, 32 + 4*i)[0]
                                for i in range(164)) if x)
    result = {}
    for i, start in enumerate(starts):
        end = starts[i+1] if i+1 < len(starts) else len(image)
        while start < end:
            result[tuple(image[start:start+3])] = start + 16
            start += 16 + struct.unpack_from("<H", image, start+14)[0]
    return result


def build(media: str) -> bytes:
    if media not in MEDIA:
        raise ValueError("媒体ID")
    image = bytearray(build_blank_disk(fat_value=0xff, filler=0xff,
        sector_fills={(18, 1, 13): 0x10 if media == "BP" else 0},
        fat_positions={74: 0xa0, 75: 0xa0}))
    off = offsets(image)
    fat = bytearray(b"\xff" * 256)
    fat[74:76] = b"\xa0\xa0"
    entries = script.manifest()["media"][media]
    for index, entry in enumerate(entries):
        units = entry["units"]
        record = entry["name"].encode("ascii").ljust(9, b" ") + bytes((0, units[0])) + b"\xff" * 5
        pos = off[(18, 1, 1)] + 16*index
        image[pos:pos+16] = record
        for j, unit in enumerate(units):
            fat[unit] = units[j+1] if j+1 < len(units) else (0xc8 if media == "BF" else 0xc1)
    if media == "B1":
        payload = b"10 PRINT 1\r\n\x1a"
        linear = 10*8
        pos = off[(linear//32, (linear//16)%2, linear%16+1)]
        image[pos:pos+len(payload)] = payload
    for r in (14, 15, 16):
        pos = off[(18, 1, r)]
        image[pos:pos+256] = fat
    return bytes(image)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("output_dir", type=Path)
    args = ap.parse_args()
    names = [f"{name}.d88" for name in MEDIA] + ["manifest.json"]
    if any((args.output_dir / name).exists() for name in names):
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in MEDIA:
        (args.output_dir / f"{name}.d88").write_bytes(build(name))
    raw = script.canonical(script.manifest())
    (args.output_dir / "manifest.json").write_bytes(raw)
    print("manifest_sha256=" + hashlib.sha256(raw).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
