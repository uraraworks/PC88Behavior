# l4-c2 — 直接モードPRINTの公式・自作比較 — 事前登録

記録日: 2026-09-15
状態: 事前登録、測定前

## 位置づけ

段階3b（BASIC核、仕様書 [l4-basic.md](l4-basic.md) 第2版 `91ae29a` 準拠、並行して
実装中）の測定時HEADの自作ROM一式（自作main ROM込み）で、直接モードの
`PRINT`（および `?` 省略形）を打ち、実行結果の出力が公式ROM一式と一致するかを
確かめる場面。`l4-c1`／`l4-c1b`（打鍵エコー）が確かめたのは打鍵の反映だったが、
本ノートはゴールA（公式と同じ出力）を**BASIC の実行結果**で初めて確かめる。

`l4-basic.md` の整数・式・文字列・区切り記号の書式は `l4-s3a`・`l4-s3b`
（公式ROM一式のみの測定）から起こしたもので、自作ROM側との突き合わせはまだ
行っていない。特に構文の誤り（P6）のエラー文言は、公式ROM画面を直接見ず
（禁止事項7）**マニュアルのエラーメッセージ一覧**（`refs/manual.txt` 1125〜1161
行目、`l4-basic.md` 第1.1版の根拠、`docs/notes/refs-manual-error-messages.md`）
から採って自作ROMに実装したものであり、公式ROMの画面表示と一致するかどうかは
本ノートの場面で初めて確かめる（値は出さず、署名だけで一致／不一致を見る）。

## 比べるもの（判定の定義はこの節を参照する——l4-c1 の事前登録で2つの節が
食い違った教訓を踏まえ、判定の節は本節の名前をそのまま使う）

- 出力の行（打った行の次の行から、`Ok` の行まで）のうち「前が空白だった
  セル」の (相対の行, 相対の桁, 文字コード) の並び。原点は打った行の先頭の
  セル（`l4-s3a`・`l4-c1` と同じ定義）
- `Ok` の行の相対の行
- **エラーの行（P6のみ）**: 自作はマニュアルの一覧の文言、公式はROMの文言と
  由来が異なるため、内容そのものは比べない。比べるのは**署名だけ**——両ROM
  で「エラーの行の文字コードの並び」の件数と SHA-256 を作り、一致／不一致
  だけを記録する。値（文字コードそのもの）は出さない
- 比べない: バナーの行、**最下行**（ファンクションキー表示行。開発者判断
  2026-09-15、`l4-c1`／`l4-c1b` と同じ扱い）、位置の絶対値（row0そのもの。
  バナー行数が違うため両ROM間の比較には使えない、`l4-c1` と同じ理由）
- 最下行を比較対象から外すことは、この節と判定の節の両方に明記する
  （`l4-c1` 事前登録での食い違いを繰り返さないため）

## 腕

- P1 整数: `print 1`・`print 0`・`print -5`・`print 32767`・`print -32768`
- P2 式: `print 2*(3+4)`・`print 1+2*3`・`print -(4)`
- P3 文字列と区切り: `print "q7z"`・`print 1;2`・`print "a";"b"`・
  `print "a","b"`・`print 1,2`
- P4 行末の区切り: `print "a";:print "b"`・`print "a",:print "b"`
- P5 省略形: `? 7`
- P6 構文の誤り（エラーの行は署名だけ）: `print 1+`・`printx 1`

腕の総数: P1(5) + P2(3) + P3(5) + P4(2) + P5(1) + P6(2) = **18腕**。

（英字命令語は打鍵注入がシフト無しで小文字を送るため小文字表記とする。
`l4-s3a` 条件節と同じ根拠）

## 条件・フレーム

- 公式ROM一式・自作ROM一式とも、起動settleは既存測定と同じ
  `--type-at 300 --type '\n'`、実打鍵の開始は `--type-at 700`
  （`l4-s3a`・`l4-s3b` 条件節と同じ根拠。自作ROM側も同じ起動時間を仮定するが、
  差があれば `--diff-before`/`--diff-after` の差分抽出自体は打鍵開始時刻に
  依存しないため判定には影響しない）
- 1文字あたり `hold+gap=8` フレーム/文字（`--key-hold`/`--key-gap` 既定値、
  `l4-s3a`・`l4-c1` と同じ根拠）
- フレーム計算式（`l4-s3a`・`l4-s3b` と同じ式をそのまま使う）:
  ```
  line_end(k) = 700 + 8 * (その腕で打った文字数の累計、\n も1文字)
  dump(k)     = line_end(k) + 20   （実行の余裕。l4-s3a 同節の根拠）
  run(k)      = dump(k) + 200      （走行フレームの余裕。l4-s3a・l4-s1a の踏襲）
  ```
- 写しは打鍵前（`--type-at` の10フレーム前、`l4-s3a`・`l4-c1` と同じ間隔）と
  `dump(k)` の後の2枚を `--diff-before`/`--diff-after` に渡す
- 自作main ROMは測定時HEADで `python3 src/build_main_rom.py <新規dir>`
  により都度組み立てる（`tools/l3_main_selftest.sh` と同じ作法）。**公式ROMは
  自作ROM側の測定には一切使わない**

## 記録する内容

- 腕ごと・両ROMごとに、「比べるもの」節の並びそのもの
  （P1〜P5・P6以外は原点セル・相対セル列・`Ok`の相対行）
- P6のみ、エラーの行の件数と SHA-256（値は出さない）
- 機械可読な表で結果ノート（`docs/notes/l4-c2-print-conformance-results.md`）
  に記載する

## エラーの行の署名を作る器具

以下の既存道具の usage を確認した:

- `tools/check_l3_screen_output.py` — q88measureの「測定終了時のテキスト
  画面」節（テキストのレポートファイル）を対象にした行の署名。**入力の形が
  VRAMダンプ（`--vram-dump`）ではなくq88measureのテキスト報告であり、本場面
  の入力形式と一致しない**
- `tools/l4_vram_probe.py` — VRAMダンプの差分から「前が空白だったセル」の
  相対座標・文字コードの並びは出せるが、**行単位でまとめて件数とSHA-256だけ
  を出す署名モードは無い**（差分の正規化データそのものを返す設計）
- `tools/l4_echo_conform_record.py` — `l4_vram_probe.py` の差分出力を
  正規化・ハッシュ化するが、対象は打鍵エコーの記録全体（記録項目1・2・3・5
  相当）であり、**エラーの行1行だけを取り出して署名する機能は無い**

**結論: エラーの行だけを対象に、値を出さずに件数とSHA-256を出す器具は現状
存在しない。** 測定の前に、`tools/l4_vram_probe.py` の差分抽出（前が空白
だったセルの並び）を土台に、対象行を1行に絞ってその文字コード列を
`行番号<TAB>文字コード16進の並び<LF>` の形でハッシュ化する小道具
（leak検査つきの自己検査を含む。`tools/screen_content_leak_selftest.sh` の
陰性対照つきの作法を踏襲）を足す必要がある。器具そのものは本ノートでは
作らない。

## 本文を出さない取り扱い

- 自分が打った数・文字列・演算結果として妥当な数値の出力は値を出してよい
  （自分で指定した打鍵文字列とその直接の結果であるため、`l4-basic.md`
  「この文書の根拠」節と同じ扱い）
- エラーの行（P6）は件数と SHA-256 だけを記録し、文字コードの並びそのもの
  ・文言は一切出さない（禁止事項7、公式ROMの画面文言を扱うため）
- 前が空白でなかったセル・最下行は件数だけを記録し、位置・値は出さない
  （`l4-c1b`「比べるもの」節と同じ扱い）

## 関門

- G1 器具の自己検査: 測定時HEADで `tools/harness/vram_dump_selftest.sh`・
  `tools/harness/vram_dump_dynamic_selftest.sh`・
  `tools/harness/mem_write_log_selftest.sh`・`tools/harness/key_matrix_selftest.sh`・
  `tools/screen_content_leak_selftest.sh` の全項目がOK（本場面で新設する
  エラー行署名の小道具についても、作成時に同水準の自己検査と陰性対照を
  用意してから使う）
- G2 取りこぼし0・打てない文字の警告0（全走のstderrで確認）
- G3 決定論性: 各腕2走とも、写し・記録のsha256が一致（公式側・自作側とも）
- G4 陰性対照: 何も打たない走（起動settleのみ）で、差分（文字域・属性域とも）
  が0件
- G5 自作ROM側の `tools/l4_basic_selftest.sh` と `tools/l3_main_selftest.sh`
  が、測定時HEADでともに rc=0

## 判定（本事前登録で定めた名前だけを使う。「比べるもの」節を参照する）

- `print_matches` / `print_differs`: P1〜P5各腕、「比べるもの」節の
  原点セル・相対セル列・`Ok`の相対行が両ROMで完全に一致すれば
  `print_matches`、一致しなければ `print_differs`
- `error_signature_matches` / `error_signature_differs`: P6各腕、
  「比べるもの」節のエラー行の件数とSHA-256が両ROMで一致すれば
  `error_signature_matches`、一致しなければ `error_signature_differs`
- `gate_failed`: 関門（G1〜G5）のいずれかが偽だった腕。判定に含めず、
  理由を記述する
- 最下行は判定に含めない（「比べるもの」節と同じ）
- 全18腕が `print_matches` または `error_signature_matches` なら、
  `tools/conform_l4.sh` に本場面を追加する（期待値は件数とSHA-256のみを
  コミットし、自作ROM側は公式環境が無くても照合できる形にする。
  `tools/conform_l4.sh`（l4-c1b分）と同じ二層方針）

## 判定後の行き先

- 全腕一致なら、`tests/conformance/expected_l4_print.tsv`（件数とSHA-256の
  みを持つ新規ファイル）を作り、`tools/conform_l4.sh` に l4-c2 の場面として
  追加登録する（`tools/run_all_selftests.sh` からも回る形にする）
- `print_differs`／`error_signature_differs` を含む場合は、`docs/spec/
  l4-basic.md` と突き合わせ、実装差か仕様の未解釈かを切り分ける次の作業の
  入力にする

## 結果ノート

`docs/notes/l4-c2-print-conformance-results.md` に書く。関門・判定名・
数え方は本ノートから動かさない。

## 根拠リンク

[l4-basic.md](l4-basic.md) 第2版 `91ae29a`（PRINTの書式、エラーメッセージの
資料由来の記載）・
[l4-s3a-print-format-preregistration.md](l4-s3a-print-format-preregistration.md)
（フレーム計算式・原点定義の原型）・
[l4-s3b-print-trailing-preregistration.md](l4-s3b-print-trailing-preregistration.md)
（数の後ろの空白・行末区切りの測定条件）・
[l4-c1b-echo-conformance-scene-preregistration.md](l4-c1b-echo-conformance-scene-preregistration.md)
（最下行を「比べるもの」節と判定節の両方で除外する作法、期待値を件数と
SHA-256だけにする作法、判定名を事前登録で固定する作法）・
`tools/l4_vram_probe.py`（差分モード・`--count-only-rows`）・
`tools/l4_echo_conform_record.py`（正規化・ハッシュ化の既存実装）・
`tools/check_l3_screen_output.py`（画面本文を出さない署名の既存実装。
本場面の入力形式とは異なるため流用不可と判断した根拠）・
`tools/conform_l4.sh`（二層方針の既存実装）・
`tools/l4_basic_selftest.sh`・`tools/l3_main_selftest.sh`（自作ROM側の
組み立てと関門G5）。
