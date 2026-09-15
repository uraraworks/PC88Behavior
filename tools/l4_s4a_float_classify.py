#!/usr/bin/env python3
"""PC88Behavior: l4-s4a 直接モードPRINT浮動小数点 — 分類・記録道具。

`tools/l4_vram_probe.py` の差分モード(`diff_vram_dumps`)をそのまま import
して使う（二重実装しない。`tools/l4_print_conform_record.py`・
`tools/l4_echo_conform_record.py` と同じ作法）。

事前登録 `docs/notes/l4-s4a-float-print-preregistration.md`
「記録する内容」節・「本文を出さない取り扱い」節どおり:

- 原点(origin_row)は「打った行」(変化した行のうち最小row0)、
  `Ok`行(ok_row)は変化した行のうち最大row0（`tools/l4_print_conform_record.py`
  と同じ判定）。
- 出力セルは origin_row と ok_row のあいだの行の、押す前が空白だった
  セルだけを対象にする。
- 出力セルの文字コードが全て「数字0-9・`.`・`+`・`-`・`E`・`D`・空白」の
  集合に入っていれば `numeric_output`、1つでも集合外があれば
  `non_numeric_output`。押す前が空白でなかった(コードが読めない)セルが
  混じる場合も安全側に倒して `non_numeric_output` とする。
- `numeric_output` のときだけ、かつ `--range-only` が指定されていない
  ときだけ、(相対行, 相対桁, コード)の並びを出す。それ以外は行ごとの
  件数と桁の範囲(最小・最大)だけを出す（コードは一切出さない）。
  `--range-only` は out_of_range群(X1・X2)用で、分類の判定自体は行うが
  セルの列挙を強制的に抑止する。

出してよいもの（これ以外は標準出力へ出さない。CLAUDE.md 禁止事項7 厳守）:
  - classification（numeric_output/non_numeric_output）
  - origin_row0・origin_col0・ok_relative_row
  - 行ごとの件数(count)・桁範囲(col_min/col_max)
  - numeric_output かつ --range-only 無指定のときに限り、セルの
    (相対行, 相対桁, コード)の並び（コードは数字・記号のみなので
    自分で打った式の直接の結果として出してよい。l4-s3a と同じ扱い）

使い方:
  python3 tools/l4_s4a_float_classify.py --before before.bin --after after.bin \
      [--range-only]

出力: JSON 1行。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import l4_vram_probe  # noqa: E402

# 許される文字コードの集合（数字0-9・.・+・-・E・D・空白）。
NUMERIC_CODES = frozenset(
    [ord(c) for c in "0123456789.+-ED "]
)


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

    output_cells = [
        c for c in char_changes if origin_row < c["row0"] < ok_row
    ]

    all_numeric = True
    per_row: "dict[int, dict]" = {}
    typed_cells = []  # (relative_row, col0, code_int) だけ内部に保持。出すかは呼び出し側で決める。

    for c in output_cells:
        rel_row = c["row0"] - origin_row
        row_info = per_row.setdefault(
            rel_row, {"count": 0, "col_min": None, "col_max": None}
        )
        row_info["count"] += 1
        col0 = c["col0"]
        if row_info["col_min"] is None or col0 < row_info["col_min"]:
            row_info["col_min"] = col0
        if row_info["col_max"] is None or col0 > row_info["col_max"]:
            row_info["col_max"] = col0

        if not c.get("was_blank"):
            # 押す前が空白でなかった=コードが読めない。安全側で非数値扱い。
            all_numeric = False
            continue
        code_int = int(c["char_after"], 16)
        if code_int not in NUMERIC_CODES:
            all_numeric = False
            continue
        typed_cells.append((rel_row, col0, code_int))

    classification = "numeric_output" if all_numeric else "non_numeric_output"

    return {
        "classification": classification,
        "origin_row0": origin_row,
        "origin_col0": 0,
        "ok_relative_row": ok_row - origin_row,
        "row_summary": [
            {
                "relative_row": r,
                "count": per_row[r]["count"],
                "col_min": per_row[r]["col_min"],
                "col_max": per_row[r]["col_max"],
            }
            for r in sorted(per_row)
        ],
        "_cells": typed_cells,  # 呼び出し側だけが使う。外へ出すかは main() が決める。
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument(
        "--range-only",
        action="store_true",
        help="numeric_output でもセルの列挙を出さず件数・範囲だけにする(out_of_range群用)",
    )
    args = ap.parse_args()

    record = classify(args.before, args.after)
    cells = record.pop("_cells", [])

    out = dict(record)
    if record.get("classification") == "numeric_output" and not args.range_only:
        out["cells"] = [[r, c, code] for (r, c, code) in cells]

    print(json.dumps(out, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
