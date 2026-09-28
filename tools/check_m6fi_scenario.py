#!/usr/bin/env python3
"""m6f-i のG3: 凍結manifestと媒体名・打鍵名の一致を検査する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def verify(raw: bytes, frozen: bytes) -> None:
    doc = json.loads(raw)
    values = dict(row.split("\t") for row in frozen.decode("ascii").splitlines())
    if hashlib.sha256(raw).hexdigest() != values["manifest_sha256"]:
        raise ValueError("manifest_sha256")
    entries = doc["entries"]
    names = [entry["name"] for entry in entries]
    if len(names) != 3 or any(not re.fullmatch(r"[a-z]+", name) for name in names):
        raise ValueError("media_names")
    targets = {"I-1": names[0], "I-2": names[0], "I-3": names[1],
               "I-4": names[0], "E-1": "qzz", "E-2": names[2]}
    arms = doc["arms"]
    if len(arms) != len(targets) or {arm["id"] for arm in arms} != set(targets):
        raise ValueError("arms")
    for arm in arms:
        typed = re.findall(r'\bload "2:([^"\n]+)"', arm["command"])
        if typed != [targets[arm["id"]]]:
            raise ValueError("typed_name")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--frozen", type=Path,
                    default=Path(__file__).with_name("m6fi_frozen.tsv"))
    args = ap.parse_args()
    try:
        verify(args.manifest.read_bytes(), args.frozen.read_bytes())
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        print("m6fi_g3=ng", file=sys.stderr)
        return 1
    print("m6fi_g3=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
