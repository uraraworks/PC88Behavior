#!/usr/bin/env python3
"""m6i-b B1/B2/B5の実ログを、件数・順序・真偽・SHAだけへ縮約する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_boot_fdc_sequence as boot_fdc  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402
import build_m6ib_measure_rom as build_m6ib  # noqa: E402

MEM_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+([0-9A-Fa-f]{4})\s+"
    r"([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s*$"
)
SUB_EXEC_RE = re.compile(r"\[サブCPU\] 総アクセス回数: exec=(\d+)")


def mem_rows(path: Path) -> list[tuple[int, int, int]]:
    rows = []
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        match = MEM_RE.match(line)
        if match:
            rows.append((int(match.group(2)), int(match.group(4), 16),
                         int(match.group(5), 16)))
    return rows


def one_count(rows: list[tuple[int, int, int]], addr: int) -> int:
    return sum(row_addr == addr and value == 1 for _frame, row_addr, value in rows)


def sector_blocks(rows: list[tuple[int, int, int]]) -> list[bytes]:
    blocks: list[bytes] = []
    current: list[int] = []
    expected = 0xDF00
    for _frame, addr, value in rows:
        if not 0xDF00 <= addr <= 0xDFFF:
            continue
        if addr == 0xDF00:
            current = []
            expected = 0xDF00
        if addr != expected:
            current = []
            expected = 0xDF00
            continue
        current.append(value)
        expected += 1
        if expected == 0xE000:
            blocks.append(bytes(current))
            current = []
            expected = 0xDF00
    return blocks


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


def init_shape(rows: list[m2s.Ev]) -> tuple[int, int, int] | None:
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
    return len(runs) // 2, sub[start].clock, sub[end - 1].clock


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=("B1", "B2", "B5"))
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--memlog", required=True, type=Path)
    ap.add_argument("--rom-dir", required=True, type=Path)
    ap.add_argument("--stop-report", type=Path)
    args = ap.parse_args()

    try:
        m2s_rows, masked = m2s.parse_iolog(args.iolog)
        if sum(masked.values()):
            raise ValueError("masked live input")
        memory = mem_rows(args.memlog)
        issue, issue_data = find_read_issue(m2s_rows)
        before = [row for row in m2s_rows if row.clock < issue.clock]
        gate_fe = sum(row.cpu == "sub" and row.kind == "IN" and row.port == "00FE"
                      and issue.clock < row.clock < issue_data.clock for row in m2s_rows)
        blocks = sector_blocks(memory)
        counter_writes = [(frame, value) for frame, addr, value in memory
                          if addr == 0xE009]
        increments = counter_writes[1:]
        per_frame: dict[int, int] = {}
        for frame, _value in increments:
            per_frame[frame] = per_frame.get(frame, 0) + 1
        counter_corresponds = (
            len(increments) == 55
            and bool(increments)
            and increments[0][0] == 6
            and increments[-1][0] == 59
            and per_frame.get(6) == 2
            and all(count == 1 for frame, count in per_frame.items() if frame != 6)
        )
        payload: dict[str, object] = {
            "arm": args.arm,
            "read_issue_count": 1,
            "read_issue_frame": issue.frame,
            "read_issue_frame_60": issue.frame == 60,
            "frame_counter_increment_count": len(increments),
            "counter_to_frame_correspondence": counter_corresponds,
            "release_gate_handoff_count": gate_fe,
            "release_gate_handoff_observed": gate_fe > 0,
            "receive_complete_count": len(blocks),
            "receive_sha256": hashlib.sha256(blocks[-1]).hexdigest() if blocks else None,
            "rom_set_sha256": build_m6ib.rom_set_sha256(args.rom_dir),
        }

        if args.arm == "B1":
            if args.stop_report is None:
                raise ValueError("stop report missing")
            match = SUB_EXEC_RE.search(args.stop_report.read_text(
                encoding="utf-8", errors="strict"))
            if match is None:
                raise ValueError("sub exec count missing")
            stop_rows, stop_masked = m2s.parse_iolog(args.stop_report.with_suffix(".io.txt"))
            if sum(stop_masked.values()):
                raise ValueError("masked stop input")
            sub_exec = int(match.group(1))
            fdc = sum(row.cpu == "sub" and row.port in ("00FA", "00FB")
                      for row in stop_rows)
            sends = sum(row.cpu == "main" and row.kind == "OUT" and row.port == "00FD"
                        for row in stop_rows)
            payload.update({
                "stop_sub_cpu_exec_count": sub_exec,
                "stop_fdc_io_count": fdc,
                "stop_main_send_count": sends,
                "stop_0_59_all_zero": sub_exec == fdc == sends == 0,
            })
        elif args.arm == "B2":
            startup_send = sum(row.cpu == "main" and row.kind == "OUT"
                               and row.port == "00FD" for row in before)
            startup_recv = sum(row.cpu == "sub" and row.kind == "IN"
                               and row.port == "00FC" for row in before)
            fdc = sum(row.cpu == "sub" and row.port in ("00FA", "00FB")
                      for row in before)
            round0 = sum(row.cpu == "sub" and row.kind == "OUT"
                         and row.port == "00FD" for row in before)
            payload.update({
                "startup_send_count": startup_send,
                "startup_recv_count": startup_recv,
                "pre_issue_fdc_io_count": fdc,
                "pre_issue_round0_response_count": round0,
                "startup_only_before_issue": (
                    startup_send == startup_recv == 1 and fdc == round0 == 0),
            })
        else:
            shape = init_shape(m2s_rows)
            if shape is None:
                raise ValueError("boot init shape missing")
            batches, init_start, init_end = shape
            b_events = [row for row in m2s_rows if row.cpu == "sub" and row.kind == "IN"
                        and row.port == "00FC" and row.clock < init_start]
            c_events = [row for row in m2s_rows if row.cpu == "main" and row.kind == "IN"
                        and row.port == "00FC" and init_end < row.clock < issue.clock]
            mark_b = one_count(memory, 0xE00B)
            mark_c = one_count(memory, 0xE00C)
            order_ok = bool(b_events and c_events and
                            b_events[0].clock < init_start < init_end < c_events[0].clock)
            payload.update({
                "b_count": mark_b,
                "a_count": int(batches == 7),
                "c_count": mark_c,
                "fdc_init_batch_count": batches,
                "order_b_a_c": order_ok,
                "b_a_c_once_in_order": mark_b == mark_c == 1 and batches == 7 and order_ok,
            })

        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        required = (payload["read_issue_frame_60"]
                    and payload["counter_to_frame_correspondence"]
                    and payload["release_gate_handoff_observed"])
        if args.arm == "B1":
            required = required and payload["stop_0_59_all_zero"]
        elif args.arm == "B2":
            required = required and payload["startup_only_before_issue"]
        else:
            required = required and payload["b_a_c_once_in_order"]
        return 0 if required else 1
    except (OSError, UnicodeError, ValueError):
        print(json.dumps({"arm": args.arm, "analysis_ok": False},
                         sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
