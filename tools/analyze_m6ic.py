#!/usr/bin/env python3
"""m6i-c の実ログを、件数・真偽・SHA・登録済み判定名だけへ縮約する。"""
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
import build_m6ic_measure_rom as build_m6ic  # noqa: E402
import check_m6ic_rom_gate as rom_gate  # noqa: E402

ARMS = build_m6ic.ARMS
FAULTS = (
    "preamble_marker_deleted",
    "read_issue_frame_changed",
    "gate_run_deleted",
    "request_counter_fixed",
)


@dataclass(frozen=True)
class GateRun:
    length: int
    end_clock: int


def sub_fe_runs(rows: list[m2s.Ev], after_clock: int,
                minimum: int) -> list[GateRun]:
    """round #0 応答後の sub IN $FE run を返す。main 行は初めから除く。"""
    runs: list[GateRun] = []
    length = 0
    end_clock = -1
    for row in (event for event in rows
                if event.cpu == "sub" and event.clock > after_clock):
        if row.kind == "IN" and row.port == "00FE":
            length += 1
            end_clock = row.clock
        else:
            if length >= minimum:
                runs.append(GateRun(length, end_clock))
            length = 0
            end_clock = -1
    if length >= minimum:
        runs.append(GateRun(length, end_clock))
    return runs


def gate_observation(rows: list[m2s.Ev], issue_clock: int,
                     minimum: int) -> tuple[list[GateRun], bool]:
    responses = [row for row in rows if row.cpu == "sub" and row.kind == "OUT"
                 and row.port == "00FD" and row.clock < issue_clock]
    if not responses:
        return [], False
    runs = sub_fe_runs(rows, responses[-1].clock, minimum)
    released = bool(runs) and any(
        row.cpu == "sub" and not (row.kind == "IN" and row.port == "00FE")
        and row.clock > runs[-1].end_clock
        for row in rows
    )
    return runs, released


def reached(preamble_ok: bool, issue_frame: int,
            request_counter_integrity: bool) -> bool:
    return preamble_ok and issue_frame == 60 and request_counter_integrity


def result_detail(facts: dict[str, object], memory: list[m6ia.MemEvent],
                  expected_sha: str) -> str:
    return m6ib.classify_result(facts, memory, expected_sha)


def result_kind(detail: str, request_runs: int) -> str:
    return "success" if detail == "positions_256_match" and request_runs == 1 else "failure"


def inject_fault(fault: str | None, b_count: int, issue_frame: int,
                 gate_runs: list[GateRun], gate_released: bool,
                 actual_request_runs: int) -> tuple[int, int, list[GateRun], bool, int, bool]:
    """G6の単一故障を観測量へ注入し、独立再計数との整合も返す。"""
    if fault == "preamble_marker_deleted":
        b_count = 0
    if fault == "read_issue_frame_changed":
        issue_frame += 1
    if fault == "gate_run_deleted":
        gate_runs, gate_released = [], False
    request_runs = 0 if fault == "request_counter_fixed" else actual_request_runs
    counter_integrity = fault != "request_counter_fixed" and request_runs == actual_request_runs
    return (b_count, issue_frame, gate_runs, gate_released,
            request_runs, counter_integrity)


def cfg_one(path: Path, key: str) -> str:
    values = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        fields = raw.split("\t")
        if len(fields) == 2 and fields[0] == key:
            values.append(fields[1])
    if len(values) != 1:
        raise ValueError("frozen config")
    return values[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--memlog", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--intlog", type=Path)
    ap.add_argument("--rom-dir", required=True, type=Path)
    ap.add_argument("--config", type=Path, default=HERE / "m6ic_frozen.tsv")
    ap.add_argument("--fault", choices=FAULTS)
    args = ap.parse_args()

    base: dict[str, object] = {
        "arm": args.arm, "reached": False, "result": "failure",
        "result_detail": "other_incomplete", "gate_entered": False,
        "gate_released": False, "request_runs": 0,
        "gate_run_count": 0, "gate_run_max_length": 0,
        "fault_injection": args.fault,
    }
    try:
        rows, masked = m2s.parse_iolog(args.iolog)
        if sum(masked.values()):
            raise ValueError("masked live input")
        memory = m6ia.read_memlog(args.memlog)
        issue, _issue_data = m6ib.find_read_issue(rows)
        issue_frame = issue.frame

        shape = m6ib.init_shape(rows)
        if shape is None:
            init_batches, init_start, init_end = 0, -1, -1
        else:
            init_batches, init_start, init_end = shape[:3]
        b_count = m6ia.one_writes(memory, 0xE00B)
        c_count = m6ia.one_writes(memory, 0xE00C)
        b_events = [row for row in rows if row.cpu == "sub" and row.kind == "IN"
                    and row.port == "00FC" and row.clock < init_start]
        c_events = [row for row in rows if row.cpu == "main" and row.kind == "IN"
                    and row.port == "00FC" and init_end < row.clock < issue.clock]
        preamble_ok = (
            b_count == 1 and c_count == 1 and init_batches == 7
            and bool(b_events) and bool(c_events)
            and b_events[0].clock < init_start < init_end < c_events[0].clock
        )

        minimum = int(cfg_one(args.config, "gate_run_min_length"))
        gate_runs, gate_released = gate_observation(rows, issue.clock, minimum)

        post_issue = [row for row in rows if row.clock >= issue.clock]
        actual_request_runs = m6ia.request_runs(post_issue, 1)
        (b_count, issue_frame, gate_runs, gate_released,
         request_runs, counter_integrity) = inject_fault(
             args.fault, b_count, issue_frame, gate_runs, gate_released,
             actual_request_runs)

        # 故障注入後の観測量で前置き成立を評価する。
        preamble_ok = preamble_ok and b_count == 1

        facts, _blocks = m6ia.analyze_single(
            m6ia.Inputs(args.memlog, args.iolog, args.report, args.intlog), 1, 0, 0)
        expected_sha = cfg_one(args.config, "sector1_sha256")
        detail = result_detail(facts, memory, expected_sha)
        run_count = len(gate_runs)
        base.update({
            "reached": reached(preamble_ok, issue_frame, counter_integrity),
            "result": result_kind(detail, request_runs),
            "result_detail": detail,
            "gate_entered": run_count > 0,
            "gate_released": gate_released,
            "request_runs": request_runs,
            "gate_run_count": run_count,
            "gate_run_max_length": max((run.length for run in gate_runs), default=0),
            "rom_set_sha256": rom_gate.m6ib.rom_set_sha256(args.rom_dir),
        })
        print(json.dumps(base, sort_keys=True, separators=(",", ":")))
        return 0 if base["reached"] else 1
    except (OSError, UnicodeError, ValueError, m6ia.AnalysisError):
        print(json.dumps(base, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
