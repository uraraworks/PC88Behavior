#!/usr/bin/env python3
"""K00 完了結線後の再アーム数と非データ列の差位置を安全に検査する。

データ経路の値は保持しても表示しない。標準出力には件数、位置、ポート、
PC、および差異の分類だけを出す。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_main_to_sub import Ev, parse_iolog  # noqa: E402


def rearm_counts(rows: list[Ev]) -> tuple[int, int, int, int]:
    sub = [e for e in rows if e.cpu == "sub"]
    total = corresponding = blank = unresolved = 0
    for i, event in enumerate(sub):
        if not (event.kind == "OUT" and event.port == "00FF" and event.value == 0x0B):
            continue
        total += 1
        for following in sub[i + 1:]:
            if following.kind == "IN" and following.port == "00FC":
                corresponding += 1
                break
            if following.kind == "OUT" and following.port in {"00FB", "00FD"}:
                blank += 1
                break
            if (following.kind == "OUT" and following.port == "00FF"
                    and following.value == 0x0B):
                unresolved += 1
                break
        else:
            unresolved += 1
    return total, corresponding, blank, unresolved


def nondata_main(rows: list[Ev]) -> list[Ev]:
    return [
        e for e in rows
        if e.cpu == "main" and e.kind == "IN" and e.port not in {"00FC", "00FD"}
    ]


def first_difference(left: list[Ev], right: list[Ev]) -> tuple[int | None, str, Ev | None, Ev | None]:
    for index, (a, b) in enumerate(zip(left, right), 1):
        if (a.port, a.pc, a.value) != (b.port, b.pc, b.value):
            kind = "座標差" if (a.port, a.pc) != (b.port, b.pc) else "値差"
            return index, kind, a, b
    if len(left) != len(right):
        index = min(len(left), len(right)) + 1
        a = left[index - 1] if index <= len(left) else None
        b = right[index - 1] if index <= len(right) else None
        return index, "長さ差", a, b
    return None, "差なし", None, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official", required=True, type=Path)
    parser.add_argument("--mixed", required=True, type=Path)
    parser.add_argument("--expected-corresponding", required=True, type=int)
    parser.add_argument("--min-nondata-difference", required=True, type=int)
    args = parser.parse_args()

    official, _ = parse_iolog(args.official)
    mixed, _ = parse_iolog(args.mixed)
    total, corresponding, blank, unresolved = rearm_counts(mixed)
    position, difference_kind, left, right = first_difference(
        nondata_main(official), nondata_main(mixed)
    )

    print(f"再アーム: 総数={total} 対応あり={corresponding} 空振り={blank} 未解決={unresolved}")
    if position is None:
        print("最初の非データ差: なし")
    else:
        print(f"最初の非データ差: {position}件目（{difference_kind}）")
        sites = []
        for label, event in (("公式", left), ("混成", right)):
            if event is not None:
                sites.append(f"{label}:port=${event.port[-2:]} pc={event.pc}")
        if sites:
            print("差位置: " + " / ".join(sites))

    failures = []
    if total != args.expected_corresponding or corresponding != args.expected_corresponding:
        failures.append("必要な再アーム件数が期待値と不一致")
    if blank != 0:
        failures.append("空振り再アームを検出")
    if unresolved != 0:
        failures.append("対応を確定できない再アームを検出")
    if position is None or position < args.min_nondata_difference:
        failures.append("非データ差位置が下限未満または差なし")
    if failures:
        for failure in failures:
            print("NG: " + failure)
        return 1
    print("OK: K00 完了結線の測定条件を満たす")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
