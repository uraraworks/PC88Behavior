#!/usr/bin/env python3
"""需要入口の公式・混成FDCコマンド種別列を値なしで比較する。

生iologを内部で読むが、出力するのは公開μPD765コマンド名、件数、共通
prefix、最初の差の分類だけである。FDCパラメータ・結果・データ値は出さない。
終了コードは、コマンド種別列が完全一致なら0、不一致なら1、解析不能なら2。
"""
from __future__ import annotations

import argparse
import collections
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


def drive_head(value: int) -> str:
    """μPD765公開unit/headパラメータを値ではなく分類名へ変換する。"""
    drive = ("A", "B", "unit2", "unit3")[value & 0x03]
    return f"{drive}/head{(value >> 2) & 1}"


def status_fields(command: awp.Command) -> list[tuple[str, int]]:
    """公開結果相のステータスだけを返す。READデータ本文・PCNは除外する。"""
    values = command.input_values or []
    if command.opcode == 0x04 and values:
        return [("ST3", values[-1])]
    if command.opcode == 0x08 and len(values) >= 2:
        return [("ST0", values[-2])]
    if command.opcode not in awp.NO_RESULT and len(values) >= 7:
        tail = values[-7:]
        return [("ST0", tail[0]), ("ST1", tail[1]), ("ST2", tail[2])]
    return []


def describe_status(field: str, value: int) -> str:
    """結果バイトを公開ビット名だけで記号化する（数値は返さない）。"""
    if field == "ST0":
        ic = ("正常終了", "異常終了", "無効コマンド", "Ready状態変化")[(value >> 6) & 3]
        flags = [name for bit, name in (
            (0x20, "SEEK END"), (0x10, "EQUIPMENT CHECK"),
            (0x08, "NOT READY"),
        ) if value & bit]
        return "/".join([f"IC={ic}", *flags, drive_head(value)])
    if field == "ST1":
        flags = [name for bit, name in (
            (0x80, "END OF CYLINDER"), (0x20, "DATA ERROR"),
            (0x10, "OVERRUN"), (0x04, "NO DATA"),
            (0x02, "NOT WRITABLE"), (0x01, "MISSING ADDRESS MARK"),
        ) if value & bit]
        return "/".join(flags or ["エラービットなし"])
    if field == "ST2":
        flags = [name for bit, name in (
            (0x40, "CONTROL MARK"), (0x20, "DATA ERROR IN DATA FIELD"),
            (0x10, "WRONG CYLINDER"), (0x08, "SCAN EQUAL HIT"),
            (0x04, "SCAN NOT SATISFIED"), (0x02, "BAD CYLINDER"),
            (0x01, "MISSING ADDRESS MARK IN DATA FIELD"),
        ) if value & bit]
        return "/".join(flags or ["エラービットなし"])
    flags = [name for bit, name in (
        (0x80, "FAULT"), (0x40, "WRITE PROTECTED"), (0x20, "READY"),
        (0x10, "TRACK 0"), (0x08, "TWO SIDE"),
    ) if value & bit]
    if not value & 0x20:
        flags.append("NOT READY")
    return "/".join([*(flags or ["状態フラグなし"]), drive_head(value)])


def is_error_status(field: str, value: int, write_operation: bool = False) -> bool:
    if field == "ST0":
        return (value & 0xC0) != 0 or bool(value & 0x18)
    if field == "ST1":
        return bool(value & 0xB7)
    if field == "ST2":
        return bool(value & 0x73)
    return (bool(value & 0x80) or not bool(value & 0x20)
            or (write_operation and bool(value & 0x40)))


def print_entry_classification(
    label: str, commands: list[awp.Command], write_operation: bool = False
) -> None:
    units: collections.Counter[tuple[str, str]] = collections.Counter()
    for command in commands:
        params = command.param_values or []
        if command.opcode != 0x03 and command.opcode != 0x08 and params:
            units[(awp.NAMES[command.opcode], drive_head(params[0]))] += 1
    if units:
        joined = ", ".join(
            f"{name}:{unit}×{count}"
            for (name, unit), count in sorted(units.items())
        )
        print(f"{label}入口区間unit/head分類: {joined}")
    else:
        print(f"{label}入口区間unit/head分類: 対象コマンドなし")

    for index, command in enumerate(commands, 1):
        fields = status_fields(command)
        errors = [(field, value) for field, value in fields
                  if is_error_status(field, value, write_operation)]
        if errors:
            detail = ", ".join(
                f"{field}={describe_status(field, value)}" for field, value in errors
            )
            print(f"{label}入口区間の最初のエラー結果: コマンド{index}件目"
                  f"({awp.NAMES[command.opcode]})、{detail}")
            break
    else:
        print(f"{label}入口区間のエラー結果: なし")


def print_first_entry_difference(
    official: list[awp.Command], mixed: list[awp.Command]
) -> None:
    for index, (a, b) in enumerate(zip(official, mixed), 1):
        ap, bp = a.param_values or [], b.param_values or []
        if a.opcode == b.opcode and a.opcode not in (0x03, 0x08) and ap and bp:
            if (ap[0] & 0x07) != (bp[0] & 0x07):
                print(f"入口区間の最初のunit/head差: コマンド{index}件目"
                      f"({awp.NAMES[a.opcode]})、公式={drive_head(ap[0])}、"
                      f"混成={drive_head(bp[0])}")
                break
    else:
        print("入口区間のunit/head差: なし")

    for index, (a, b) in enumerate(zip(official, mixed), 1):
        af, bf = status_fields(a), status_fields(b)
        for (an, av), (bn, bv) in zip(af, bf):
            if an != bn or av != bv:
                print(f"入口区間の最初の結果ステータス差: コマンド{index}件目"
                      f"({awp.NAMES[a.opcode]})の{an}/{bn}、"
                      f"公式={describe_status(an, av)}、"
                      f"混成={describe_status(bn, bv)}")
                return
        if len(af) != len(bf):
            print(f"入口区間の最初の結果ステータス差: コマンド{index}件目"
                  "の結果相長差")
            return
    if len(official) != len(mixed):
        print("入口区間の最初の結果ステータス差: コマンド列終端差")
    else:
        print("入口区間の結果ステータス差: なし")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--official", required=True, type=Path)
    ap.add_argument("--mixed", required=True, type=Path)
    ap.add_argument("--after-frame", type=int,
                    help="このframe以降を入口区間としてunit/headと結果を分類する")
    ap.add_argument("--write-operation", action="store_true",
                    help="ST3 WRITE PROTECTEDをエラー原因として分類する")
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
    if args.after_frame is not None:
        off_entry = [c for c in off_cmds if c.frame >= args.after_frame]
        mix_entry = [c for c in mix_cmds if c.frame >= args.after_frame]
        print_entry_classification("公式", off_entry, args.write_operation)
        print_entry_classification("混成", mix_entry, args.write_operation)
        print_first_entry_difference(off_entry, mix_entry)
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
