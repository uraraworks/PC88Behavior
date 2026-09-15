#!/usr/bin/env python3
"""PC88Behavior: l4-c5 代表プログラム集の適合場面 — 正規化・ハッシュ化道具。

`tools/l4_vram_probe.py` の差分モード(`diff_vram_dumps`)をそのまま import
して使う（二重実装しない。`tools/l4_print_conform_record.py`と同じ作法）。

事前登録 `docs/notes/l4-c5-representative-programs-conformance-scene-
preregistration.md`（`2837926`）「比べるもの・正規化」節どおり:

  - `origin_row` = 変化した行のうち最小のrow0（=`run`を打った行）
  - `ok_row` = 変化した行のうち最大のrow0（=`Ok`の行）
  - `cells`: `origin_row`より大きく`ok_row`より小さい行(=出力行)の
    「前が空白だったセル」を(row0-origin_row, col0, 文字コード)に
    正規化した並び
  - `ok_relative_row` = `ok_row - origin_row`
  - 比較しない: バナーの行(0-5)、最下行(19、ファンクションキー表示行)、
    位置の絶対値(row0そのもの)

`--before`には、`run`を打つ直前の写し（`tools/l4_program_typeplan.py`の
`run_start_frame`で取った写し）を渡すことを前提とする。この前提により
`origin_row`（変化した行の最小row0）が「`run`を打った行」と一致する
（`run`はこの写しより後にしか打たれていないため）。

## 「見つからない」の判別（黙ってSHAを出さない）

`l4_print_conform_record.py`と異なり、本ツールは複数行にわたる出力を
扱うため、スクロール等で前提が崩れる可能性がある。以下のいずれかに
該当する場合は、`status`列に理由を書き、`cell_count`・`ok_relative_row`・
`sha256`はいずれも`NA`にする（SHA-256を計算・出力しない）。

  - `no_changes`: 変化した行が無い（何も起きなかった）
  - `insufficient_rows`: 変化した行が1行だけ（出力も`Ok`も区別できない）
  - `ok_row_not_found`: 最大row0の行が`Ok`らしい形（前が空白だった
    セルだけで構成される、件数が少ない）をしていない。出力の続きを
    `Ok`行と誤認している可能性がある（写しが早すぎた、または出力が
    多すぎて`Ok`が捉えられていない）
  - `origin_row_suspicious`: 最小row0が6未満（`l4-s5a`以来の段階5測定
    全体で、打鍵はrow6以降にしか現れていない）。スクロールにより
    `run`を打った行自体が画面外へ押し出され、無関係な行を`origin_row`
    と誤認している可能性がある

出してよいもの（これ以外は標準出力・標準エラーへ出さない。CLAUDE.md
禁止事項7 厳守）:
  - `status`・出力セル件数(cell_count)・`Ok`行の相対行(ok_relative_row)・
    正規化した記録のSHA-256(sha256)
  - 文字コード・列位置そのものは出さない(ハッシュの中にしか現れない)

使い方:
  python3 tools/l4_program_conform_record.py --before before.bin --after after.bin \
      [--exclude-rows 0,1,2,3,4,5,19] [--ok-max-count 6]

出力(TSV、1行):
  status<TAB>cell_count<TAB>ok_relative_row<TAB>sha256
（`status`が`ok`以外のときは、残り3列はすべて`NA`）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import l4_vram_probe  # noqa: E402

DEFAULT_EXCLUDE_ROWS = {0, 1, 2, 3, 4, 5, 19}
DEFAULT_OK_MAX_COUNT = 6
ORIGIN_ROW_MIN_EXPECTED = 6


def build_record(
    before_path: str,
    after_path: str,
    exclude_rows: "set[int]",
    ok_max_count: int = DEFAULT_OK_MAX_COUNT,
) -> dict:
    diff = l4_vram_probe.diff_vram_dumps(before_path, after_path, count_only_rows=exclude_rows)
    char_changes = diff["char_changes"]

    rows_touched = sorted({c["row0"] for c in char_changes})

    if not rows_touched:
        return {"status": "no_changes"}
    if len(rows_touched) < 2:
        return {"status": "insufficient_rows"}

    origin_row = rows_touched[0]
    ok_row = rows_touched[-1]

    if origin_row < ORIGIN_ROW_MIN_EXPECTED:
        return {"status": "origin_row_suspicious"}

    ok_cells = [c for c in char_changes if c["row0"] == ok_row]
    ok_looks_valid = len(ok_cells) <= ok_max_count and all(c.get("was_blank") for c in ok_cells)
    if not ok_looks_valid:
        return {"status": "ok_row_not_found"}

    cells = []
    for c in char_changes:
        if not c.get("was_blank"):
            continue
        row0 = c["row0"]
        if row0 <= origin_row or row0 >= ok_row:
            continue
        cells.append([row0 - origin_row, c["col0"], c["char_after"]])
    cells.sort()

    record = {
        "cells": cells,
        "ok_relative_row": ok_row - origin_row,
    }
    return {"status": "ok", "record": record}


def hash_record(record: dict) -> str:
    canon = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("ascii")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--exclude-rows", default="0,1,2,3,4,5,19")
    ap.add_argument("--ok-max-count", type=int, default=DEFAULT_OK_MAX_COUNT)
    args = ap.parse_args()

    exclude_rows = {int(x) for x in args.exclude_rows.split(",") if x.strip() != ""}
    result = build_record(args.before, args.after, exclude_rows, args.ok_max_count)

    status = result["status"]
    if status != "ok":
        print("\t".join([status, "NA", "NA", "NA"]))
        return 1

    record = result["record"]
    sha = hash_record(record)
    print(
        "\t".join(
            [
                "ok",
                str(len(record["cells"])),
                str(record["ok_relative_row"]),
                sha,
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
