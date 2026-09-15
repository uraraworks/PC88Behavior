#!/usr/bin/env python3
"""PC88Behavior: l4-s5a 直接モードLISTの出力行 — 分類・記録道具。

`tools/l4_vram_probe.py` の差分モード(`diff_vram_dumps`)・写しの読み込み
(`load_vram_dump`/`char_rows`)をそのまま import して使う
（二重実装しない。`tools/l4_s4a_float_classify.py`と同じ作法・同じ
原点の決め方を踏襲する）。

事前登録（別担当が並行で作成中）の規則どおり:

- 原点(origin_row)は「打った行」(変化した行のうち最小row0)、
  `Ok`行(ok_row)は変化した行のうち最大row0（`tools/l4_s4a_float_
  classify.py`と同じ判定）。
- origin_rowとok_rowのあいだの各行を、行ごとに分類する。
  - `list_line`: 先頭の空白を除いた最初の文字が数字`0`〜`9`で、かつ
    行の全80セルが表示可能なASCII(0x20〜0x7E)の行。この行だけ、
    押す前が空白だったセルの(相対行, 相対桁, コード)を出す。
  - `other_line`: 上記に当てはまらない行。件数と位置の範囲(相対桁の
    最小・最大)だけを出す。**この行のコードは一切出さない**
    （`tools/l4_s4a_float_classify.py`の`--range-only`と同じ設計）。
- 押す前が空白でなかった(コードが読めない)セルが行に混じる場合も、
  安全側で`other_line`に倒す（`l4_s4a_float_classify.py`と同じ扱い）。

出してよいもの（これ以外は標準出力へ出さない。CLAUDE.md 禁止事項7 厳守）:
  - classification（行ごとの`list_line`/`other_line`）
  - origin_row0・origin_col0・ok_relative_row
  - 行ごとの件数(count)・桁範囲(col_min/col_max)
  - `list_line`の行だけ、(相対行, 相対桁, コード)の並び
    （コードは数字0-9・空白と、行の残りの表示可能ASCII文字。自分で
    打ったBASICプログラムの行番号から始まる行であり、l4-s4a〜l4-s4lの
    「自分で打った式の直接の結果」と同じ扱いで出してよい）

使い方:
  python3 tools/l4_list_classify.py --before before.bin --after after.bin

出力: JSON 1行。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import l4_vram_probe  # noqa: E402

COLS = l4_vram_probe.COLS  # 80
DIGITS = frozenset(ord(c) for c in "0123456789")


def _row_bytes(dump_path: str, row0: int) -> bytes:
    data = l4_vram_probe.load_vram_dump(dump_path)
    rows = l4_vram_probe.char_rows(data)
    return rows[row0]


def _classify_row(row_bytes: bytes) -> bool:
    """行の全80セルが表示可能ASCII(0x20-0x7E)で、先頭の空白を除いた
    最初の文字が数字0-9なら True(list_line)。それ以外は False。

    自己検査専用の故障注入(既定では無効。PC88_LIST_FAULT_SKIP_DIGIT_
    CHECK=1を設定すると数字始まりの判定を外す)を持つ。これは
    tools/l4_list_classify_selftest.shが、この判定を外すと陰性対照が
    NGになる(=検出力がある)ことを確かめるためだけに使う。測定では
    設定しない。
    """
    if not all(0x20 <= b <= 0x7E for b in row_bytes):
        return False
    if os.environ.get("PC88_LIST_FAULT_SKIP_DIGIT_CHECK"):
        return True
    first_nonspace = None
    for b in row_bytes:
        if b != 0x20:
            first_nonspace = b
            break
    if first_nonspace is None:
        return False
    return first_nonspace in DIGITS


def classify(before_path: str, after_path: str) -> dict:
    diff = l4_vram_probe.diff_vram_dumps(before_path, after_path)
    char_changes = diff["char_changes"]

    rows_touched = sorted({c["row0"] for c in char_changes})
    if len(rows_touched) < 2:
        return {
            "classification": "insufficient_rows",
            "rows_touched": rows_touched,
        }

    origin_row = rows_touched[0]
    ok_row = rows_touched[-1]

    # 行ごとに変化セルをまとめる。
    by_row: "dict[int, list[dict]]" = {}
    for c in char_changes:
        r = c["row0"]
        if origin_row < r < ok_row:
            by_row.setdefault(r, []).append(c)

    lines = []
    for row0 in sorted(by_row):
        cells = by_row[row0]
        row_bytes = _row_bytes(after_path, row0)
        is_list_line = _classify_row(row_bytes)

        # 押す前が空白でなかった(コードが読めない)セルが混じる場合は
        # 安全側でother_lineに倒す。
        unreadable = any(not c.get("was_blank") for c in cells)
        if unreadable:
            is_list_line = False

        rel_row = row0 - origin_row
        cols = [c["col0"] for c in cells]
        row_summary = {
            "relative_row": rel_row,
            "count": len(cells),
            "col_min": min(cols) if cols else None,
            "col_max": max(cols) if cols else None,
        }

        if is_list_line:
            cell_list = [
                [rel_row, c["col0"], int(c["char_after"], 16)]
                for c in cells
                if c.get("was_blank")
            ]
            lines.append(
                {
                    "relative_row": rel_row,
                    "classification": "list_line",
                    "row_summary": row_summary,
                    "cells": cell_list,
                }
            )
        else:
            lines.append(
                {
                    "relative_row": rel_row,
                    "classification": "other_line",
                    "row_summary": row_summary,
                }
            )

    return {
        "classification": "ok",
        "origin_row0": origin_row,
        "origin_col0": 0,
        "ok_relative_row": ok_row - origin_row,
        "lines": lines,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    args = ap.parse_args()

    record = classify(args.before, args.after)
    print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
