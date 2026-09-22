#!/usr/bin/env bash
# m6i-b解析器のG7(B6枝別印)・G8(5結果分類)自己検査。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "tools"))
import analyze_m6ia_main_sub as a6
import analyze_m6ib_first_request as b6


def facts(**updates):
    base = {
        "timeout_marker_count": 0,
        "receive_complete_block_count": 1,
        "receive_sha256": a6.EXPECT_SHA[1],
        "key_input_accepted": True,
        "request_marker_count": 1,
        "recv256_marker_count": 1,
        "success_marker_count": 1,
        "request_run_count": 1,
        "complete_protocol_run_count": 1,
        "fdc_read_data_count": 1,
        "fdc_read_coordinate_match_count": 1,
        "fdc_sense_drive_status_count": 2,
        "fault_cont_marker_count": 1,
        "fault_pair_marker_count": 1,
        "bank_probe_count": 200,
        "repeat_done_marker_count": 1,
        "main_interrupt_count": 1,
    }
    base.update(updates)
    return base


def mem(count):
    return [a6.MemEvent(i + 1, 1, 0x7000, 0xDF00 + i, i & 0xFF)
            for i in range(count)]


# G8: 同じ入口が5結果を互いに異なる名前へ分類する。
cases = {
    "positions_256_match": (facts(), mem(256)),
    "one_position_missing": (
        facts(receive_complete_block_count=0, receive_sha256=None), mem(255)),
    "sha_mismatch": (facts(receive_sha256="0" * 64), mem(256)),
    "timeout": (facts(timeout_marker_count=1), mem(0)),
    "steady_wait_not_returned": (facts(key_input_accepted=False), mem(256)),
}
seen = set()
for expected, (row, memory) in cases.items():
    actual = b6.classify_result(row, memory, a6.EXPECT_SHA[1])
    if actual != expected:
        raise SystemExit(f"G8分類不一致: expected={expected} actual={actual}")
    seen.add(actual)
if len(seen) != 5:
    raise SystemExit("G8の5結果が独立名になっていない")

# G7/B6: 各枝が依存するm6i-a到達印を1種類だけ欠落させると未到達になる。
branch_marker = {
    "B6-A0": "request_marker_count",
    "B6-A1": "recv256_marker_count",
    "B6-A2": "timeout_marker_count",
    "B6-A4-cont": "fault_cont_marker_count",
    "B6-A4-pair": "fault_pair_marker_count",
    "B6-A5": "repeat_done_marker_count",
}
for arm, marker in branch_marker.items():
    if arm == "B6-A2":
        positive = facts(request_marker_count=1, fdc_read_data_count=0,
                         timeout_marker_count=1)
    elif arm == "B6-A5":
        positive = facts(request_marker_count=200, recv256_marker_count=200,
                         success_marker_count=200, request_run_count=200,
                         receive_complete_block_count=200,
                         complete_protocol_run_count=200, fdc_read_data_count=200,
                         fdc_read_coordinate_match_count=200)
    else:
        positive = facts()
    if not b6.b6_reached(arm, positive):
        raise SystemExit(f"G7陽性対照が未到達: {arm}")
    broken = dict(positive)
    broken[marker] = 0
    if b6.b6_reached(arm, broken):
        raise SystemExit(f"G7印欠落を検出できない: {arm}/{marker}")

print("analyze_m6ib_first_request_selftest: G7枝別6種・G8結果5種 OK")
PY
