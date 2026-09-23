#!/usr/bin/env python3
"""m6i-hの実ログを腕別の到達状態・結果・SHAだけへ縮約する。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_m6ia_main_sub as m6ia  # noqa: E402
import analyze_m6ib_first_request as m6ib  # noqa: E402
import analyze_m6ig as base  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402
import build_m6ih_measure_rom as build_m6ih  # noqa: E402

ARMS = build_m6ih.ARMS
ISSUE_FRAMES = {"H-N": 6, "H-W": 60}
EXPECTED_STATES = {
    "H-N": (0, 0, 0), "H-W": (1, 1, 0),
    "H-A": (None, 1, 0), "H-B": (None, 0, 0),
}
RETRY_MARKER_ADDRESS = 0xE00D
RESULT_CONDITIONS = {"H-N": "standard", "H-W": "standard",
                     "H-A": "standard", "H-B": "retry"}
FAULTS = base.FAULTS + ("retry_marker_changed",)

StateObservation = base.StateObservation
observe_state = base.observe_state
state_event_counts = base.state_event_counts
request_runs_after_issue = base.request_runs_after_issue
rom_digest = base.rom_digest


def last_marker_is_one(memory: list[m6ia.MemEvent], address: int) -> bool:
    values = [row.value for row in memory if row.addr == address]
    return bool(values) and values[-1] == 1


def reached(arm: str, observed: StateObservation, issue_frame: int,
            retry_count: int, request_counter_integrity: bool) -> bool:
    expected = EXPECTED_STATES[arm]
    state_ok = all(want is None or got == want
                   for got, want in zip(observed.counts, expected))
    frame_ok = arm not in ISSUE_FRAMES or issue_frame == ISSUE_FRAMES[arm]
    retry_ok = retry_count == 1 if arm == "H-B" else retry_count == 0
    return (state_ok and frame_ok and retry_ok and observed.independent
            and observed.event_counts_consistent and request_counter_integrity)


def h_b_result_detail(facts: dict[str, object], memory: list[m6ia.MemEvent],
                      expected_sha: str) -> str:
    """履歴上の1回目失敗でなく、2回目後の成功印・最終256位置を判定する。"""
    positions = m6ib.writes_since_last_start(memory)
    if positions == 255:
        return "one_position_missing"
    if facts["receive_complete_block_count"] and facts["receive_sha256"] != expected_sha:
        return "sha_mismatch"
    complete = (last_marker_is_one(memory, 0xE002) and positions == 256
                and facts["receive_complete_block_count"]
                and facts["receive_sha256"] == expected_sha)
    if complete and not facts["key_input_accepted"]:
        return "steady_wait_not_returned"
    if complete and facts["key_input_accepted"]:
        return "positions_256_match"
    return "retry_failed"


def result_kind(arm: str, detail: str, request_runs: int) -> str:
    if arm == "H-B":
        return "success" if detail == "positions_256_match" else "failure"
    return "success" if detail == "positions_256_match" and request_runs == 1 else "failure"


def inject_fault(fault: str | None, observed: StateObservation, issue_frame: int,
                 retry_count: int, actual_request_runs: int):
    observed, issue_frame, request_runs, integrity = base.inject_fault(
        fault if fault in base.FAULTS else None, observed, issue_frame, actual_request_runs)
    if fault == "retry_marker_changed":
        retry_count ^= 1
    return observed, issue_frame, retry_count, request_runs, integrity


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--memlog", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--intlog", type=Path)
    ap.add_argument("--rom-dir", required=True, type=Path)
    ap.add_argument("--config", type=Path, default=HERE / "m6ih_frozen.tsv")
    ap.add_argument("--fault", choices=FAULTS)
    args = ap.parse_args()
    out: dict[str, object] = {
        "arm": args.arm, "reached": False, "result": "failure",
        "result_detail": "other_incomplete", "request_runs": 0,
        "state_a": 0, "state_b": 0, "state_c": 0, "retry_marker_count": 0,
        "state_observations_independent": False, "fault_injection": args.fault,
    }
    try:
        rows, masked = m2s.parse_iolog(args.iolog)
        if sum(masked.values()):
            raise ValueError("masked live input")
        memory = m6ia.read_memlog(args.memlog)
        issue, _data = m6ib.find_read_issue(rows)
        observed = observe_state(m6ib.init_shape(rows), rows, memory, issue.clock)
        actual_runs = request_runs_after_issue(rows, issue.clock)
        retry_count = m6ia.one_writes(memory, RETRY_MARKER_ADDRESS)
        observed, frame, retry_count, runs, integrity = inject_fault(
            args.fault, observed, issue.frame, retry_count, actual_runs)
        facts, _blocks = m6ia.analyze_single(
            m6ia.Inputs(args.memlog, args.iolog, args.report, args.intlog), 1, 0, 0)
        expected_sha = base.cfg_one(args.config, "sector1_sha256")
        detail = (h_b_result_detail(facts, memory, expected_sha) if args.arm == "H-B"
                  else m6ib.classify_result(facts, memory, expected_sha))
        out.update({
            "reached": reached(args.arm, observed, frame, retry_count, integrity),
            "result": result_kind(args.arm, detail, runs), "result_detail": detail,
            "request_runs": runs, "read_issue_frame": frame,
            "state_a": observed.counts[0], "state_b": observed.counts[1],
            "state_c": observed.counts[2], "retry_marker_count": retry_count,
            "state_observations_independent": observed.independent,
            "state_event_counts_consistent": observed.event_counts_consistent,
            "rom_set_sha256": rom_digest(args.rom_dir),
        })
        print(json.dumps(out, sort_keys=True, separators=(",", ":")))
        return 0 if out["reached"] else 1
    except (OSError, UnicodeError, ValueError, m6ia.AnalysisError):
        print(json.dumps(out, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
