#!/usr/bin/env python3
"""第2チャンネルをバルク前・中・後へ分解する（m7cy第1段）。

値列は読み取り時の書式確認以外には使わず、出力しない。バルク区間は事前登録どおり、
最初から最後の ``sub OUT $FC`` と同じ共通クロック範囲（両端を含む）とする。
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402


@dataclass(frozen=True)
class Summary:
    counts: dict[str, dict[str, int]]
    paired_fc: int
    unpaired_fc_slots: tuple[int, ...]
    extra_fd_ordinals: tuple[int, ...]
    extra_fd_slots: tuple[int, ...]
    boundary_followed_by_fd: bool


def analyze(path: Path) -> Summary:
    try:
        events = cmp_io.parse_iolog(str(path), "sub")
    except (cmp_io.FormatError, OSError) as exc:
        raise ValueError(str(exc)) from exc
    channel = [e for e in events if e.kind == "OUT" and e.port in ("00FC", "00FD")]
    if not channel:
        raise ValueError("sub OUT $FC/$FD が0件")
    if any(e.clock is None for e in channel):
        raise ValueError("共通クロックが無いイベントを含む")
    clocks = [int(e.clock) for e in channel]
    if clocks != sorted(clocks):
        raise ValueError("共通クロックが時系列順でない")
    fc = [e for e in channel if e.port == "00FC"]
    if not fc:
        raise ValueError("バルク境界となる sub OUT $FC が0件")
    start, end = int(fc[0].clock), int(fc[-1].clock)
    if start > end:
        raise ValueError("バルク境界が逆転している")

    def zone(clock: int) -> str:
        if clock < start:
            return "前"
        if clock > end:
            return "後"
        return "中"

    counts = {port: {z: 0 for z in ("前", "中", "後")} for port in ("00FC", "00FD")}
    during = []
    for event in channel:
        z = zone(int(event.clock))
        counts[event.port][z] += 1
        if z == "中":
            during.append(event)

    used_fd: set[int] = set()
    paired_fc = 0
    unpaired_fc_slots: list[int] = []
    fc_seen = 0
    for pos, event in enumerate(during):
        if event.port != "00FC":
            continue
        fc_seen += 1
        if pos + 1 < len(during) and during[pos + 1].port == "00FD":
            paired_fc += 1
            used_fd.add(pos + 1)
        else:
            unpaired_fc_slots.append(fc_seen)

    extra_fd_ordinals: list[int] = []
    extra_fd_slots: list[int] = []
    fd_seen = 0
    fc_seen = 0
    for pos, event in enumerate(during):
        if event.port == "00FC":
            fc_seen += 1
        else:
            fd_seen += 1
            if pos not in used_fd:
                extra_fd_ordinals.append(fd_seen)
                extra_fd_slots.append(fc_seen)

    last_fc_pos = max(i for i, event in enumerate(channel) if event.port == "00FC")
    boundary_followed_by_fd = (
        last_fc_pos + 1 < len(channel) and channel[last_fc_pos + 1].port == "00FD"
    )
    return Summary(counts, paired_fc, tuple(unpaired_fc_slots),
                   tuple(extra_fd_ordinals), tuple(extra_fd_slots),
                   boundary_followed_by_fd)


def interval_hist(values: tuple[int, ...]) -> str:
    if len(values) < 2:
        return "なし"
    hist = Counter(b - a for a, b in zip(values, values[1:]))
    return ", ".join(f"{gap}:{count}" for gap, count in sorted(hist.items()))


def compact_positions(values: tuple[int, ...]) -> str:
    if not values:
        return "なし"
    if len(values) == 1:
        return str(values[0])
    gaps = {b - a for a, b in zip(values, values[1:])}
    if len(gaps) == 1:
        gap = next(iter(gaps))
        return f"{values[0]}..{values[-1]}（間隔{gap}、{len(values)}件）"
    if len(values) <= 24:
        return ",".join(str(v) for v in values)
    return (f"先頭12件={','.join(map(str, values[:12]))}; "
            f"末尾12件={','.join(map(str, values[-12:]))}; 全{len(values)}件")


def report(label: str, result: Summary) -> None:
    print(f"[{label}]")
    for port in ("00FC", "00FD"):
        c = result.counts[port]
        print(f"sub OUT ${port[-2:]}: バルク前={c['前']} 中={c['中']} 後={c['後']} 合計={sum(c.values())}")
    print(f"バルク中の隣接FC→FD対: {result.paired_fc}")
    print(f"最終FC直後の次チャンネルイベントがFD: {'はい' if result.boundary_followed_by_fd else 'いいえ'}")
    print(f"直後FDを欠くFC位置（FC内1-based）: {compact_positions(result.unpaired_fc_slots)}")
    print(f"余分FD位置（FD内1-based）: {compact_positions(result.extra_fd_ordinals)}")
    print(f"余分FD挿入slot（直前FC件数、0-based）: {compact_positions(result.extra_fd_slots)}")
    print(f"余分FD間隔度数（FD内ordinal差:件数）: {interval_hist(result.extra_fd_ordinals)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("logs", nargs="+", type=Path)
    ap.add_argument("--label", action="append", default=[])
    args = ap.parse_args()
    if args.label and len(args.label) != len(args.logs):
        print("エラー: --label はログ数と同数にする", file=sys.stderr)
        return 2
    labels = args.label or [p.stem for p in args.logs]
    try:
        for label, path in zip(labels, args.logs):
            report(label, analyze(path))
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
