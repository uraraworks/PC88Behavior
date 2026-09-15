#!/usr/bin/env python3
"""
make_error_table.py — docs/spec/l4-basic.md 第6.1節のエラーメッセージ表
（マニュアルのエラー番号・文言、資料の記載として仕様書に既に転記済み）から
src/l4_basic/errors.tsv と src/l4_basic/errors.asm を機械生成する。

第6.1節は「開発者判断で採る」と明記済みの一覧であり、この版で使うのは
構文の誤り（番号2, "Syntax error"）の文言だけだが、指示どおり一覧全体を
表にしてよいのでそうする。番号に "?" が付く項（60?）は資料自身が確信を
持てないと注記している項なので、この版の表からは除外する
（l4-basic.md 第6.1節の指示どおり）。

読むのは docs/spec/l4-basic.md（仕様書側）だけであり、マニュアル本文
（refs/manual.txt 等）は読まない。CLAUDE.md「情報の流れ」（仕様書から
右側だけを見る）に従う。

出力:
  src/l4_basic/errors.tsv  : number<TAB>message（機械可読）
  src/l4_basic/errors.asm  : 全項目のテーブル＋SYNTAX_ERROR_MSGラベル
                             （番号2の項を直接指す独立ラベル）

使い方:
  src/l4_basic/make_error_table.py
  src/l4_basic/make_error_table.py --spec <path> --tsv <path> --asm <path>
"""
from __future__ import annotations

import argparse
import os
import re

TABLE_HEADER = "| 番号 | メッセージ |"
ROW_RE = re.compile(r"^\|\s*(\S+)\s*\|\s*(.+?)\s*\|$")
SYNTAX_ERROR_NUMBER = "2"
SYNTAX_ERROR_TEXT = "Syntax error"


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def extract_rows(spec_text: str) -> list[tuple[str, str]]:
    lines = spec_text.splitlines()
    try:
        header_idx = lines.index(TABLE_HEADER)
    except ValueError as exc:
        raise SystemExit(f"仕様書にエラー表の見出し行が無い: {TABLE_HEADER!r}") from exc

    rows: list[tuple[str, str]] = []
    i = header_idx + 1
    # 見出しの次はセパレータ行（|---|---|）のはず。
    if i >= len(lines) or not re.match(r"^\|[-\s|]+\|$", lines[i]):
        raise SystemExit("エラー表のセパレータ行が見つからない（表の形式が変わった？）")
    i += 1
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        m = ROW_RE.match(line)
        if not m:
            raise SystemExit(f"エラー表の行が読めない: {line!r}")
        number, message = m.group(1), m.group(2)
        if "?" in number:
            i += 1
            continue  # 資料自身が確信を持てないと注記した項は除外（第6.1節の指示）
        rows.append((number, message))
        i += 1
    if not rows:
        raise SystemExit("エラー表の行を1つも抽出できなかった")
    return rows


def asm_escape(text: str) -> str:
    # エラーメッセージ本体は資料6.1節の抜粋どおり英字ASCIIのみ（二重引用符・
    # 制御文字は含まれない、抽出時に確認済み）。
    if '"' in text:
        raise SystemExit(f"メッセージに二重引用符が含まれ、DB文字列化できない: {text!r}")
    return text


def write_outputs(rows: list[tuple[str, str]], tsv_path: str, asm_path: str) -> None:
    with open(tsv_path, "w", encoding="utf-8") as f:
        f.write("# 生成: src/l4_basic/make_error_table.py（手で編集しない）\n")
        f.write("# 出所: docs/spec/l4-basic.md 第6.1節（開発者判断で採用したマニュアルのエラー一覧）\n")
        f.write("# 番号に'?'が付く項（資料が確信を持てないと注記）は除外済み\n")
        f.write("# 列: number<TAB>message\n")
        for number, message in rows:
            f.write(f"{number}\t{message}\n")

    syntax_hits = [m for n, m in rows if n == SYNTAX_ERROR_NUMBER]
    if len(syntax_hits) != 1:
        raise SystemExit(
            f"番号{SYNTAX_ERROR_NUMBER}の項が1つでない（{len(syntax_hits)}件）。表が変わった？"
        )
    if syntax_hits[0] != SYNTAX_ERROR_TEXT:
        raise SystemExit(
            f"番号{SYNTAX_ERROR_NUMBER}の文言が想定と違う: {syntax_hits[0]!r} (期待 {SYNTAX_ERROR_TEXT!r})"
        )

    lines: list[str] = []
    lines.append("; errors.asm — src/l4_basic/make_error_table.py が生成")
    lines.append("; 手で編集しない（再実行で再生成する）。")
    lines.append("; 出所: docs/spec/l4-basic.md 第6.1節（開発者判断で採用したマニュアルの")
    lines.append("; エラーメッセージ一覧。番号に'?'が付く項は除外済み）。")
    lines.append(";")
    lines.append("; 今回使うのは構文の誤り(SYNTAX_ERROR_MSG、番号2)の文言だけ。")
    lines.append("; 他の項目は一覧として持つのみで、この段階では未使用。")
    lines.append("")
    for number, message in rows:
        safe_num = re.sub(r"[^0-9A-Za-z]", "_", number)
        lines.append(f"ERR_MSG_{safe_num}:")
        lines.append(f'    DB "{asm_escape(message)}",0')
    lines.append("")
    lines.append("; 構文の誤り（番号2）を直接指す独立ラベル。interp.asmが参照する。")
    lines.append("SYNTAX_ERROR_MSG:")
    lines.append(f'    DB "{asm_escape(SYNTAX_ERROR_TEXT)}",0')
    lines.append("")

    with open(asm_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> int:
    root = repo_root()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", default=os.path.join(root, "docs", "spec", "l4-basic.md"))
    ap.add_argument("--tsv", default=os.path.join(root, "src", "l4_basic", "errors.tsv"))
    ap.add_argument("--asm", default=os.path.join(root, "src", "l4_basic", "errors.asm"))
    args = ap.parse_args()

    spec_text = open(args.spec, encoding="utf-8").read()
    rows = extract_rows(spec_text)
    write_outputs(rows, args.tsv, args.asm)
    print(f"エラー項目数={len(rows)} 出力: {args.tsv}, {args.asm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
