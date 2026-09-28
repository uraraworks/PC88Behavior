#!/usr/bin/env python3
"""m6f-j の媒体名、打鍵、予測本体、実行時刻を一元化する。"""
from __future__ import annotations

import hashlib
import json

ARMS = ("J-1", "J-2", "J-3", "J-4", "J-5", "J-6")
MEDIA = dict(zip(ARMS, ("B0", "B1", "B2", "BP", "BF", "B0")))
NAMES = dict(zip(ARMS, ("qsb", "qsa", "qsc", "qsd", "qse", "qsf")))
PRINT_VALUES = dict(zip(ARMS, (1, 2, 1, 1, 1, 1)))
FRAMES = {arm: 8000 for arm in ARMS}
INSERT_FRAME = 1200


def keystrokes(arm: str) -> str:
    if arm not in ARMS:
        raise ValueError("腕ID")
    return f'new\n10 print {PRINT_VALUES[arm]}\ncls:save "2:{NAMES[arm]}",a\n'


def body(arm: str) -> bytes:
    if arm not in ("J-1", "J-2"):
        raise ValueError("本体対象")
    return f"10 PRINT {PRINT_VALUES[arm]}\r\n".encode("ascii") + b"\x1a"


def manifest() -> dict:
    return {"format": "m6fj-scenario-v1", "disk_spec": "l3-disk-format-v5",
            "media": {"B0": [], "B1": [{"name": "qsa", "units": [10], "type": 0}],
                      "B2": [{"name": "qused", "units": list(range(10)), "type": 0}],
                      "BP": [], "BF": [{"name": "qfull", "units": [n for n in range(160)
                                      if n not in (74, 75)], "type": 0}]},
            "arms": [{"id": arm, "media": MEDIA[arm], "name": NAMES[arm],
                      "command": keystrokes(arm), "runs": 2,
                      "frames": FRAMES[arm], "insert_frame": INSERT_FRAME if arm == "J-6" else None}
                     for arm in ARMS]}


def canonical(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")


def digest(doc: dict) -> str:
    return hashlib.sha256(canonical(doc)).hexdigest()


def validate(doc: dict) -> None:
    if doc != manifest():
        raise ValueError("G3")
    for arm in doc["arms"]:
        if arm["name"] not in arm["command"] or arm["name"] != arm["name"].lower():
            raise ValueError("G3")
