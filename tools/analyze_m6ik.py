#!/usr/bin/env python3
"""m6i-k の生ログを事前登録 §5.3 の欄だけに縮約する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_main_to_sub import Ev, parse_iolog  # noqa: E402
from analyze_m6ia_main_sub import MemEvent, read_memlog, sector_blocks  # noqa: E402

ARMS = ("K-00", "K-01", "K-F0", "K-F1", "K-M1", "K-FR")
ROWS = ((1, 0, 0, 1), (2, 0, 37, 13), (3, 1, 37, 13),
        (4, 1, 1, 1), (5, 0, 1, 1), (6, 1, 0, 1))
MARKER = 0xE039
PRE_MARKER = 0xE03A


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def status_names(st0: int, st1: int) -> dict[str, list[str]]:
    ic = ("normal_termination", "abnormal_termination", "invalid_command",
          "abnormal_ready_transition")[(st0 >> 6) & 3]
    return {
        "st0": [ic] + [name for bit, name in ((5, "seek_end"), (4, "equipment_check"),
                 (3, "not_ready"), (2, "head_address"), (1, "unit_bit1"),
                 (0, "unit_bit0")) if st0 & (1 << bit)],
        "st1": [name for bit, name in ((7, "end_of_cylinder"), (5, "data_error"),
                 (4, "overrun"), (2, "no_data"), (1, "not_writable"),
                 (0, "missing_address_mark")) if st1 & (1 << bit)],
    }


def classify(drive: int, track: int, sector: int, command: tuple[int, ...] | None) -> str:
    if command is None:
        return "no_read"
    us, c, h, r = command
    if (us & 3) != drive or r != sector or ((us >> 2) & 1) != h:
        return "other"
    logical = (c, h) == (track >> 1, track & 1)
    cylinder = (c, h) == (track, 0)
    if logical and cylinder:
        return "agree"
    if logical:
        return "logical"
    if cylinder:
        return "cylinder"
    return "other"


def read_commands(events: list[Ev]) -> list[tuple[Ev, tuple[int, ...], dict[str, list[str]]]]:
    """FDC コマンドの引数だけを保持し、READ DATA のデータ部を捨てる。"""
    writes = [e for e in events if e.cpu == "sub" and e.kind == "OUT" and e.port == "00FB"]
    found = []
    for i, event in enumerate(writes):
        if event.value not in (0x46, 0x66) or i + 8 >= len(writes):
            continue
        args = writes[i + 1:i + 9]
        if any(x.value is None for x in args):
            continue
        end = writes[i + 9].clock if i + 9 < len(writes) else float("inf")
        result = [x.value for x in events if x.cpu == "sub" and x.kind == "IN"
                  and x.port == "00FB" and args[-1].clock < x.clock < end]
        names = status_names(result[-7], result[-6]) if len(result) >= 7 else {"st0": [], "st1": []}
        found.append((event, tuple(int(x.value) for x in args[:4]), names))
    return found


def seek_commands(events: list[Ev]) -> list[tuple[Ev, int]]:
    writes = [e for e in events if e.cpu == "sub" and e.kind == "OUT" and e.port == "00FB"]
    return [(event, int(writes[i + 2].value)) for i, event in enumerate(writes)
            if event.value == 0x0F and i + 2 < len(writes) and writes[i + 2].value is not None]


def analyze_events(arm: str, events: list[Ev], memory: list[MemEvent]) -> dict[str, object]:
    sends = [e for e in events if e.cpu == "main" and e.kind == "OUT"
             and e.port == "00FD"]
    markers = [(i, e) for i, e in enumerate(memory) if e.addr == MARKER and 1 <= e.value <= 6]
    pre = next((e for e in memory if e.addr == PRE_MARKER and e.value == 1), None)
    expected = [x[0] for x in ROWS]
    ordered = [e.value for _, e in markers] == expected
    requests: list[list[Ev]] = []
    cursor = 0
    for _n, drive, track, sector in ROWS:
        want = (2, 1 if arm in ("K-01", "K-F1", "K-M1", "K-FR") else 0,
                drive, track, sector + (arm == "K-FR"))
        matches = []
        while cursor + 4 < len(sends):
            seq = tuple(x.value for x in sends[cursor:cursor + 5])
            if seq == want:
                matches.append(sends[cursor])
                cursor += 5
                # 2回目の同じ要求は次の行の開始より前にある。
                while cursor + 4 < len(sends) and tuple(x.value for x in sends[cursor:cursor + 5]) == want:
                    matches.append(sends[cursor]); cursor += 5
                break
            cursor += 1
        requests.append(matches)
    starts = [x[0].clock if x else None for x in requests]
    fdc = read_commands(events)
    seeks = seek_commands(events)
    details = []
    for pos, (number, drive, track, sector) in enumerate(ROWS):
        start = starts[pos]
        end = next((x for x in starts[pos + 1:] if x is not None), float("inf"))
        reads = [(e, args, status) for e, args, status in fdc
                 if start is not None and start < e.clock < end]
        first = reads[0] if reads else None
        command = first[1] if first else None
        category = classify(drive, track, sector, command)
        interval = []
        if ordered:
            a = markers[pos][0] + 1
            b = markers[pos + 1][0] if pos + 1 < 6 else len(memory)
            interval = memory[a:b]
        blocks = sector_blocks(interval)
        block = blocks[-1] if blocks else None
        stamp = list(block[:4]) if block is not None else None
        success_marks = [e.value for e in interval if e.addr == 0xE002]
        success = block is not None and bool(success_marks) and success_marks[-1] == 1
        if stamp is None:
            disagree = False
        elif command is None or (command[0] & 3) not in (0, 1):
            disagree = True
        else:
            disagree = tuple(stamp) != (0xA1 if (command[0] & 3) == 0 else 0xB2,
                                         command[1], command[2], command[3])
        detail: dict[str, object] = {
            "row": number, "classification": category,
            "success": "success" if success else "failed",
            "stamp": stamp, "index_disagree": disagree,
            "read_data_count": len(reads),
            "status": [item[2] for item in reads],
        }
        if command is not None:
            detail["fdc_read_args"] = list(command)
            preceding_seeks = [c for e, c in seeks if start is not None and start < e.clock < first[0].clock]
            detail["fdc_seek_c"] = preceding_seeks[-1] if preceding_seeks else None
        if block is not None:
            detail["receive_sha256"] = sha(block)
        details.append(detail)
    first_start = starts[0]
    pre_fd = 0
    pre_shape = False
    if first_start is not None:
        prior = [s for s in sends if s.clock < first_start]
        pre_code = 1 if arm == "K-M1" else 15
        pairs = [prior[i + 1] for i in range(len(prior) - 1)
                 if prior[i].value == 0x17 and prior[i + 1].value == pre_code]
        pair = pairs[0] if pairs else None
        pre_shape = (bool(prior) and prior[0].value == 0 and
                     (len(pairs) == 0 if arm in ("K-00", "K-01") else len(pairs) == 1))
        anchor = pair.clock if pair is not None else (prior[0].clock if prior else -1)
        pre_fd = sum(e.cpu == "sub" and e.kind == "OUT" and e.port == "00FD"
                     and anchor < e.clock < first_start for e in events)
    reached = (ordered and pre is not None and pre_shape and all(requests) and
               all(start is not None and (reads_for_row := [e for e, _, _ in fdc
                   if start < e.clock < next((x for x in starts[i + 1:] if x is not None), float("inf"))])
                   and reads_for_row[0].frame - requests[i][0].frame <= 2000
                   or (start is not None and details[i]["classification"] == "no_read"
                       and events[-1].frame - requests[i][0].frame >= 2000)
                   for i, start in enumerate(starts)))
    return {"arm": arm, "reached": reached, "pre_send_fd_count": pre_fd, "rows": details,
            "requests_sent": sum(bool(x) for x in requests)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--iolog", type=Path, required=True)
    ap.add_argument("--memlog", type=Path, required=True)
    args = ap.parse_args()
    try:
        events, masked = parse_iolog(args.iolog)
        if masked or not events or events[0].frame != 0:
            raise ValueError("masked_or_not_frame_zero")
        result = analyze_events(args.arm, events, read_memlog(args.memlog))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["reached"] else 1
    except (OSError, ValueError, IndexError):
        print(json.dumps({"arm": args.arm, "reached": False, "rows": [],
                          "requests_sent": 0, "pre_send_fd_count": 0},
                         sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
