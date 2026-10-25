#!/usr/bin/env python3
"""自作D88媒体の (C=0,H=0,R=1) のデータ部だけを1バイト値で埋めた複製を作る。

使い方: python3 tools/b4_fill_boot_sector.py IN.d88 OUT.d88 --fill 0xC9

検査（満たさなければ非0で終了しOUTを作らない）:
  (0,0,1) のセクタがちょうど1個、データ長256、OUTが未存在。
  書き出し後、IN と比べてそのセクタのデータ256バイト以外が不変であることを自分で検査する。
標準出力には座標・埋めた値・変化したバイト数だけを出す（媒体のバイト列は出さない）。
"""
from __future__ import annotations

import argparse
import pathlib
import struct
import sys

HEADER = 32
TRACKS = 164
BODY_START = HEADER + TRACKS * 4
COORD = (0, 0, 1)


def find_sectors(image: bytes) -> list[tuple[tuple[int, int, int], int, int]]:
    """(座標, データ開始, データ長) の一覧。ヘッダのサイズ欄に従い先頭から順に歩く。"""
    if len(image) < BODY_START or struct.unpack_from("<I", image, 28)[0] != len(image):
        raise ValueError("D88のサイズ欄が不正")
    out = []
    pos = BODY_START
    while pos < len(image):
        if pos + 16 > len(image):
            raise ValueError("セクタヘッダが途中で切れている")
        c, h, r = image[pos], image[pos + 1], image[pos + 2]
        size = struct.unpack_from("<H", image, pos + 14)[0]
        if pos + 16 + size > len(image):
            raise ValueError("セクタデータが範囲外")
        out.append(((c, h, r), pos + 16, size))
        pos += 16 + size
    return out


def fill_boot(image: bytes, value: int) -> tuple[bytes, int]:
    hits = [s for s in find_sectors(image) if s[0] == COORD]
    if len(hits) != 1:
        raise ValueError(f"(0,0,1) のセクタが{len(hits)}個（ちょうど1個が必要）")
    _, start, size = hits[0]
    if size != 256:
        raise ValueError(f"(0,0,1) のデータ長が{size}（256が必要）")
    out = bytearray(image)
    out[start:start + 256] = bytes([value]) * 256
    out = bytes(out)
    diff = [i for i in range(len(image)) if image[i] != out[i]]
    if any(not (start <= i < start + 256) for i in diff):
        raise ValueError("対象外のバイトが変化した")
    return out, len(diff)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=pathlib.Path)
    ap.add_argument("output", type=pathlib.Path)
    ap.add_argument("--fill", required=True, type=lambda s: int(s, 0))
    a = ap.parse_args()
    if not 0 <= a.fill <= 0xFF:
        print("エラー: --fill は0〜255", file=sys.stderr)
        return 2
    if a.output.exists():
        print("エラー: OUTが既に存在する", file=sys.stderr)
        return 2
    try:
        src = a.input.read_bytes()
        out, changed = fill_boot(src, a.fill)
        a.output.write_bytes(out)
        back = a.output.read_bytes()
        diff = [i for i in range(len(src)) if src[i] != back[i]]
        _, start, _ = [s for s in find_sectors(src) if s[0] == COORD][0]
        if len(back) != len(src) or len(diff) != changed or any(not (start <= i < start + 256) for i in diff):
            raise ValueError("書き出し後の検査に失敗")
    except (ValueError, OSError) as e:
        if a.output.exists():
            a.output.unlink()
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    print(f"座標=(0,0,1) 値=0x{a.fill:02X} 変化バイト数={changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
