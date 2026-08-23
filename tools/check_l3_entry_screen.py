#!/usr/bin/env python3
"""需要入口の打鍵反映と完了を、画面本文を出さずに分類する。

入力は q88measure --out の一時ファイルだけを想定する。公式ROMや公式
ディスク由来の画面文字列を表示せず、自分で打鍵したコマンドが画面に現れ、
その応答が期待する分類（正常終了またはエラー表示）かだけを終了コードで
返す。到達なら0、未到達または別分類なら1、入力不備なら2。エラー本文は
照合にも出力にも使わず、同条件で決定論的に分離した全画面の行数クラスと
正常一覧後の ``Ok`` の有無だけで分類する。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path


COMMANDS = {
    "load_existing": ['load"q7l"'],
    "seqfile": [
        'open "q7s" for output as #1',
        'print#1,"hi"',
        "close",
        'open "q7s" for input as #1',
        "input#1,w$",
        "close",
    ],
    "kill": ['kill"q7k"'],
    "name": ['name"q7n" as "q7r"'],
    "load_prepare": ['save"q7l"'],
    "write_protect": ['save"q8p"'],
    "no_disk": ["files 2"],
    "unreadable_disk": ["files 2"],
    "drive2": ["files 2"],
}

ERROR_SCENARIOS = {"write_protect", "no_disk", "unreadable_disk"}
OUTPUT_SUCCESS_SCENARIOS = {"drive2"}


def screen_rows(path: Path) -> list[str]:
    rows: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as fp:
        for line in fp:
            match = re.match(r"^\s*\d+\|\s?(.*)$", line.rstrip("\n"))
            if match:
                rows.append(match.group(1).strip().lower())
    return rows


def reached(rows: list[str], commands: list[str]) -> bool:
    """指定コマンドを順に探し、それぞれの直後がOkかを確認する。"""
    cursor = 0
    for command in commands:
        pos = next(
            (i for i in range(cursor, len(rows)) if command in rows[i]), None
        )
        if pos is None:
            return False
        response = next(
            ((i, row) for i, row in enumerate(rows[pos + 1 :], pos + 1) if row),
            None,
        )
        if response is None or response[1] != "ok":
            return False
        cursor = response[0] + 1
    return True


def reached_error(rows: list[str], command: str) -> bool:
    """打鍵反映と、一覧を伴わない短いエラー画面形を本文なしで確認する。"""
    pos = next((i for i, row in enumerate(rows) if command in row), None)
    if pos is None:
        return False
    # --outは物理行順であり時間順ではない。公式エラー3条件は8〜11行、
    # 正常FILES一覧は17行で決定論的に分離したため、本文でなく全画面の
    # 行数クラスを使う。FDCエラー分類との組合せが最終到達証拠になる。
    return pos is not None and len(rows) <= 11


def reached_output_success(rows: list[str], command: str) -> bool:
    """FILES型の出力を1行以上挟み、その後 Ok へ戻ったことを確認する。"""
    pos = next((i for i, row in enumerate(rows) if command in row), None)
    if pos is None:
        return False
    response = [row for row in rows[pos + 1 :] if row]
    try:
        ok_pos = response.index("ok")
    except ValueError:
        return False
    return len(rows) >= 12 and ok_pos >= 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--scenario", required=True, choices=sorted(COMMANDS))
    args = parser.parse_args()
    try:
        rows = screen_rows(args.report)
    except OSError:
        print("screen_reach=parse_error")
        return 2
    if args.scenario in ERROR_SCENARIOS:
        is_reached = reached_error(rows, COMMANDS[args.scenario][0])
    elif args.scenario in OUTPUT_SUCCESS_SCENARIOS:
        is_reached = reached_output_success(rows, COMMANDS[args.scenario][0])
    else:
        is_reached = reached(rows, COMMANDS[args.scenario])
    if is_reached:
        print("screen_reach=reached")
        return 0
    print("screen_reach=not_reached")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
