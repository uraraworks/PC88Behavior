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
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402
import compare_l3_entry_fdc as entry_fdc  # noqa: E402


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


class AnalysisError(Exception):
    """値を診断へ漏らさずに解析不能を通知する。"""


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


def command_kinds(path: Path) -> tuple[list[str], list[int]]:
    """既存器材を再利用し、公開FDC種別名と発行clockだけを返す。

    `compare_l3_entry_fdc.command_names()` が使う生のコマンド語・パラメータ・
    結果・データは種別境界の判定中だけに留め、この関数の戻り値にも診断にも
    含めない。未知コマンド等の例外文には生値が入り得るため、外側へは固定文の
    `AnalysisError` だけを返す。
    """
    try:
        names, commands, _rows = entry_fdc.command_names(path)
    except (OSError, ValueError, entry_fdc.awp.SafeError):
        raise AnalysisError("公開FDCコマンド種別列を抽出できない") from None
    return names, [command.clock for command in commands]


def names_sha256(names: list[str]) -> str:
    """既存 `ladder_dirfiles.py` と同じ正規JSON表現で種別列を要約する。"""
    data = json.dumps(names, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":")).encode("ascii")
    return hashlib.sha256(data).hexdigest()


def analyze(io_path: Path, int_path: Path) -> dict:
    io = read_io(io_path)
    intr, dropped = read_intr(int_path)
    fdc_names, fdc_clocks = command_kinds(io_path)
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
    interrupts_by_fdc_command_index: Counter[int] = Counter()
    interrupts_by_fb_run_index: Counter[int] = Counter()
    interrupt_position_in_run: Counter[int] = Counter()
    interrupts_without_fb_run_position = 0

    for event in intr:
        # コマンド段 j は、公開FDCコマンド j の発行時点以上、次のコマンドの
        # 発行時点未満とする。最初の発行より前は段 -1、列末尾は測定終了まで。
        command_index = bisect.bisect_right(fdc_clocks, event.clock) - 1
        interrupts_by_fdc_command_index[command_index] += 1

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
            interrupts_by_fb_run_index[ri] += 1
            interrupt_position_in_run[pos] += 1
            loc = "末尾" if pos == len(run) - 1 else "途中"
            fb_position[f"{prev.kind} run {loc}"] += 1
            if len(run) >= LONG_RUN_MIN:
                long_run_interrupts += 1
                long_run_by_direction[prev.kind] += 1
        else:
            # run内位置を持たない受理も除外せず、別の整数として残す。
            interrupts_without_fb_run_position += 1

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
    run_length_histogram = Counter(len(run) for run in runs)
    fb_runs_with_interrupt = sum(
        1 for run_index in range(len(runs))
        if interrupts_by_fb_run_index[run_index]
    )
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
        "fdc_command_kinds": fdc_names,
        "fdc_command_count": len(fdc_names),
        "fdc_command_kinds_sha256": names_sha256(fdc_names),
        # 大量出力を避けるため非0の段だけを出す。キー名の `_nonzero` は、
        # 省略した全段（段 -1 と全コマンド段のうち未掲載）が0件であることを示す。
        "interrupts_by_fdc_command_index_nonzero":
            dict(sorted(interrupts_by_fdc_command_index.items())),
        "fb_run_count": len(runs),
        "fb_run_length_histogram": dict(sorted(run_length_histogram.items())),
        # 非0のrunだけを出し、省略されたrun番号は全て0件と明示する。
        "interrupts_by_fb_run_index_nonzero":
            dict(sorted(interrupts_by_fb_run_index.items())),
        "fb_runs_with_interrupt": fb_runs_with_interrupt,
        "fb_runs_without_interrupt": len(runs) - fb_runs_with_interrupt,
        # 非0の相対位置だけを出し、省略された位置は全て0件と明示する。
        "interrupt_position_in_run_histogram_nonzero":
            dict(sorted(interrupt_position_in_run.items())),
        "interrupts_without_fb_run_position":
            interrupts_without_fb_run_position,
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
    try:
        result = analyze(args.iolog, args.intlog)
    except AnalysisError as ex:
        print(f"解析不能: {ex}", file=sys.stderr)
        return 2
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
