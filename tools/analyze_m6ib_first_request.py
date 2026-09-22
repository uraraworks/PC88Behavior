#!/usr/bin/env python3
"""m6i-b B0〜B6の実ログを、件数・順序・真偽・SHAだけへ縮約する。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_boot_fdc_sequence as boot_fdc  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_m6ia_main_sub as m6ia  # noqa: E402
import build_m6ib_measure_rom as build_m6ib  # noqa: E402

SUB_EXEC_RE = re.compile(r"\[サブCPU\] 総アクセス回数: exec=(\d+)")
FRAME_LIMIT = {"B1": 55, "B2": 55, "B3": 55, "B4": 55, "B5": 55}
SCREEN_EXPECTED = (3, 20, "580684fbac954c32feb596092a55859a03090d0030a2297c8bb39a3424583f8e")


def find_read_issue(rows: list[m2s.Ev]) -> tuple[m2s.Ev, m2s.Ev]:
    """通常READ先頭データ位置と、そのSEND開始OUT $FFを返す。"""
    data = next((row for row in rows if row.cpu == "main" and row.kind == "OUT"
                 and row.port == "00FD" and row.value == 0x02), None)
    if data is None:
        raise ValueError("read issue not reached")
    starts = [row for row in rows if row.cpu == "main" and row.kind == "OUT"
              and row.port == "00FF" and row.value == 0x0F and row.clock < data.clock]
    if not starts:
        raise ValueError("read issue start not reached")
    return starts[-1], data


def init_shape(rows: list[m2s.Ev]) -> tuple[int, int, int, int, int] | None:
    sub = [row for row in rows if row.cpu == "sub"]
    window = boot_fdc.find_boot_init_window(sub)
    if window is None:
        return None
    start, end = window
    runs = boot_fdc.segment_runs(sub[start:end])
    alternating = all(run["kind"] == ("OUT" if i % 2 == 0 else "IN")
                      for i, run in enumerate(runs))
    if len(runs) % 2 or not alternating or start == end:
        return None
    return (len(runs) // 2, sub[start].clock, sub[end - 1].clock,
            sub[start].frame, sub[end - 1].frame)


def writes_since_last_start(rows: list[m6ia.MemEvent]) -> int:
    current: set[int] = set()
    for row in rows:
        if row.addr == 0xDF00:
            current = set()
        if 0xDF00 <= row.addr <= 0xDFFF:
            current.add(row.addr)
    return len(current)


def classify_result(facts: dict[str, object], memory: list[m6ia.MemEvent],
                    expected_sha: str) -> str:
    """G8の5結果を優先順位つきで別名へ分類する。"""
    if facts["timeout_marker_count"]:
        return "timeout"
    positions = writes_since_last_start(memory)
    if positions == 255:
        return "one_position_missing"
    if facts["receive_complete_block_count"] and facts["receive_sha256"] != expected_sha:
        return "sha_mismatch"
    if (facts["receive_complete_block_count"] and facts["receive_sha256"] == expected_sha
            and not facts["key_input_accepted"]):
        return "steady_wait_not_returned"
    if (facts["receive_complete_block_count"] and facts["receive_sha256"] == expected_sha
            and facts["key_input_accepted"]):
        return "positions_256_match"
    return "other_incomplete"


def b6_reached(arm: str, facts: dict[str, object]) -> bool:
    if arm in ("B6-A0", "B6-A1"):
        return m6ia.normal_reach_indicators(facts, 1)
    if arm == "B6-A2":
        return (facts["request_marker_count"] == 1
                and facts["fdc_sense_drive_status_count"] >= 2
                and facts["fdc_read_data_count"] == 0
                and facts["timeout_marker_count"] == 1)
    if arm == "B6-A4-cont":
        return facts["fault_cont_marker_count"] >= 1
    if arm == "B6-A4-pair":
        return facts["fault_pair_marker_count"] >= 1
    if arm == "B6-A5":
        return (m6ia.normal_reach_indicators(facts, 200)
                and facts["bank_probe_count"] == 200
                and facts["repeat_done_marker_count"] == 1
                and facts["main_interrupt_count"] >= 1
                and facts["key_input_accepted"])
    return False


def b6_result(arm: str, facts: dict[str, object]) -> tuple[str, bool]:
    """到達とは独立に、m6i-aの元の結果判定名をそのまま返す。"""
    if arm in ("B6-A0", "B6-A1", "B6-A2", "B6-A5"):
        source_arm = arm.removeprefix("B6-")
        screen = SCREEN_EXPECTED if source_arm == "A5" else None
        judgment, passed, _reason = m6ia.judge_one(source_arm, facts, screen)
        return judgment, passed
    escaped = m6ia.reached_normal(facts, 1, 1)
    return ("sequence_negative_escaped" if escaped else "sequence_negative_detected",
            not escaped)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=build_m6ib.ARMS)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--memlog", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--intlog", type=Path)
    ap.add_argument("--rom-dir", required=True, type=Path)
    ap.add_argument("--stop-report", type=Path)
    ap.add_argument("--fault", choices=("b0_send", "b1_sub_step", "b2_recv",
                                         "b3_init_batch", "b4_round0_insert",
                                         "b5_round0_delete", "b6_reach"))
    args = ap.parse_args()

    try:
        m2s_rows, masked = m2s.parse_iolog(args.iolog)
        if sum(masked.values()):
            raise ValueError("masked live input")
        memory = m6ia.read_memlog(args.memlog)
        issue, issue_data = find_read_issue(m2s_rows)
        before = [row for row in m2s_rows if row.clock < issue.clock]
        send_try_count = sum(row.cpu == "main" and row.kind == "OUT"
                             and row.port == "00FF" and row.value == 0x0F
                             and row.clock == issue.clock for row in m2s_rows)
        if args.fault == "b0_send":
            send_try_count = 0
        gate_fe = sum(row.cpu == "sub" and row.kind == "IN" and row.port == "00FE"
                      and issue.clock < row.clock < issue_data.clock for row in m2s_rows)

        sector = 2 if args.arm == "B6-A1" else 1
        facts, _blocks = m6ia.analyze_single(
            m6ia.Inputs(args.memlog, args.iolog, args.report, args.intlog), sector, 0, 0)
        if args.fault == "b6_reach":
            marker_by_branch = {
                "B6-A0": "request_marker_count",
                "B6-A1": "recv256_marker_count",
                "B6-A2": "timeout_marker_count",
                "B6-A4-cont": "fault_cont_marker_count",
                "B6-A4-pair": "fault_pair_marker_count",
                "B6-A5": "repeat_done_marker_count",
            }
            marker = marker_by_branch.get(args.arm)
            if marker is None:
                raise ValueError("B6 fault on non-B6 arm")
            facts[marker] = 0
        expected_sha = m6ia.EXPECT_SHA[sector]
        result_kind = classify_result(facts, memory, expected_sha)

        mark_b = m6ia.one_writes(memory, 0xE00B)
        mark_c = m6ia.one_writes(memory, 0xE00C)
        shape = init_shape(m2s_rows)
        batches, init_start, init_end, init_start_frame, init_end_frame = (
            shape if shape is not None else (0, -1, -1, -1, -1))
        a_count = int(batches == 7 and init_end < issue.clock)
        b_count = mark_b
        c_count = mark_c
        if args.fault == "b3_init_batch":
            batches = max(0, batches - 1)
            a_count = 0
        if args.fault == "b4_round0_insert":
            c_count = 1
        if args.fault == "b5_round0_delete":
            c_count = 0

        counter_writes = [(row.frame, row.value) for row in memory if row.addr == 0xE009]
        increments = counter_writes[1:]
        expected_increments = FRAME_LIMIT.get(args.arm)
        counter_corresponds = True
        if expected_increments is not None:
            counter_corresponds = (len(increments) == expected_increments
                                   and bool(increments)
                                   and increments[-1][0] == 59)

        startup_send = sum(row.cpu == "main" and row.kind == "OUT"
                           and row.port == "00FD" for row in before)
        startup_recv = sum(row.cpu == "sub" and row.kind == "IN"
                           and row.port == "00FC" for row in before)
        if args.fault == "b2_recv":
            startup_recv = max(0, startup_recv - 1)
        round0_responses = sum(row.cpu == "sub" and row.kind == "OUT"
                               and row.port == "00FD" for row in before)
        post_issue_send_positions = sum(row.cpu == "main" and row.kind == "OUT"
                                        and row.port == "00FD" and row.clock >= issue.clock
                                        for row in m2s_rows)
        b_events = [row for row in m2s_rows if row.cpu == "sub" and row.kind == "IN"
                    and row.port == "00FC" and row.clock < init_start]
        c_events = [row for row in m2s_rows if row.cpu == "main" and row.kind == "IN"
                    and row.port == "00FC" and init_end < row.clock < issue.clock]
        order_b_a_c = bool(b_events and c_events and
                            b_events[0].clock < init_start < init_end < c_events[0].clock)

        payload: dict[str, object] = {
            "arm": args.arm,
            "fault_injection": args.fault,
            "read_issue_count": 1,
            "read_issue_frame": issue.frame,
            "read_issue_frame_60": issue.frame == 60,
            "first_send_try_count": send_try_count,
            "frame_counter_increment_count": len(increments),
            "counter_to_frame_correspondence": counter_corresponds,
            "release_gate_handoff_count": gate_fe,
            "a_count": a_count, "b_count": b_count, "c_count": c_count,
            "fdc_init_batch_count": batches,
            "fdc_init_start_frame": init_start_frame,
            "fdc_init_end_frame": init_end_frame,
            "startup_send_count": startup_send,
            "startup_recv_count": startup_recv,
            "pre_issue_round0_response_count": round0_responses,
            "post_issue_send_position_count": post_issue_send_positions,
            "order_b_a_c": order_b_a_c,
            "result_kind": result_kind,
            "receive_position_count": facts["receive_position_count"],
            "receive_sha256": facts["receive_sha256"],
            "request_marker_count": facts["request_marker_count"],
            "recv256_marker_count": facts["recv256_marker_count"],
            "success_marker_count": facts["success_marker_count"],
            "request_run_count": facts["request_run_count"],
            "complete_protocol_run_count": facts["complete_protocol_run_count"],
            "fdc_read_data_count": facts["fdc_read_data_count"],
            "timeout_marker_count": facts["timeout_marker_count"],
            "key_input_accepted": facts["key_input_accepted"],
            "rom_set_sha256": build_m6ib.rom_set_sha256(args.rom_dir),
        }

        required = send_try_count == 1
        if args.arm == "B0":
            required = required and (a_count, b_count, c_count) == (0, 0, 0)
        elif args.arm == "B1":
            if args.stop_report is None:
                raise ValueError("stop report missing")
            match = SUB_EXEC_RE.search(args.stop_report.read_text(encoding="utf-8", errors="strict"))
            if match is None:
                raise ValueError("sub exec count missing")
            stop_rows, stop_masked = m2s.parse_iolog(args.stop_report.with_suffix(".io.txt"))
            if sum(stop_masked.values()):
                raise ValueError("masked stop input")
            sub_exec = int(match.group(1)) + int(args.fault == "b1_sub_step")
            fdc = sum(row.cpu == "sub" and row.port in ("00FA", "00FB") for row in stop_rows)
            sends = sum(row.cpu == "main" and row.kind == "OUT" and row.port == "00FD"
                        for row in stop_rows)
            stop_zero = sub_exec == fdc == sends == 0
            payload.update({"stop_sub_cpu_exec_count": sub_exec,
                            "stop_fdc_io_count": fdc, "stop_main_send_count": sends,
                            "stop_0_59_all_zero": stop_zero})
            required = required and stop_zero and (a_count, b_count, c_count) == (0, 0, 0)
        elif args.arm == "B2":
            required = required and startup_send == startup_recv == 1 and batches == 0 \
                and round0_responses == 0 and (a_count, b_count, c_count) == (0, 1, 0)
        elif args.arm == "B3":
            required = required and startup_send == startup_recv == round0_responses == 0 \
                and (a_count, b_count, c_count) == (1, 0, 0)
        elif args.arm == "B4":
            required = required and startup_send == startup_recv == 1 \
                and round0_responses == 0 and (a_count, b_count, c_count) == (1, 1, 0)
        else:
            required = required and (a_count, b_count, c_count) == (1, 1, 1) \
                and order_b_a_c
        if args.arm in FRAME_LIMIT:
            required = required and issue.frame == 60 and counter_corresponds and gate_fe > 0
        if args.arm in build_m6ib.B6_BRANCHES:
            reached = b6_reached(args.arm, facts)
            payload["m6ia_reached"] = reached
            judgment, passed = b6_result(args.arm, facts)
            payload["m6ia_judgment"] = judgment
            payload["m6ia_passed"] = passed
            required = required and reached

        payload["analysis_ok"] = required
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return 0 if required else 1
    except (OSError, UnicodeError, ValueError, m6ia.AnalysisError):
        print(json.dumps({"arm": args.arm, "analysis_ok": False},
                         sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
