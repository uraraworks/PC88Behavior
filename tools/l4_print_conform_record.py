#!/usr/bin/env python3
"""PC88Behavior: l4-c2c 直接モードPRINT適合の場面固定 — 正規化・ハッシュ化道具。

`tools/l4_vram_probe.py` の差分モード(`diff_vram_dumps`)をそのまま import
して使う（二重実装しない。`tools/l4_echo_conform_record.py` と同じ作法）。

事前登録 `docs/notes/l4-c2c-print-conformance-scene-preregistration.md`
「記録する内容」節どおり、P1〜P5（打った行の次の行から `Ok` 行の直前まで）
の「前が空白だったセル」だけを正規化し、位置の絶対値(row0そのもの)・
`Ok` 行自身の文字コードを含めない形で SHA-256 を取る。

`tools/l4_echo_conform_record.py` との違い（流用しない理由。事前登録参照）:
  - 原点は「最初に変化した空白セル」ではなく「変化した行のうち最小row0
    (=打った行)」、列は0固定（打った行の先頭のセル）
  - 出力セル列は「打った行」自身と「Ok行」自身を除いた行だけを対象にする
  - `Ok` 行は相対行番号だけを記録し、文字コードは一切含めない

出してよいもの（これ以外は標準出力へ出さない。CLAUDE.md 禁止事項7 厳守）:
  - 出力セル件数(cell_count)・Ok行の相対行(ok_relative_row)・
    正規化した記録のSHA-256(sha256)
  - 文字コード・列位置そのものは出さない(ハッシュの中にしか現れない)

使い方:
  python3 tools/l4_print_conform_record.py --before before.bin --after after.bin \
      [--count-only-rows 19]

出力(TSV、1行):
  cell_count<TAB>ok_relative_row<TAB>sha256
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import l4_vram_probe  # noqa: E402


def build_record(before_path: str, after_path: str, count_only_rows: "set[int]") -> dict:
    diff = l4_vram_probe.diff_vram_dumps(before_path, after_path, count_only_rows=count_only_rows)
    char_changes = diff["char_changes"]

    rows_touched = sorted({c["row0"] for c in char_changes})
    if len(rows_touched) < 2:
        # 打った行しか変化していない(=出力もOkも無い)。P1〜P5では起こら
        # ない想定だが、gate_failed 相当として呼び出し側が扱えるように
        # origin/ok を None のまま記録する(cellsは空、ok_relative_rowは
        # null)。
        origin_row = rows_touched[0] if rows_touched else None
        ok_row = None
    else:
        origin_row = rows_touched[0]
        ok_row = rows_touched[-1]

    cells = []
    if origin_row is not None and ok_row is not None:
        for c in char_changes:
            if not c.get("was_blank"):
                continue
            row0 = c["row0"]
            if row0 <= origin_row or row0 >= ok_row:
                continue
            cells.append([row0 - origin_row, c["col0"], c["char_after"]])
    cells.sort()

    ok_relative_row = (ok_row - origin_row) if (origin_row is not None and ok_row is not None) else None

    record = {
        "cells": cells,
        "ok_relative_row": ok_relative_row,
    }
    return record


def hash_record(record: dict) -> str:
    canon = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("ascii")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--count-only-rows", default="19")
    args = ap.parse_args()

    rows = l4_vram_probe.parse_row_list(args.count_only_rows) or []
    record = build_record(args.before, args.after, set(rows))
    sha = hash_record(record)
    ok_rel = record["ok_relative_row"]
    print(
        "\t".join(
            [
                str(len(record["cells"])),
                str(ok_rel) if ok_rel is not None else "NA",
                sha,
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
