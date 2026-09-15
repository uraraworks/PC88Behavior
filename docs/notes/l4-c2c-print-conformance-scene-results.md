# l4-c2c — 直接モードPRINT適合の場面固定 — 結果

事前登録: [l4-c2c-print-conformance-scene-preregistration](l4-c2c-print-conformance-scene-preregistration.md)
（`0a2117f`）。器具: `tools/conform_l4.sh`・`tools/l4_print_conform_record.py`・
`tests/conformance/expected_l4_print.tsv`（`fb72104`）。判定名・記録項目・
関門・数え方は事前登録から動かしていない。

## 器具

- 測定時HEAD: `0a2117f0dabfdd09d3b10182debe7a5e171ac97e`
  （事前登録コミット直後。以降、測定終了まで`docs/notes`追加のみで
  `src/`は変更していない）
- 自作ROM一式: 測定時HEADで`python3 src/build_main_rom.py <新規dir>`により
  1回だけ組み立て、期待値作成時の全走で複製して使い回した
- 公式ROM一式: `PC88_REF_ROM_DIR`（`private/rom`）から`*.ROM`を走ごとに
  新しいROMディレクトリへ`cp -p`するだけ（中身は読まない）。ディスク無し
- 作業ディレクトリ: リポジトリ外`_emulator/PC88/tmp/l4-c2c-work/`
  （期待値作成用の使い捨てドライバ。本ノート作成後に削除）

## 期待値作成（公式ROM、16腕×2走）

事前登録の式（`line_end=700+8*(打鍵文字列長、末尾\n含む)`・`dump=line_end+20`・
`run=dump+200`）どおりに全16腕を2走ずつ実施し、`tools/l4_print_conform_record.py`
の記録(`cell_count`/`ok_relative_row`/`sha256`)が全16腕でrun1=run2の完全一致
だった（G3）。同時に自作ROM一式でも同じ16腕を1走ずつ測り、**全16腕で公式
ROMの記録と完全一致**した（`l4-c2b`の`print_matches`全16腕という結果を、
本場面専用の器具でも再確認した形）。この記録をそのまま
`tests/conformance/expected_l4_print.tsv`に採用した。

## `tools/conform_l4.sh` の実行結果

### 公式環境が無い場合（`PC88_REF_ROM_DIR`未設定）

- 打鍵エコー場面（既存11腕）: 自作ROM側 `conform: 11/11`
- PRINT場面（新設16腕）: 自作ROM側 `conform: 16/16`
- 公式ROM側は両場面とも目立つSKIP（「公式ROMの環境変数
  (PC88_REF_ROM_DIR)が未設定」）
- 全体の終了コード: 0（`conform_l4: 自作ROM側の照合OK・公式側はSKIP
  （公式環境未設定）`）
- 所要時間: 約19秒

### 公式環境がある場合（`PC88_REF_ROM_DIR=private/rom`）

- 打鍵エコー場面: 自作ROM側 `conform: 11/11`、公式ROM側 `conform: 11/11`
  （引き続きconform。既存場面の振る舞いは変えていない）
- PRINT場面: 自作ROM側 `conform: 16/16`、公式ROM側 `conform: 16/16`
- `not_conform`・`gate_failed`は両場面・両ROMとも0件
- 全体の終了コード: 0（`conform_l4: 自作ROM側・公式ROM側とも全項目OK`）
- 所要時間: 約40秒

## 故障注入（検出力の自己検査。公式環境不要、`tools/conform_l4.sh`が
常に実行する）

事前登録どおり、PRINT場面用に打鍵エコー場面と同型の自己検査a・b1・c・dを
追加し、上記いずれの実行でも全項目OKだった。

- 自己検査a: 記録（出力セルの文字コード相当の1バイト）を変えるとSHA-256が
  変わる（検出力あり）
- 自己検査b1: 正しい記録は期待値と`conform`、壊した記録は`not_conform`
- 自己検査c: 期待値の1行の件数(`cell_count`)を壊すと、正しい記録でも
  `not_conform`で検出される
- 自己検査d: 期待値の1行のSHA-256を壊すと`not_conform`で検出される

## 判定

- P1〜P5（16腕）: 公式ROM側・自作ROM側とも全16腕`conform`
- 公式環境が無い環境での自作ROM側の照合: 全16腕`conform`
  （コミット済み`expected_l4_print.tsv`だけで独立に回る。M8）
- 故障注入（自作側記録1バイト変更→`not_conform`、期待値1行破壊→検出）:
  いずれもOK
- 打鍵エコーの場面（既存11腕）: 引き続き`conform`（振る舞いを変えていない）

## 判定後の行き先

事前登録どおり、この場面は`tools/conform_l4.sh`に固定済みとして扱う。
`tools/run_all_selftests.sh`の既存登録(`"tools/conform_l4.sh:0"`)は変えて
いない（変更後もconform_l4.sh全体のrcは0のまま回る）。

## 生データ

期待値作成用の使い捨てドライバ・写し・記録・自作ROM一式は使い捨ての
作業ディレクトリ（`_emulator/PC88/tmp/l4-c2c-work/`）に置き、本ノートを
書いたあと削除した。
