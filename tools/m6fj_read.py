#!/usr/bin/env python3
"""m6f-j の測定前後差を安全な範囲で読む。"""
from __future__ import annotations

import json
import argparse
from pathlib import Path

from m6fh_body import BodyError, Image, read_bounded
import m6fj_script as script


def inspect(data: bytes, arm: str) -> dict:
    image = Image(data)
    entries = []
    stop = False
    for r in range(1, 13):
        sector = image.sector(18, 1, r)
        for offset in range(0, 256, 16):
            record = bytes(sector[offset:offset+16])
            if record[0] == 0xff:
                stop = True
                break
            if record[0] == 0:
                continue
            entries.append({"name": record[:9].rstrip(b" ").decode("ascii"),
                            "position": (r-1)*16+offset//16,
                            "bytes9_15": list(record[9:16])})
        if stop:
            break
    fat = bytes(image.sector_prefix((18, 1, 14), 160))
    if any(fat != bytes(image.sector_prefix((18, 1, r), 160)) for r in (15, 16)):
        raise BodyError("割り当て表の複製")
    result = {"entries": entries, "fat_0_159": list(fat), "g8_max_position": 159}
    if arm in ("J-1", "J-2"):
        target = next((e for e in entries if e["name"] == script.NAMES[arm]), None)
        if target is not None:
            unit = target["bytes9_15"][1]
            units = []
            seen = set()
            while unit < 160 and unit not in seen:
                seen.add(unit)
                units.append(unit)
                value = fat[unit]
                if 0xc0 <= value <= 0xc8:
                    used = value-0xc0
                    break
                unit = value
            else:
                raise BodyError("鎖")
            coords = []
            for index, number in enumerate(units):
                for sub in range(used if index == len(units)-1 else 8):
                    linear = number*8+sub
                    coords.append((linear//32, (linear//16)%2, linear%16+1))
            expected = script.body(arm)
            actual, max_pos = read_bounded(image, coords, len(expected)+1)
            result.update(body_matches_2_6=actual[:len(expected)] == expected,
                          body_read_max_position=max_pos, body_read_limit=len(expected))
    return result


def unchanged(before: dict, after: dict) -> bool:
    return before["entries"] == after["entries"] and before["fat_0_159"] == after["fat_0_159"]


def safe_result(value: dict) -> dict:
    """FATの値列は測定成果へ出さず、差と割り当て単位だけを残す。"""
    return {key: item for key, item in value.items() if key != "fat_0_159"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--arm", required=True, choices=script.ARMS)
    ap.add_argument("--before", type=Path)
    args = ap.parse_args()
    try:
        after = inspect(args.image.read_bytes(), args.arm)
        result = safe_result(after)
        if args.before is not None:
            result["media_unchanged"] = unchanged(inspect(args.before.read_bytes(), args.arm), after)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, ValueError, UnicodeError, BodyError):
        print('{"gate":"NG","reason":"read"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
