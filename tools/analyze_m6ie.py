#!/usr/bin/env python3
"""m6i-e の実ログを、到達・成否・SHA・登録済み名称だけへ縮約する。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_m6ia_main_sub as m6ia  # noqa: E402
import analyze_m6ib_first_request as m6ib  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402
import build_m6ie_measure_rom as build_m6ie  # noqa: E402
import build_m6ib_measure_rom as roms  # noqa: E402

ARMS = build_m6ie.ARMS
FAULTS = ("preamble_marker_deleted", "read_issue_frame_changed",
          "request_counter_fixed")


def reached(preamble_ok: bool, issue_frame: int,
            request_counter_integrity: bool) -> bool:
    return preamble_ok and issue_frame == 60 and request_counter_integrity


def preamble_complete(b_count: int, c_count: int, init_batches: int,
                      b_clock: int | None, init_start: int, init_end: int,
                      c_clock: int | None) -> bool:
    """前置き b→a→c が各1回、この順で完了したことだけを判定する。"""
    return (b_count == 1 and c_count == 1 and init_batches == 7
            and b_clock is not None and c_clock is not None
            and b_clock < init_start < init_end < c_clock)


def result_detail(facts: dict[str, object], memory: list[m6ia.MemEvent],
                  expected_sha: str) -> str:
    return m6ib.classify_result(facts, memory, expected_sha)


def result_kind(detail: str, request_runs: int) -> str:
    return "success" if detail == "positions_256_match" and request_runs == 1 else "failure"


def inject_fault(fault: str | None, b_count: int, issue_frame: int,
                 actual_request_runs: int) -> tuple[int, int, int, bool]:
    if fault == "preamble_marker_deleted":
        b_count = 0
    if fault == "read_issue_frame_changed":
        issue_frame += 1
    request_runs = 0 if fault == "request_counter_fixed" else actual_request_runs
    integrity = fault != "request_counter_fixed" and request_runs == actual_request_runs
    return b_count, issue_frame, request_runs, integrity


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
    """固定7ファイルだけを読む。ディレクトリ列挙を到達判定へ混ぜない。"""
    return roms.rom_set_sha256(rom_dir)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--memlog", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--intlog", type=Path)
    ap.add_argument("--rom-dir", required=True, type=Path)
    ap.add_argument("--config", type=Path, default=HERE / "m6ie_frozen.tsv")
    ap.add_argument("--fault", choices=FAULTS)
    args = ap.parse_args()
    base: dict[str, object] = {
        "arm": args.arm, "reached": False, "result": "failure",
        "result_detail": "other_incomplete", "request_runs": 0,
        "fault_injection": args.fault,
    }
    try:
        rows, masked = m2s.parse_iolog(args.iolog)
        if sum(masked.values()):
            raise ValueError("masked live input")
        memory = m6ia.read_memlog(args.memlog)
        issue, _issue_data = m6ib.find_read_issue(rows)
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
        preamble_ok = preamble_complete(
            b_count, c_count, init_batches,
            b_events[0].clock if b_events else None, init_start, init_end,
            c_events[0].clock if c_events else None)
        actual_request_runs = m6ia.request_runs(
            [row for row in rows if row.clock >= issue.clock], 1)
        b_count, issue_frame, request_runs, integrity = inject_fault(
            args.fault, b_count, issue.frame, actual_request_runs)
        preamble_ok = preamble_ok and b_count == 1
        facts, _blocks = m6ia.analyze_single(
            m6ia.Inputs(args.memlog, args.iolog, args.report, args.intlog), 1, 0, 0)
        detail = result_detail(facts, memory, cfg_one(args.config, "sector1_sha256"))
        base.update({
            "reached": reached(preamble_ok, issue_frame, integrity),
            "result": result_kind(detail, request_runs),
            "result_detail": detail,
            "request_runs": request_runs,
            "rom_set_sha256": rom_digest(args.rom_dir),
        })
        print(json.dumps(base, sort_keys=True, separators=(",", ":")))
        return 0 if base["reached"] else 1
    except (OSError, UnicodeError, ValueError, m6ia.AnalysisError):
        print(json.dumps(base, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
