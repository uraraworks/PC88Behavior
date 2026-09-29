#!/usr/bin/env python3
"""m6i-j の共通 clock 転送を安全な意味値へ縮約する。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import analyze_main_to_sub as io
import analyze_record_boundaries as rec
import analyze_write_path as fdc
import m6ij_script as script


class GateError(ValueError):
    pass


def load(path: Path) -> list[io.Ev]:
    if path.stat().st_size > 128_000_000:
        raise GateError("log_capacity")
    rows, masked = io.parse_iolog(path)
    if not rows or masked:
        raise GateError("log_missing_or_masked")
    if any(b.clock <= a.clock for a, b in zip(rows, rows[1:])):
        raise GateError("clock")
    if any(b.seq <= a.seq for a, b in zip([e for e in rows if e.cpu == "main"],
                                           [e for e in rows if e.cpu == "main"][1:])):
        raise GateError("sequence")
    if any(b.seq <= a.seq for a, b in zip([e for e in rows if e.cpu == "sub"],
                                           [e for e in rows if e.cpu == "sub"][1:])):
        raise GateError("sequence")
    return rows


def exchanges(rows: list[io.Ev]) -> tuple[list[dict], list[io.Ev]]:
    sends = [e for e in rows if e.cpu == "main" and e.kind == "OUT" and e.port == "00FD"]
    received = [e for e in rows if e.cpu == "sub" and e.kind == "IN" and e.port == "00FC"]
    if not sends or len(sends) != len(received):
        raise GateError("transfer_count")
    if any(a.value != b.value or a.clock >= b.clock for a, b in zip(sends, received)):
        raise GateError("transfer_mapping")
    # 対応は単調な全単射。run番号を結ぶ仮定は置かない。
    main = [e for e in rows if e.cpu == "main"]
    fd_idx = [i for i, e in enumerate(main) if e.kind == "OUT" and e.port == "00FD"]
    mr = []
    current = []
    for i in fd_idx:
        if current and any(e.port not in ("00FE", "00FF") for e in main[current[-1]+1:i]):
            mr.append(current); current = []
        current.append(i)
    if current:
        mr.append(current)
    sub = [e for e in rows if e.cpu == "sub"]
    sr = rec.window_a_runs(sub, rec.sub_fc_indices(sub))
    if sum(map(len, mr)) != len(sends) or sum(map(len, sr)) != len(received):
        raise GateError("run_count")
    return ([{"length": len(run), "first_control": main[run[0]].value,
              "first_clock": main[run[0]].clock} for run in mr], received)


def coordinate(params: list[int]) -> tuple[int, int, int]:
    if len(params) < 4 or any(x is None for x in params[1:4]):
        raise GateError("fdc_coordinate")
    return tuple(params[1:4])


def location(coord: tuple[int, int, int]) -> str:
    c, h, r = coord
    if (c, h) == (18, 1):
        if 1 <= r <= 12: return "directory"
        if r == 13: return "marker"
        if 14 <= r <= 16: return "fat"
    return "body" if 0 <= c < 40 and h in (0, 1) and 1 <= r <= 16 else "unknown"


def records(rows: list[io.Ev], arm: str, runs: list[dict]) -> tuple[list[dict], list[dict]]:
    commands = [c for c in fdc.parse_commands(rows) if c.opcode in (5, 6)]
    incoming = [e for e in rows if e.cpu == "sub" and e.kind == "IN" and e.port == "00FC"]
    writes, order = [], []
    expected_body = script.body(arm)
    for command_index, c in enumerate(commands):
        coord = coordinate(c.param_values or [])
        if not c.param_values or (c.param_values[0] & 1) != int(arm[3])-1:
            raise GateError("fdc_drive")
        kind = location(coord)
        direction = "WRITE" if c.opcode == 5 else "READ"
        if direction == "WRITE":
            if c.data_bytes != 256 or c.result_bytes != 7 or c.data_values is None:
                raise GateError("fdc_write_shape")
            # FDC 書込相に渡った256位置を、直前の sub 受信列の全数と照合。
            candidates = [i for i in range(len(incoming)-255)
                          if c.clock < incoming[i].clock and
                          incoming[i+255].clock < c.end_clock and
                          [x.value for x in incoming[i:i+256]] == c.data_values]
            candidates = [i for i in candidates if i >= 6 and incoming[i-6].clock < c.clock]
            if len(candidates) != 1:
                raise GateError("write_data_mapping")
            i = candidates[0]
            control = [e.value for e in incoming[i-6:i]]
            if control[4:] != [coord[0]*2+coord[1], coord[2]]:
                raise GateError("control_coordinate")
            next_clock = commands[command_index+1].clock if command_index+1 < len(commands) else 2**63
            replies = [e for e in rows if e.cpu == "sub" and e.kind == "OUT"
                       and e.port == "00FD" and c.end_clock < e.clock < next_clock]
            main_replies = [e for e in rows if e.cpu == "main" and e.kind == "IN"
                            and e.port == "00FC" and c.end_clock < e.clock < next_clock]
            if len(replies) != 1 or len(main_replies) != 1 or replies[0].value != main_replies[0].value or replies[0].clock >= main_replies[0].clock:
                raise GateError("write_response")
            body_index = None
            linear = coord[0]*32 + coord[1]*16 + coord[2]-1
            if kind == "body" and 72*8 <= linear < 72*8 + 8:
                body_index = linear - 72*8
            if kind == "body" and 73*8 <= linear < 73*8 + 8:
                body_index = 8 + linear - 73*8
            if body_index is not None and body_index < (len(expected_body)+255)//256:
                start = body_index*256
                limit = min(256, len(expected_body)-start)
                if bytes(c.data_values[:limit]) != expected_body[start:start+limit]:
                    raise GateError("body_data")
            writes.append({"control": control, "drive": int(arm[3]),
                           "track": control[4], "r": control[5],
                           "coord": list(coord), "location": kind,
                           "data_match_count": 256, "body_index": body_index,
                           "response_count": 1,
                           "control_send_clocks": [e.clock for e in rows if e.cpu == "main" and
                                                   e.kind == "OUT" and e.port == "00FD"][i-6:i]})
        relevant = [r for r in runs if c.clock <= r["first_clock"] <= c.end_clock]
        order.append({"direction": direction, "drive": int(arm[3]),
                      "coord": list(coord), "location": kind,
                      "main_send_lengths": [r["length"] for r in relevant],
                      "first_control": [],
                      "fdc_result_count": c.result_bytes})
    if not writes:
        raise GateError("write_missing")
    return writes, order


def axis_values(records_by_arm: dict[str, list[dict]]) -> dict[str, list[str]]:
    all_records = [r for arm in script.ARMS for r in records_by_arm.get(arm, [])]
    if not all_records:
        return {str(i): [] for i in range(4)}
    # 群は制御・応答の閉じ目が観測できた場合にのみ count_order を付す。
    for records_ in records_by_arm.values():
        for index, row in enumerate(records_):
            row.setdefault("count_order", (len(records_), index+1))
    matched = {}
    for pos in range(4):
        candidates = []
        for axis in script.AXES:
            keys = [0 if axis == "constant" else r[axis] for r in all_records]
            vals = [r["control"][pos] for r in all_records]
            if all((keys[i] == keys[j]) == (vals[i] == vals[j])
                   for i in range(len(vals)) for j in range(i+1, len(vals))):
                candidates.append(axis)
        matched[str(pos)] = candidates
    return matched


def judgment(candidates: dict[str, list[str]], groups_clear: bool = True) -> str:
    if not groups_clear: return "inconclusive_group_boundary"
    if any(not x for x in candidates.values()): return "inconclusive_control_other"
    if any(len(x) > 1 for x in candidates.values()): return "inconclusive_multiple_candidates"
    return "m6i_j_main_write_send_unique"


def confounded(records_by_arm: dict[str, list[dict]], candidates: dict[str, list[str]]) -> bool:
    all_records = [r for records_ in records_by_arm.values() for r in records_]
    for choices in candidates.values():
        if len(choices) != 1 or choices[0] == "constant":
            continue
        axis = choices[0]
        others = [x for x in script.AXES if x not in (axis, "constant")]
        if not any(a[axis] != b[axis] and all(a[x] == b[x] for x in others)
                   for i, a in enumerate(all_records) for b in all_records[i+1:]):
            return True
    return False


def analyze(rows: list[io.Ev], arm: str) -> dict:
    runs, received = exchanges(rows)
    writes, order = records(rows, arm, runs)
    # READ を挟まない連続 WRITE を要求群とし、各応答の閉じ目を検証済みのときだけ確定。
    write_at = 0
    index = 0
    while index < len(order):
        if order[index]["direction"] != "WRITE":
            index += 1; continue
        end = index
        while end < len(order) and order[end]["direction"] == "WRITE":
            end += 1
        for position in range(index, end):
            writes[write_at]["count_order"] = (end-index, position-index+1)
            write_at += 1
        index = end
    safe = {clock for write in writes for clock in write.pop("control_send_clocks")}
    return {"arm": arm, "send_runs": [{k: v for k, v in run.items()
                                      if k != "first_clock" and
                                      (k != "first_control" or run["first_clock"] in safe)}
                                    for run in runs],
            "sub_receive_count": len(received), "writes": writes, "order": order}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iolog", type=Path, required=True)
    ap.add_argument("--arm", choices=script.ARMS, required=True)
    args = ap.parse_args()
    try:
        print(json.dumps(analyze(load(args.iolog), args.arm), sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, ValueError, fdc.SafeError):
        print('{"judgment":"gate_failed"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
