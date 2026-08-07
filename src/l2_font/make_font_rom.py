#!/usr/bin/env python3
"""
make_font_rom.py — L2 フォント（半角ANK + セミグラフィック）の FONT.ROM を組み立てる

根拠は `docs/spec/l2-font.md` 第2版と `docs/notes/l2-code-assignment.md`（本ファイルと
同じセッションで書いた、コード⇔グリフ対応表の根拠ノート）である。測定ログ
（`measurements/`）も公式 ROM も参照していない。

  出力フォーマット（`docs/spec/l2-font.md` 1節）:
    FONT.ROM = 4096 バイト。前半 2048 バイト = ANK面（コード0x00-0xFF、
    1文字8バイト）。後半 2048 バイト = グラフィック面（コード0x100-0x1FF
    相当。同じ面のオフセット0x800-0xFFF）。

  半角ANKの出どころは3系統（利用者判断。docs/notes/l2-code-assignment.md）:
    1. 英数記号（0x20-0x7E、資料から確定できた範囲） → unscii-8（CC-0/PD）。
       ただし 0x7E（JIS X0201 のオーバーライン ‾ U+203E）だけは unscii-8.hex に
       該当コードポイントが無いため対象外とし、横棒1本のルール生成に回す（3.）。
       `--unscii-hex` で渡された unscii-8.hex をこのスクリプトがパースする。
       unscii-8.hex 自体は `tools/fetch_unscii.sh` で取得するだけで、
       このリポジトリにはコミットしない。
    2. 半角カタカナ63字（0xA1-0xDF） → **美咲フォント（BDF版）から取得**
       （第4版。差し替えの経緯は docs/notes/l2-font-misaki-recheck.md）。
       `--misaki-bdf` で渡された misaki_gothic.bdf をこのスクリプトがパースする。
       misaki_gothic.bdf 自体は `tools/fetch_misaki.sh` で取得するだけで、
       このリポジトリにはコミットしない。
       旧・手描きASCIIアート（`KANA_ART`、下記）は判読性の初稿評価が
       「判別はできるが読みやすくはない」だったため差し替えた。美咲は
       8x8で読ませるために設計された完成品であり、かつ全角側カタカナ63字が
       すべて8x8セル内(7x7の範囲)で揃っていることを確認済み
          （docs/notes/l2-font-misaki-recheck.md (a)）。
       `KANA_ART` はビルドには使わず、消さずに残してある
          （このリポジトリのコミット規律。CLAUDE.md）。
    3. セミグラフィック（後半2048バイト） → ルールから生成（4節）。
  0x00-0x1F・0x7F は制御コードのため空白グリフ。0x80-0xA0・0xE0-0xFF は
  資料から確定できなかったため空白グリフ（`docs/notes/l2-code-assignment.md` 3節）。

  なぜ Python でバイト列を組むのか:
  `src/l1_ipl/make_ipl_rom.py` と同じ理由。外部依存ゼロなら第三者が
  `python3 make_font_rom.py <出力先> --unscii-hex <取得したunscii-8.hex>` だけで
  同じ ROM を再生成できる。

  二重検査について:
  `--selftest` はサイズ・空欄コードの一覧など「組み立ての整合性」を検査する。
  「意図した字形が入っていること」を独立に確かめる検査は
  `tools/verify_l2.sh` 側（本スクリプトとは別の実装で、unscii-8.hex と
  misaki_gothic.bdf から**独立に**ビットパターンを組み直し、生成された
  FONT.ROM と突き合わせる）に置く。理由は `docs/notes/m4-l1-impl.md`
  の先例と同じ: 同じコードパスで比較しても「そのコードが自己矛盾しない」
  ことしか言えないため。
"""

import argparse
import pathlib
import re
import sys

CELL_BYTES = 8          # 1文字 = 8バイト（8x8 1bpp）
PLANE_CHARS = 256        # 1面 = 256文字
PLANE_BYTES = CELL_BYTES * PLANE_CHARS   # 2048
ROM_SIZE = PLANE_BYTES * 2               # 4096 (ANK面 + GRAPH面)

# --------------------------------------------------------------------------
# 1. 半角カタカナ 63字（旧稿） — 手描き ASCII アート（第2〜3版で使用。現在は不使用）
# --------------------------------------------------------------------------
# **このセクションはビルドには使わない（1b節の美咲フォント由来に差し替え済み。
# docs/notes/l2-font-misaki-recheck.md）。** 消さずに残してあるのは、行き止まりを
# git reset で消さないというこのリポジトリのコミット規律（CLAUDE.md）のため。
#
# 各グリフは "#"=点灯 "."=消灯 の8x8。ここで描いた形は完全に自作であり、
# 公式ROM・他社ROMのいずれも見ていない（このセッションで新規に描いた）。
# 並び順・コードは JIS X0201 標準（Unicode半角カナ U+FF61-U+FF9F と1対1、
# docs/notes/l2-code-assignment.md 2節）。
# 差し替えの理由: 利用者から「半角カナが識字できない」との評価が出た。
# 美咲フォントは8x8で読ませるために設計された完成品であり、差し替えると
# 改善する見込みがあったため（docs/notes/l2-font-misaki-recheck.md）。
KANA_ART = {
    0xFF61: (  # 。 句点
        "........",
        "........",
        "........",
        "........",
        "........",
        "..##....",
        "..##....",
        "........",
    ),
    0xFF62: (  # 「 かぎ括弧(開)
        "..####..",
        "..#.....",
        "..#.....",
        "..#.....",
        "........",
        "........",
        "........",
        "........",
    ),
    0xFF63: (  # 」 かぎ括弧(閉)
        "........",
        "........",
        "........",
        "........",
        ".....#..",
        ".....#..",
        "..####..",
        "........",
    ),
    0xFF64: (  # 、 読点
        "........",
        "........",
        "........",
        "........",
        "........",
        "..##....",
        "..#.....",
        ".#......",
    ),
    0xFF65: (  # ・ 中黒
        "........",
        "........",
        "........",
        "...##...",
        "...##...",
        "........",
        "........",
        "........",
    ),
    0xFF66: (  # ヲ
        ".######.",
        "...#....",
        "...#....",
        ".####...",
        "...#....",
        "...#....",
        "..#.....",
        ".#......",
    ),
    0xFF67: (  # ァ (小字。アを縮小し右下へ寄せる)
        "........",
        "........",
        "..####..",
        "....#...",
        "...##...",
        "..#.#...",
        "........",
        "........",
    ),
    0xFF68: (  # ィ
        "........",
        "...##...",
        "..#.....",
        ".#......",
        "#.......",
        "........",
        "........",
        "........",
    ),
    0xFF69: (  # ゥ
        "........",
        "..###...",
        "....#...",
        "...#....",
        "..#.....",
        "........",
        "........",
        "........",
    ),
    0xFF6A: (  # ェ
        "........",
        "..####..",
        "....#...",
        "....#...",
        "..####..",
        "........",
        "........",
        "........",
    ),
    0xFF6B: (  # ォ
        "........",
        ".#.#....",
        "#####...",
        "..#.....",
        ".#.#....",
        "........",
        "........",
        "........",
    ),
    0xFF6C: (  # ャ
        "........",
        "..#.#...",
        ".####...",
        "...#....",
        "..#.#...",
        "........",
        "........",
        "........",
    ),
    0xFF6D: (  # ュ
        "........",
        ".#..#...",
        ".######.",
        ".....#..",
        "..###...",
        "........",
        "........",
        "........",
    ),
    0xFF6E: (  # ョ
        "........",
        "..####..",
        "..#.....",
        "..###...",
        "..####..",
        "........",
        "........",
        "........",
    ),
    0xFF6F: (  # ッ
        "........",
        "..#.#...",
        "..#.#...",
        "...#.#..",
        "..###...",
        "........",
        "........",
        "........",
    ),
    0xFF70: (  # ー 長音符
        "........",
        "........",
        "........",
        "########",
        "........",
        "........",
        "........",
        "........",
    ),
    0xFF71: (  # ア
        ".######.",
        "....#...",
        "...##...",
        "..#.#...",
        ".#..#...",
        "#...#...",
        "....#...",
        "........",
    ),
    0xFF72: (  # イ
        "....##..",
        "...#....",
        "..#.....",
        "..#.....",
        ".#......",
        "#.......",
        "#.......",
        "........",
    ),
    0xFF73: (  # ウ
        "..###...",
        "........",
        ".######.",
        "....#...",
        "...#....",
        "..#.....",
        ".#......",
        "........",
    ),
    0xFF74: (  # エ
        "######..",
        "........",
        "..#.....",
        "..#.....",
        "..#.....",
        "........",
        "######..",
        "........",
    ),
    0xFF75: (  # オ
        "..#..#..",
        "..#..#..",
        "#######.",
        "..#.....",
        "..##....",
        ".#..#...",
        "#....#..",
        "........",
    ),
    0xFF76: (  # カ
        "..#.....",
        ".######.",
        "..#.....",
        "..#.....",
        "..#.....",
        ".#..#...",
        "#....#..",
        "........",
    ),
    0xFF77: (  # キ
        "...#....",
        "..###...",
        "######..",
        "...#....",
        "..##....",
        ".#..#...",
        "#....#..",
        "........",
    ),
    0xFF78: (  # ク
        ".#......",
        ".######.",
        "......#.",
        ".....#..",
        "....#...",
        "...#....",
        "..#.....",
        "........",
    ),
    0xFF79: (  # ケ
        "..#..#..",
        "..#..#..",
        "..#..#..",
        "..######",
        "..#.....",
        ".#......",
        "#.......",
        "........",
    ),
    0xFF7A: (  # コ
        ".######.",
        ".#......",
        ".#......",
        ".#......",
        ".#......",
        ".######.",
        "........",
        "........",
    ),
    0xFF7B: (  # サ
        "..#.#...",
        "..#.#...",
        "######..",
        "...#....",
        "...#....",
        "..#.....",
        ".#......",
        "........",
    ),
    0xFF7C: (  # シ
        "....#...",
        "...#....",
        "..#.....",
        "........",
        "#.......",
        "#.......",
        ".######.",
        "........",
    ),
    0xFF7D: (  # ス
        ".######.",
        ".#......",
        "..#.....",
        "...#....",
        "..#.....",
        ".#..#...",
        "#....#..",
        "........",
    ),
    0xFF7E: (  # セ
        "..#.....",
        "######..",
        "..#.....",
        ".###....",
        "..#..#..",
        "..#.....",
        "........",
        "........",
    ),
    0xFF7F: (  # ソ
        "....#...",
        "...#....",
        "..#.....",
        "........",
        "#....#..",
        "#....#..",
        ".####...",
        "........",
    ),
    0xFF80: (  # タ
        "..#.....",
        ".######.",
        "..#.....",
        "..#.....",
        "..#..#..",
        ".#....#.",
        "......#.",
        "........",
    ),
    0xFF81: (  # チ
        "..###...",
        "########",
        "...#....",
        "..#.....",
        ".#......",
        "#.......",
        "........",
        "........",
    ),
    0xFF82: (  # ツ
        "#...#...",
        "#...#...",
        "#...#...",
        "..#.#...",
        ".#..#...",
        "#...#...",
        ".###....",
        "........",
    ),
    0xFF83: (  # テ
        "########",
        "...#....",
        "..#.....",
        "..#.....",
        ".#..#...",
        "#....#..",
        ".####...",
        "........",
    ),
    0xFF84: (  # ト
        "..#.....",
        "..#.....",
        "..######",
        "..#.....",
        "..#.....",
        ".#......",
        "#.......",
        "........",
    ),
    0xFF85: (  # ナ
        "########",
        "...#....",
        "...#....",
        "..#.....",
        ".#......",
        "#.......",
        "........",
        "........",
    ),
    0xFF86: (  # ニ
        "######..",
        "........",
        "........",
        "........",
        "########",
        "........",
        "........",
        "........",
    ),
    0xFF87: (  # ヌ
        ".#...#..",
        "..#.#...",
        "...#....",
        "..###...",
        ".#..#...",
        "#....#..",
        "........",
        "........",
    ),
    0xFF88: (  # ネ
        "..#..#..",
        "..#..#..",
        "######..",
        "..#.....",
        ".##.....",
        "#..#....",
        "....#...",
        "........",
    ),
    0xFF89: (  # ノ
        ".......#",
        "......#.",
        ".....#..",
        "....#...",
        "...#....",
        "..#.....",
        ".#......",
        "........",
    ),
    0xFF8A: (  # ハ
        "..#..#..",
        "..#..#..",
        ".#....#.",
        ".#....#.",
        "#......#",
        "........",
        "........",
        "........",
    ),
    0xFF8B: (  # ヒ
        "..#.....",
        "..#.....",
        "..#####.",
        "..#.....",
        "..#.....",
        "..##....",
        "........",
        "........",
    ),
    0xFF8C: (  # フ
        "#######.",
        "......#.",
        ".....#..",
        "....#...",
        "...#....",
        "..#.....",
        ".#......",
        "........",
    ),
    0xFF8D: (  # ヘ
        "...#....",
        "..#.#...",
        ".#...#..",
        "#.....#.",
        "........",
        "........",
        "........",
        "........",
    ),
    0xFF8E: (  # ホ
        "..#..#..",
        "..#..#..",
        "######..",
        "..#..#..",
        ".#.#....",
        "#...#...",
        "........",
        "........",
    ),
    0xFF8F: (  # マ
        "########",
        "....#...",
        "...##...",
        "..#.#...",
        ".#..#...",
        "....#...",
        "........",
        "........",
    ),
    0xFF90: (  # ミ
        ".####...",
        "........",
        "..####..",
        "........",
        ".#####..",
        "........",
        "........",
        "........",
    ),
    0xFF91: (  # ム
        "...##...",
        "..#..#..",
        "..#..#..",
        "...##...",
        "..#..#..",
        ".#....#.",
        "........",
        "........",
    ),
    0xFF92: (  # メ
        "#....#..",
        ".#..#...",
        "..##....",
        "..##....",
        ".#..#...",
        "#....#..",
        "........",
        "........",
    ),
    0xFF93: (  # モ
        "..#.....",
        "########",
        "..#.....",
        "########",
        "..#.....",
        "..#.....",
        "........",
        "........",
    ),
    0xFF94: (  # ヤ
        "..#..#..",
        ".######.",
        "...#....",
        "..##....",
        ".#..#...",
        "#....#..",
        "........",
        "........",
    ),
    0xFF95: (  # ユ
        ".#...#..",
        ".#...#..",
        ".#...#..",
        ".######.",
        "......#.",
        "......#.",
        "..####..",
        "........",
    ),
    0xFF96: (  # ヨ
        ".######.",
        ".#......",
        ".#####..",
        ".#......",
        ".#......",
        ".######.",
        "........",
        "........",
    ),
    0xFF97: (  # ラ
        "########",
        "......#.",
        ".....#..",
        "....#...",
        "...#....",
        "..#.....",
        "........",
        "........",
    ),
    0xFF98: (  # リ
        "..#..#..",
        "..#..#..",
        "..#..#..",
        "..#..#..",
        "..#..#..",
        "..#.#...",
        "..##....",
        "........",
    ),
    0xFF99: (  # ル
        "..#..#..",
        "..#..#..",
        "..#..#..",
        "..#..#..",
        "..#..#..",
        "..#..#..",
        "..#####.",
        "........",
    ),
    0xFF9A: (  # レ
        "..#.....",
        "..#.....",
        "..#.....",
        "..#.....",
        "..#.....",
        "..#...#.",
        "...###..",
        "........",
    ),
    0xFF9B: (  # ロ
        ".#####..",
        ".#...#..",
        ".#...#..",
        ".#...#..",
        ".#...#..",
        ".#####..",
        "........",
        "........",
    ),
    0xFF9C: (  # ワ
        "..#..#..",
        ".######.",
        "..#..#..",
        "..#..#..",
        "..#..#..",
        "...##...",
        "........",
        "........",
    ),
    0xFF9D: (  # ン
        "....#...",
        "...#....",
        "..#.....",
        "........",
        "..#..#..",
        ".#....#.",
        "#......#",
        "........",
    ),
    0xFF9E: (  # ゛ 濁点
        "........",
        "..#..#..",
        "...##...",
        "........",
        "........",
        "........",
        "........",
        "........",
    ),
    0xFF9F: (  # ゜ 半濁点
        "........",
        "..###...",
        "..#.#...",
        "..###...",
        "........",
        "........",
        "........",
        "........",
    ),
}
assert len(KANA_ART) == 63, f"半角カナは63字のはずが {len(KANA_ART)} 字"
for _cp, _rows in KANA_ART.items():
    assert len(_rows) == CELL_BYTES, f"U+{_cp:04X} の行数が8でない"
    for _r in _rows:
        assert len(_r) == 8 and set(_r) <= {"#", "."}, f"U+{_cp:04X} の行が不正: {_r!r}"

# JIS X0201 の半角カナ域(0xA1-0xDF)と Unicode(U+FF61-U+FF9F)の対応
# (docs/notes/l2-code-assignment.md 2節)。
def kana_code_map():
    m = {}
    for i, cp in enumerate(range(0xFF61, 0xFF9F + 1)):
        m[0xA1 + i] = cp
    return m


KANA_CODE_TO_UNICODE = kana_code_map()

# --------------------------------------------------------------------------
# 1b. 半角カタカナ 63字（現行） — 美咲フォント(BDF)から取得
# --------------------------------------------------------------------------
# 半角カナの「半角」は呼び名であって寸法ではない。PC-88のテキストセルはどの
# 文字も8ドット幅であり、必要なのは「8x8のカタカナのグリフ」である。美咲は
# 全角側のかな・カタカナを8x8(実際は7x7に収める設計)で持つ日本語ビットマップ
# フォントなので、その全角側から該当63字を取り出す
# （docs/notes/l2-font-misaki-recheck.md）。

# JIS X0201 半角カナ(Unicode U+FF61-U+FF9F)と、美咲BDFが収録する全角側
# Unicodeコードポイントの対応。JIS X0201/Unicode の標準的な半角→全角
# 互換対応表であり、ROM由来のデータではない
# （docs/notes/l2-font-misaki-recheck.md (a)節で実測に使ったものと同じ表）。
HALFWIDTH_TO_FULLWIDTH_KATAKANA = {
    0xFF61: 0x3002, 0xFF62: 0x300C, 0xFF63: 0x300D, 0xFF64: 0x3001, 0xFF65: 0x30FB,
    0xFF66: 0x30F2, 0xFF67: 0x30A1, 0xFF68: 0x30A3, 0xFF69: 0x30A5, 0xFF6A: 0x30A7,
    0xFF6B: 0x30A9, 0xFF6C: 0x30E3, 0xFF6D: 0x30E5, 0xFF6E: 0x30E7, 0xFF6F: 0x30C3,
    0xFF70: 0x30FC, 0xFF71: 0x30A2, 0xFF72: 0x30A4, 0xFF73: 0x30A6, 0xFF74: 0x30A8,
    0xFF75: 0x30AA, 0xFF76: 0x30AB, 0xFF77: 0x30AD, 0xFF78: 0x30AF, 0xFF79: 0x30B1,
    0xFF7A: 0x30B3, 0xFF7B: 0x30B5, 0xFF7C: 0x30B7, 0xFF7D: 0x30B9, 0xFF7E: 0x30BB,
    0xFF7F: 0x30BD, 0xFF80: 0x30BF, 0xFF81: 0x30C1, 0xFF82: 0x30C4, 0xFF83: 0x30C6,
    0xFF84: 0x30C8, 0xFF85: 0x30CA, 0xFF86: 0x30CB, 0xFF87: 0x30CC, 0xFF88: 0x30CD,
    0xFF89: 0x30CE, 0xFF8A: 0x30CF, 0xFF8B: 0x30D2, 0xFF8C: 0x30D5, 0xFF8D: 0x30D8,
    0xFF8E: 0x30DB, 0xFF8F: 0x30DE, 0xFF90: 0x30DF, 0xFF91: 0x30E0, 0xFF92: 0x30E1,
    0xFF93: 0x30E2, 0xFF94: 0x30E4, 0xFF95: 0x30E6, 0xFF96: 0x30E8, 0xFF97: 0x30E9,
    0xFF98: 0x30EA, 0xFF99: 0x30EB, 0xFF9A: 0x30EC, 0xFF9B: 0x30ED, 0xFF9C: 0x30EF,
    0xFF9D: 0x30F3, 0xFF9E: 0x309B, 0xFF9F: 0x309C,
}
assert set(HALFWIDTH_TO_FULLWIDTH_KATAKANA) == set(KANA_CODE_TO_UNICODE.values())


def misaki_code_to_unicode(code):
    """PC-88の半角カナコード(0xA1-0xDF)から、美咲BDF内の全角側コードポイントへ。"""
    return HALFWIDTH_TO_FULLWIDTH_KATAKANA[KANA_CODE_TO_UNICODE[code]]


def parse_misaki_bdf(path):
    """misaki_gothic.bdf(X11 BDF形式)をパースする。

    戻り値: (ascent, descent, {codepoint: {"dwidth": int, "bbx": (w,h,xoff,yoff),
    "bitmap": [хех行,...]}})。ヘッダの FONT_ASCENT/FONT_DESCENT から
    セル内の基準線位置を、STARTCHAR〜ENDCHAR の各ブロックからグリフを読む。
    行単位で状態を追うシンプルな実装（正規表現は使わない）。
    """
    ascent = descent = None
    glyphs = {}
    cur = None
    in_bitmap = False
    with open(path, "r", encoding="ascii", errors="strict") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("FONT_ASCENT "):
                ascent = int(line.split()[1])
            elif line.startswith("FONT_DESCENT "):
                descent = int(line.split()[1])
            elif line.startswith("STARTCHAR"):
                cur = {"bitmap": []}
                in_bitmap = False
            elif cur is not None and line.startswith("ENCODING "):
                cur["encoding"] = int(line.split()[1])
            elif cur is not None and line.startswith("DWIDTH "):
                cur["dwidth"] = int(line.split()[1])
            elif cur is not None and line.startswith("BBX "):
                parts = line.split()
                cur["bbx"] = tuple(int(x) for x in parts[1:5])
            elif line == "BITMAP":
                in_bitmap = True
            elif line == "ENDCHAR":
                if cur is not None and "encoding" in cur:
                    glyphs[cur["encoding"]] = cur
                cur = None
                in_bitmap = False
            elif in_bitmap and cur is not None:
                cur["bitmap"].append(line)
    if ascent is None or descent is None:
        raise ValueError(f"{path}: FONT_ASCENT/FONT_DESCENT が見つからない")
    return ascent, descent, glyphs


def misaki_glyph_to_rows(ascent, descent, glyph):
    """美咲BDFの1グリフ(BBX+BITMAP)を8x8セルの行配列("#"/".")へ配置する。

    美咲は7x7に収める設計で、文字ごとにBBXの幅・高さ・オフセットが違う。
    ここを決め打ちで揃えると字がずれるので、BDFの座標系をそのまま使う:
    セル内の行rは基準線からの高さ y=(ascent-1)-r に対応し、ビットマップの
    行iはy=yoff+height-1-iに対応する。列は x=xoff+c（cはビットマップ内の
    列インデックス）。範囲外(0<=x<8, 0<=r<8でない)は描画しない。
    """
    width, height, xoff, yoff = glyph["bbx"]
    rows = [["."] * CELL_BYTES for _ in range(CELL_BYTES)]
    for i, hexrow in enumerate(glyph["bitmap"]):
        nbits = len(hexrow) * 4
        value = int(hexrow, 16) if hexrow else 0
        bits = bin(value)[2:].zfill(nbits)
        y = yoff + height - 1 - i
        r = (ascent - 1) - y
        if not (0 <= r < CELL_BYTES):
            continue
        for c in range(min(width, nbits)):
            x = xoff + c
            if not (0 <= x < CELL_BYTES):
                continue
            if bits[c] == "1":
                rows[r][x] = "#"
    return tuple("".join(row) for row in rows)


# --------------------------------------------------------------------------
# 2. unscii-8.hex のパース（英数記号 0x20-0x7E 用）
# --------------------------------------------------------------------------
_HEX_LINE_RE = re.compile(r"^([0-9A-Fa-f]{4,6}):([0-9A-Fa-f]{16}|[0-9A-Fa-f]{32})$")


def parse_unscii_hex(path):
    """unscii-8.hex を { codepoint(int): bytes(8) } に変換する。

    形式は Unifont 互換の .hex（1行 = "<codepoint hex>:<16進データ>"）。
    8x8 の1bppフォントなので、通常は8バイト=16進16文字だが、
    unscii-8.hex にはコードポイント0(未使用グリフ)だけ16進32文字（16バイト、
    倍幅扱い）の行が1件混ざっている。今回使うのは0x20-0x7Eの範囲だけで
    codepoint 0は使わないため、32文字の行は先頭8バイトだけを採用する
    （全ゼロなので実害は無いが、形式の違いとして明示しておく）。
    """
    table = {}
    with open(path, "r", encoding="ascii", errors="strict") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            m = _HEX_LINE_RE.match(line)
            if not m:
                raise ValueError(f"{path}:{lineno}: 行の形式が想定外: {line!r}")
            cp = int(m.group(1), 16)
            data = bytes.fromhex(m.group(2))[:CELL_BYTES]
            table[cp] = data
    return table


# JIS X0201ラテン(0x20-0x7D)とunscii-8のUnicodeコードポイントの対応。
# 0x5C=円記号(U+00A5)がASCIIとの相違点。unscii-8.hexに U+00A5(codepoint行
# "000A5:...")が実在することを確認済み（vendor/unscii/unscii-8.hex）ので、
# 他の英数記号と同じくunscii-8由来のままでよい。
# 0x7E=オーバーライン(U+203E)は unscii-8.hex に該当コードポイントが無いため、
# ここでは扱わない。呼び出し側(build_ank_plane)で 0x7E は先に分岐し、
# overline_glyph()（ルール生成。4.）を使う。
def latin_code_to_unicode(code):
    if code == 0x5C:
        return 0x00A5  # ¥ YEN SIGN
    return code  # 0x20-0x7D(0x5C除く)はASCIIと同じコードポイント


# --------------------------------------------------------------------------
# 3. セミグラフィック — ルールから生成（データではなく規則。docs/PLAN.md）
# --------------------------------------------------------------------------
def semigraphic_glyph(code):
    """8bitコード(0x00-0xFF)を「2列×4行」のブロック格子とみなして描く。

    ビット0..7を格子の8マス(左上から右→下の順、2列4行)に割り当て、
    立っているマスを 4x2 画素のブロックで塗る。これは幾何規則であって
    実測データではない（docs/PLAN.md「データテーブルはルールから生成する」、
    docs/spec/l2-font.md 6節5）。
    """
    rows = [["." for _ in range(8)] for _ in range(8)]
    for bit in range(8):
        col = bit % 2          # 0=左, 1=右
        row = bit // 2         # 0..3
        on = (code >> bit) & 1
        if not on:
            continue
        x0 = col * 4
        y0 = row * 2
        for dy in range(2):
            for dx in range(4):
                rows[y0 + dy][x0 + dx] = "#"
    return tuple("".join(r) for r in rows)


# --------------------------------------------------------------------------
# 3b. オーバーライン(0x7E) — ルールから生成（unscii-8にU+203Eが無いため）
# --------------------------------------------------------------------------
def overline_glyph():
    """JIS X0201 の 0x7E（‾ オーバーライン、U+203E）。

    横棒1本という形自体が「セルの最上段ラインを点灯させる」という幾何規則
    そのものなので、セミグラフィックと同じ扱いでルールから生成する
    （unscii-8.hex には U+203E が無く、代用も置かない。実装セッションで確認）。
    ASCIIチルダ(U+007E)の字形は使わない——チルダは波線でオーバーラインとは
    別の文字。
    """
    return ("########",) + ("........",) * (CELL_BYTES - 1)


# --------------------------------------------------------------------------
# 4. 組み立て
# --------------------------------------------------------------------------
def rows_to_bytes(rows):
    out = bytearray(CELL_BYTES)
    for i, row in enumerate(rows):
        b = 0
        for x, ch in enumerate(row):
            if ch == "#":
                b |= 0x80 >> x
        out[i] = b
    return bytes(out)


def build_ank_plane(unscii_table, misaki):
    """ANK面(2048バイト)を組み立てる。戻り値: (plane_bytes, undetermined_codes)"""
    misaki_ascent, misaki_descent, misaki_glyphs = misaki
    plane = bytearray(PLANE_BYTES)
    undetermined = []
    for code in range(256):
        glyph = None
        if code == 0x7E:
            glyph = rows_to_bytes(overline_glyph())
        elif code in KANA_CODE_TO_UNICODE:
            cp = misaki_code_to_unicode(code)
            info = misaki_glyphs.get(cp)
            if info is None:
                raise ValueError(
                    f"美咲BDFにコードポイント U+{cp:04X}（PC-88コード0x{code:02X}用）が無い"
                )
            glyph = rows_to_bytes(misaki_glyph_to_rows(misaki_ascent, misaki_descent, info))
        elif 0x20 <= code <= 0x7D:
            cp = latin_code_to_unicode(code)
            data = unscii_table.get(cp)
            if data is None:
                raise ValueError(
                    f"unscii-8.hex にコードポイント U+{cp:04X}（PC-88コード0x{code:02X}用）が無い"
                )
            glyph = data
        elif code <= 0x1F or code == 0x7F:
            glyph = bytes(CELL_BYTES)  # 制御コード。可視グリフ無し
        else:
            # 0x80-0xA0, 0xE0-0xFF: 資料から確定できなかった未決定コード
            glyph = bytes(CELL_BYTES)
            undetermined.append(code)
        plane[code * CELL_BYTES:(code + 1) * CELL_BYTES] = glyph
    return bytes(plane), undetermined


def build_graph_plane():
    plane = bytearray(PLANE_BYTES)
    for code in range(256):
        glyph = rows_to_bytes(semigraphic_glyph(code))
        plane[code * CELL_BYTES:(code + 1) * CELL_BYTES] = glyph
    return bytes(plane)


def build_font_rom(unscii_hex_path, misaki_bdf_path):
    unscii_table = parse_unscii_hex(unscii_hex_path)
    misaki = parse_misaki_bdf(misaki_bdf_path)
    ank, undetermined = build_ank_plane(unscii_table, misaki)
    graph = build_graph_plane()
    rom = ank + graph
    assert len(rom) == ROM_SIZE
    return rom, undetermined


# --------------------------------------------------------------------------
# 5. 自己検査（--selftest）
# --------------------------------------------------------------------------
def selftest(rom, undetermined):
    ok = True
    print("=== make_font_rom.py --selftest ===")

    if len(rom) != ROM_SIZE:
        print(f"NG: ROMサイズが {len(rom)} バイト（期待 {ROM_SIZE}）")
        ok = False
    else:
        print(f"OK: ROMサイズ {len(rom)} バイト")

    # ANK面: 0x20-0x7E, 0xA1-0xDF は非ゼロであること（何らかのグリフが入っている）。
    # 0x20(space)は意図的に全消灯が正しいグリフなので検査から除外する。
    missing_expected = []
    for code in range(0x21, 0x7F):
        off = code * CELL_BYTES
        if rom[off:off + CELL_BYTES] == bytes(CELL_BYTES):
            missing_expected.append(code)
    for code in range(0xA1, 0xE0):
        off = code * CELL_BYTES
        if rom[off:off + CELL_BYTES] == bytes(CELL_BYTES):
            missing_expected.append(code)
    if missing_expected:
        print(f"NG: グリフが入っているはずのコードが空: {[hex(c) for c in missing_expected]}")
        ok = False
    else:
        print("OK: 英数記号(0x20-0x7E)・半角カナ(0xA1-0xDF)はすべて非ゼロ")

    print(f"-- 未決定（空欄）コード: {len(undetermined)} 個")
    print("   " + ", ".join(f"0x{c:02X}" for c in undetermined))

    # GRAPH面の簡易検査: code=0x00は全消灯、code=0xFFは全点灯であること
    graph_off = PLANE_BYTES
    if rom[graph_off:graph_off + CELL_BYTES] != bytes(CELL_BYTES):
        print("NG: GRAPH面 code=0x00 が全消灯でない")
        ok = False
    else:
        print("OK: GRAPH面 code=0x00 = 全消灯")
    all_on = bytes([0xFF] * CELL_BYTES)
    off_ff = graph_off + 0xFF * CELL_BYTES
    if rom[off_ff:off_ff + CELL_BYTES] != all_on:
        print("NG: GRAPH面 code=0xFF が全点灯でない")
        ok = False
    else:
        print("OK: GRAPH面 code=0xFF = 全点灯")

    print("合格" if ok else "不合格")
    return ok


def main():
    ap = argparse.ArgumentParser(
        description="L2 フォントの FONT.ROM を組み立てる（docs/spec/l2-font.md 第2版）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir", help="ROM を書き出すディレクトリ")
    ap.add_argument("--unscii-hex", required=True,
                     help="tools/fetch_unscii.sh が取得した unscii-8.hex のパス")
    ap.add_argument("--misaki-bdf", required=True,
                     help="tools/fetch_misaki.sh が取得した misaki_gothic.bdf のパス")
    ap.add_argument("--selftest", action="store_true",
                     help="生成物の自己検査（サイズ・未決定コード一覧など）を行う")
    args = ap.parse_args()

    rom, undetermined = build_font_rom(args.unscii_hex, args.misaki_bdf)

    d = pathlib.Path(args.outdir)
    d.mkdir(parents=True, exist_ok=True)
    out = d / "FONT.ROM"
    out.write_bytes(rom)
    print(f"生成した: {out} ({len(rom)} bytes)")
    print(f"未決定（空欄）コード: {len(undetermined)} 個")

    if args.selftest:
        ok = selftest(rom, undetermined)
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
