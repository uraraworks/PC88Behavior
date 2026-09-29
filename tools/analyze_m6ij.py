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


def exchanges(rows: list[io.Ev]) -> tuple[list[dict], list[io.Ev], dict[int, int], list[tuple[int, io.Ev]]]:
    sends = [e for e in rows if e.cpu == "main" and e.kind == "OUT" and e.port == "00FD"]
    received = [e for e in rows if e.cpu == "sub" and e.kind == "IN" and e.port == "00FC"]
    if not sends or not received:
        raise GateError("transfer_mapping")
    # 各受信を、その時点で直近の送信へ結ぶ。同一送信の再読は認めない。
    send_index = -1
    linked: dict[int, int] = {}
    for event in rows:
        if event.cpu == "main" and event.kind == "OUT" and event.port == "00FD":
            send_index += 1
        elif event.cpu == "sub" and event.kind == "IN" and event.port == "00FC":
            if send_index < 0 or send_index in linked or sends[send_index].value != event.value:
                raise GateError("transfer_mapping")
            linked[send_index] = event.clock
    unread = [(i + 1, send) for i, send in enumerate(sends) if i not in linked]
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
              "first_clock": main[run[0]].clock} for run in mr], received,
            {sends[i].clock: clock for i, clock in linked.items()}, unread)


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
            # 事前登録 §3「各 WRITE の直前に対応する制御6位置と256位置のデータを同定」と
            # l3-subrom.md 1.35節（データ部は直前に sub が受信した列の末尾256バイト、
            # 受信後に WRITE DATA へ進む）に従い、WRITE コマンドより前の受信の末尾256位置を取る。
            # 旧版はコマンド開始後の受信を探しており、事前登録と逆だった（m6i-j 5回目で判明）。
            before = [k for k, x in enumerate(incoming) if x.clock < c.clock]
            if len(before) < 262:
                raise GateError("write_data_mapping")
            i = before[-1] - 255
            if [x.value for x in incoming[i:i+256]] != c.data_values:
                raise GateError("write_data_mapping")
            control = [e.value for e in incoming[i-6:i]]
            if control[4:] != [coord[0]*2+coord[1], coord[2]]:
                raise GateError("control_coordinate")
            next_clock = commands[command_index+1].clock if command_index+1 < len(commands) else 2**63
            replies = [e for e in rows if e.cpu == "sub" and e.kind == "OUT"
                       and e.port == "00FD" and c.end_clock < e.clock < next_clock]
            main_replies = [e for e in rows if e.cpu == "main" and e.kind == "IN"
                            and e.port == "00FC" and c.end_clock < e.clock < next_clock]
            # 1.35節: 応答はレコード1つにつき1バイト（制御12なら2バイト）。件数は1以上で、
            # sub の各応答を main が後で1回ずつ受け取ること（値一致）を検査する。
            if (not replies or len(replies) != len(main_replies)
                    or any(r.value != m.value or r.clock >= m.clock for r, m in zip(replies, main_replies))):
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
                           "response_count": len(replies),
                           "control_receive_clocks": [e.clock for e in incoming[i-6:i]],
                           "data_receive_clocks": [e.clock for e in incoming[i:i+256]]})
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


def unread_summary(rows: list[io.Ev], linked: dict[int, int],
                   unread: list[tuple[int, io.Ev]], writes: list[dict]) -> list[dict]:
    sends = [e for e in rows if e.cpu == "main" and e.kind == "OUT" and e.port == "00FD"]
    controls = {clock for write in writes for clock in write["control_receive_clocks"]}
    data = {clock for write in writes for clock in write["data_receive_clocks"]}
    read_positions = [i for i, send in enumerate(sends, 1) if send.clock in linked]

    def neighbor(position: int | None) -> dict | None:
        if position is None:
            return None
        send = sends[position - 1]
        receive_clock = linked[send.clock]
        kind = "control" if receive_clock in controls else "data" if receive_clock in data else "other"
        result = {"position": position, "classification": kind}
        if kind == "control":
            result["control_value"] = send.value
        return result

    output = []
    for position, send in unread:
        before = next((p for p in reversed(read_positions) if p < position), None)
        after = next((p for p in read_positions if p > position), None)
        left, right = neighbor(before), neighbor(after)
        classification = ("inside_data" if left and right and
                          left["classification"] == right["classification"] == "data"
                          else "between_control" if left and right and
                          left["classification"] == right["classification"] == "control"
                          else "boundary")
        gap_length = ((after if after is not None else len(sends) + 1) -
                      (before if before is not None else 0) - 1)
        item = {"position": position, "classification": classification,
                "gap_length": gap_length, "previous": left, "next": right}
        if classification == "between_control":
            item["control_value"] = send.value
        output.append(item)
    return output


def unread_judgment(observations: dict[str, dict]) -> str:
    if len(observations) != len(script.ARMS):
        return "inconclusive_unread_send"
    positions = [tuple(x["position"] for x in observations[arm]["unread_send"])
                 for arm in script.ARMS]
    return "unread_send_rule_unique" if len(set(positions)) == 1 else "inconclusive_unread_send"


def analyze(rows: list[io.Ev], arm: str) -> dict:
    runs, received, linked, unread = exchanges(rows)
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
    unread_result = unread_summary(rows, linked, unread, writes)
    safe = {send_clock for send_clock, receive_clock in linked.items()
            if any(receive_clock in write["control_receive_clocks"] for write in writes)}
    for write in writes:
        write.pop("control_receive_clocks")
        write.pop("data_receive_clocks")
    return {"arm": arm, "send_runs": [{k: v for k, v in run.items()
                                      if k != "first_clock" and
                                      (k != "first_control" or run["first_clock"] in safe)}
                                    for run in runs],
            "sub_receive_count": len(received), "unread_send_count": len(unread_result),
            "unread_send": unread_result, "writes": writes, "order": order}


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
