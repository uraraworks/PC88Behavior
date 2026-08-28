#!/usr/bin/env python3
"""m7da第1段を伏せ字済み2走から値なしで再集計する。"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_second_channel_structure as second  # noqa: E402
import cmp_io  # noqa: E402


class Stage1Error(Exception):
    pass


def histogram(events, kind: str, port: str) -> tuple[tuple[str, int], ...]:
    counts = Counter(e.pc for e in events if e.kind == kind and e.port == port)
    return tuple(sorted(counts.items(), key=lambda x: (-x[1], x[0])))


def analyze(path: Path) -> dict:
    try:
        main = cmp_io.parse_iolog(str(path), "main")
        sub = cmp_io.parse_iolog(str(path), "sub")
        channels = second.analyze(path)
    except (OSError, cmp_io.FormatError, ValueError) as exc:
        raise Stage1Error(str(exc)) from exc

    main_fd = [e for e in main if e.kind == "IN" and e.port == "00FD"]
    sub_fc = [e for e in sub if e.kind == "OUT" and e.port == "00FC"]
    if not main_fd or not sub_fc:
        raise Stage1Error("5635件バルクが0件または欠落")
    if len(main_fd) != 5635 or len(sub_fc) != 5635:
        raise Stage1Error(f"バルク件数が5635でない: main={len(main_fd)} sub={len(sub_fc)}")
    main_hist = histogram(main_fd, "IN", "00FD")
    sub_hist = histogram(sub_fc, "OUT", "00FC")
    if sorted(n for _, n in main_hist) != [3, 5632]:
        raise Stage1Error(f"main PC別内訳が5632+3でない: 群数={len(main_hist)}")
    if sorted(n for _, n in sub_hist) != [3, 5632]:
        raise Stage1Error(f"sub PC別内訳が5632+3でない: 群数={len(sub_hist)}")

    c = channels.counts
    if c["00FC"] != {"前": 0, "中": 5635, "後": 0}:
        raise Stage1Error(f"FCの区間件数が期待外: {c['00FC']}")
    if channels.paired_fc != 5634 or not channels.boundary_followed_by_fd:
        raise Stage1Error(
            f"隣接対が期待外: 区間内={channels.paired_fc} 最終境界={channels.boundary_followed_by_fd}"
        )

    target = [
        e for e in main + sub
        if e.port in ("00FB", "00FC", "00FD")
    ]
    if any(e.value != "--" for e in target):
        raise Stage1Error("対象ログのデータポートに伏せ字でない値がある")

    channel_sequence = tuple(
        (e.port, e.pc) for e in sub
        if e.kind == "OUT" and e.port in ("00FC", "00FD")
    )
    return {
        "main_hist": main_hist,
        "sub_hist": sub_hist,
        "channels": channels,
        "channel_sequence": channel_sequence,
    }


def fmt_hist(hist: tuple[tuple[str, int], ...]) -> str:
    return ", ".join(f"pc={pc}:{count}件" for pc, count in hist)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("logs", nargs=2, type=Path)
    args = ap.parse_args()
    try:
        results = [analyze(path) for path in args.logs]
    except Stage1Error as exc:
        print(f"NG: {exc}", file=sys.stderr)
        return 1

    for index, (path, result) in enumerate(zip(args.logs, results), 1):
        channels = result["channels"]
        print(f"[run{index}] {path.name}")
        print(f"main IN $FD PC別内訳: {fmt_hist(result['main_hist'])}")
        print(f"sub OUT $FC PC別内訳: {fmt_hist(result['sub_hist'])}")
        for port in ("00FC", "00FD"):
            c = channels.counts[port]
            print(f"sub OUT ${port[-2:]}: 前={c['前']} 中={c['中']} 後={c['後']} 合計={sum(c.values())}")
        print(
            f"隣接FC→FD対: バルク区間内={channels.paired_fc} "
            f"最終境界をまたぐ対={1 if channels.boundary_followed_by_fd else 0}"
        )

    same_hist = all(
        results[0][key] == results[1][key] for key in ("main_hist", "sub_hist")
    )
    same_summary = results[0]["channels"] == results[1]["channels"]
    same_sequence = results[0]["channel_sequence"] == results[1]["channel_sequence"]
    print(f"2走PC別内訳一致: {'はい' if same_hist else 'いいえ'}")
    print(f"2走区間・隣接構造一致: {'はい' if same_summary else 'いいえ'}")
    print(f"2走チャンネル(port,pc)全列一致: {'はい' if same_sequence else 'いいえ'}")
    print("値依存の全位置座標対応: 判定不能（保存ログのデータポート値は伏せ字）")
    if not (same_hist and same_summary and same_sequence):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
