#!/usr/bin/env python3
"""需要入口の打鍵反映と完了を、画面本文を出さずに分類する。

入力は q88measure --out の一時ファイルだけを想定する。公式ROMや公式
ディスク由来の画面文字列を表示せず、自分で打鍵したコマンドが画面に現れ、
その直後が ``Ok`` かだけを終了コードで返す。到達なら0、未到達または
エラーなら1、入力不備なら2。
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
}


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
    if reached(rows, COMMANDS[args.scenario]):
        print("screen_reach=reached")
        return 0
    print("screen_reach=not_reached")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
