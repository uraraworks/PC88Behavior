#!/usr/bin/env python3
"""PC88Behavior: 受信runのフィールドが「連続READ移行」を判断しているかを、
値を一切出さずに測る比較器（m7hl事前登録）。

`docs/notes/m7hl-recv-run-count-field-preregistration.md` の「新設する
測定器」節が定める設計をそのまま実装する。既存モジュールを import して
使い、二重実装はしない:

- `analyze_main_to_sub.parse_iolog`
- `analyze_record_boundaries.sub_fc_indices` / `window_a_runs`
- `analyze_write_path.parse_commands`
- `compare_l3_entry_fdc.command_names`

**設計の中心は「値を1つも出さないこと」である。** 標準出力・標準エラーへ
出してよいのは、run通し番号・run長・位置番号p・`eq`の真偽・`cmp`の符号
（-1/0/+1）・件数・rc・真偽値のみ。バイト値そのもの・差の絶対値・
シリンダ値・PCN値・画面本文・実ファイル名は出さない。値を保持する変数は
比較関数の内部にとどめ、print/format/logging/例外メッセージ/トレース
バックへ到達させない（比較関数内で例外を握って真偽へ落とす）。

サブコマンド:
    stage1  --iolog PATH
        段階1（対応づけの成否判定）を出す。
    stage2  --iolog PATH
        段階1を内部でやり直し、中止規則に該当しなければ段階2（群R・群Sの
        比較、C1/C2/C3判定）を出す。中止規則に該当すれば verdict=N を出す。

再実行方法:
    python3 tools/compare_recv_run_fields.py stage1 --iolog measurements/x.iolog.txt.gz
    python3 tools/compare_recv_run_fields.py stage2 --iolog measurements/x.iolog.txt.gz
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_record_boundaries as arb  # noqa: E402
import analyze_write_path as awp  # noqa: E402
import compare_l3_entry_fdc as cef  # noqa: E402


class SafeError(Exception):
    """値を漏らさず失敗を伝えるための例外。メッセージに値を含めない。"""


# --- 内部データ構造（外へは真偽・件数・位置番号だけを出す） ----------------


class _Stage:
    __slots__ = ("start", "end", "read_count")

    def __init__(self, start: int, end: int, read_count: int):
        self.start = start          # コマンド列上の開始インデックス(SEEK)
        self.end = end              # 次段の開始インデックス(排他)
        self.read_count = read_count  # このSEEK段に含まれるREAD DATA件数


def _build_stages(names: list[str], cmds: list[awp.Command]) -> list[_Stage]:
    """SEEK出現位置でコマンド列を段に分ける。SEEK以前のコマンドは段に
    含めない(起動区間・前置区間として扱う)。"""
    seek_positions = [i for i, n in enumerate(names) if n == "SEEK"]
    stages: list[_Stage] = []
    for si, start in enumerate(seek_positions):
        end = seek_positions[si + 1] if si + 1 < len(seek_positions) else len(names)
        read_count = sum(1 for n in names[start:end] if n == "READ DATA")
        stages.append(_Stage(start, end, read_count))
    return stages


def _recv_runs(rows: list[m2s.Ev]) -> list[list[int]]:
    """受信run = sub視点 IN $FC 連続列(window_a_runs)。戻り値は
    sub_rowsへのインデックス列のリスト。"""
    sub_rows = [e for e in rows if e.cpu == "sub"]
    fc_idx = arb.sub_fc_indices(sub_rows)
    return arb.window_a_runs(sub_rows, fc_idx), sub_rows


def _run_completion_clock(run: list[int], sub_rows: list[m2s.Ev]) -> int:
    return sub_rows[run[-1]].clock


def _match_stage_entry_runs(
    stages: list[_Stage],
    cmds: list[awp.Command],
    runs: list[list[int]],
    sub_rows: list[m2s.Ev],
) -> list[list[int]]:
    """段ごとに、直前に完了している受信runの候補(runsへのインデックス)の
    リストを返す。候補が1件なら一意に定まったことを意味する。"""
    completions = [_run_completion_clock(r, sub_rows) for r in runs]
    results: list[list[int]] = []
    prev_boundary = -1
    for stage in stages:
        seek_cmd = cmds[stage.start]
        hi = seek_cmd.clock
        candidates = [
            ri for ri, c in enumerate(completions) if prev_boundary < c <= hi
        ]
        results.append(candidates)
        last_idx = stage.end - 1
        prev_boundary = cmds[last_idx].end_clock if 0 <= last_idx < len(cmds) else hi
    return results


# --- 段階1 ------------------------------------------------------------


def stage1_report(iolog: Path) -> dict:
    rows, masked = m2s.parse_iolog(iolog)
    if sum(masked.values()):
        raise SafeError("伏せ字ログでは受信runの内容を比較できない")
    names, cmds, full_rows = cef.command_names(iolog)
    stages = _build_stages(names, cmds)
    runs, sub_rows = _recv_runs(full_rows)

    continuous = [s for s in stages if s.read_count > 1]
    single = [s for s in stages if s.read_count == 1]

    lengths = [s.read_count for s in continuous]
    lengths_equal = len(set(lengths)) <= 1

    match = _match_stage_entry_runs(stages, cmds, runs, sub_rows)
    ambiguous_count = sum(1 for c in match if len(c) != 1)

    continuous_idx = [i for i, s in enumerate(stages) if s.read_count > 1]
    entry_ambiguous_count = sum(
        1 for i in continuous_idx if len(match[i]) != 1
    )

    return {
        "total_recv_run_count": len(runs),
        "stage_count": len(stages),
        "continuous_region_count": len(continuous),
        "continuous_region_lengths_equal": lengths_equal,
        "single_region_count": len(single),
        "stage_entry_ambiguous_count": ambiguous_count,
        "entry_ambiguous_count": entry_ambiguous_count,
        "halt_stage2": entry_ambiguous_count > 0,
        # 内部専用(段階2で使う。出力はしない)
        "_stages": stages,
        "_match": match,
        "_runs": runs,
        "_sub_rows": sub_rows,
        "_continuous_idx": continuous_idx,
    }


def _print_stage1(rep: dict, out) -> None:
    for key in (
        "total_recv_run_count",
        "stage_count",
        "continuous_region_count",
        "continuous_region_lengths_equal",
        "single_region_count",
        "stage_entry_ambiguous_count",
        "entry_ambiguous_count",
        "halt_stage2",
    ):
        print(f"{key}={rep[key]}", file=out)


# --- 段階2 ------------------------------------------------------------


def _eq(a: Optional[int], b: Optional[int]) -> bool:
    if a is None or b is None:
        raise SafeError("伏せ字値は比較できない")
    return a == b


def _cmp_sign(a: Optional[int], b: Optional[int]) -> int:
    if a is None or b is None:
        raise SafeError("伏せ字値は比較できない")
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _run_values(run: list[int], sub_rows: list[m2s.Ev]) -> list[Optional[int]]:
    return [sub_rows[i].value for i in run]


def stage2_report(iolog: Path) -> dict:
    st1 = stage1_report(iolog)
    if st1["halt_stage2"]:
        return {"verdict": "N", "reason": "stage1_entry_ambiguous"}

    stages = st1["_stages"]
    match = st1["_match"]
    runs = st1["_runs"]
    sub_rows = st1["_sub_rows"]
    continuous_idx = st1["_continuous_idx"]

    group_r_run_idx = [match[i][0] for i in continuous_idx]

    single_idx = [i for i, s in enumerate(stages) if s.read_count == 1]
    single_unique = [i for i in single_idx if len(match[i]) == 1]
    group_s_run_idx = [
        match[i][0] for i in single_unique if match[i][0] not in group_r_run_idx
    ]

    group_r = [_run_values(runs[i], sub_rows) for i in group_r_run_idx]
    group_s = [_run_values(runs[i], sub_rows) for i in group_s_run_idx]

    r_lengths = [len(v) for v in group_r]
    s_lengths = [len(v) for v in group_s]
    r_lengths_equal = len(set(r_lengths)) <= 1

    comparable_length = min(r_lengths + s_lengths) if (group_r and group_s) else 0

    c1_positions: list[int] = []
    distinguishing_positions: list[int] = []

    for p in range(comparable_length):
        r_vals = [run[p] for run in group_r]
        r_eq = all(_eq(r_vals[0], v) for v in r_vals[1:]) if r_vals else False
        if not r_eq:
            continue
        r_ref = r_vals[0]
        s_vals = [run[p] for run in group_s]
        s_eq_r = all(_eq(r_ref, v) for v in s_vals)
        if s_eq_r:
            continue
        distinguishing_positions.append(p)
        signs = [_cmp_sign(r_ref, v) for v in s_vals]
        sign_consistent = len(set(signs)) == 1
        if sign_consistent and signs[0] == 1:
            c1_positions.append(p)

    if c1_positions:
        verdict = "C1"
    elif not distinguishing_positions:
        verdict = "C2"
    else:
        verdict = "C3"

    return {
        "verdict": verdict,
        "group_r_count": len(group_r),
        "group_s_count": len(group_s),
        "group_r_lengths_equal": r_lengths_equal,
        "comparable_length": comparable_length,
        "distinguishing_position_count": len(distinguishing_positions),
        "distinguishing_positions": distinguishing_positions,
        "c1_position_count": len(c1_positions),
        "c1_positions": c1_positions,
    }


def _print_stage2(rep: dict, out) -> None:
    if rep.get("verdict") == "N":
        print("verdict=N", file=out)
        print(f"reason={rep['reason']}", file=out)
        return
    for key in (
        "group_r_count",
        "group_s_count",
        "group_r_lengths_equal",
        "comparable_length",
        "distinguishing_position_count",
        "c1_position_count",
    ):
        print(f"{key}={rep[key]}", file=out)
    print(
        "distinguishing_positions="
        + ",".join(str(p) for p in rep["distinguishing_positions"]),
        file=out,
    )
    print(
        "c1_positions=" + ",".join(str(p) for p in rep["c1_positions"]),
        file=out,
    )
    print(f"verdict={rep['verdict']}", file=out)


# --- CLI ----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("stage1")
    p1.add_argument("--iolog", required=True, type=Path)

    p2 = sub.add_parser("stage2")
    p2.add_argument("--iolog", required=True, type=Path)

    args = ap.parse_args()

    try:
        if args.cmd == "stage1":
            rep = stage1_report(args.iolog)
            _print_stage1(rep, sys.stdout)
        else:
            rep = stage2_report(args.iolog)
            _print_stage2(rep, sys.stdout)
    except SafeError as ex:
        # 例外メッセージは固定文言のみ(値を含めない)。
        print(f"解析不可: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
