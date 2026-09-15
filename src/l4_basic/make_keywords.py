#!/usr/bin/env python3
"""
make_keywords.py — src/l4_basic/reserved_words_transcript.tsv から
src/l4_basic/keywords.tsv（v2）を機械生成する。

## 背景（なぜ v1 から作り直したか）

v1（`tools/l4_extract_keywords.py`、189語）はマニュアルの**目次の見出し**を
機械抽出したものだったが、目次見出しは命令語の一覧そのものではなかった
（`docs/notes/l4-keywords-extraction.md` 追記「v2 — 資料1への切り替え」参照）。
正しい出所は資料1「N88-BASIC/N88-日本語BASICの予約語」（資-1、PDF 377頁）で、
この語の一覧は2人が独立に画像から書き起こし（A本・B本）、突き合わせて
A本（190語）を正とした。本スクリプトはそのA本
（`src/l4_basic/reserved_words_transcript.tsv`）だけを読む。

## このスクリプトが行う変換

1. `reserved_words_transcript.tsv` の word 列をそのまま読む
2. 末尾が `**`（footnote記号。KLEN**・KPLOAD** 等、資料1本文中でも同じ位置に
   `**` が現れるため書き起こし側のノイズではなく資料の脚注記号だが、脚注記号は
   命令語のスペリングの一部ではない）の語は `**` を取り除く。対象は
   AKCNV$**・KACNV$**・KLEN**・KPLOAD**・KPOS** の5語のみ（実行時に検出し、
   想定外の語に付いていたらエラーにする）
3. word・col・row・source の4列で `keywords.tsv` に書き出す。source列は
   固定文字列「資料1 資-1・PDF 377」（全行共通）
4. 語の重複が無いこと、190語ちょうどであることを確認する

並び順は変えない（transcript の col→row 昇順のまま。make_token_table.py が
辞書順に並べ替えるのはその後段の責務であり、ここでは踏襲元の並びを保存する）。

使い方:
  src/l4_basic/make_keywords.py
    （引数なし。リポジトリ内の固定パスを読み書きする）
  src/l4_basic/make_keywords.py --transcript <path> --out <path>
    （自己検査が別ディレクトリに書き出すためのオーバーライド）
"""
from __future__ import annotations

import argparse
import os

FOOTNOTE_SUFFIX = "**"
KNOWN_FOOTNOTE_WORDS = {
    "AKCNV$**",
    "KACNV$**",
    "KLEN**",
    "KPLOAD**",
    "KPOS**",
}
SOURCE_LABEL = "資料1 資-1・PDF 377"
EXPECTED_COUNT = 190

GENERATED_NOTICE = (
    "# N88-BASIC/N88-日本語BASIC 予約語一覧 v2（手で編集しない。再実行で再生成する）\n"
    "# 出典: 資料1「N88-BASIC/N88-日本語BASICの予約語」（資-1、PDF 377頁）\n"
    "# 2人が独立に画像から書き起こし、突き合わせた（docs/notes/l4-keywords-extraction.md）\n"
    "# 入力: src/l4_basic/reserved_words_transcript.tsv（A本、190語）\n"
    "# 生成: src/l4_basic/make_keywords.py\n"
    "# 列: word<TAB>col(段番号1-6)<TAB>row(段の中の行番号1-32)<TAB>source\n"
)


def repo_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def read_transcript(path: str) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if cols[0] == "col":
                continue  # ヘッダ行
            if len(cols) < 3:
                raise SystemExit(f"reserved_words_transcript.tsv の行の列数が足りない: {line!r}")
            col, row, word = cols[0], cols[1], cols[2]
            rows.append((col, row, word))
    return rows


def strip_footnote(word: str) -> str:
    if word.endswith(FOOTNOTE_SUFFIX):
        if word not in KNOWN_FOOTNOTE_WORDS:
            raise SystemExit(
                f"未知の脚注記号付き語: {word!r}"
                f"（既知は {sorted(KNOWN_FOOTNOTE_WORDS)} のみ。資料が変わったか書き起こしにノイズがある）"
            )
        return word[: -len(FOOTNOTE_SUFFIX)]
    return word


def build_entries(rows: list[tuple[str, str, str]]) -> list[tuple[str, str, str, str]]:
    entries: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for col, row, raw_word in rows:
        word = strip_footnote(raw_word)
        if word in seen:
            raise SystemExit(f"語が重複している: {word!r}（col={col} row={row}）")
        seen.add(word)
        entries.append((word, col, row, SOURCE_LABEL))
    if len(entries) != EXPECTED_COUNT:
        raise SystemExit(
            f"語数が想定と違う: {len(entries)}（期待 {EXPECTED_COUNT}）"
        )
    return entries


def write_keywords(entries: list[tuple[str, str, str, str]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(GENERATED_NOTICE)
        for word, col, row, source in entries:
            f.write(f"{word}\t{col}\t{row}\t{source}\n")


def main() -> int:
    root = repo_root()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--transcript",
        default=os.path.join(root, "src", "l4_basic", "reserved_words_transcript.tsv"),
    )
    ap.add_argument(
        "--out",
        default=os.path.join(root, "src", "l4_basic", "keywords.tsv"),
    )
    args = ap.parse_args()

    rows = read_transcript(args.transcript)
    entries = build_entries(rows)
    write_keywords(entries, args.out)
    print(f"語数={len(entries)} 出力: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
