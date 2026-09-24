#!/usr/bin/env python3
"""
check_m6fc_markers.py — q88measure レポートの画面節から目印だけをJSONで出す

事前登録: docs/notes/m6f-c-blank-disk-acceptance-preregistration.md 第3節。

画面本文は禁止事項7（CLAUDE.md）の対象なので、標準出力・標準エラーの
どちらにも1文字も出さない。画面節の読み方は tools/check_l3_screen_output.py
の read_screen() をそのまま import して使う（見出し・行形式の扱いを重複
実装しない）。

出す情報は次の3種類だけ:
  - markers: `ZQ`+英字2文字（+空白区切りの数値列）に完全一致した行
    （行番号除く本文を右トリムしたもの）を、行順に
    {"row": 行番号, "tag": タグ小文字, "numbers": [整数...]} で列挙する。
  - malformed_marker_rows: `ZQ`で始まるが上の形式に一致しない行の数
    （本文は出さない）。
  - name_counts: --name で指定した名前ごとの、画面全体での出現回数
    （大文字小文字を区別、重なりなしの部分文字列数）。

終了コード: 0=正常。画面節が無い・形式不正・引数不正は2（本文は出さない）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_l3_screen_output import ScreenError, read_screen  # noqa: E402

MARKER_RE = re.compile(r"^ZQ([A-Za-z]{2})((?:\s+-?\d+)*)$")
NAME_RE = re.compile(r"^[A-Za-z0-9]+$")

# selftest専用の欠陥注入スイッチ。tools/check_m6fc_markers_selftest.sh が
# sedでTrueに書き換えた変異体を走らせ、「本文が漏れたら検査がNGになる」
# ことを確認する（陰性対照）。本番は常にFalseのままにする。
DEBUG_LEAK_MALFORMED_FOR_SELFTEST = False


class MarkerError(ValueError):
    """引数または画面節が不正。"""


def parse_markers(rows: list[tuple[int, str]]) -> tuple[list[dict], int]:
    markers: list[dict] = []
    malformed = 0
    for row, body in rows:
        stripped = body.rstrip()
        if not stripped.startswith("ZQ"):
            continue
        match = MARKER_RE.match(stripped)
        if not match:
            malformed += 1
            if DEBUG_LEAK_MALFORMED_FOR_SELFTEST:
                print(f"debug_leak_row={row} body={stripped}", file=sys.stderr)
            continue
        tag = match.group(1).lower()
        numbers_field = match.group(2).split()
        numbers = [int(token) for token in numbers_field]
        markers.append({"row": row, "tag": tag, "numbers": numbers})
    return markers, malformed


def count_names(rows: list[tuple[int, str]], names: list[str]) -> dict[str, int]:
    joined = "\n".join(body for _, body in rows)
    counts: dict[str, int] = {}
    for name in names:
        counts[name] = joined.count(name)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        help="出現回数を数える名前（英数字のみ、複数指定可）",
    )
    args = parser.parse_args()

    for name in args.name:
        if not name or not NAME_RE.match(name):
            print("引数エラー", file=sys.stderr)
            return 2

    try:
        rows = read_screen(args.report)
    except (OSError, UnicodeError, ScreenError):
        print("画面節エラー", file=sys.stderr)
        return 2

    try:
        markers, malformed = parse_markers(rows)
    except MarkerError:
        print("目印形式エラー", file=sys.stderr)
        return 2

    name_counts = count_names(rows, args.name)

    output = {
        "markers": markers,
        "malformed_marker_rows": malformed,
        "name_counts": name_counts,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
