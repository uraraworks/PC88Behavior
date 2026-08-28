#!/usr/bin/env python3
"""m7dh: 実ログのrun切り出し例外を独立境界アンカーへ帰属する。

境界アンカーが使うのはcpu、kind、port、pc、seq、共通clock、割り込み受理
clockだけである。判定対象の0F有無、run長偶奇、末尾pc、FE bit0成否は、
アンカーを作り終えた後の評価にだけ使う。データポート値は参照・出力しない。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_run_boundary as current_send  # noqa: E402
import analyze_sub_proto as sub_proto  # noqa: E402

Ev = m2s.Ev
FE_PCS = {"recv_pre": "3853", "recv_post": "386F"}
EXIT_BITS = {"recv_pre": 1, "recv_post": 0}


def validate(rows: list[Ev], interrupts) -> dict:
    if not rows:
        raise ValueError("解析可能なiologイベントが0件")
    io_clocks = [e.clock for e in rows]
    int_events = [e for cpu in ("main", "sub") for e in interrupts[cpu]]
    int_clocks = [e.clock for e in int_events]
    all_clocks = io_clocks + int_clocks
    if len(all_clocks) != len(set(all_clocks)):
        raise ValueError("iolog/intlog共通clockに重複がある")
    if io_clocks != sorted(io_clocks):
        raise ValueError("iologの共通clockが昇順でない")
    for cpu in ("main", "sub"):
        seqs = [e.seq for e in rows if e.cpu == cpu]
        if seqs != sorted(seqs) or len(seqs) != len(set(seqs)):
            raise ValueError(f"{cpu} iolog seqが単調一意でない")
        ints = interrupts[cpu]
        if [e.clock for e in ints] != sorted(e.clock for e in ints):
            raise ValueError(f"{cpu} intlog clockが昇順でない")
        int_seqs = [e.seq for e in ints]
        if int_seqs != sorted(int_seqs) or len(int_seqs) != len(set(int_seqs)):
            raise ValueError(f"{cpu} intlog seqが単調一意でない")
    canonical = [
        f"I|{e.clock}|{e.seq}|{e.cpu}|{e.kind}|{e.port}|{e.pc}"
        for e in rows
    ] + [
        f"N|{e.clock}|{e.seq}|{e.cpu}|{e.ret_pc}|{e.handler_pc}"
        for e in int_events
    ]
    canonical.sort(key=lambda line: int(line.split("|")[1]))
    digest = hashlib.sha256("\n".join(canonical).encode("ascii")).hexdigest()
    return {
        "iolog_events": len(rows), "intlog_events": len(int_events),
        "clock_unique": True, "seq_monotonic": True,
        "structure_sha256": digest,
    }


def current_fe_spins(rows: list[Ev], pc: str) -> list[list[Ev]]:
    main = [e for e in rows if e.cpu == "main"]
    spins: list[list[Ev]] = []
    i = 0
    while i < len(main):
        e = main[i]
        if e.kind == "IN" and e.port == "00FE" and e.pc == pc:
            j = i + 1
            while (j < len(main) and main[j].kind == "IN"
                   and main[j].port == "00FE" and main[j].pc == pc):
                j += 1
            spins.append(main[i:j])
            i = j
        else:
            i += 1
    return spins


def handshake_landmarks(main: list[Ev]) -> list[int]:
    return [
        i for i, e in enumerate(main)
        if ((e.kind == "OUT" and e.port == "00FD")
            or (e.kind == "IN" and e.port == "00FC"))
    ]


def anchored_fe_spins(rows: list[Ev], role: str) -> list[list[Ev]]:
    """受信データイベントを独立ランドマークに前後の待ちを囲む。"""
    main = [e for e in rows if e.cpu == "main"]
    landmarks = handshake_landmarks(main)
    pc = FE_PCS[role]
    groups: list[list[Ev]] = []
    for pos, idx in enumerate(landmarks):
        event = main[idx]
        if not (event.kind == "IN" and event.port == "00FC"):
            continue
        prev_idx = landmarks[pos - 1] if pos else -1
        next_idx = landmarks[pos + 1] if pos + 1 < len(landmarks) else len(main)
        interval = main[prev_idx + 1:idx] if role == "recv_pre" else main[idx + 1:next_idx]
        group = [
            e for e in interval
            if e.kind == "IN" and e.port == "00FE" and e.pc == pc
        ]
        if group:
            groups.append(group)
    return groups


def bit_exception(group: list[Ev], exit_bit: int) -> bool:
    values = [e.value for e in group if e.value is not None]
    if not values:
        return True
    final_ok = (values[-1] & 1) == exit_bit
    loop_ok = all((value & 1) != exit_bit for value in values[:-1])
    return not (final_ok and loop_ok)


def relation(group: list[Ev], anchors: list[list[Ev]]) -> str:
    clocks = {e.clock for e in group}
    matches = [{e.clock for e in anchor} for anchor in anchors if clocks & {e.clock for e in anchor}]
    if not matches:
        return "unanchored"
    if len(matches) > 1:
        return "false_merge"
    anchor = matches[0]
    if clocks == anchor:
        return "boundary_match"
    if clocks < anchor:
        return "false_split"
    if anchor < clocks:
        return "false_merge"
    return "unanchored"


def has_interrupt_near(group: list[Ev], int_clocks: list[int]) -> bool:
    if not group:
        return False
    lo, hi = group[0].clock, group[-1].clock
    return any(lo < clock < hi for clock in int_clocks)


def classify_group(group: list[Ev], anchors: list[list[Ev]],
                   int_clocks: list[int], main_rows: list[Ev]) -> str:
    if group and main_rows and (group[0].clock == main_rows[0].clock
                                or group[-1].clock == main_rows[-1].clock):
        return "log_endpoint"
    rel = relation(group, anchors)
    if has_interrupt_near(group, int_clocks):
        return "interrupt_boundary"
    return rel


def analyze_fe(rows: list[Ev], interrupts) -> dict:
    int_clocks = [e.clock for e in interrupts["main"]]
    result = {}
    for role in ("recv_pre", "recv_post"):
        pc = FE_PCS[role]
        current = current_fe_spins(rows, pc)
        anchors = anchored_fe_spins(rows, role)
        current_bad = [group for group in current if bit_exception(group, EXIT_BITS[role])]
        anchor_bad = [group for group in anchors if bit_exception(group, EXIT_BITS[role])]
        main_rows = [e for e in rows if e.cpu == "main"]
        categories = Counter(
            classify_group(group, anchors, int_clocks, main_rows) for group in current_bad
        )
        covered = {e.clock for group in anchors for e in group}
        current_clocks = {e.clock for group in current for e in group}
        result[role] = {
            "current_spins": len(current), "current_exceptions": len(current_bad),
            "anchor_spins": len(anchors), "anchor_exceptions": len(anchor_bad),
            "attribution": dict(sorted(categories.items())),
            "anchor_covered_events": len(covered),
            "current_events": len(current_clocks),
            "uncovered_current_events": len(current_clocks - covered),
        }
    return result


def anchor_send_runs(rows: list[Ev]) -> list[list[int]]:
    """mainの選択データイベントを方向だけで束ねた最大SEND区間。"""
    main = [e for e in rows if e.cpu == "main"]
    selected = [
        (i, "SEND" if e.kind == "OUT" else "RECV")
        for i, e in enumerate(main)
        if ((e.kind == "OUT" and e.port == "00FD")
            or (e.kind == "IN" and e.port == "00FC"))
    ]
    runs: list[list[int]] = []
    current: list[int] = []
    for idx, direction in selected:
        if direction == "RECV":
            if current:
                runs.append(current)
                current = []
        else:
            current.append(idx)
    if current:
        runs.append(current)
    return runs


def has_0f(main: list[Ev], all_fd: list[int], idx: int) -> bool:
    flat = all_fd.index(idx)
    start = all_fd[flat - 1] + 1 if flat else 0
    return any(e.kind == "OUT" and e.port == "00FF" and e.value == 0x0F
               for e in main[start:idx])


def send_outcomes(runs: list[list[int]], main: list[Ev]) -> tuple[dict, list[tuple[list[int], int]], list[list[int]]]:
    all_fd = [idx for run in runs for idx in run]
    first_yes = first_total = cont_no = cont_total = 0
    ff_bad: list[tuple[list[int], int]] = []
    parity_bad: list[list[int]] = []
    for run in runs:
        for pos, idx in enumerate(run):
            present = has_0f(main, all_fd, idx)
            if pos == 0:
                first_total += 1
                first_yes += int(present)
                if not present:
                    ff_bad.append((run, idx))
            else:
                cont_total += 1
                cont_no += int(not present)
                if present:
                    ff_bad.append((run, idx))
        if len(run) >= 2:
            expected = "3811" if len(run) % 2 == 0 else "37F4"
            if main[run[-1]].pc != expected:
                parity_bad.append(run)
    return ({
        "runs": len(runs), "first_0f_yes": first_yes, "first_total": first_total,
        "continuation_0f_no": cont_no, "continuation_total": cont_total,
        "ff_exceptions": len(ff_bad), "parity_exceptions": len(parity_bad),
    }, ff_bad, parity_bad)


def run_relation(run: list[int], anchors: list[list[int]], main: list[Ev]) -> str:
    clocks = {main[idx].clock for idx in run}
    anchor_clocks = [{main[idx].clock for idx in anchor} for anchor in anchors]
    matches = [anchor for anchor in anchor_clocks if clocks & anchor]
    if not matches:
        return "unanchored"
    if len(matches) > 1:
        return "false_merge"
    anchor = matches[0]
    if clocks == anchor:
        return "boundary_match"
    if clocks < anchor:
        return "false_split"
    if anchor < clocks:
        return "false_merge"
    return "unanchored"


def classify_send(run: list[int], event_idx: int | None, anchors: list[list[int]],
                  main: list[Ev], int_clocks: list[int], all_fd: list[int]) -> str:
    if not run:
        return "unanchored"
    if run[0] == 0 or run[-1] == len(main) - 1:
        return "log_endpoint"
    rel = run_relation(run, anchors, main)
    if event_idx is None:
        lo, hi = main[run[0]].clock, main[run[-1]].clock
    else:
        flat = all_fd.index(event_idx)
        lo = main[all_fd[flat - 1]].clock if flat else main[event_idx].clock
        hi = main[event_idx].clock
    if any(lo < clock < hi for clock in int_clocks):
        return "interrupt_boundary"
    return rel


def analyze_send(rows: list[Ev], interrupts) -> dict:
    current, main = current_send.main_send_runs(rows)
    anchors = anchor_send_runs(rows)
    current_metrics, ff_bad, parity_bad = send_outcomes(current, main)
    anchor_metrics, _anchor_ff_bad, _anchor_parity_bad = send_outcomes(anchors, main)
    all_fd = [idx for run in current for idx in run]
    int_clocks = [e.clock for e in interrupts["main"]]
    ff_categories = Counter(
        classify_send(run, idx, anchors, main, int_clocks, all_fd)
        for run, idx in ff_bad
    )
    parity_categories = Counter(
        classify_send(run, None, anchors, main, int_clocks, all_fd)
        for run in parity_bad
    )
    current_events = {main[idx].clock for run in current for idx in run}
    anchor_events = {main[idx].clock for run in anchors for idx in run}
    return {
        "current": current_metrics, "anchor": anchor_metrics,
        "ff_attribution": dict(sorted(ff_categories.items())),
        "parity_attribution": dict(sorted(parity_categories.items())),
        "current_events": len(current_events), "anchor_events": len(anchor_events),
        "uncovered_current_events": len(current_events - anchor_events),
    }


def analyze(iolog: Path, intlog: Path, label: str) -> dict:
    rows, _ = m2s.parse_iolog(iolog)
    interrupts = sub_proto.parse_intlog(intlog)
    return {
        "label": label, "validation": validate(rows, interrupts),
        "fe": analyze_fe(rows, interrupts), "send": analyze_send(rows, interrupts),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--intlog", required=True, type=Path)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    result = analyze(args.iolog, args.intlog, args.label)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(
        f"{args.label}: FE例外 pre={result['fe']['recv_pre']['current_exceptions']} "
        f"post={result['fe']['recv_post']['current_exceptions']} / "
        f"SEND例外 0F={result['send']['current']['ff_exceptions']} "
        f"parity={result['send']['current']['parity_exceptions']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
