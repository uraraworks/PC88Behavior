# 事前登録: l4-c2c — 直接モードPRINT適合の場面固定

記録日: 2026-09-15
状態: 事前登録、器具作成前

## 位置づけ

`l4-c2b`（事前登録`43071f2`、結果`8b924bf`）で、直接モードPRINTのP1〜P5
（16腕）が全て`print_matches`だった。本ノートは、`l4-c1b`（打鍵エコー、
事前登録`6b206b5`、器具`a6d9b3e`、結果`4422f92`）が打鍵エコーを
`tools/conform_l4.sh`の適合の場面として固定したのと同じ作法で、この
P1〜P5の16腕を**同じランナーに場面として追加する**ための事前登録である
（M7・M8。依頼: l4-c2bで一致した16腕を適合テストの場面として足す）。

## 比べるもの（最下行・バナー行・P6のエラー行は比較しない。判定の定義は
この節を参照する）

`l4-c2b`「比べるもの」節のP1〜P5の定義をそのまま引き継ぐ。

- 出力の行（打った行の次の行から、`Ok`の行の直前まで）のうち「前が
  空白だったセル」の(相対の行, 相対の桁, 文字コード)の並び。原点は
  **打った行の先頭のセル**（列は0固定。`l4-c2`/`l4-c2b`と同じ定義。
  `l4-c1b`の「最初に変化した空白セル」を原点にする方式とは異なる）
- `Ok`の行の相対の行（内容そのものは比較にも記録にも使わない。行位置
  だけを見る）
- **比較しない**: バナーの行、最下行（ファンクションキー表示行）、
  P6（構文の誤り2腕。`l4-c2b`の開発者判断どおり比較対象から外したまま
  引き継ぐ）、位置の絶対値（row0そのもの）、`Ok`行自身の文字コード
  （"Ok"という2文字はBASIC自身の定型応答であり、打鍵の直接の結果でも
  自分の入力でもないため、cellsの並びには含めない。相対行番号だけを
  記録する）

## 腕（16腕。`l4-c2`/`l4-c2b`のP1〜P5をそのまま使う。P6は含めない）

`l4-c2b`「腕」節のP1〜P5と完全に同一（変更しない）。

- P1 整数(5): `print 1`・`print 0`・`print -5`・`print 32767`・
  `print -32768`
- P2 式(3): `print 2*(3+4)`・`print 1+2*3`・`print -(4)`
- P3 文字列と区切り(5): `print "q7z"`・`print 1;2`・`print "a";"b"`・
  `print "a","b"`・`print 1,2`
- P4 行末の区切り(2): `print "a";:print "b"`・`print "a",:print "b"`
- P5 省略形(1): `? 7`

腕の総数: P1(5) + P2(3) + P3(5) + P4(2) + P5(1) = **16腕**。

## 条件・フレーム

`l4-c2`/`l4-c2b`の条件節と同一の式をそのまま使う。

- 起動settle`--type-at 300 --type '\n'`、実打鍵開始`--type-at 700`
- 1文字あたり`hold+gap=8`フレーム/文字（`--type`の既定値。末尾の
  `\n`（Enter）も1文字として数える。`tools/harness/frontend/main.c`の
  `schedule_typing()`が`\n`を1トークンとして同じ間隔で進める仕様どおり）
- フレーム計算式:
  ```
  line_end = 700 + 8 * (打鍵文字列の長さ。末尾の\nを含む)
  dump     = line_end + 20
  run      = dump + 200
  ```
- 写しは打鍵前（`--type-at`の10フレーム前=690）と`dump`後の2枚を
  `--diff-before`/`--diff-after`に渡す（`tools/l4_vram_probe.py`差分
  モード、`--count-only-rows 19`を必ず付ける）
- 自作main ROMは測定開始時のHEADで`python3 src/build_main_rom.py <新規dir>`
  により1回だけ組み立て、以後の全走で複製して使い回す
  （`tools/conform_l4.sh`既存部分・`l4-c2b`と同じ作法）
- 公式ROM一式は`PC88_REF_ROM_DIR`から走ごとに新しいROMディレクトリへ
  `cp -p`するだけ（中身は読まない）。ディスク無し

## 記録する内容（正規化・ハッシュ化する道具を新設する）

`tools/l4_echo_conform_record.py`はP1〜P5の比較項目（原点列0固定・
Ok行を除いた出力セル列・Ok相対行）を作れない設計（原点を最初の空白
変化セルから決め、Ok行も含めて全部セルとして数える）ので、そのまま
使い回さない。**新設する`tools/l4_print_conform_record.py`が
`tools/l4_vram_probe.py`の`diff_vram_dumps`をそのままimportして使う**
（二重実装しない。`l4_echo_conform_record.py`と同じ作法）。

正規化の中身:
- `origin_row` = 変化した行(文字域・属性域を問わず`char_changes`に
  現れた行)のうち最小のrow0（=打った行。列は使わず0固定として扱う）
- `ok_row` = 変化した行のうち最大のrow0（=Okの行。`l4-c2b`の結果が
  示すとおり、P1〜P5はいずれも「打った行→出力行→Ok行」の3行構成で
  Ok行が常に最後に変化する行になる）
- `cells`: `origin_row`より大きく`ok_row`より小さい行(=出力行)の
  「前が空白だったセル」を、(row0-origin_row, col0, 文字コード)に
  正規化した並び（列は`0`基準にしない。原点定義が列0固定のため、
  相対列=col0そのもの）
- `ok_relative_row` = `ok_row - origin_row`
- 上記をJSON(sort_keys, 区切り無し)に直列化してSHA-256を取る
- 出力(TSV、1行): `cell_count<TAB>ok_relative_row<TAB>sha256`
  （文字コード・列位置そのものはハッシュの中にしか現れない。
  CLAUDE.md禁止事項7遵守）

## 期待値ファイル

`tests/conformance/expected_l4_print.tsv`。値そのもの（文字コード・
セル位置の並び）は一切コミットしない。件数（`cell_count`）と
`ok_relative_row`とSHA-256のみ（`expected_l4_echo.tsv`と同じ作法、
CLAUDE.md禁止事項4）。

書式（TSV、1行1腕）:
```
arm<TAB>cell_count<TAB>ok_relative_row<TAB>sha256
```

生成: 公式ROM一式(`PC88_REF_ROM_DIR`)で16腕それぞれ**2走**実施し
（G3決定論性の確認を兼ねる）、2走の記録が完全一致した腕を採用する。
作業ディレクトリ`_emulator/PC88/tmp/l4-c2c-work/`（結果ノート作成後に
削除）。

## 自作ROM側の照合のしかた

`tools/conform_l4.sh`の既存の二層方針（`l4-c1b`分）と同じ:

- 自作ROM側の照合は**公式環境の有無に関わらず常に**、コミット済みの
  `expected_l4_print.tsv`とだけ照合して回る
- 公式環境（`PC88_REF_ROM_DIR`）が無い環境では、公式側の再導出は
  **目立つSKIP**（既存の打鍵エコー場面のSKIP注記と同じ形）にする
- 既存の打鍵エコーの場面（`ARM_NAMES`・`arm_params`・
  `expected_l4_echo.tsv`）はそのまま残し、振る舞いを変えない。PRINT場面
  は別配列・別関数（例: `PRINT_ARM_NAMES`・`print_arm_params`）として
  並置する

## 判定名（本事前登録で定める。この3つ以外は作らない。`l4-c1b`と同じ名前
を踏襲する）

- `conform`: 記録する内容（cell_count・ok_relative_row・SHA-256）が
  期待値と完全に一致する
- `not_conform`: 上記のいずれかが一致しない。一致しない具体的な形
  （件数不一致かSHA-256不一致か）を判定名の後に文章で記述する。値
  そのもの（文字コード・セル位置の並び）は出さない（期待値ファイル
  自体が値を持たないため）
- `gate_failed`: 関門（下記G1〜G5）のいずれかが偽だった腕。判定に
  含めず、理由を記述する

## 関門

`l4-c1b`・`l4-c2b`と同一（G1〜G5）。

- G1 器具の自己検査: 測定時HEADで`tools/harness/vram_dump_selftest.sh`・
  `tools/harness/vram_dump_dynamic_selftest.sh`・
  `tools/harness/mem_write_log_selftest.sh`・
  `tools/harness/key_matrix_selftest.sh`・
  `tools/screen_content_leak_selftest.sh`の全項目がOK
- G2 取りこぼし0・打てない文字の警告0（全走のstderrで確認）
- G3 決定論性: 公式ROM側、各腕2走とも記録(cell_count/ok_relative_row/
  sha256)が完全一致
- G4 陰性対照: 何も打たない走（起動settleのみ）で、差分（文字域・属性域
  とも）が0件（既存の打鍵エコー場面の陰性対照をそのまま使い回す。PRINT
  専用の陰性対照は追加しない——起動直後のVRAM状態は場面に依らず共通の
  ため二重に測る意味が無い）
- G5 自作ROM側の`tools/l4_basic_selftest.sh`と`tools/l3_main_selftest.sh`
  が、測定時HEADでともにrc=0

## 検出力の自己検査（`tools/conform_l4.sh`が常に実行する。公式環境不要）

`l4-c1b`分の自己検査a・b1・c・dと同じ構造をPRINT用の記録に対しても行う:

- a. 自作ROM側の記録を模した対照データの1バイト（属性またはセルの
  文字コード）を変えるとSHA-256が変わる（検出力の確認）
- b. 正しい記録は期待値と`conform`、壊した記録は`not_conform`
- c. 期待値の1行の`cell_count`または`ok_relative_row`を壊すと、正しい
  記録との照合でも`not_conform`になる（件数不一致の検出）
- d. 期待値の1行のSHA-256を壊すと`not_conform`になる（ハッシュ不一致の
  検出）

## 判定後の行き先

- 16腕すべてが`conform`なら、この場面は`tools/conform_l4.sh`に固定
  済みとして扱う（`tools/run_all_selftests.sh`の既存登録
  `"tools/conform_l4.sh:0"`は変えない。conform_l4.sh全体のrcが0のまま
  回る前提）
- いずれかが`not_conform`なら、原因を結果ノートに記述し次の作業の
  入力にする

## 結果ノート

`docs/notes/l4-c2c-print-conformance-scene-results.md`に書く。関門・
判定名・数え方は本ノートから動かさない。

## 根拠リンク

[l4-c2b-print-conformance-rerun-preregistration.md](l4-c2b-print-conformance-rerun-preregistration.md)
（`43071f2`）・
[l4-c2b-print-conformance-rerun-results.md](l4-c2b-print-conformance-rerun-results.md)
（`8b924bf`、P1〜P5全16腕`print_matches`）・
[l4-c1b-echo-conformance-scene-preregistration.md](l4-c1b-echo-conformance-scene-preregistration.md)
（`6b206b5`、`tools/conform_l4.sh`の二層方針・期待値を件数とSHA-256だけに
する作法・判定名を事前登録で固定する作法の原型）・
`tools/conform_l4.sh`（`a6d9b3e`、既存の打鍵エコー場面の実装）・
`tools/l4_echo_conform_record.py`（正規化・ハッシュ化の既存実装。原点定義
が異なるため今回は流用せず新設する根拠）・`tools/l4_vram_probe.py`
（差分モード・`--count-only-rows`）。
