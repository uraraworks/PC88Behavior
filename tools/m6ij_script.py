#!/usr/bin/env python3
"""m6i-j の自作媒体・打鍵・事前登録定数。"""
from __future__ import annotations

import hashlib
import json

ARMS = tuple(f"J-D{drive}-{size}-{mode}" for drive in (1, 2)
             for size in ("S", "L") for mode in ("N", "O"))
AXES = ("constant", "drive", "track", "r", "count_order")
JUDGMENTS = ("m6i_j_main_write_send_unique", "inconclusive_axis_confounded",
             "inconclusive_multiple_candidates", "inconclusive_control_other",
             "inconclusive_group_boundary", "inconclusive_transfer_mapping",
             "inconclusive_write_response", "inconclusive_save_order", "gate_failed")
FRAMES = 30000
SWAP_FRAME = 1200
TYPE_FRAME = 1600
OLD_BODY = b"10 PRINT 1\r\n\x1a"


def name(arm: str) -> str:
    if arm not in ARMS:
        raise ValueError("腕ID")
    return "qjs" if "-S-" in arm else "qjl"


def lines(arm: str) -> list[str]:
    if arm not in ARMS:
        raise ValueError("腕ID")
    if "-S-" in arm:
        return ['10 PRINT 2']
    # 70行、終端を含め2049〜2304バイト。各行は独立の自作 REM 行。
    # 打鍵は小文字で届き、REM の本文は大文字化されない（m6f-a 結果 (i)、m6i-j 7回目で A→a を確認）。
    # 大小の区別が出ない数字だけにする。
    return [f"{i * 10} REM " + "0" * 20 for i in range(1, 71)]


def body(arm: str) -> bytes:
    return ("\r\n".join(lines(arm)) + "\r\n").encode("ascii") + b"\x1a"


def keys(arm: str) -> str:
    drive = arm[3]
    return "new\n" + "\n".join(lines(arm)) + f'\ncls:save "{drive}:{name(arm)}",a\n'


def manifest() -> dict:
    return {"format": "m6ij-v1", "frames": FRAMES, "swap_frame": SWAP_FRAME,
            "type_frame": TYPE_FRAME, "axes": AXES, "judgments": JUDGMENTS,
            "arms": [{"id": arm, "drive": int(arm[3]),
                      "media": "B1" if arm.endswith("-O") else "B0",
                      "name": name(arm), "body_sha256": sha(body(arm)),
                      "body_length": len(body(arm)), "sectors": 1 if "-S-" in arm else 9,
                      "keys": keys(arm), "runs": 2} for arm in ARMS]}


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True,
                       separators=(",", ":")) + "\n").encode("ascii")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
