# l4-c3 — 直接モードPRINT浮動小数点の適合場面固定 — 結果

事前登録: [l4-c3-float-print-conformance-scene-preregistration](l4-c3-float-print-conformance-scene-preregistration.md)
（`71d81a8`）。器具: `tools/conform_l4.sh`（FLOAT_ARM_NAMES/float_arm_params/
群ごとの実装状態表示/検出力自己検査a〜e）・
`tests/conformance/expected_l4_float.tsv`のヘッダ・群状態表示（`0cce846`）。
判定名・記録項目・関門・数え方は事前登録から動かしていない。

## 器具

- 測定時HEAD（器具コミット直後）: `0cce846`
- 記録の正規化・ハッシュ化は`tools/l4_print_conform_record.py`をそのまま
  使い回した（l4-c2cから二重実装しない）。写しの時刻はl4-s4d追補以降の
  全腕一律延長（`dump=line_end+300`・`run=dump+200`）を適用し、関門G8
  （出力完了の確認）を満たした2走のみを採用した。
- 自作main ROM一式: `python3 src/build_main_rom.py`により1回だけ組み立て、
  以後の全走で複製して使い回した（l4-c2cと同じ作法）。単精度(FS)・
  倍精度(FD)とも段階4a/4bの実装が進行中のため、`expected_l4_float.tsv`
  の見出しコメントで両群とも`selfmade=not_implemented_yet`とし、
  自作ROM側の照合は判定外(`not_implemented_yet`)として表示するだけに
  とどめた。
- 公式ROM一式: `PC88_REF_ROM_DIR`（`private/rom`）から`*.ROM`を走ごとに
  新しいROMディレクトリへ`cp -p`するだけ（中身は読まない）。ディスク無し

## 期待値作成（公式ROM、25腕×2走）

事前登録の式（`line_end=700+8*(打鍵文字列長、末尾\n含む)`・
`dump=line_end+300`・`run=dump+200`）どおりに全25腕（FS単精度17腕・
FD倍精度8腕）を2走ずつ実施した。

- G1（器具の自己検査）: `vram_dump_selftest.sh`・
  `vram_dump_dynamic_selftest.sh`・`mem_write_log_selftest.sh`・
  `key_matrix_selftest.sh`・`screen_content_leak_selftest.sh`の全項目OK
- G2（取りこぼし0・打てない文字の警告0）: 全50走のstderrで該当行0件
- G3（決定論性）: 25腕全てでrun1=run2の記録（`cell_count`/
  `ok_relative_row`/`sha256`）が完全一致
- G4（陰性対照）: 何も打たない走で文字域・属性域・row19とも変化0件
- G5（陽性対照）: `print 7717\n`の出力行(相対行+1)の相対列1-4に文字
  コード`37 37 31 37`(`7717`)が連続4セルとして出現
- G8（出力完了の確認）: 25腕全てで`ok_relative_row=2`（1以下、または
  `NA`になった腕は無かった）

G1〜G5・G8すべて真のため、`gate_failed`として除外した腕は無い。25腕
全てで2走の記録が完全一致し、この記録をそのまま
`tests/conformance/expected_l4_float.tsv`に採用した（値そのものは含めず、
`cell_count`/`ok_relative_row`/`sha256`のみ）。

## `tools/conform_l4.sh` の実行結果

### 公式環境が無い場合（`PC88_REF_ROM_DIR`未設定）

- 打鍵エコー場面（既存11腕）: 自作ROM側 `conform: 11/11`
- PRINT場面（既存16腕）: 自作ROM側 `conform: 16/16`
- **FLOAT場面（新設25腕）**: 自作ROM側 `not_implemented_yet: 25/25`
  （FS・FDとも`not_implemented_yet`。`na()`による黄色`--`の判定外表示で、
  既存場面のSKIP（cat見出しブロック）とは別の表示。rcには含まれない）
- 検出力の自己検査a〜d(FLOAT)・自己検査e(群の印の切替)は全項目OK
- 公式ROM側は3場面ともSKIP（「公式ROMの環境変数(PC88_REF_ROM_DIR)が
  未設定」）
- 全体の終了コード: **0**
  （`conform_l4: 自作ROM側の照合OK・公式側はSKIP（公式環境未設定）`）

### 公式環境がある場合（`PC88_REF_ROM_DIR=private/rom`）

- 打鍵エコー場面: 自作ROM側 `conform: 11/11`、公式ROM側 `conform: 11/11`
- PRINT場面: 自作ROM側 `conform: 16/16`、公式ROM側 `conform: 16/16`
- **FLOAT場面**: 自作ROM側 `not_implemented_yet: 25/25`（引き続き判定外）、
  **公式ROM側 `conform: 25/25`**（`not_conform`・`gate_failed`とも0件。
  公式ROMを2走再導出した記録が`expected_l4_float.tsv`の全25行と一致）
- 全体の終了コード: **0**
  （`conform_l4: 自作ROM側・公式ROM側とも全項目OK`）

## 故障注入（検出力の自己検査。公式環境不要、`tools/conform_l4.sh`が
常に実行する）

事前登録どおり、FLOAT場面用にPRINT場面と同型の自己検査a・b1・c・dを
追加し、上記いずれの実行でも全項目OKだった（既存の
`check_print_record_against_expected`をそのまま使い回し、二重実装は
していない）。

- 自己検査a(FLOAT): 記録（出力セルの文字コード相当の1バイト）を変えると
  SHA-256が変わる（検出力あり）
- 自己検査b1(FLOAT): 正しい記録は期待値と`conform`、壊した記録は
  `not_conform`
- 自己検査c(FLOAT): 期待値の1行の`cell_count`を壊すと、正しい記録でも
  `not_conform`で検出される
- 自己検査d(FLOAT): 期待値の1行のSHA-256を壊すと`not_conform`で検出
  される

さらに本場面で新設した自己検査e（群の印の切替）も全項目OKだった。
実データではなく、明らかに不一致になる合成の期待値行（`cell_count=999`・
架空のSHA-256）を使い、実際の自作ROM(`SELF_ROMDIR`)に対して走らせた。

- 自己検査e-1: 見出しコメントが`selfmade=not_implemented_yet`のとき、
  `float_group_status`が`not_implemented_yet`を正しく返す
- 自己検査e-2: 見出しコメントを`selfmade=implemented`に書き換えると、
  `float_group_status`が`implemented`を正しく返す
- 自己検査e-3: `implemented`にした状態で実際に自作ROMを走らせて合成の
  期待値と照合すると、`not_conform`（または走行自体の失敗）として
  **NG**になった。すなわち、`not_implemented_yet`による判定外の扱いは
  「本物の判定を隠していない」——実際に照合させれば、未実装ゆえの不一致
  がちゃんと検出できる状態であることを確認した

## 判定

- FS（単精度17腕）・FD（倍精度8腕）: 公式ROM側は全25腕`conform`
  （2走一致・期待値とも一致）
- 自作ROM側: 全25腕`not_implemented_yet`（判定外、rc算入なし）。段階4a
  （単精度）・4bの実装が完了した時点で、見出しコメントを`implemented`
  に書き換えれば`conform`/`not_conform`の実判定に移る設計になっている
  ことを自己検査eで確認済み
- 打鍵エコー・整数/文字列PRINTの場面（既存27腕）: 振る舞いを変えず、
  引き続き自作・公式とも全`conform`
- 故障注入（FLOAT場面の記録・期待値を壊す自己検査a〜d、群の印を切り替
  える自己検査e）: いずれもOK

## 判定後の行き先

事前登録どおり、公式側の期待値25腕は`tests/conformance/
expected_l4_float.tsv`にコミット済みとして固定する。自作ROM側の単精度
（FS）実装が完了した時点でFS群の見出しコメントを`implemented`に書き換え
FS群17腕を照合し、`conform`/`not_conform`の判定に移す。倍精度（FD）も
実装完了後に同様に切り替える。実装担当（`src/l4_basic/`・
`tools/l4_mbf_*`）への申し送りとして、本ノートと器具コミット
（`0cce846`）を参照する。

## 生データ

期待値作成用の使い捨てドライバ・写し・記録・自作ROM一式・公式ROM一式の
複製はリポジトリ外の作業ディレクトリ（scratchpad配下）に置き、本ノートを
書いたあと削除した。
