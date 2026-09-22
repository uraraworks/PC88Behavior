#!/usr/bin/env bash
# m6i-c解析器のG6(4故障)、G7(5結果)、G8-1(3状態)自己検査。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO" <<'PY'
from pathlib import Path
import sys

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "tools"))
import analyze_m6ia_main_sub as a6
import analyze_main_to_sub as m2s
import analyze_m6ic as a
import judge_m6ic as j


def facts(**updates):
    base = {
        "timeout_marker_count": 0,
        "receive_complete_block_count": 1,
        "receive_sha256": a6.EXPECT_SHA[1],
        "key_input_accepted": True,
    }
    base.update(updates)
    return base


def mem(count):
    return [a6.MemEvent(i + 1, 1, 0x7000, 0xDF00 + i, i & 0xFF)
            for i in range(count)]


# G6: 3故障は到達条件、gate run削除は副問の変化で検出する。
if not a.reached(True, 60, True):
    raise SystemExit("G6陽性対照が未到達")
for fault in a.FAULTS:
    b_count, frame, runs, _released, _requests, integrity = a.inject_fault(
        fault, 1, 60, [a.GateRun(32, 100)], True, 1)
    preamble_ok = b_count == 1
    is_reached = a.reached(preamble_ok, frame, integrity)
    if fault == "gate_run_deleted":
        side = j.gate_result({"gate_entered": bool(runs),
                              "gate_released": _released,
                              "gate_run_count": len(runs),
                              "gate_run_max_length": max(
                                  (run.length for run in runs), default=0),
                              "request_runs": _requests})
        if not is_reached or side != "gate_not_entered":
            raise SystemExit("G6故障注入を副問で検出できない: gate_run_deleted")
    elif is_reached:
        raise SystemExit(f"G6故障注入を到達条件で検出できない: {fault}")

# G7: 結果5種を同じ分類入口で別名にする。
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
    actual = a.result_detail(row, memory, a6.EXPECT_SHA[1])
    if actual != expected:
        raise SystemExit(f"G7分類不一致: {expected}/{actual}")
    seen.add(actual)
if len(seen) != 5 or a.result_kind("positions_256_match", 1) != "success":
    raise SystemExit("G7結果が独立していない")

# G8-1: main行はrunを切らず、subの別I/Oだけが解除を示す。
rows = [m2s.Ev(1, 10, 1, "sub", "OUT", "00FD", 0, "0000")]
seq = 2
for clock in range(20, 52):
    rows.append(m2s.Ev(seq, clock * 2, 2, "sub", "IN", "00FE", 0, "0000"))
    seq += 1
    rows.append(m2s.Ev(seq, clock * 2 + 1, 2, "main", "OUT", "00FD", 0, "0000"))
    seq += 1
permanent_runs, permanent_released = a.gate_observation(rows, 200, 32)
if len(permanent_runs) != 1 or permanent_released:
    raise SystemExit("G8-1永久待ちを識別できない")
permanent = j.gate_result({"gate_entered": True, "gate_released": False,
                           "gate_run_count": 1, "gate_run_max_length": 32,
                           "request_runs": 0})

released_rows = rows + [m2s.Ev(seq, 210, 3, "sub", "OUT", "00F8", 0, "0000")]
released_runs, released = a.gate_observation(released_rows, 220, 32)
if len(released_runs) != 1 or not released:
    raise SystemExit("G8-1素通りを識別できない")
passed = j.gate_result({"gate_entered": True, "gate_released": True,
                        "gate_run_count": 1, "gate_run_max_length": 32,
                        "request_runs": 0})
if (permanent, passed) != ("gate_never_released",
                           "gate_released_but_request_lost"):
    raise SystemExit("G8-1副問判定を取り違えた")

# 旧実装は1本目後の非FE I/Oを拾い、未解除の2本目があっても released と取り違える。
two_run_rows = [m2s.Ev(1, 10, 1, "sub", "OUT", "00FD", 0, "0000")]
seq = 2
for clock in range(20, 52):
    two_run_rows.append(m2s.Ev(seq, clock, 2, "sub", "IN", "00FE", 0, "0000"))
    seq += 1
two_run_rows.append(m2s.Ev(seq, 60, 2, "sub", "OUT", "00F8", 0, "0000"))
seq += 1
for clock in range(70, 102):
    two_run_rows.append(m2s.Ev(seq, clock, 3, "sub", "IN", "00FE", 0, "0000"))
    seq += 1
two_runs, two_released = a.gate_observation(two_run_rows, 200, 32)
old_released = any(
    row.cpu == "sub" and not (row.kind == "IN" and row.port == "00FE")
    and row.clock > run.end_clock
    for run in two_runs for row in two_run_rows
)
two_result = j.gate_result({"gate_entered": bool(two_runs),
                            "gate_released": two_released,
                            "gate_run_count": len(two_runs),
                            "gate_run_max_length": max(
                                (run.length for run in two_runs), default=0),
                            "request_runs": 0})
if (len(two_runs) != 2 or two_released or not old_released
        or two_result != "gate_never_released"):
    raise SystemExit("G8-1最後のrunの永久待ちを識別できない")

print("analyze_m6ic_selftest: 項目数=12、G6=4・G7=5・G8-1=3 OK")
PY
