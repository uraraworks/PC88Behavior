# グラフィック命令の容量計画と共通部の入口

設計メモ（仕様ではない）/ 2026-10-09 / 実装: PSET・PRESET・POINT・CLS n・SCREEN（l4-graphics.md 第1版、l4-s9t）の実装コミットに含める。

根拠は [docs/spec/l4-graphics.md](../spec/l4-graphics.md) 第1版と [docs/spec/ext-rom-bank.md](../spec/ext-rom-bank.md)。
ここに書く「見積もり」は、すでに入った部分の実バイト数（アセンブラの番地差）を物差しにした自作の推定であり、
後続の命令の仕様はまだ測っていない（LINE・CIRCLE・PAINT・GET@/PUT@・VIEW・WINDOW は l4-graphics.md 第9節「未測定」）。
命令の挙動を決める材料ではなく、**置き場所と容量が足りるか**だけを判断するための表。

## 1. 空き容量（実測。tools の自作ROMビルドの末尾の 0 埋めから）

| 領域 | 実装前(HEAD) | 実装後 | 備考 |
|---|---|---|---|
| main (N88.ROM 0x0000〜0x7FFF) の末尾 | 126B | **126B** | 測定ROM用に116B以上を維持する条件を満たす。mainの増減は 0x79D7 手前の埋め草（46B→40B）で吸収した |
| bank0 (N88_0.ROM) の末尾 | 77B | 65B | COLOR の前景/背景の記録とバンク2への中継を足した分 |
| bank0 の途中の空き（0x6A33〜0x6AFF） | 205B | 27B 残 | gfxhook.asm（165B）を置いた。**ORG の都合で bank0 は連結順に前から詰めるしかない**（`make_ext_rom_banks.py`） |
| bank1 | 1995B | 1995B | 未使用 |
| bank2 | 3400B | **2267B** | gfx.asm が 1133B（0x7300〜0x7725、先頭の入口表のすき間を含む） |
| bank3 | 27B | 27B | 使わない（中継を置かない） |

拡張ROMバンクの数は **4本で固定**（ポート 0x32 の下位2ビット `EROMSL`、ext-rom-bank.md 第1節）。増やせない。
したがって「バンクを足す」ではなく「どのバンクへ何を置くか」と「バンクをまたぐ共通部をどう持つか」が設計の中心になる。

## 2. 今回入れたものの内訳（実バイト）

| 部品 | 場所 | バイト | 役割 |
|---|---|---|---|
| 窓外中継・誤り終了・文末判定 | bank2 gfx.asm | 112 | `gx_expect`・`gx_parse_int`・`gx_set_int`・`gx_text_cls`（main の呼び先）、`gx_ok`・`gx_err*`・`gx_bad`・`gx_stmt_end` |
| 座標の読み取り（`gx_coord`）・色引数（`gx_color_arg`） | bank2 | 215 | STEP 相対・LP 更新は ')' まで読み終えた時点 |
| 番地計算・点を打つ・点を読む・塗りつぶし | bank2 | 243 | `gx_addr`・`gx_plot`・`gx_getpix`・`gx_clear_gfx`（DI の間だけスタックとRAMに触れない） |
| PSET・PRESET・POINT 文 | bank2 | 40 | 共通部の上に載る薄い層 |
| POINT 関数 | bank2 | 108 | n 形と (x,y) 形 |
| CLS の引数 | bank2 | 74 | main の CLS_STMT は 8 バイトの中継だけ（従来 11B より小さい） |
| SCREEN 文 | bank2 | 241 | 引数検査→反映の二段（誤りのときは何も変えない） |
| 文の語の表・中継・POINT( の先見 | bank0 gfxhook.asm | 165 | 語の表（fn_words、101B）を deftype.asm から移した。deftype 側は 74B 空いた |
| COLOR の前景・背景の記録 | bank0 widthbeep.asm | 12 | 前景は xor 7 で持つ（ゼロ初期化で既定の 7） |
| 起動時の GFX 状態の0初期化 | main relay.asm | 9 | EXT_BANK_INIT |

RAM は GFX 領域 24B（0xFFBC〜、memmap.py。測定専用の M6IA 域と宣言した上で重ねた。正味の空きは 0 だった）。

## 3. 後続の命令の見積もり（推定。単位バイト）

| 命令 | 見積もり | 根拠（推定の組み立て） |
|---|---|---|
| LINE（STEP・色・B・BF・線種） | 550 | 座標の読み取りは `gx_coord` を再利用（2点目は LP からの STEP 相当）。Bresenham 約170、B（4辺）約40、BF（水平スパンを窓の中でまとめて塗る）約120、線種 16bit パターン約40、引数解析約150 |
| CIRCLE（円・楕円・円弧・扇） | 850 | 中点法の楕円約250、開始・終了角の象限判定と弧の切り出し約250（角度→傾きの比較。三角関数は bank0 の SIN/COS を窓外中継で呼ぶ想定）、中心への線は LINE を再利用約60、引数解析約250 |
| PAINT（境界色・タイル） | 600 | 走査線塗りつぶし。作業スタックは空きRAM（MM_FREE_TOP 付近）を使う設計が別途要る（RAM は余りが無い） |
| GET@／PUT@ | 600 | 3プレーンの行詰めヘッダ付き配列。PUT の演算（PSET・PRESET・AND・OR・XOR）約200 |
| VIEW・WINDOW | 300 | 座標変換。入れると `gx_coord` に変換段が入る（影響は共通部1か所） |
| COLOR=（パレット） | 150 | アナログパレットは 0x54〜 の書式（l1-ipl.md 第5c節）。bank0 の wb_color_stmt と隣り合う |
| 合計 | 約3050 | |

## 4. 置き場所

窓外中継（バンクをまたぐ呼び出し）は再入不可・1回往復・割り込みハンドラは窓の外、という ext-rom-bank.md 第2節の制約のとおり。
**バンクから別のバンクを直接 CALL できない**ので、点を打つ共通部は「同じバンクの中にある」ことが望ましい。

- **bank2（残り 2267B）**: 共通部（今回入れた分）＋ **LINE（550）＋ CIRCLE（850）＝約1400B**。収まる（残り約860B）。
  CIRCLE は LINE（B）と `gx_plot` を同じバンクの中から呼ぶ。
- **bank1（1995B、空き）**: **PAINT（600）＋ GET@／PUT@（600）＋ VIEW・WINDOW（300）＝約1500B**。
  bank1 には共通部の複製が要る（`gx_addr`・`gx_getpix`・`gx_plot`・`gx_coord`・窓外中継の呼び先で約400B）。
  合計約1900B で、1995B にぎりぎり収まる。**余裕は 100B 未満なので、PAINT より先に bank1 の複製を小さくする設計（下記）を決める**。
- **bank0**: 文の語の表と中継だけ。LINE・CIRCLE・PAINT・GET・PUT・VIEW・WINDOW の語（約38B）と、種別→バンクの選択（約8B）を足す。
  gfxhook.asm の残り 27B＋末尾の 65B で収まる（連結順の都合で、足す語は gfxhook.asm の先頭側＝残り27Bの範囲に置く）。
- **main**: 触らない。種別44以上は deftype.asm の `fn_stmt_dispatch` からすべて bank0 の中継へ流れる。

### bank1 の複製を小さくする案（決めてから PAINT に入る）

1. 点単位の `gx_plot`・`gx_getpix` は複製せず、**行単位（1ライン80バイト×3プレーン）の読み書き**を共通の入口にする。
   PAINT（走査線）も GET@／PUT@（行詰め）も行単位で足りる。行単位の入口は約120B。
2. 座標の読み取り `gx_coord` は文ごとに形が違う（PAINT と GET は `(x,y)`、GET@ は `(x1,y1)-(x2,y2)`）ので共有しにくい。共通の「数値引数1個」（`gx_parse_int`）だけ複製する。
3. それでも足りなければ、bank2 の SCREEN 文（241B）を bank1 へ移す。SCREEN は点を打たないので共通部をほとんど要らない。

### 足りなかったときの退避先（既存の処理を詰める・移す）

- bank0 の途中の空き: 0x6137〜0x61FF（201B）、0x741C〜0x744F（52B）。固定入口の間のすき間なので、**連結順の都合で入れられるのは該当ファイルの末尾側**（0x741C は deffn.asm の末尾の後ろ）。
- main の 0x79D7 手前の埋め草 40B（今の main の変更はここへ入る）。
- bank3 の 27B は使わない（バンク3は割り込みや中継から呼ばれる経路の埋め草域の取り決め）。

## 5. 共通部の入口（後続の命令が呼ぶ）

すべて bank2 の中の `CALL`（bank2 以外から呼ばない）。レジスタは破壊してよい（呼び出し側が保存する）。

| ラベル | 入力 | 出力 | 注意 |
|---|---|---|---|
| `gx_coord` | CUR_PTR が `[STEP](x,y)` の先頭 | LP に反映、ERROR_FLAG | LP の更新は ')' まで読み終えた時点。誤りなら LP は動かない |
| `gx_parse_int` | CUR_PTR が数値式 | DE=四捨五入した整数 | 文字列は ERR 13、範囲外は ERR 6。終わったら `gx_bad`（NZ=誤り）で確かめる |
| `gx_color_arg` | CUR_PTR が `[,色]` | MM_GFX_TC=色、Z=正常 | 色の範囲外は ERR 5。既定色は呼び出し側が MM_GFX_TC に先に入れる（PSET は前景、PRESET は背景） |
| `gx_stmt_end` | — | Z=ここで文が終わってよい | 行末・':'・ELSE 以外は ERR 2。**描く前に呼ぶ**（構文が最後まで正しいときだけ描く） |
| `gx_plot` | HL=x, DE=y（符号付き）, A=色(0〜7) | — | 範囲外は何もしない。白黒（screen 1）はアクティブページ1枚へ |
| `gx_getpix` | HL=x, DE=y | A=色(0〜7)、範囲外は 0FFh | 白黒は 1/0 |
| `gx_addr` | HL=x, DE=y | CF=1 範囲外／CF=0 で HL=VRAM番地・B=ビットマスク | 行の走査（LINE の BF・PAINT）で隣の点へ進むときの基準 |
| `gx_clear_gfx` | A=背景色 | — | 128B ごとに割り込みを通す |
| `gx_ok`・`gx_err2/5/6/22`・`gx_bad` | — | — | 文の終わり方。文の入口は MM_ERROR_KIND=2 を先に入れる（式の誤りが既定の2を前提にする） |

状態（memmap.py の GFX 領域）: `MM_GFX_LPX`・`MM_GFX_LPY`（LP、2B ずつ）・`MM_GFX_FG`（前景 xor 7）・`MM_GFX_BG`・`MM_GFX_MONO`・`MM_GFX_APAGE`。
作業値 `MM_GFX_TX/TY/STEP/TC/SI/SM/S0〜S3` は文の内側だけで使う。LINE などが増やす作業値は GFX 領域（残り 4B）では足りないので、
**別の一時域を重ねる**（例: SECTOR 域 0xEDB2〜を OVERLAPS に宣言。LINE・PAINT はディスク文を呼ばず排他的）。

## 6. 割り込みとVRAMの切替（実装の約束）

- グラフィックVRAMを選ぶ（OUT 0x5C〜0x5E）と C000〜FFFF がグラフィックVRAMに替わる。CPUスタックも BASIC のRAMもそこにあるので、
  **選択中はスタックにもRAMにも触れない**（レジスタだけで完結させる）。割り込み（VSYNC ハンドラ）がスタックへ積むと壊れるので、
  選択の前に `DI`、OUT 0x5F でメインRAMへ戻したあとに `EI`。
- BASIC は定常状態で常に割り込みを許可しており、グラフィック文を割り込み禁止で呼ぶ経路は無いので、`EI` は無条件にした
  （`LD A,I` の P/V は NMOS Z80 で割り込み直前に誤った値を返しうるため、保存・復元はしない）。
- 長い処理（cls 2・3 の塗りつぶし）は 128 バイトごとに DI〜EI で区切る。
- 点の書き込みは、公式が使う OUT 0x34/0x35（ビットの意味は未測定）ではなく、プレーン選択（0x5C〜0x5E）の読み書きにした
  （l4-graphics.md 第2節: 「実装は同じ画素が立つことが本質」）。ポート列そのものを公式に合わせる必要が出たら、gx_plot の中だけを差し替える。

## 7. 副作用（測定で見えたもの）

- 実行の時間が変わる要因は3つ: (1) 文の語の表に4語足した（代入文などが文頭で表を引いて外れる経路が長くなる）、
  (2) 式の中の識別子ごとに POINT( を先に見る（FN_TRY_NUM の入口）、(3) CLS が bank2 経由になった。
  3つを全部外した ROM は `l4_console_measure` の cls 系3腕で HEAD と cur_n・cur_pre まで一致し、1つ外すだけでは一致しない
  （外す要素によって cur_n が増減両方向に動く）。
- `l4_console_measure` の cursor 判定は「終了の印を打つ直前に垂直同期が拾った位置」で、cls の直後に垂直同期が1回入るかどうかで
  「cls 前の位置（旧）」か「ホーム（新）」かが決まる。実行時間が少し変わるとこの位相が入れ替わる。HEAD→68d36c5 で
  agree→differ が4腕（sc20-0_3・sc20-0_2・sc20-17_2・sc25-full-f0）、differ→agree が4腕（sc20-10_9・sc25-0_3・sc25-20_3・sc25-23_1）、
  全判定 243項目の agree 103・differ 140 は HEAD と同数、rows・z・err・ポート値は全腕で同一。colorattr は全82腕が HEAD でも関門失敗で、
  差は mix80-m2・mix40-m2 の cur の個数（1）だけ。
- PSET の速さは 1 文あたり約 1 フレーム未満（BASIC の式評価が支配的）。
