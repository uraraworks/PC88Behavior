#!/usr/bin/env python3
"""第5版の規則だけから m6f-k の2媒体を作る。予測器には依存しない。"""
from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

from make_m6fc_blank_disk import build_blank_disk
import m6fk_script as script

MEDIA = ("KM", "KP")

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
        sector_fills={(18, 1, 13): 0x10 if media == "KP" else 0},
        fat_positions={74: 0xa0, 75: 0xa0}))
    off = offsets(image)
    fat = bytearray(b"\xff" * 256)
    fat[74:76] = b"\xa0\xa0"
    # 9セクタ以上の有効なASCIIプログラム。鎖20→21、末尾単位は1セクタ。
    bodies = (b"10 PRINT 1\r\n\x1a",
              b"".join(f"{n*10} REM ".encode() + b"X"*60 + b"\r\n" for n in range(1, 31)) + b"\x1a",
              b"10 PRINT 3\r\n\x1a")
    for index, (entry, payload) in enumerate(zip(script.manifest()["media"][media], bodies)):
        units = entry["units"]
        record = entry["name"].encode("ascii").ljust(9, b" ") + bytes((0, units[0])) + b"\xff"*5
        pos = off[(18, 1, 1)] + 16*index
        image[pos:pos+16] = record
        sectors = (len(payload)+255)//256
        for j, unit in enumerate(units):
            fat[unit] = units[j+1] if j+1 < len(units) else 0xc0 + sectors - j*8
            for sub in range(min(8, sectors-j*8)):
                linear = unit*8+sub
                pos = off[(linear//32, (linear//16)%2, linear%16+1)]
                chunk = payload[(j*8+sub)*256:(j*8+sub+1)*256]
                image[pos:pos+len(chunk)] = chunk
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
