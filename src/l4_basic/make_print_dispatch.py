#!/usr/bin/env python3
"""
make_print_dispatch.py — src/l4_basic/tokens.tsv から PRINT の語形と
トークン番号を機械抽出し、src/l4_basic/print_dispatch.asm を生成する。

## 背景（なぜ分割抽出が要るか）

tokens.tsv の word 列は、語の一覧の出所である keywords.tsv がマニュアル
目次から抽出したそのままの見出し文字列であり（docs/notes/l4-keywords-extraction.md）、
PRINT は単独では載っておらず、"PRINT/LPRINT"（PRINT文とLPRINT文をまとめた
1つの目次見出し）という1行になっている。実際に打鍵される "PRINT" という
5文字だけを取り出すため、word列を '/' で分割し、分割後の候補の中から
大文字ASCIIで完全一致するものを探す。

この分割規則（'/'を区切りとして複数語の同義見出しを分ける）はこのスクリプト
固有の実装判断であり、tokens.tsv/keywords.tsv の生成規則（既存の
make_token_table.py・l4-token-design.md）そのものではない。理由は
docs/notes/l4-design.md に書けないこの版の実装ノート
（この生成物のヘッダコメントと報告に残す）。

このスクリプトは tokens.tsv 以外を読まない。tokens.tsv・tokens.asm・
keywords.tsv・make_token_table.py 自体は変更しない（新規ファイルの追加のみ）。

出力: src/l4_basic/print_dispatch.asm
  TOK_PRINT_LEN   EQU <PRINTの文字数=5>
  TOK_PRINT_TEXT: DB "PRINT"
  TOK_PRINT_TOKEN_LEN EQU <1 or 2>
  TOK_PRINT_TOKEN: DB <トークンバイト列>

使い方:
  src/l4_basic/make_print_dispatch.py
  src/l4_basic/make_print_dispatch.py --tokens-tsv <path> --asm <path>
"""
from __future__ import annotations

import argparse
import os

TARGET_WORD = "PRINT"


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def read_tokens(tokens_tsv_path: str) -> list[tuple[str, list[int]]]:
    rows: list[tuple[str, list[int]]] = []
    with open(tokens_tsv_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) != 2:
                raise SystemExit(f"tokens.tsvの行の列数が2でない: {line!r}")
            word, token_str = cols
            token_bytes = [int(b, 16) for b in token_str.split(" ")]
            rows.append((word, token_bytes))
    return rows


def find_print_token(rows: list[tuple[str, list[int]]]) -> list[int]:
    """word列を'/'で分割し、候補の中に完全一致するTARGET_WORDを含む行を探す。

    複数行がヒットしたら曖昧（tokens.tsvが変わった証拠）としてエラーにする。
    """
    hits: list[tuple[str, list[int]]] = []
    for word, token_bytes in rows:
        parts = word.split("/")
        if TARGET_WORD in parts:
            hits.append((word, token_bytes))
    if len(hits) == 0:
        raise SystemExit(
            f"tokens.tsvに '{TARGET_WORD}' を含む語形の行が無い（tokens.tsvが変わった？）"
        )
    if len(hits) > 1:
        raise SystemExit(
            f"tokens.tsvに '{TARGET_WORD}' を含む語形の行が複数ある（曖昧）: {hits}"
        )
    return hits[0][1]


def write_asm(token_bytes: list[int], path: str) -> None:
    lines: list[str] = []
    lines.append("; print_dispatch.asm — src/l4_basic/make_print_dispatch.py が生成")
    lines.append("; 手で編集しない（再実行で再生成する）。")
    lines.append("; 入力: src/l4_basic/tokens.tsv。PRINTの語形とトークン番号は")
    lines.append(f'; word列を"/"で分割した候補から "{TARGET_WORD}" に完全一致する行を')
    lines.append("; 機械的に探して取り出した（make_print_dispatch.py 参照）。")
    lines.append(";")
    lines.append("; 用途: 直接モードの行頭キーワード照合（interp.asm TRY_MATCH_PRINT）。")
    lines.append("; '?'の代替表記は l4-token-design.md の追記により字句解析側で")
    lines.append("; 別扱いする（この表の対象外）。")
    lines.append("")
    lines.append(f"TOK_PRINT_LEN EQU {len(TARGET_WORD)}")
    lines.append("TOK_PRINT_TEXT:")
    lines.append(f'    DB "{TARGET_WORD}"')
    lines.append(f"TOK_PRINT_TOKEN_LEN EQU {len(token_bytes)}")
    lines.append("TOK_PRINT_TOKEN:")
    lines.append("    DB " + ", ".join(f"0x{b:02X}" for b in token_bytes))
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> int:
    root = repo_root()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tokens-tsv", default=os.path.join(root, "src", "l4_basic", "tokens.tsv"))
    ap.add_argument("--asm", default=os.path.join(root, "src", "l4_basic", "print_dispatch.asm"))
    args = ap.parse_args()

    rows = read_tokens(args.tokens_tsv)
    token_bytes = find_print_token(rows)
    write_asm(token_bytes, args.asm)
    print(f"PRINT語形='{TARGET_WORD}' トークン={['0x%02X' % b for b in token_bytes]} 出力: {args.asm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
