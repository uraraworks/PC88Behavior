#!/usr/bin/env python3
"""PC88Behavior: l4-s1g 事前登録
（docs/notes/l4-s1g-screen-editor-return-preregistration.md）向け —
RETURN再読込の腕が出しうる数値出力の候補署名を、測定前に機械計算する。

l4-basic.md 第2節（整数の書式: 符号スペース1桁+数字+後置スペース1）の
規則から、正の整数の出力行のバイト列を組み立て、
tools/l4_s1f_window_probe.py の window_signature() と同じ正規化
（末尾の0x20を除いてSHA-256、先頭の空白は残す）でハッシュ化する。

**これはq88measureを一切呼ばない。実測とは独立に、自分で決めた仮説の
値（12・42・4・423など、本ノートの腕が打つ/生じると想定する数値）から
機械的に導いた候補であり、公式ROMの画面を読んで作ったものではない**
（CLAUDE.md 禁止事項7の対象外。l4-c2/l4-s1fの候補生成と同じ位置づけ）。

出してよいもの（これ以外は出さない）:
  1. 候補名・対応する数値（自分で選んだ仮説値であり画面本文ではない）
  2. 正規化後バイト長・SHA-256
故障注入用に、1バイトだけ違う値でも候補を用意する（`_fault_dummy_of_*`）。
"""
from __future__ import annotations

import argparse
import hashlib
import json

COLS = 80


def positive_int_output_bytes(value: int) -> bytes:
    """l4-basic.md 第2節: 正の整数は符号スペース1桁+数字+後置スペース1。"""
    if value < 0:
        raise ValueError("この器具は正の整数のみを対象とする(本ノートの腕はすべて正)")
    digits = str(value).encode("ascii")
    row = bytearray(b"\x20" * COLS)
    row[0:1] = b"\x20"  # 符号スペース(正の数は空白)
    row[1:1 + len(digits)] = digits
    row[1 + len(digits):1 + len(digits) + 1] = b"\x20"  # 後置スペース1
    return bytes(row)


def row_signature(row: bytes) -> dict:
    norm = row.rstrip(b"\x20")
    return {
        "nonblank_count": sum(1 for b in row if b != 0x20),
        "normalized_length": len(norm),
        "row_sha256": hashlib.sha256(norm).hexdigest(),
    }


def build_table() -> dict:
    # 本ノートの腕が生じさせうる数値(自分で打つ・上書きの結果として想定する値)。
    # 根拠は事前登録本体「候補」節の各腕の設計。
    values = {
        "print_12": 12,   # buffer_wins / 未編集(陽性対照PC1) / 上下移動の再実行(U1)
        "print_42": 42,   # screen_wins(行全体を読み直す)
        "print_4": 4,     # from_start_to_cursor(カーソルまでを読む)
        "print_423": 423, # T群: 行末に古い文字が残ったまま行全体を読む場合
        "print_34": 34,   # U群: 2本目の直接モード文(位置確認用)
    }
    table = {}
    for name, v in values.items():
        row = positive_int_output_bytes(v)
        sig = row_signature(row)
        table[name] = {"value": v, **sig}
        # 故障注入用ダミー: 数字1桁を+1しただけの別の値(1バイトだけ違う想定)
        dummy_row = positive_int_output_bytes(v + 1)
        table[f"_fault_dummy_of_{name}"] = {"value": v + 1, **row_signature(dummy_row)}
    return table


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output")
    ap.add_argument("--check", action="store_true",
                     help="出力を書かず既存ファイルと一致するかだけ確認する(再現性確認用)")
    args = ap.parse_args()

    table = build_table()
    text = json.dumps(table, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        assert args.output, "--checkには--outputが要る"
        with open(args.output, encoding="utf-8") as f:
            existing = f.read()
        if existing != text:
            print("[l4_s1g_candidates] NG: 再生成した候補表が既存ファイルと不一致")
            return 1
        print(f"[l4_s1g_candidates] OK: {len(table)}件 (既存ファイルと一致)")
        return 0

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[l4_s1g_candidates] {len(table)}件 -> {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
