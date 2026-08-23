#!/usr/bin/env python3
"""FILES/LOAD入口の公式・混成FDCコマンド種別列を値なしで比較する。

生iologを内部で読むが、出力するのは公開μPD765コマンド名、件数、共通
prefix、最初の差の分類だけである。FDCパラメータ・結果・データ値は出さない。
終了コードは、コマンド種別列が完全一致なら0、不一致なら1、解析不能なら2。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_write_path as awp  # noqa: E402


READ_UNIT = (
    "SEEK", "SENSE INTERRUPT STATUS", "SENSE DRIVE STATUS", "READ DATA",
)
WRITE_UNIT = (
    "SEEK", "SENSE INTERRUPT STATUS", "SENSE DRIVE STATUS", "WRITE DATA",
)


def command_names(path: Path) -> tuple[list[str], list[awp.Command], list[m2s.Ev]]:
    rows, masked = m2s.parse_iolog(path)
    if sum(masked.values()):
        raise awp.SafeError("伏せ字ログではFDCコマンド語を判定できない")
    cmds = awp.parse_commands(rows)
    return [awp.NAMES[c.opcode] for c in cmds], cmds, rows


def compact(names: list[str]) -> str:
    """頻出する公開4コマンド単位へ畳み、順序を保った短い列にする。"""
    tokens: list[str] = []
    i = 0
    while i < len(names):
        four = tuple(names[i:i + 4])
        if four == READ_UNIT:
            tokens.append("READ単位")
            i += 4
        elif four == WRITE_UNIT:
            tokens.append("WRITE単位")
            i += 4
        else:
            tokens.append(names[i])
            i += 1
    runs: list[list[object]] = []
    for token in tokens:
        if runs and runs[-1][0] == token:
            runs[-1][1] = int(runs[-1][1]) + 1
        else:
            runs.append([token, 1])
    return " -> ".join(
        str(token) if count == 1 else f"{token} x {count}"
        for token, count in runs
    )


def first_parameter_difference(
    official: list[awp.Command], mixed: list[awp.Command]
) -> str:
    """コマンド種別より内側の最初のパラメータ差を値なしで分類する。"""
    for ci, (a, b) in enumerate(zip(official, mixed), start=1):
        if a.opcode != b.opcode:
            return "コマンド種別差が先"
        ap = a.param_values or []
        bp = b.param_values or []
        for pi, (av, bv) in enumerate(zip(ap, bp), start=1):
            if av != bv:
                return (f"FDCイベント内の最初の値差: コマンド{ci}件目"
                        f"({awp.NAMES[a.opcode]})のパラメータ{pi}件目")
        if len(ap) != len(bp):
            return f"コマンド{ci}件目のパラメータ長差"
    return "FDCコマンドの公開パラメータ列に差なし"


def raw_fb_prefix(a_rows: list[m2s.Ev], b_rows: list[m2s.Ev]) -> tuple[int, str]:
    a = [e for e in a_rows if e.cpu == "sub" and e.port == "00FB"]
    b = [e for e in b_rows if e.cpu == "sub" and e.port == "00FB"]
    n = min(len(a), len(b))
    for i in range(n):
        if (a[i].kind, a[i].value) != (b[i].kind, b[i].value):
            kind = "同方向の値差" if a[i].kind == b[i].kind else "方向差"
            return i, kind
    if len(a) != len(b):
        return n, "列終端差"
    return n, "完全一致"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--official", required=True, type=Path)
    ap.add_argument("--mixed", required=True, type=Path)
    args = ap.parse_args()
    try:
        off_names, off_cmds, off_rows = command_names(args.official)
        mix_names, mix_cmds, mix_rows = command_names(args.mixed)
    except (ValueError, OSError, awp.SafeError) as ex:
        print(f"解析不能: {ex}", file=sys.stderr)
        return 2

    n = min(len(off_names), len(mix_names))
    prefix = next((i for i in range(n) if off_names[i] != mix_names[i]), n)
    same = prefix == n and len(off_names) == len(mix_names)

    print(f"公式FDCコマンド種別列({len(off_names)}件): {compact(off_names)}")
    print(f"混成FDCコマンド種別列({len(mix_names)}件): {compact(mix_names)}")
    print(f"FDCコマンド種別の一致prefix: {prefix}件")
    if same:
        print("FDCコマンド種別の最初の差: なし（全長一致）")
    else:
        pos = prefix + 1
        if prefix >= len(off_names):
            detail = "公式列が先に終端"
        elif prefix >= len(mix_names):
            detail = "混成列が先に終端（停止または未到達）"
        else:
            detail = f"種別差（公式={off_names[prefix]}、混成={mix_names[prefix]}）"
        print(f"FDCコマンド種別の最初の差: {pos}件目、{detail}")

    raw_prefix, raw_class = raw_fb_prefix(off_rows, mix_rows)
    raw_same = raw_class == "完全一致"
    print(f"FDCポート値列の一致prefix: {raw_prefix}件")
    if raw_same:
        print("FDCポート値列の最初の差: なし")
    else:
        print(f"FDCポート値列の最初の差: {raw_prefix + 1}件目、{raw_class}")
        print(first_parameter_difference(off_cmds, mix_cmds))
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
