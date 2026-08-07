#!/usr/bin/env python3
"""
redact.py — 測定結果に写り込んだ私物の情報を伏せる

測定結果には終了時のテキスト画面を残している。条件が意図どおりだったかを
結果自身で検証できるようにするためで、この方針は変えない。

ただし `FILES` の出力にはディスクの中のファイル名が並ぶ。これは測定に
必要な情報ではなく、私物の内容である。公開リポジトリに載せる前に伏せる。

伏せても測定の妥当性は確かめられる。`files` を打って `Ok` が返っている
ことが分かれば、その条件が成立したことは分かるため。

判定: 1 行に「6文字以内の名前 + '.' か '*' + 拡張子 + 数字」の並びが
3 つ以上あればディレクトリ一覧とみなす。PC-88 の FILES はこの形で出る。

使い方: tools/redact.py <ファイル>...  （その場で書き換える）
"""

import pathlib
import re
import sys

# 例: "dtools.j88 1    @cc4h *rel 1    fm    *ipl 1"
ENTRY = re.compile(r"\S{1,6}\s*[.*]\s*\S{0,3}\s+\d+")
MASK = "(ディスクのファイル一覧は伏せた)"


def redact_text(text):
    out, n = [], 0
    for line in text.splitlines():
        # 画面の行だけを対象にする（先頭が "  NN| " の形）
        m = re.match(r"^(\s+\d+\|\s)(.*)$", line)
        if m and len(ENTRY.findall(m.group(2))) >= 3:
            out.append(m.group(1) + MASK)
            n += 1
        else:
            out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), n


def main(argv):
    total = 0
    for f in argv:
        p = pathlib.Path(f)
        new, n = redact_text(p.read_text(encoding="utf-8"))
        if n:
            p.write_text(new, encoding="utf-8")
            print(f"{p.name}: {n} 行を伏せた")
        total += n
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
