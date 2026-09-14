#!/usr/bin/env python3
"""PC88Behavior: l4-s1b Q2 の腕（修飾×文字キー）を、Q1 の結果ノートから
機械的に生成する（G7）。

事前登録の追補
docs/notes/l4-s1b-key-matrix-preregistration-addendum.md（d484cdb）が定める
規則:
  - Q1 の結果ノートの表から、判定が writes_code(xx) となったキーの集合 K を
    機械的に作る（手で選ばない）
  - Q2 の腕は、修飾5種（SHIFT・カナ・GRPH・CTRL・CAPS）それぞれと K の
    各キーの組。腕の数は 5×|K|

入力: docs/notes/l4-s1b-key-matrix-results-q1q3.md の
      "### `writes_code(xx)` の一覧" 節にある表
      （`| port | bit | code(hex) | ラベル |` 形式、2桁16進のport/bit/code）。

出力: TSV（modifier, mod_port, mod_bit, key_port, key_bit）。
      文字コード自体は「挙動から再構成した対応表」であって画面本文ではない
      （事前登録本体の「本文を出さない取り扱い」節、l4-s1a のコード割り当てと
      同じ扱い）。ラベル列は参考情報としてQ1ノートに既にコミット済みのため
      再掲してよいが、この生成スクリプトは規則の追跡性のためコードのみを
      使い、ラベルは出力しない。

G7（再実行で同じ一覧になる）: 入力ファイルへの単純な正規表現抽出のみで、
乱数・時刻・環境依存の要素を一切使わない。
"""
from __future__ import annotations

import argparse
import csv
import re
import sys

DEFAULT_INPUT = "docs/notes/l4-s1b-key-matrix-results-q1q3.md"
DEFAULT_OUTPUT = "docs/notes/l4-s1b-q2-arms.tsv"

# 事前登録が定める修飾5種とそのポート・ビット
# (SHIFT 08H D6, カナ 08H D5, GRPH 08H D4, CTRL 08H D7, CAPS 0AH D7)
MODIFIERS = [
    ("SHIFT", 0x08, 6),
    ("KANA", 0x08, 5),
    ("GRPH", 0x08, 4),
    ("CTRL", 0x08, 7),
    ("CAPS", 0x0A, 7),
]

TABLE_HEADER_RE = re.compile(r"^###\s.*writes_code\(xx\).*の一覧")
ROW_RE = re.compile(
    r"^\|\s*([0-9A-Fa-f]{2})\s*\|\s*([0-9]+)\s*\|\s*([0-9A-Fa-f]{2})\s*\|"
)


def extract_k(md_path: str) -> list[tuple[int, int]]:
    """Q1結果ノートの writes_code(xx) 表から (port, bit) の一覧 K を抜き出す。

    手で選ばず、見出し直後の表を機械的にパースするだけ。区切り行
    (|---|---|...) とヘッダ行(| port | bit | ...)は数値にならないため
    自然に除外される。
    """
    with open(md_path, encoding="utf-8") as f:
        lines = f.readlines()

    k: list[tuple[int, int]] = []
    in_table = False
    header_seen = False
    for line in lines:
        if TABLE_HEADER_RE.search(line):
            in_table = True
            header_seen = False
            continue
        if not in_table:
            continue
        stripped = line.strip()
        if stripped.startswith("## ") or stripped.startswith("### "):
            # 次の節に入ったら終わり
            break
        if not stripped.startswith("|"):
            if header_seen:
                # 表が終わって本文に戻った
                break
            continue
        m = ROW_RE.match(stripped)
        if not m:
            # ヘッダ行・区切り行はここで弾かれる
            continue
        header_seen = True
        port = int(m.group(1), 16)
        bit = int(m.group(2))
        k.append((port, bit))
    return k


def build_arms(k: list[tuple[int, int]]) -> list[dict]:
    arms = []
    for mod_name, mod_port, mod_bit in MODIFIERS:
        for key_port, key_bit in k:
            arms.append(
                {
                    "modifier": mod_name,
                    "mod_port": f"{mod_port:02X}",
                    "mod_bit": str(mod_bit),
                    "key_port": f"{key_port:02X}",
                    "key_bit": str(key_bit),
                }
            )
    return arms


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default=DEFAULT_INPUT, help="Q1結果ノートのパス")
    ap.add_argument("--output", default=DEFAULT_OUTPUT, help="出力TSVのパス")
    ap.add_argument(
        "--check", action="store_true",
        help="出力ファイルを書かず、既存ファイルと一致するかだけ確認する(G7用)",
    )
    args = ap.parse_args()

    k = extract_k(args.input)
    if not k:
        print("[l4_s1b_q2_arms] K が空。入力ファイル・表の見出しを確認せよ",
              file=sys.stderr)
        return 1
    arms = build_arms(k)

    fieldnames = ["modifier", "mod_port", "mod_bit", "key_port", "key_bit"]
    if args.check:
        with open(args.output, encoding="utf-8", newline="") as f:
            existing = f.read()
        import io
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fieldnames, delimiter="\t",
                            lineterminator="\n")
        w.writeheader()
        w.writerows(arms)
        if buf.getvalue() != existing:
            print("[l4_s1b_q2_arms] NG: 再生成した一覧が既存ファイルと不一致",
                  file=sys.stderr)
            return 1
        print(f"[l4_s1b_q2_arms] OK: |K|={len(k)} 腕={len(arms)} "
              f"(G7: 既存ファイルと一致)")
        return 0

    with open(args.output, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t",
                            lineterminator="\n")
        w.writeheader()
        w.writerows(arms)

    print(f"[l4_s1b_q2_arms] |K|={len(k)} 腕={len(arms)} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
