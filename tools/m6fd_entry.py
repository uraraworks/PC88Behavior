#!/usr/bin/env python3
"""m6fd_entry.py — m6f-d: 媒体からエントリの位置と9〜15バイト目を探す小道具。

事前登録 docs/notes/m6f-d-disk-rules-preregistration.md §0.1・§1 の通り、
出力してよいのは「名前欄（自分で与えた名前）と9〜15バイト目だけ」。本体の
セクタの中身・割り当て表の位置160以降は一切触らない（トラック18の割り当て表
3セクタそのものを検索対象から除くので、そもそも読まない）。

entry_fields(image, name) は測定ドライバ(tools/measure_m6fd.sh)が、結果JSONの
各run.entry_fieldsを作るために呼ぶ前提。探し方は m6f-c の find_name と同じ
（トラック18のうち割り当て表3セクタを除く全セクタを、H=0→1、R=1→16の順に
生の部分一致で走査し、最初に一致した位置を返す。エントリ境界への整列は
求めない — 事前登録の文言どおり）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from d88_read_sector import D88Error, D88Reader  # noqa: E402

HEADS = 2
SECTORS_PER_TRACK = 16
SECTOR_BASE = 1
TRACK = 18
ALLOCATION_TABLE_COORDS = frozenset({(18, 1, 14), (18, 1, 15), (18, 1, 16)})
SEARCH_COORDS = tuple(
    (TRACK, h, r)
    for h in range(HEADS)
    for r in range(SECTOR_BASE, SECTOR_BASE + SECTORS_PER_TRACK)
    if (TRACK, h, r) not in ALLOCATION_TABLE_COORDS
)
NAME_FIELD_LENGTH = 9
FIELD_OFFSETS = (9, 10, 11, 12, 13, 14, 15)  # 0始まり。9〜15バイト目


class InputError(ValueError):
    pass


def entry_fields(image: bytes, name: bytes) -> dict[str, Any] | None:
    """トラック18(割り当て表3セクタを除く)から name を最初に含むセクタ・位置を探し、
    {"pos": {"c","h","r","offset"}, "bytes9_15": [7整数]} を返す。無ければ None。"""
    if not (1 <= len(name) <= NAME_FIELD_LENGTH):
        raise InputError("name の長さは1〜9バイトで指定すること")
    try:
        reader = D88Reader(image)
    except D88Error as exc:
        raise InputError(f"媒体読み取り: {exc}") from None
    for coord in SEARCH_COORDS:
        try:
            payload = reader.read_sector(*coord)
        except D88Error:
            continue
        idx = payload.find(name)
        if idx < 0:
            continue
        bytes9_15 = [payload[idx + j] for j in FIELD_OFFSETS if idx + j < len(payload)]
        if len(bytes9_15) != len(FIELD_OFFSETS):
            continue  # 名前欄の一致位置が末尾すぎて9〜15バイト目が取れない場合は無視
        return {
            "pos": {"c": coord[0], "h": coord[1], "r": coord[2], "offset": idx},
            "bytes9_15": bytes9_15,
        }
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=pathlib.Path)
    ap.add_argument("--name", required=True, help="探す名前(ASCII、1〜9バイト)")
    args = ap.parse_args()
    try:
        image = args.image.read_bytes()
        result = entry_fields(image, args.name.encode("ascii"))
    except (OSError, UnicodeEncodeError, InputError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
