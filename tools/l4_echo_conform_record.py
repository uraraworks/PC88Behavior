#!/usr/bin/env python3
"""PC88Behavior: l4-c1b 打鍵エコー適合の場面固定 — 正規化・ハッシュ化道具。

`tools/l4_vram_probe.py` の差分モード(`diff_vram_dumps`)と `attr_rows`・
`load_vram_dump` をそのまま import して使う（二重実装しない。
`tools/hash_io_stream.py` が `tools/cmp_io.py` の抽出ロジックを import する
既存の作法を踏襲する）。

事前登録 `docs/notes/l4-c1b-echo-conformance-scene-preregistration.md`
「比べるもの」節どおり、記録項目1・2・3・5（最下行を除く）だけを正規化し、
位置の絶対値(row0そのもの)を含まない形に組み立てて SHA-256 を取る。

出してよいもの（これ以外は標準出力へ出さない。CLAUDE.md 禁止事項7 厳守）:
  - 相対セル件数(cell_count)・非空白セル件数(nonblank_count)・
    属性行数(attr_row_count)・正規化した記録のSHA-256(sha256)
  - 文字コード・属性域の値そのものは出さない(ハッシュの中にしか現れない)

使い方:
  python3 tools/l4_echo_conform_record.py --before before.bin --after after.bin \
      [--count-only-rows 19]

出力(TSV、1行):
  cell_count<TAB>nonblank_count<TAB>attr_row_count<TAB>sha256
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
    blanks = [c for c in char_changes if c.get("was_blank")]
    nonblanks = [c for c in char_changes if not c.get("was_blank")]

    if blanks:
        origin_row0 = blanks[0]["row0"]
        origin_col0 = blanks[0]["col0"]
    else:
        origin_row0 = None
        origin_col0 = None

    cells = []
    for b in blanks:
        rel_row = b["row0"] - origin_row0
        rel_col = b["col0"] - origin_col0
        cells.append([rel_row, rel_col, b["char_after"]])

    rows_touched = sorted({c["row0"] for c in char_changes})
    before_data = l4_vram_probe.load_vram_dump(before_path)
    after_data = l4_vram_probe.load_vram_dump(after_path)
    before_attrs = l4_vram_probe.attr_rows(before_data)
    after_attrs = l4_vram_probe.attr_rows(after_data)

    attr_rows_out = []
    for r in rows_touched:
        rel_row = (r - origin_row0) if origin_row0 is not None else r
        attr_rows_out.append(
            {
                "rel_row": rel_row,
                "before": before_attrs[r].hex().upper(),
                "after": after_attrs[r].hex().upper(),
            }
        )
    attr_rows_out.sort(key=lambda e: e["rel_row"])

    record = {
        "cells": cells,
        "nonblank_count": len(nonblanks),
        "attr_rows": attr_rows_out,
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
    print(
        "\t".join(
            [
                str(len(record["cells"])),
                str(record["nonblank_count"]),
                str(len(record["attr_rows"])),
                sha,
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
