#!/usr/bin/env python3
"""公式subの割り込み受理を、I/Oの値を使わず外形だけで解析する。

共通clockでmain/sub I/Oとsub割り込みをマージし、直前・直後、$FBの
同方向run内の位置、SENSE INTERRUPT STATUS候補、frame分布を数える。
データポートの値は読み出し結果にも診断にも一切出力しない。

SENSE候補は公開μPD765仕様の外形（$FB OUT 1件→IN 1〜2件）だけによる。
値が伏せられているため、コマンド種別そのものを確定するものではない。
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402


IO_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(IN|OUT)\s+"
    r"([0-9A-Fa-f]{4})\s+(?:[0-9A-Fa-f]{2}|--)\s+([0-9A-Fa-f]{4})\s*$"
)
INT_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+\d+\s+\d+\s+"
    r"[0-9A-Fa-f]{4}\s+[0-9A-Fa-f]{4}\s*$"
)
DROP_RE = re.compile(r"取りこぼし:\s*(\d+)件")
LONG_RUN_MIN = 16


@dataclass(frozen=True)
class Io:
    seq: int
    clock: int
    frame: int
    cpu: str
    kind: str
    port: str
    pc: str


@dataclass(frozen=True)
class Intr:
    seq: int
    clock: int
    frame: int


def read_io(path: Path) -> list[Io]:
    out: list[Io] = []
    with cmp_io._open_iolog(str(path)) as f:
        for line in f:
            m = IO_RE.match(line)
            if not m:
                continue
            seq, clock, frame, cpu, kind, port, pc = m.groups()
            out.append(Io(int(seq), int(clock), int(frame), cpu, kind,
                          port.upper(), pc.upper()))
    return out


def read_intr(path: Path) -> tuple[list[Intr], int]:
    out: list[Intr] = []
    dropped = 0
    with cmp_io._open_iolog(str(path)) as f:
        for line in f:
            dm = DROP_RE.search(line)
            if dm:
                dropped = int(dm.group(1))
            m = INT_RE.match(line)
            if m and m.group(4) == "sub":
                out.append(Intr(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return out, dropped


def intervals(frames: list[int]) -> list[list[int]]:
    if not frames:
        return []
    result: list[list[int]] = []
    start = prev = frames[0]
    for frame in frames[1:]:
        if frame != prev + 1:
            result.append([start, prev])
            start = frame
        prev = frame
    result.append([start, prev])
    return result


def fb_runs(sub: list[Io]) -> tuple[list[list[Io]], dict[int, tuple[int, int]]]:
    """$FBだけを抜き、方向が変わるまでをrunとする。clock→(run,位置)。"""
    runs: list[list[Io]] = []
    for event in sub:
        if event.port != "00FB":
            continue
        if not runs or runs[-1][0].kind != event.kind:
            runs.append([])
        runs[-1].append(event)
    where: dict[int, tuple[int, int]] = {}
    for ri, run in enumerate(runs):
        for pos, event in enumerate(run):
            where[event.clock] = (ri, pos)
    return runs, where


def key(event: Io) -> str:
    return f"{event.cpu} {event.kind} ${event.port[-2:]}"


def analyze(io_path: Path, int_path: Path) -> dict:
    io = read_io(io_path)
    intr, dropped = read_intr(int_path)
    merged = sorted(io, key=lambda e: e.clock)
    clocks = [e.clock for e in merged]
    sub = sorted((e for e in io if e.cpu == "sub"), key=lambda e: e.clock)
    runs, where = fb_runs(sub)
    sub_fb = [e for e in sub if e.port == "00FB"]
    sub_fb_clocks = [e.clock for e in sub_fb]

    before: Counter[str] = Counter()
    after: Counter[str] = Counter()
    fb_position: Counter[str] = Counter()
    long_run_interrupts = 0
    long_run_by_direction: Counter[str] = Counter()
    sense_candidates = 0
    missing_before = missing_after = 0

    for event in intr:
        idx = bisect.bisect_left(clocks, event.clock)
        if idx == 0:
            missing_before += 1
            prev = None
        else:
            prev = merged[idx - 1]
            before[key(prev)] += 1
        if idx == len(merged):
            missing_after += 1
        else:
            after[key(merged[idx])] += 1

        if prev is not None and prev.clock in where:
            ri, pos = where[prev.clock]
            run = runs[ri]
            loc = "末尾" if pos == len(run) - 1 else "途中"
            fb_position[f"{prev.kind} run {loc}"] += 1
            if len(run) >= LONG_RUN_MIN:
                long_run_interrupts += 1
                long_run_by_direction[prev.kind] += 1

        # 受理後、最初の$FBから見てOUT 1件→IN 1〜2件ならSENSE候補。
        # 受理直前のOUTと方向が同じでも、受理点を局所境界として数える。
        # 値なしで言える上限であり、コマンド確定ではない。
        next_fb = bisect.bisect_left(sub_fb_clocks, event.clock)
        if next_fb < len(sub_fb):
            j = next_fb
            out_count = 0
            while j < len(sub_fb) and sub_fb[j].kind == "OUT":
                out_count += 1
                j += 1
            in_count = 0
            while j < len(sub_fb) and sub_fb[j].kind == "IN":
                in_count += 1
                j += 1
            if out_count == 1 and in_count in (1, 2):
                sense_candidates += 1

    frame_counts = Counter(e.frame for e in intr)
    active_frames = sorted(frame_counts)
    return {
        "interrupts": len(intr),
        "dropped": dropped,
        "missing_before": missing_before,
        "missing_after": missing_after,
        "before": dict(sorted(before.items())),
        "after": dict(sorted(after.items())),
        "fb_run_position": dict(sorted(fb_position.items())),
        "sense_candidates_after": sense_candidates,
        "long_fb_run_min": LONG_RUN_MIN,
        "interrupts_after_long_fb_run_event": long_run_interrupts,
        "interrupts_after_long_fb_run_event_by_direction":
            dict(sorted(long_run_by_direction.items())),
        "active_frame_count": len(active_frames),
        "frame_intervals": intervals(active_frames),
        "frame_min": active_frames[0] if active_frames else None,
        "frame_max": active_frames[-1] if active_frames else None,
        "max_interrupts_per_frame": max(frame_counts.values(), default=0),
        "mean_interrupts_per_active_frame": (
            round(len(intr) / len(active_frames), 6) if active_frames else 0
        ),
        "frame_counts": [[f, frame_counts[f]] for f in active_frames],
    }


def check_shape(result: dict, expect_none: bool) -> list[str]:
    errors: list[str] = []
    if result["dropped"]:
        errors.append("割り込みログに取りこぼしがある")
    if expect_none:
        if result["interrupts"] != 0:
            errors.append("割り込み0件を期待したが受理点がある")
        return errors
    if result["interrupts"] == 0:
        errors.append("受理点が0件で外形を判定できない")
        return errors
    if result["missing_before"] or result["missing_after"]:
        errors.append("直前または直後のI/Oを持たない受理点がある")
    main_before = sum(n for k, n in result["before"].items()
                      if k.startswith("main "))
    if main_before:
        errors.append("直前1件がmain側の受理点がある")
    expected_after = result["after"].get("sub IN $FA", 0)
    if expected_after != result["interrupts"]:
        errors.append("直後1件がsub IN $FAでない受理点がある")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--intlog", required=True, type=Path)
    ap.add_argument("--label", default="log")
    ap.add_argument("--check", action="store_true",
                    help="観測外形（直前main=0、直後sub IN $FA=全件）を検査")
    ap.add_argument("--expect-no-interrupt", action="store_true")
    args = ap.parse_args()
    result = analyze(args.iolog, args.intlog)
    print(json.dumps({"label": args.label, **result}, ensure_ascii=False,
                     sort_keys=True, indent=2))
    if not args.check:
        return 0
    errors = check_shape(result, args.expect_no_interrupt)
    for error in errors:
        print(f"NG: {error}", file=sys.stderr)
    if not errors:
        print("OK: 割り込み受理の外形が期待どおり", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
