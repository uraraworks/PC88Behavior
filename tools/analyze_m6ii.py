#!/usr/bin/env python3
"""m6i-iのメモリ書込み記録を11行の3値結果へ縮約する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze_m6ia_main_sub import AnalysisError, MemEvent, read_memlog, sector_blocks  # noqa: E402
from d88_read_sector import D88Error, D88Reader  # noqa: E402

ARMS = ("I-S", "I-F-H", "I-F-D", "I-F-R", "I-F-RETRY")
ROWS = (
    (1, "A", 0, 0, 1), (2, "A", 0, 1, 1), (3, "A", 1, 0, 1),
    (4, "A", 0, 0, 16), (5, "A", 39, 1, 16), (6, "A", 20, 0, 8),
    (7, "A", 5, 1, 11), (8, "B", 0, 0, 1), (9, "B", 0, 1, 1),
    (10, "B", 39, 1, 16), (11, "A", 0, 0, 1),
)
ROW_MARKER_ADDRESS = 0xE038
READ_ENTRY_ADDRESS = 0xE002


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def analyze_events(memory: list[MemEvent], disk_a: bytes, disk_b: bytes) -> dict[str, object]:
    readers = {"A": D88Reader(disk_a), "B": D88Reader(disk_b)}
    markers = [(index, row.value) for index, row in enumerate(memory)
               if row.addr == ROW_MARKER_ADDRESS and 1 <= row.value <= len(ROWS)]
    observed = [value for _index, value in markers]
    ordered = observed == list(range(1, len(ROWS) + 1))
    details: list[dict[str, object]] = []
    entry_ok = True
    for position, (row_no, drive, cyl, head, sector) in enumerate(ROWS):
        interval: list[MemEvent] = []
        if position < len(markers) and markers[position][1] == row_no:
            start = markers[position][0] + 1
            end = markers[position + 1][0] if position + 1 < len(markers) else len(memory)
            interval = memory[start:end]
        entries = sum(row.addr == READ_ENTRY_ADDRESS and row.value == 0 for row in interval)
        entry_ok = entry_ok and entries >= 1
        blocks = sector_blocks(interval)
        block = blocks[-1] if blocks else None
        expected = readers[drive].read_sector(cyl, head, sector)
        result = ("row_no_data" if block is None else
                  "row_match" if block == expected else "row_mismatch")
        detail: dict[str, object] = {
            "row": row_no, "result": result, "entry_count": entries,
            "retried": entries > 1,
        }
        if block is not None:
            detail["receive_sha256"] = _sha(block)
        if result == "row_mismatch":
            detail["actual_coordinate"] = list(block[:4])
        details.append(detail)
    return {
        "reached": ordered and entry_ok,
        "row_marker_count": len(markers),
        "row_markers_in_order": ordered,
        "read_entry_rows": sum(int(row["entry_count"] >= 1) for row in details),
        "rows": details,
    }


def emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--memlog", required=True, type=Path)
    ap.add_argument("--disk-a", required=True, type=Path)
    ap.add_argument("--disk-b", required=True, type=Path)
    args = ap.parse_args()
    try:
        disk_a = args.disk_a.read_bytes()
        disk_b = args.disk_b.read_bytes()
        result = analyze_events(read_memlog(args.memlog), disk_a, disk_b)
        payload = {
            "arm": args.arm, **result,
            "memlog_sha256": _sha(args.memlog.read_bytes()),
            "disk_a_sha256": _sha(disk_a), "disk_b_sha256": _sha(disk_b),
        }
        emit(payload)
        return 0 if payload["reached"] else 1
    except (OSError, UnicodeError, ValueError, AnalysisError, D88Error):
        emit({"arm": args.arm, "reached": False, "row_marker_count": 0,
              "row_markers_in_order": False, "read_entry_rows": 0, "rows": []})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
