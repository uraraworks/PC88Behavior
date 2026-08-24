#!/usr/bin/env python3
"""A:/B: 操作で main が sub へ送る要求runを全位置比較する（m7cj）。

入力はリポジトリ外の生 iolog を想定する。比較対象は main ``OUT $FD``
（sub ``IN $FC`` に対応する要求バイト）だけであり、sub応答、FDCデータ部、
画面本文は読まず、出力もしない。run境界は既存の
``analyze_run_boundary.main_send_runs`` を再利用する。

終了コードは、完全一致=0、値または構造の差あり=1、解析不能=2。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_run_boundary as arb  # noqa: E402


# 1.11節旧固定部のうち、今回の比較対象であるbyte2/7は照合時に可変とする。
FIXED8 = (0x02, 0x01, None, None, None, 0x06, 0x12, None)


def request_runs(path: Path, after_frame: int) -> list[list[int]]:
    rows, _masked = m2s.parse_iolog(path)
    rows = [e for e in rows if e.frame >= after_frame]
    indices, main_rows = arb.main_send_runs(rows)
    runs: list[list[int]] = []
    for run in indices:
        values = [main_rows[i].value for i in run]
        if any(v is None for v in values):
            raise ValueError("main要求に伏せ字(--)が含まれる")
        runs.append([int(v) for v in values])
    return runs


def is_fixed8(run: list[int]) -> bool:
    return len(run) == 8 and all(
        expected is None or run[pos] == expected
        for pos, expected in enumerate(FIXED8)
    )


def fixed8_sequences(runs: list[list[int]]) -> list[tuple[str, list[int]]]:
    """単独8件と、実測FILESで分節された隣接6+2件の双方を拾う。"""
    found: list[tuple[str, list[int]]] = []
    for i, run in enumerate(runs):
        if is_fixed8(run):
            found.append((f"run[{i}]", run))
        if i + 1 < len(runs) and len(run) + len(runs[i + 1]) == 8:
            joined = run + runs[i + 1]
            if is_fixed8(joined):
                found.append((f"run[{i}]+run[{i + 1}]", joined))
    return found


def compare(a: list[list[int]], b: list[list[int]]) -> tuple[list[str], bool]:
    lines = [f"run数: A={len(a)} B={len(b)}"]
    structural = False
    if len(a) != len(b):
        structural = True
        lines.append("構造差: run数が異なる")

    lines.append("全要求run（main OUT $FD、16進）:")
    for ri, (ra, rb) in enumerate(zip(a, b)):
        sa = " ".join(f"{v:02X}" for v in ra)
        sb = " ".join(f"{v:02X}" for v in rb)
        lines.append(f"  run[{ri}] len={len(ra)}/{len(rb)} A=[{sa}] B=[{sb}]")

    diffs: list[tuple[int, int, int, int]] = []
    length_diffs: list[tuple[int, int, int]] = []
    for ri, (ra, rb) in enumerate(zip(a, b)):
        if len(ra) != len(rb):
            structural = True
            length_diffs.append((ri, len(ra), len(rb)))
        for pos, (va, vb) in enumerate(zip(ra, rb)):
            if va != vb:
                diffs.append((ri, pos, va, vb))

    lines.append(f"run長差: {len(length_diffs)}件")
    for ri, la, lb in length_diffs:
        lines.append(f"  run[{ri}]: A={la} B={lb}")
    lines.append(f"同一run・同一位置の値差: {len(diffs)}件")
    for ri, pos, va, vb in diffs:
        lines.append(f"  run[{ri}] byte[{pos}]: A={va:02X} B={vb:02X}")

    fixed_a = fixed8_sequences(a)
    fixed_b = fixed8_sequences(b)
    lines.append(f"固定8バイト形: A={len(fixed_a)}件 B={len(fixed_b)}件")
    for ordinal, ((ia, ra), (ib, rb)) in enumerate(zip(fixed_a, fixed_b)):
        changed = [pos for pos in range(8) if ra[pos] != rb[pos]]
        lines.append(
            f"  fixed8[{ordinal}] A={ia}/B={ib}: "
            + ("差なし" if not changed else "差位置=" + ",".join(map(str, changed)))
        )
    if len(fixed_a) != len(fixed_b):
        structural = True
        lines.append("構造差: 固定8バイト形の件数が異なる")
    return lines, structural or bool(diffs)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--drive-a", required=True, type=Path)
    ap.add_argument("--drive-b", required=True, type=Path)
    ap.add_argument("--after-frame", type=int, default=700)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    try:
        a = request_runs(args.drive_a, args.after_frame)
        b = request_runs(args.drive_b, args.after_frame)
        lines, different = compare(a, b)
    except (OSError, ValueError) as ex:
        print(f"解析不能: {ex}", file=sys.stderr)
        return 2
    text = "# A:/B: main→sub要求run全位置比較\n\n" + "\n".join(lines) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 1 if different else 0


if __name__ == "__main__":
    raise SystemExit(main())
