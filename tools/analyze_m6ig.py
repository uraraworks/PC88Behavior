#!/usr/bin/env python3
"""m6i-g の実ログを到達状態・結果・SHAだけへ縮約する。"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_m6ia_main_sub as m6ia  # noqa: E402
import analyze_m6ib_first_request as m6ib  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402
import build_m6ig_measure_rom as build_m6ig  # noqa: E402
import build_m6ib_measure_rom as roms  # noqa: E402

ARMS = build_m6ig.ARMS
ISSUE_FRAMES = {"G-N": 6, "G-L0": 60, "G-L1": 60, "G-L2": 60}
EXPECTED_STATES = {
    "G-N": (0, 0, 0), "G-L0": (0, 0, 0),
    "G-L1": (1, 1, 0), "G-L2": (1, 1, 1),
}
FAULTS = ("state_changed", "read_issue_frame_changed",
          "request_counter_fixed", "shared_state_event")


@dataclass(frozen=True)
class StateObservation:
    counts: tuple[int, int, int]
    independent: bool
    event_counts_consistent: bool


def state_event_counts(shape: tuple[int, int, int, int, int] | None,
                       rows: list[m2s.Ev], issue_clock: int) -> tuple[int, int, int | None]:
    """初期化の有無から意味的な窓を選び、前置きI/Oを数える。"""
    if shape is None:
        startup_end = issue_clock
        round0_response = None
    else:
        init_start, init_end = shape[1], shape[2]
        startup_end = min(init_start, issue_clock)
        round0_response = (sum(row.cpu == "sub" and row.kind == "OUT"
                               and row.port == "00FD"
                               and init_end < row.clock < issue_clock for row in rows)
                           if init_end < issue_clock else None)
    startup_rows = [row for row in rows if row.clock < startup_end]
    startup_send = sum(row.cpu == "main" and row.kind == "OUT"
                       and row.port == "00FD" for row in startup_rows)
    startup_recv = sum(row.cpu == "sub" and row.kind == "IN"
                       and row.port == "00FC" for row in startup_rows)
    return startup_send, startup_recv, round0_response


def observe_state(shape: tuple[int, int, int, int, int] | None,
                  rows: list[m2s.Ev], memory: list[m6ia.MemEvent],
                  issue_clock: int) -> StateObservation:
    """aは初期化完了I/O、b/cは別番地の書込みで数え、出所の重複も検査する。"""
    a_sources: set[tuple[str, int, int]] = set()
    if shape is not None and shape[0] == 7 and shape[2] < issue_clock:
        a_sources.add(("io", shape[2], 0))
    b_sources = {("mem", row.seq, row.addr) for row in memory
                 if row.addr == 0xE00B and row.value == 1}
    c_sources = {("mem", row.seq, row.addr) for row in memory
                 if row.addr == 0xE00C and row.value == 1}
    groups = (a_sources, b_sources, c_sources)
    independent = all(groups[i].isdisjoint(groups[j])
                      for i in range(3) for j in range(i + 1, 3))
    startup_send, startup_recv, round0_response = state_event_counts(
        shape, rows, issue_clock)
    b_count = m6ia.one_writes(memory, 0xE00B)
    c_count = m6ia.one_writes(memory, 0xE00C)
    consistent = (startup_send == startup_recv == b_count
                  and (c_count == 0 if round0_response is None
                       else round0_response == c_count))
    return StateObservation((len(a_sources), b_count, c_count),
                            independent, consistent)


def request_runs_after_issue(rows: list[m2s.Ev], issue_clock: int) -> int:
    """前置き通信を捨て、通常READ発行以後だけから要求runを数える。"""
    return m6ia.request_runs([row for row in rows if row.clock >= issue_clock], 1)


def reached(observed: StateObservation, expected: tuple[int, int, int],
            issue_frame: int, expected_frame: int,
            request_counter_integrity: bool) -> bool:
    return (observed.counts == expected and observed.independent
            and observed.event_counts_consistent
            and issue_frame == expected_frame and request_counter_integrity)


def result_detail(facts: dict[str, object], memory: list[m6ia.MemEvent],
                  expected_sha: str) -> str:
    return m6ib.classify_result(facts, memory, expected_sha)


def result_kind(detail: str, request_runs: int) -> str:
    return "success" if detail == "positions_256_match" and request_runs == 1 else "failure"


def inject_fault(fault: str | None, observed: StateObservation, issue_frame: int,
                 actual_request_runs: int) -> tuple[StateObservation, int, int, bool]:
    if fault == "state_changed":
        observed = StateObservation((observed.counts[0] ^ 1, *observed.counts[1:]),
                                    observed.independent, observed.event_counts_consistent)
    if fault == "read_issue_frame_changed":
        issue_frame += 1
    request_runs = 0 if fault == "request_counter_fixed" else actual_request_runs
    integrity = fault != "request_counter_fixed" and request_runs == actual_request_runs
    if fault == "shared_state_event":
        observed = StateObservation(observed.counts, False,
                                    observed.event_counts_consistent)
    return observed, issue_frame, request_runs, integrity


def cfg_one(path: Path, key: str) -> str:
    values = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        fields = raw.split("\t")
        if len(fields) == 2 and fields[0] == key:
            values.append(fields[1])
    if len(values) != 1:
        raise ValueError("frozen config")
    return values[0]


def rom_digest(rom_dir: Path) -> str:
    """走が追加しうるファイルを列挙せず、固定7名だけを読む。"""
    return roms.rom_set_sha256(rom_dir)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--memlog", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--intlog", type=Path)
    ap.add_argument("--rom-dir", required=True, type=Path)
    ap.add_argument("--config", type=Path, default=HERE / "m6ig_frozen.tsv")
    ap.add_argument("--fault", choices=FAULTS)
    args = ap.parse_args()
    base: dict[str, object] = {
        "arm": args.arm, "reached": False, "result": "failure",
        "result_detail": "other_incomplete", "request_runs": 0,
        "state_a": 0, "state_b": 0, "state_c": 0,
        "state_observations_independent": False,
        "fault_injection": args.fault,
    }
    try:
        rows, masked = m2s.parse_iolog(args.iolog)
        if sum(masked.values()):
            raise ValueError("masked live input")
        memory = m6ia.read_memlog(args.memlog)
        issue, _issue_data = m6ib.find_read_issue(rows)
        observed = observe_state(m6ib.init_shape(rows), rows, memory, issue.clock)
        actual_request_runs = request_runs_after_issue(rows, issue.clock)
        observed, issue_frame, request_runs, integrity = inject_fault(
            args.fault, observed, issue.frame, actual_request_runs)
        facts, _blocks = m6ia.analyze_single(
            m6ia.Inputs(args.memlog, args.iolog, args.report, args.intlog), 1, 0, 0)
        detail = result_detail(facts, memory, cfg_one(args.config, "sector1_sha256"))
        base.update({
            "reached": reached(observed, EXPECTED_STATES[args.arm], issue_frame,
                               ISSUE_FRAMES[args.arm], integrity),
            "result": result_kind(detail, request_runs),
            "result_detail": detail,
            "request_runs": request_runs,
            "read_issue_frame": issue_frame,
            "state_a": observed.counts[0], "state_b": observed.counts[1],
            "state_c": observed.counts[2],
            "state_observations_independent": observed.independent,
            "state_event_counts_consistent": observed.event_counts_consistent,
            "rom_set_sha256": rom_digest(args.rom_dir),
        })
        print(json.dumps(base, sort_keys=True, separators=(",", ":")))
        return 0 if base["reached"] else 1
    except (OSError, UnicodeError, ValueError, m6ia.AnalysisError):
        print(json.dumps(base, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
