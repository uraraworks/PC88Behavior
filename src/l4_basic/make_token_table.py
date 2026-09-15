#!/usr/bin/env python3
"""
make_token_table.py — src/l4_basic/keywords.tsv からトークン番号表を機械生成する

規則の出所: docs/notes/l4-token-design.md 末尾の追記
「追記（2026-09-15、番号の振り方 — 開発者判断）」（e77ddbe。ただし語の一覧は
その後 keywords.tsv（1f99654、189語）へ置き換え済み。docs/notes/l4-token-design.md
の追記「（2026-09-15、語の一覧の出所）」を参照）。

規則:
  1. keywords.tsv の word 列（1列目）を、大文字 ASCII の辞書順（Python の
     既定の文字列比較。対象語はすべて大文字ASCIIと記号のみなので、これは
     単純なコードポイント順と一致する）に並べる。
  2. 先頭127語に 0x80〜0xFE を順に割り当てる（1バイト）。
  3. 128語目以降は 0xFF を前置し、0x80から順の2バイト目を続ける（2バイト）。
  4. '（REM の略記）や ?（PRINT の略記）のような記号1文字の省略形は、この
     表の対象outにしない（字句解析の段階で対応する語に置き換える。
     keywords.tsv 自体にもこれらの行は無い）。

このスクリプトは keywords.tsv 以外の入力を一切見ない。外部依存もゼロ
（python3 標準ライブラリのみ）。第三者が keywords.tsv とこのスクリプトだけから
同じ出力を再生成できることが自己検査の主眼になる。

出力（2つ、どちらも「手で編集しない」ヘッダ付き）:
  - src/l4_basic/tokens.tsv  : word<TAB>token（人と機械の両方が読める表）
  - src/l4_basic/tokens.asm  : 自作 main ROM の字句解析が引く表（.asm）

使い方:
  src/l4_basic/make_token_table.py
    （引数なし。リポジトリ内の固定パスを読み書きする）
  src/l4_basic/make_token_table.py --keywords <path> --tokens-tsv <path> --asm <path>
    （自己検査が別ディレクトリに書き出すためのオーバーライド）
"""

from __future__ import annotations

import argparse
import os

FIRST_RANGE_START = 0x80
FIRST_RANGE_END = 0xFE  # inclusive
FIRST_RANGE_SIZE = FIRST_RANGE_END - FIRST_RANGE_START + 1  # 127
EXT_PREFIX = 0xFF
EXT_SECOND_START = 0x80

GENERATED_NOTICE_TSV = (
    "# 生成: src/l4_basic/make_token_table.py（手で編集しない。再実行で再生成する）\n"
    "# 入力: src/l4_basic/keywords.tsv（word列のみ使用。大文字ASCII辞書順に並べ替えて番号を振る）\n"
    "# 規則: docs/notes/l4-token-design.md「追記（2026-09-15、番号の振り方 — 開発者判断）」\n"
    "# 列: word<TAB>token（1バイトは0xNN、拡張は '0xFF 0xNN' の2バイトを空白区切りで表記）\n"
)


def repo_root() -> str:
    # このファイルは <repo>/src/l4_basic/make_token_table.py に置かれている前提。
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def read_words(keywords_path: str) -> list[str]:
    words: list[str] = []
    with open(keywords_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if not cols or not cols[0]:
                continue
            words.append(cols[0])
    return words


def assign_tokens(words: list[str]) -> list[tuple[str, tuple[int, ...]]]:
    """辞書順に並べ、規則どおりの番号（1バイトまたは2バイトのtuple）を振る。"""
    ordered = sorted(words)
    out: list[tuple[str, tuple[int, ...]]] = []
    for i, word in enumerate(ordered):
        if i < FIRST_RANGE_SIZE:
            out.append((word, (FIRST_RANGE_START + i,)))
        else:
            second = EXT_SECOND_START + (i - FIRST_RANGE_SIZE)
            if second > 0xFF:
                raise ValueError(
                    f"拡張範囲の2バイト目が0xFFを超えた（語数が多すぎる）: word={word!r} second=0x{second:02X}"
                )
            out.append((word, (EXT_PREFIX, second)))
    return out


def format_token(token: tuple[int, ...]) -> str:
    return " ".join(f"0x{b:02X}" for b in token)


def write_tokens_tsv(entries: list[tuple[str, tuple[int, ...]]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(GENERATED_NOTICE_TSV)
        for word, token in entries:
            f.write(f"{word}\t{format_token(token)}\n")


def asm_escape(word: str) -> str:
    # z80 アセンブラの文字列リテラルとして安全な形にする。対象語は
    # keywords.tsv の表記どおり（$ @ ( ) / . = # - を含みうる）で、
    # 二重引用符自体は語に含まれない（keywords.tsv に無いことを確認済み）。
    return word


def write_asm(entries: list[tuple[str, tuple[int, ...]]], path: str) -> None:
    # 引き方の並び順: 最長一致のため「語の長さの降順」。同じ長さの語同士は
    # 番号表と同じ「大文字ASCII辞書順」（昇順）にして、生成のたびに順序が
    # 変わらないようにする（安定ソートを2段掛けすれば実現できる）。
    # 理由: たとえば "ON" と "ONERRORGOTO" のように、短い語が長い語の
    # 先頭に一致してしまう組がkeywords.tsvに実在する
    # （ON...GOSUB/ON...GOTO, ONERRORGOTO, ONHELPGOSUB, ONKEYGOSUB,
    #   ONSTOPGOSUB, ONTIME$GOSUB）。長い語を先に試さないと、短い語で
    # 早期に一致してしまい、後続の文字を読み違える。
    by_dict_order = sorted(entries, key=lambda e: e[0])
    by_length_desc = sorted(by_dict_order, key=lambda e: -len(e[0]))

    lines: list[str] = []
    lines.append("; L4_BASIC トークン表 — src/l4_basic/make_token_table.py が生成")
    lines.append("; 手で編集しない（再実行で再生成する）。")
    lines.append("; 入力: src/l4_basic/keywords.tsv（189語）。番号の規則は")
    lines.append("; docs/notes/l4-token-design.md「追記（2026-09-15、番号の振り方）」。")
    lines.append(";")
    lines.append("; 引き方の並び順: 語の長さの降順（最長一致）。同じ長さは")
    lines.append("; 大文字ASCII辞書順（昇順）で安定させてある。短い語が長い語の")
    lines.append("; 先頭に一致する組（例: ON と ONERRORGOTO 系）があるため、")
    lines.append("; 字句解析はこの並び順のまま先頭から順に試すこと。")
    lines.append(";")
    lines.append("; 各エントリ: db 語長, 語（ASCII文字列。$ @ 等の記号を含む）,")
    lines.append(";            db トークン（1バイトまたは 0xFF+2バイト目の2バイト）")
    lines.append("; 表の終端は 語長0 の番兵行。")
    lines.append("")
    lines.append("L4_TOKEN_TABLE:")
    for word, token in by_length_desc:
        token_str = ", ".join(f"0x{b:02X}" for b in token)
        lines.append(f'    db {len(word)}, "{asm_escape(word)}", {token_str}')
    lines.append("    db 0        ; 番兵（語長0＝表の終端）")
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> int:
    root = repo_root()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--keywords",
        default=os.path.join(root, "src", "l4_basic", "keywords.tsv"),
    )
    ap.add_argument(
        "--tokens-tsv",
        default=os.path.join(root, "src", "l4_basic", "tokens.tsv"),
    )
    ap.add_argument(
        "--asm",
        default=os.path.join(root, "src", "l4_basic", "tokens.asm"),
    )
    args = ap.parse_args()

    words = read_words(args.keywords)
    if len(set(words)) != len(words):
        seen = set()
        dups = []
        for w in words:
            if w in seen:
                dups.append(w)
            seen.add(w)
        raise SystemExit(f"keywords.tsv に重複語がある: {dups}")

    entries = assign_tokens(words)
    write_tokens_tsv(entries, args.tokens_tsv)
    write_asm(entries, args.asm)

    n_total = len(entries)
    n_first = min(n_total, FIRST_RANGE_SIZE)
    n_ext = max(0, n_total - FIRST_RANGE_SIZE)
    print(
        f"語数={n_total} 1バイト(0x80-0xFE)={n_first} 拡張(0xFF+)={n_ext} "
        f"出力: {args.tokens_tsv}, {args.asm}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
