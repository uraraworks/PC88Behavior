#!/usr/bin/env python3
"""m6f-i 追補2の自作 ASCII ファイル4件と測定計画を作る。"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

from make_m6fc_blank_disk import build_blank_disk

ARMS = ("I-4'", "E-2'", "E-3", "E-3m")
FILES = (
    ("qia", 0, ("10 PRINT 1", "20 PRINT 2")),
    ("qib", 1, ("30 PRINT 3", "10 PRINT 1")),
    ("qid", 2, ("ABC", "DE")),
    ("qie", 3, ("10 PRINT 1", "ABC", "30 PRINT 3")),
)


def manifest() -> dict:
    entries = []
    for name, unit, lines in FILES:
        body = ("\r\n".join(lines) + "\r\n").encode("ascii") + b"\x1a"
        entries.append({"name": name, "type": 0, "position": unit,
                        "units": [unit], "terminal": 0xC1,
                        "body_hex": body.hex()})
    qia, qib, qid, qie = (item[0] for item in FILES)
    commands = {
        "I-4'": f'cls:load "2:{qia}"\n',
        "E-2'": f'new\ncls:load "2:{qid}"\n',
        "E-3": f'new\ncls:load "2:{qie}"\n',
        "E-3m": f'new\ncls:load "2:{qie}"\n',
    }
    return {"format": "m6fi-add2-scenario-v1", "disk_spec": "l3-disk-format-v5",
            "media_file": "ascii.d88", "entries": entries,
            "arms": [{"id": arm, "runs": 2, "drive1": "reference_boot_copy",
                      "drive2": "ascii", "command": commands[arm],
                      "list_frame": 4000 if arm == "E-3" else None,
                      "final_frame": 8000} for arm in ARMS]}


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n").encode("ascii")


def sector_offsets(image: bytes) -> dict[tuple[int, int, int], int]:
    starts = sorted(struct.unpack_from("<I", image, 32 + 4 * i)[0]
                    for i in range(164) if struct.unpack_from("<I", image, 32 + 4 * i)[0])
    result = {}
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(image)
        pos = start
        while pos < end:
            size = struct.unpack_from("<H", image, pos + 14)[0]
            result[tuple(image[pos:pos + 3])] = pos + 16
            pos += 16 + size
    return result


def build_disk(doc: dict) -> bytes:
    image = bytearray(build_blank_disk(fat_value=0xFF, filler=0xFF,
        sector_fills={(18, 1, 13): 0}, fat_positions={74: 0xA0, 75: 0xA0}))
    offsets = sector_offsets(image)
    fat = bytearray(b"\xff" * 256)
    fat[74] = fat[75] = 0xA0
    for entry in doc["entries"]:
        record = (entry["name"].encode("ascii").ljust(9, b" ") +
                  bytes((entry["type"], entry["units"][0])) + b"\xff" * 5)
        start = offsets[(18, 1, 1)] + 16 * entry["position"]
        image[start:start + 16] = record
        unit = entry["units"][0]
        fat[unit] = entry["terminal"]
        body = bytes.fromhex(entry["body_hex"])
        linear = unit * 8
        start = offsets[(linear // 32, (linear // 16) % 2, linear % 16 + 1)]
        image[start:start + len(body)] = body
    for r in (14, 15, 16):
        start = offsets[(18, 1, r)]
        image[start:start + 256] = fat
    return bytes(image)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output_dir", type=Path)
    ap.add_argument("--expected-manifest-sha256")
    args = ap.parse_args()
    doc = manifest()
    raw = canonical(doc)
    digest = hashlib.sha256(raw).hexdigest()
    if args.expected_manifest_sha256 is not None and digest != args.expected_manifest_sha256:
        print("NG manifest_sha256", file=sys.stderr)
        return 1
    targets = [args.output_dir / name for name in ("ascii.d88", "manifest.json")]
    if any(path.exists() for path in targets):
        print("NG output_exists", file=sys.stderr)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    targets[0].write_bytes(build_disk(doc))
    targets[1].write_bytes(raw)
    print(f"manifest_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
