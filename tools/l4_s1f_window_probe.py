#!/usr/bin/env python3
"""PC88Behavior: l4-s1f 追補向け — 写しから列範囲(window)限定の署名を作る。

docs/notes/l4-s1f-screen-editor-preregistration-addendum.md が定める
window(idx0=col_start-1 .. idx7=col_start+6、既定8バイト)を、実際の
--vram-dump写しから切り出してSHA-256だけを返す。tools/l4_vram_probe.py
の row_signature() と同じ正規化(末尾0x20を除いてSHA-256)を、
行全体(80バイト)ではなくwindowだけに適用する点だけが違う。

出してよいもの(これ以外は出さない。CLAUDE.md禁止事項7):
  1. row0・col_start・window_len(位置情報、ハードウェア設定値相当)
  2. window内の非空白セル件数
  3. 正規化後バイト長
  4. 正規化後バイト列のSHA-256

文字コードの並びそのものは一切出さない。
"""
from __future__ import annotations

import argparse
import hashlib
import sys

BASE = 0xF3C8
ROWS = 25
COLS = 80
STRIDE = 120


def load(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def char_row(data: bytes, row0: int) -> bytes:
    off = row0 * STRIDE
    return data[off:off + COLS]


def window_signature(path: str, row0: int, col_start: int, window_len: int) -> dict:
    data = load(path)
    row = char_row(data, row0)
    lo = col_start - 1
    hi = lo + window_len
    lo_clamped = max(0, lo)
    hi_clamped = min(COLS, hi)
    w = bytes(row[lo_clamped:hi_clamped])
    norm = w.rstrip(b"\x20")
    return {
        "row0": row0,
        "col_start": col_start,
        "window": [lo, hi],
        "nonblank_count": sum(1 for b in w if b != 0x20),
        "normalized_length": len(norm),
        "row_sha256": hashlib.sha256(norm).hexdigest(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vram-dump", required=True)
    ap.add_argument("--row0", type=int, required=True)
    ap.add_argument("--col-start", type=int, required=True)
    ap.add_argument("--window-len", type=int, default=8)
    args = ap.parse_args()

    sig = window_signature(args.vram_dump, args.row0, args.col_start, args.window_len)
    for k, v in sig.items():
        print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
