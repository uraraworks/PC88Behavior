# M5 調査メモ — フォント経路サーベイ

2026-08-07 / 仕様セッション

`docs/PLAN.md` L2（フォント/漢字ROM）着手前の下調べ。読んだのは上流 QUASI88 の
ソースコード（BSD-3）と、それを対象にした実測ログのみ。`private/` 配下のバイト列、
`vendor/quasi88-libretro/src/font.h` のデータ行（`0x` の並ぶ行）は開いていない。

## 1. 読んだファイル

- `vendor/quasi88-libretro/src/memory.h` — 変数宣言（`font_mem` 系、`font_type`、
  `has_kanji_rom` 等）
- `vendor/quasi88-libretro/src/memory.c` 300〜530行、640〜700行 —
  上流の標準ロード経路（`memory_allocate()` の一部）と、`font_rom` の切り替え
  （`memory_set_font()`）
- `vendor/quasi88-libretro/src/font.h` — **コメント行とシンボル名のみ**
  （`grep -v '0x'` で抽出）。3配列のサイズ宣言 `[8*256*1]` だけを見た
- `vendor/quasi88-libretro/src/crtcdmac.c` 660〜751行 — `get_font_gryph()`。
  文字コードからグリフを作る箇所
- `vendor/quasi88-libretro/src/crtcdmac.h` — `T_GRYPH`、`crtc_font_height`
- `vendor/quasi88-libretro/src/screen-vram-base.h` — `ROWS`、`CHARA_LINES` の定義
- `vendor/quasi88-libretro/src/screen-vram-full.h`、`screen-vram-double.h`、
  `screen-vram-half.h` — `IF_LINE200_OR_EVEN_LINE()` の実体（3種の描画倍率で定義が違う）
- `vendor/quasi88-libretro/src/screen-vram.h` 1〜180行 — 実際にラスタへ書く場所
- `vendor/quasi88-libretro/src/LIBRETRO/libretro.c` 449〜504行（`load_system_file`）、
  560〜638行（`retro_init()` のROM読み込み全体）
- `vendor/quasi88-libretro/src/getconf.c` 540〜541行 — `use_built_in_font` は
  スタンドアロン版の設定オプションで、libretro 版では未使用と確認

## 2. 分かったこと（コードを読んだ事実）

### 2.1 フォントメモリの構造

`font_mem` / `font_mem2` / `font_mem3` はいずれも `8*256*2 = 4096` バイト確保
（`memory.c:334-336`）だが、実際に使うのは前半 `8*256*1 = 2048` バイトが ANK系、
後半 2048 バイトがセミグラフィック(`graph`)系という 2048+2048 の構成
（`font.h` の3配列 `built_in_font_ANK` / `built_in_font_ANH` / `built_in_font_graph`
がいずれも `[8*256*1]` = 2048 バイトであることと符合する）。

1 文字 = 8 バイト（8 行 × 1 バイト = 8x8 の 1bpp ビットマップ）、256 文字ぶん。
コード 0x000-0x0FF が「通常フォント」、0x100-0x1FF が「グラフィックフォント」
（`get_font_gryph()` で `attr & ATTR_GRAPH` により `chara|0x100` に切り替える。
`crtcdmac.c:731-734`）。

`font_type`（0/1/2）は `font_mem`/`font_mem2`/`font_mem3` のどれを実際に
使うかを選ぶ変数だが、これを変更するのは `menu.c`（設定メニュー）だけで、
libretro 版にはメニューが無い。**libretro 版では `font_type` は常に既定値 0
のまま**であり、`font_mem2`・`font_mem3`（FONT2.ROM・FONT3.ROM の読み込み結果）
は実際の描画には一度も使われない（`memory.c:671-673`、呼び出し元は
`menu.c:1667` のみで libretro.c に呼び出しは無い、と `grep` で確認）。

### 2.2 画面までの経路

`get_font_gryph()`（`crtcdmac.c`）が文字コード→グリフの変換点。
`font_rom`（`font_mem` 等のどれかを指す）から 8 バイトを取り出し、
`T_GRYPH`（`bit8 b[12]`）の先頭 8 バイトへコピーする。9〜12バイト目は
0 初期化（`ATTR_LOWER` 属性が立っているときだけ `b[crtc_font_height-1]` に
下線を焼く）。

`screen-vram.h` の描画ループが `T_GRYPH` を 1 ラスタラインずつ消費する。
その消費回数（`CHARA_LINES`）は `screen-vram-base.h` で
`200LINE時 = 200/ROWS`、`400LINE時 = 400/ROWS` と定義される。

**400ライン・24kHz・80×20（本プロジェクトが測定対象にしている条件）では
`CHARA_LINES = 400/20 = 20`。** つまり 1 文字セルは 20 ラスタラインぶんある。

一方フォント側のバイト消費は `IF_LINE200_OR_EVEN_LINE()` というマクロが
制御しており、`screen-vram-full.h`（400ライン相当）では
`if ((k & 1) == 0)` — **k が偶数のときだけ次の1バイトを読む**、
つまり同じフォントバイトを2ラインぶん続けて出す（縦2倍のライン倍化）。
`k` は 0〜19（`CHARA_LINES-1`）まで回るので、フォントバイトの読み出しは
k=0,2,4,...,18 の10回だけ起きる。

8x8 のグリフは `b[0]`〜`b[7]` にしか入っていないので、10回の読み出しのうち
実際に使われるのは最初の8回（k=0〜14偶数）で、残り2回（k=16,18）は
`b[8]`・`b[9]` を読む。`get_font_gryph()` は `b[8]`・`b[9]` を明示的な
グリフとしては埋めておらず、`ATTR_LOWER` が立っているときだけ
`crtc_font_height-1` 番目（`crtc_font_height` は `crtc_sz_lines<=20` のとき10 —
`crtcdmac.c:269`）＝ `b[9]` に下線用のベタパターンを焼く。それ以外は 0（空白）。

**結論（観測）**: 8x8 のグリフを「10行ぶんの論理セル」の上8行に置き、
下2行は空白（下線属性のときだけ下から2行目にアンダーラインが乗る）。
論理10行を24kHzモニタ向けにライン倍化して20ラスタラインにする——という
2段構えで、8x8 のビットマップのまま 20 ラインのセルに収まっている。
**フォント自体を拡大・補間しているわけではない。**

### 2.3 供給元とすり替わりの数え上げ

`memory.c`（上流の標準ロード経路。`memory_allocate()` の一部）と
`LIBRETRO/libretro.c`（`retro_init()` 内の独自ロード）の**両方**が
font_mem 系を埋めており、**libretro 版は `memory_allocate()` の後に
自前のロードを重ねて実行する**（`libretro.c:559` で `memory_allocate()` を呼び、
その直後 570行台から独自ロジックが同じ `font_mem`/`font_mem2`/`font_mem3` を
上書きする）。**実際に効くのは後から実行される libretro.c 側**であり、
`memory.c` 側の結果は握りつぶされる。

`libretro.c` 側の分岐（599〜627行）を精読すると、成功時・失敗時のどちらでも
ROM 由来のデータを維持しない箇所がある。**バイト列は転記しないが、
分岐構造だけを図にすると**:

| 対象 | ROMファイルを見つけた場合 | 見つからなかった場合 |
|---|---|---|
| font_mem[0x000-0x7FF]（Font1 ANK） | **読み込んだ内容を使わず**、`kanji_rom[0]` の一部で上書き | `built_in_font_ANK`（出所不明） |
| font_mem[0x800-0xFFF]（Font1 graph） | `built_in_font_graph`（出所不明）で上書き | **何もしない**（`malloc` 直後の未初期化領域が残る） |
| font_mem2[0x000-0x7FF]（Font2 ANH） | **読み込んだ内容を使わず**、`built_in_font_ANH`（出所不明）で上書き | 同じく `built_in_font_ANH` |
| font_mem2[0x800-0xFFF] | 読み込んだ内容を保持 | `built_in_font_graph`（出所不明） |
| font_mem3[0x000-0x7FF] | 読み込んだ内容を保持 | 0 埋め |
| font_mem3[0x800-0xFFF] | `built_in_font_graph`（出所不明）で上書き | 0 埋め |

ただし前述のとおり `font_mem2`・`font_mem3` は libretro 版では描画に使われない
（2.1節）。**実際に画面へ出るのは font_mem のみ**であり、その ANK 半分は
「ROM ファイルが見つかっても中身を使わない」という、成否に関係なく
すり替わる経路になっている。

### 2.4 実測で裏を取った点

`tools/measure.sh` でこのリポジトリの `private/rom` を対象に 60 フレーム
測定を実行し、フロントエンド（`tools/harness/frontend/`）が libretro の
`log_cb`（`RETRO_ENVIRONMENT_GET_LOG_INTERFACE`）を標準エラーへ転送する
仕組みを使って、**ROMファイル探索のログだけ**を確認した
（グリフのバイト列は一切出力していない。ログに出るのはファイルパスと
見つかった/見つからなかったの別だけ）。

結果: `KANJI1.ROM` / `KANJI2.ROM` は読み込みに成功、`FONT.ROM` /
`FONT2.ROM` / `FONT3.ROM` は3つとも「見つからない」。

この条件をコードに当てはめると、`memory_allocate()`（上流の標準経路）は
`has_kanji_rom == TRUE` なので `font_mem[0x000-0x7FF]` を
`kanji_rom[0][(1<<11)]` 由来のデータで埋める（2.3節の表とは別に、
`memory.c:441-442` にこの分岐がある）。ところが**その直後に走る
`libretro.c` 側の独自ロードが、`FONT.ROM` が見つからない場合の分岐として
無条件に `built_in_font_ANK` で上書きする**（`libretro.c:606`）。

つまり、**この測定環境では「漢字ROMは実在し、上流の標準ロジックなら
そこから ANK フォントを導出できたはずなのに、libretro 版の二重ロードが
それを踏みつぶして出所不明の内蔵フォントに差し替えている」**ことが、
コードの構造だけでなく実際のログでも確認できた。これは M1 で扱った
疑似BIOS（`pseudo_bios.h`）と同型の「黙って別のものが動く」パターンであり、
しかも疑似BIOSの場合と違って**ROMが無いときのフォールバックですらなく、
上流自身の正しいフォールバックを二重ロードが上書きしてしまう**、
一段質の悪いケースだった。

## 3. 分からなかったこと・保留にしたこと

- `built_in_font_ANK` / `built_in_font_ANH` / `built_in_font_graph`
  （`font.h`）の出所。コメントには由来の記載が無い。中身は見ていないので
  判定材料が無い。**L2 では使わない前提で進める**（4節）
- `FONT.ROM` が実在する場合に、`kanji_rom[0][(1<<11)]` 由来のデータと
  `FONT.ROM` 本来の内容がどの程度違うのか（＝この2つが同一のものを指しているのか、
  別物なのか）は、私物の `FONT.ROM` サンプルを持っていないため確認していない
- セミグラフィックコード（0x100-0x1FF）が実際にどんな用途で呼ばれるか
  （BASIC のセミグラフィックキャラクタ、罫線など）は未調査
- `main_high_ram`／PCG (`use_pcg`) 経由でのフォント差し替え（`pc88main.c:173`
  `font_pcg[...]  = src`）は、今回のテキスト画面の範囲では触れていない
