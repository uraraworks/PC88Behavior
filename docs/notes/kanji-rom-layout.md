# 自作漢字 ROM の配置

公式 ROM は読まず、次の QUASI88 エミュレータのソースから配置を読み取った。`vendor` はリポジトリの隣にある。

- `../vendor/quasi88-libretro/src/pc88main.c` 1176–1192 行、1473–1482 行: OUT E8/E9 と EC/ED はそれぞれ第1・第2 ROM の16ビット番地の下位・上位を設定。IN E8/EC は配列の添字1、IN E9/ED は添字0。
- `../vendor/quasi88-libretro/src/menu-screen.c` 26–45 行、`screen-menu.h` 43–66 行: 添字0が左、添字1が右。全角は各行を左右交互に16行、半角は連続バイト。QUART は8行、HALF は16行。
- `../vendor/quasi88-libretro/src/q8tk-glib.c` 872–928 行: JIS および半角コードからの番地変換。番地は2バイト単位であり、ファイル上のオフセットは番地の2倍。

## 全角

JIS X 0208 の行・列を表す2バイト値を `c` とする。下式は16行の先頭のワード番地。各行のファイル上の順は左1バイト、右1バイト。IN E9/ED が左、E8/EC が右を読む。

| JIS の範囲 | ROM | 先頭ワード番地 |
|---|---|---|
| 0x2121–0x2e7e（非漢字） | 1 | `((c & 0x60) << 7) | ((c & 0x700) << 1) | ((c & 0x1f) << 4)` |
| 0x3021–0x4f7e（第1水準） | 1 | `((c & 0x60) << 9) | ((c & 0x1f00) << 1) | ((c & 0x1f) << 4)` |
| 0x5021–0x6f7e（第2水準） | 2 | `((c & 0x60) << 9) | ((c & 0xf00) << 1) | ((c & 0x1f) << 4) | (c & 0x2000)` |
| 0x7021–0x7e7e（第2水準） | 2 | `((c & 0x60) << 7) | ((c & 0x700) << 1) | ((c & 0x1f) << 4)` |

実際には JIS 各バイトの 0x21–0x7e だけを受け入れる。東雲 `shnmk16.bdf` は JIS X 0208 コードを直接 ENCODING に持ち、第2水準も含む。存在しない字形と未割当領域はゼロ。

## 半角

ROM 1 の英数 0x20–0x7f とカナ 0xa0–0xdf はファイルオフセット `code * 16` に東雲 `shnm8x16r.bdf` の16行を置く。BDF にない 0x7f と 0xa0 は未充填。その他のコードは QUART とし、オフセット `((code << 2) | 0x800) * 2` に既存の `src/l2_font/make_font_rom.py` が生成する8行を置く。制御コードは ANK 面、グラフィックコードはグラフィック面を使用。既存生成器の空白コードおよび他の未割当領域はゼロ。

## 生成・検査

`python3 tools/make_kanji_rom.py` は `build/KANJI1.ROM` と `build/KANJI2.ROM` をそれぞれ 131072 バイトで書く。8×8 の生成には既存の `../vendor/unscii/unscii-8.hex` と `../vendor/misaki/misaki_gothic.bdf` が必要。場所は `--unscii-hex` と `--misaki-bdf` で指定できる。これらが無ければ既存の `tools/fetch_unscii.sh` と `tools/fetch_misaki.sh` を使う。

`python3 tools/kanji_rom_selftest.py` は既定の依存ファイルで2回生成し、固定番地の既知の第1・第2水準の字形および半角字形を BDF と比較、2回の出力一致を確認する。番地を1文字分ずらす陰性対照が検査に失敗することも確認する。フォントのライセンス文書は同梱した原文を参照。
