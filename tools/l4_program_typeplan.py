#!/usr/bin/env python3
"""PC88Behavior: l4-c5 代表プログラム集 — 打鍵計画の組み立て道具。

事前登録 `docs/notes/l4-c5-representative-programs-conformance-scene-
preregistration.md`（`2837926`）「腕」節・「P8（INPUT）の打鍵タイミング」
節どおり、`tests/programs/*.bas` の1本を読み、`new` → 各行 → `run` の
打鍵文字列と、`--vram-dump`を置くべきフレーム番号を組み立てる。

## フレームの決め方（全腕共通）

1文字あたり `hold+gap=8` フレーム（`l4-s5a` 以来の段階5の前例どおり）。
`type_at` の基準は `700`（起動settle `--type-at 300 --type '\n'` の後）。

- `prefix` = `"new\n"` + プログラムの各行を `\n` 区切りで連結したもの +
  `"\n"`（＝`run` を打つ直前までの打鍵文字列）
- `run_start_frame` = `700 + 8 * len(prefix)`
  （`run` の最初の文字 `r` が打鍵される瞬間のフレーム。ここより前に
  `run` は一切打たれていないため、事前登録の記録器
  （`tools/l4_program_conform_record.py`）が要求する
  「`origin_row` = 変化した行のうち最小のrow0（=`run`を打った行）」を
  満たすには、この`run_start_frame`を「写し(前)」に使う）
- `full` = `prefix` + `"run\n"`
- `line_end_full` = `700 + 8 * len(full)`
- `dump_final` = `line_end_full + 300`
- `run_total_frames` = `dump_final + 200`

P8（`INPUT`を含む）だけは、事前登録の「P8（INPUT）の打鍵タイミング」
節の式をそのまま使う（`l4-s5e` のE1・E2と同じ考え方）。`prog`（`new`+
各行+`run`）は`full`と同一。

## 使い方

```
python3 tools/l4_program_typeplan.py --bas tests/programs/p01_kuku.bas
python3 tools/l4_program_typeplan.py --bas tests/programs/p08_input_calc.bas --input 5,3
```

出力はJSON 1行（安全な計画情報のみ。画面本文・実行結果は含まない）。
`--type`にそのまま渡せる打鍵文字列も含む（自分で書いた`tests/programs/`
のソースそのものであり、公式ROM由来のデータではないため、禁止事項7
（画面本文）の対象外——打つ前の入力そのものであって、実行結果の画面
ではない）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import l4_vram_probe  # noqa: E402

TYPE_AT_BASE = 700
FRAMES_PER_CHAR = 8
SETTLE_TYPE_AT = 300


def read_program_lines(bas_path: str) -> "list[str]":
    """`.bas`ファイルを読み、空行を除いた各行(改行なし)を返す。"""
    lines: "list[str]" = []
    with open(bas_path, "r", encoding="ascii") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if line.strip() == "":
                continue
            lines.append(line)
    return lines


def build_strings(lines: "list[str]") -> "tuple[str, str]":
    """(prefix, full) を返す。prefix は `run` を打つ直前まで、full は
    `run\n` まで含む。"""
    prefix = "new\n" + "\n".join(lines) + "\n"
    full = prefix + "run\n"
    return prefix, full


def frame_plan(lines: "list[str]") -> dict:
    """INPUTを含まない腕(P1〜P7)の打鍵計画。"""
    prefix, full = build_strings(lines)
    run_start_frame = TYPE_AT_BASE + FRAMES_PER_CHAR * len(prefix)
    line_end_full = TYPE_AT_BASE + FRAMES_PER_CHAR * len(full)
    dump_final = line_end_full + 300
    run_total_frames = dump_final + 200
    return {
        "num_lines": len(lines),
        "prefix_char_count": len(prefix),
        "full_char_count": len(full),
        "type_string": full,
        "settle_type_at": SETTLE_TYPE_AT,
        "type_at": TYPE_AT_BASE,
        "run_start_frame": run_start_frame,
        "line_end_full": line_end_full,
        "dump_before_frame": run_start_frame,
        "dump_after_frame": dump_final,
        "run_total_frames": run_total_frames,
    }


def input_frame_plan(lines: "list[str]", input_value: str) -> dict:
    """INPUTを含む腕(P8)の打鍵計画。事前登録「P8（INPUT）の打鍵タイミング」
    節の式をそのまま使う。"""
    prefix, full = build_strings(lines)
    run_start_frame = TYPE_AT_BASE + FRAMES_PER_CHAR * len(prefix)

    n1 = len(full)
    line_end1 = TYPE_AT_BASE + FRAMES_PER_CHAR * n1
    dump1 = line_end1 + 300
    type_at2 = dump1
    val = input_value + "\n"
    n2 = len(val)
    line_end2 = type_at2 + FRAMES_PER_CHAR * n2
    dump2 = line_end2 + 300
    run2 = dump2 + 200

    return {
        "num_lines": len(lines),
        "prefix_char_count": len(prefix),
        "full_char_count": n1,
        "type_string": full,
        "settle_type_at": SETTLE_TYPE_AT,
        "type_at": TYPE_AT_BASE,
        "run_start_frame": run_start_frame,
        # G9(打鍵の到達確認)には run_start_frame の写しを使う(runより前)。
        "dump_before_frame": run_start_frame,
        "line_end1": line_end1,
        "dump_prompt_frame": dump1,
        "type_at2": type_at2,
        "input_type_string": val,
        "input_char_count": n2,
        "line_end2": line_end2,
        "dump_final_frame": dump2,
        "run_total_frames": run2,
    }


def check_keystroke_arrival(
    dump_path: str, expected_line_count: int, exclude_rows: "set[int] | None" = None
) -> dict:
    """G9(打鍵の到達確認)。`run`を打つ直前の写し(dump_before_frame)を
    `--nonblank-summary-rows`で調べ、非空白セルを含む行数を数える。
    事前登録どおり、比較するのは「行数」だけ(文字コードは見ない)。

    非空白行数の期待値は `expected_line_count + 2`
    （`new`自身の行1つ + `new`直後の`Ok`行1つ + プログラムの行数ぶん）。
    この+2は、l4-s5a〜l4-s5gの公式ROM測定で一貫して観測された「`new`の
    直後に`Ok`が現れ、以後の行入力は追加のOk無しで受け付けられる」という
    構造に基づく前提であり、想定が崩れていれば不一致として検出される
    （黙って一致扱いにはしない）。

    バナー行(0-5)・最下行(19、ファンクションキー表示行)は除く。
    """
    if exclude_rows is None:
        exclude_rows = {0, 1, 2, 3, 4, 5, 19}
    rows = [r for r in range(l4_vram_probe.ROWS) if r not in exclude_rows]
    summary = l4_vram_probe.nonblank_char_summary(dump_path, rows)
    nonblank_rows = [e for e in summary["nonblank_summary"] if e["nonblank_count"] > 0]
    actual = len(nonblank_rows)
    expected = expected_line_count + 2
    return {
        "expected_nonblank_row_count": expected,
        "actual_nonblank_row_count": actual,
        "arrived": actual == expected,
    }


def check_keystroke_arrival_by_list(before_path: str, after_path: str, expected_line_count: int) -> dict:
    """G9の任意の二重確認(事前登録どおり「使えるなら」)。`list`を打った
    結果を`tools/l4_list_classify.py`（`d330dd2`）で分類し、`list_line`
    に分類された行数がプログラムの行数と一致するかを見る。自作ROM側の
    プログラムモードがまだ`LIST`を実装していない段階では、この関数は
    使わず、`check_keystroke_arrival`の件数確認だけで足りるとする
    （事前登録どおり）。"""
    import l4_list_classify

    record = l4_list_classify.classify(before_path, after_path)
    if record.get("classification") != "ok":
        return {"list_checked": False, "reason": record.get("classification")}
    list_line_count = sum(1 for l in record["lines"] if l["classification"] == "list_line")
    return {
        "list_checked": True,
        "expected_line_count": expected_line_count,
        "actual_list_line_count": list_line_count,
        "arrived": list_line_count == expected_line_count,
    }


def check_output_fits_screen(ok_relative_row: int, max_screen_rows: int = 20) -> dict:
    """G10(出力が画面に収まっていること)。`origin_row`(`run`を打った行)
    から`ok_row`(`Ok`の行)までの行数(=ok_relative_row+1)が、画面の行数
    (既定表示20行、`docs/spec/l3-main.md`第5節)を超えていないかを見る。
    """
    span = ok_relative_row + 1
    return {
        "span_rows": span,
        "max_screen_rows": max_screen_rows,
        "fits": span <= max_screen_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", required=True, help="tests/programs/*.bas のパス")
    ap.add_argument("--input", default=None, help="INPUTに打つ値(例: 5,3)。指定したP8向けの計画を返す")
    args = ap.parse_args()

    lines = read_program_lines(args.bas)
    if args.input is not None:
        plan = input_frame_plan(lines, args.input)
    else:
        plan = frame_plan(lines)
    plan["bas_path"] = args.bas
    print(json.dumps(plan, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
