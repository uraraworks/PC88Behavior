# 事前登録: l4-c3 — 直接モードPRINT浮動小数点の適合場面固定

記録日: 2026-09-15
状態: 事前登録、測定・器具作成前

## 位置づけ

`l4-c2c`（事前登録`0a2117f`、器具`fb72104`、測定`90ab7ce`）で、整数・
文字列のPRINT16腕を`tools/conform_l4.sh`の適合の場面として固定した。
浮動小数点の書式は`l4-s4a`〜`l4-s4f`の測定と仕様書`docs/spec/
l4-basic.md`第3.3版（`4df3908`）第5節で確定したので、本ノートは
`l4-c2c`と同じ作法で、浮動小数点のPRINTを同じランナーに場面として
追加するための事前登録である。

**自作main ROM側の実装は段階4a（単精度）・4b（倍精度）で進行中**（別
担当が`src/l4_basic/`・`tools/`を並行して作業中）であるため、
**公式側の期待値を先に固定し、自作側は群ごとに実装が済んでから後で
照合する**（CLAUDE.md「コミット規律」の「測定コミットが実装コミットに
先行する」の順序をそのまま踏襲する）。

## 比べるもの（最下行・バナー行・エラー行は比較しない。判定の定義は
この節を参照する）

`l4-c2c`「比べるもの」節の定義をそのまま引き継ぐ。

- 出力の行（打った行の次の行から、`Ok`の行の直前まで）のうち「前が
  空白だったセル」の(相対の行, 相対の桁, 文字コード)の並び。原点は
  **打った行の先頭のセル**（列は0固定。`l4-c2`/`l4-c2b`/`l4-c2c`と
  同じ定義）
- `Ok`の行の相対の行（内容そのものは比較にも記録にも使わない。行位置
  だけを見る）
- **比較しない**: バナーの行、最下行（ファンクションキー表示行）、
  位置の絶対値（row0そのもの）、`Ok`行自身の文字コード（`l4-c2c`と
  同じ理由）
- **範囲外・0除算の腕は本場面に含めない**（`l4-s4a`のX1・X2に相当する
  腕は立てない。エラー行はROMのデータであり比較対象から外す方針を
  `l4-c2b`のP6以来踏襲しているため）

## 腕（単精度群FS 17腕・倍精度群FD 8腕、計25腕）

打鍵はそのまま使う（`l4-s4a`〜`l4-s4f`で使った腕のうち、単精度・倍精度
それぞれの固定⇔指数切替の確定規則を代表する腕を選び直したもの。
`l4-s4a`〜`l4-s4f`の腕番号とは対応しない新しい選定）。

### FS（単精度、17腕）

`print 1.5`・`print .5`・`print -.5`・`print 1/3`・`print 2/3`・
`print 9999999`・`print 1e10`・`print -1.5e+20`・`print .001`・
`print 1e-7`・`print 1e-8`・`print 40000`・`print 30000+30000`・
`print -32768-1`・`print 7/2`・`print 1234567`・`print 1.23456e-3`

### FD（倍精度、8腕）

`print 1#/3`・`print 1d16`・`print 1234567890123456#`・
`print 1#/30`・`print 1.23456789012345d-3`・`print 1d-16`・
`print 1.5d-15`・`print 12345678`

腕の総数: FS(17) + FD(8) = **25腕**。

## 条件・フレーム

`l4-c2c`の条件節と同じ式を土台にするが、**写しの時刻は`l4-s4d`追補
（`e80a55b`）の教訓（長い浮動小数点の出力は+20フレームの余裕では描画
途中で切れることがあった）を踏まえ、全腕一律で延長する**。

- 起動settle`--type-at 300 --type '\n'`、実打鍵開始`--type-at 700`
- 1文字あたり`hold+gap=8`フレーム/文字（`--type`の既定値。末尾の`\n`
  も1文字として数える）
- フレーム計算式（`l4-s4d`追補以降と同一の延長を適用）:
  ```
  line_end = 700 + 8 * (打鍵文字列の長さ。末尾の\nを含む)
  dump     = line_end + 300   （l4-s4d追補以降と同じ、全腕一律）
  run      = dump + 200
  ```
- 写しは打鍵前（`--type-at`の10フレーム前=690）と`dump`後の2枚を
  `--diff-before`/`--diff-after`に渡す（`tools/l4_vram_probe.py`差分
  モード、`--count-only-rows 19`を必ず付ける）
- 自作main ROMは測定開始時のHEADで`python3 src/build_main_rom.py <新規dir>`
  により1回だけ組み立て、以後の全走で複製して使い回す（`l4-c2c`と同じ
  作法）
- 公式ROM一式は`PC88_REF_ROM_DIR`から走ごとに新しいROMディレクトリへ
  `cp -p`するだけ（中身は読まない）。ディスク無し

## 記録する内容

`l4-c2c`の`tools/l4_print_conform_record.py`（正規化: `origin_row`・
`ok_row`・`cells`・`ok_relative_row`、`tools/l4_vram_probe.py`の
`diff_vram_dumps`をimportして使う設計）をそのまま使い回す。浮動小数点
特有の正規化（丸め・指数記号の扱い等）は追加しない——出力行の非空白
セル列をそのまま(row0-origin_row, col0, 文字コード)として記録する
という規則自体は整数・文字列と変わらないため。

出力(TSV、1行): `cell_count<TAB>ok_relative_row<TAB>sha256`
（`l4-c2c`と同一の書式）。

## 期待値ファイル

`tests/conformance/expected_l4_float.tsv`（**器具の担当が作る**。本
ノートの担当範囲外）。値そのもの（文字コード・セル位置の並び）は一切
コミットしない。件数（`cell_count`）と`ok_relative_row`とSHA-256のみ
（`expected_l4_print.tsv`と同じ作法、CLAUDE.md禁止事項4）。

書式（TSV、1行1腕）:
```
arm<TAB>cell_count<TAB>ok_relative_row<TAB>sha256
```

生成: 公式ROM一式(`PC88_REF_ROM_DIR`)で25腕それぞれ**2走**実施し
（G3決定論性の確認を兼ねる）、2走の記録が完全一致した腕を採用する。

## 自作ROM側の照合のしかた

`tools/conform_l4.sh`の既存の二層方針（`l4-c1b`・`l4-c2c`分）と同じ
だが、次の点が異なる。

- 自作ROM側の実装は段階4a（単精度）・4b（倍精度）で進行中のため、**群
  の実装が済むまでは、その群の腕を`not_implemented_yet`として記録
  でき、判定から外してよい**（本事前登録で定義する新しい判定名。下記
  「判定名」節参照）。
- 公式側の期待値（`expected_l4_float.tsv`）は、実装の進行状況に関わら
  ず本ノートの手順で先に固定する（「位置づけ」節のとおり、測定が実装
  に先行する順序を保つ）。
- 公式環境（`PC88_REF_ROM_DIR`）が無い環境では、公式側の再導出は**目立
  つSKIP**（既存の場面のSKIP注記と同じ形）にする。
- 既存の打鍵エコー・整数/文字列PRINTの場面（`ARM_NAMES`・
  `PRINT_ARM_NAMES`等）はそのまま残し、振る舞いを変えない。浮動小数点
  PRINT場面は別配列・別関数（例: `FLOAT_ARM_NAMES`・
  `float_arm_params`）として並置する。

## 判定名（本事前登録で定める。この4つ以外は作らない。`l4-c2c`の3つに
新しい名前を1つ加える）

- `conform`: 記録する内容（cell_count・ok_relative_row・SHA-256）が
  期待値と完全に一致する
- `not_conform`: 上記のいずれかが一致しない。一致しない具体的な形
  （件数不一致かSHA-256不一致か）を判定名の後に文章で記述する。値
  そのものは出さない
- `gate_failed`: 関門（下記G1〜G6・G8）のいずれかが偽だった腕。判定に
  含めず、理由を記述する
- **`not_implemented_yet`**（新設）: **自作ROM側で、その腕が属する群
  （単精度FS・倍精度FD）の実装がまだ完了していないために照合自体を
  行っていない腕。判定外として扱う**（`conform`にも`not_conform`にも
  数えない）。公式側の期待値がすでに固定されているかどうかとは独立に、
  自作main ROM側の実装状況だけで判定する。群の実装が完了し、自作ROM
  側の照合を実際に行った後は、この判定名は使わず`conform`/
  `not_conform`のいずれかに移る

## 関門

`l4-c2c`のG1〜G5に加え、`l4-s4d`追補以降のG8（出力完了の確認）を含める。

- G1 器具の自己検査: 測定時HEADで`tools/harness/vram_dump_selftest.sh`・
  `tools/harness/vram_dump_dynamic_selftest.sh`・
  `tools/harness/mem_write_log_selftest.sh`・
  `tools/harness/key_matrix_selftest.sh`・
  `tools/screen_content_leak_selftest.sh`の全項目がOK
- G2 取りこぼし0・打てない文字の警告0（全走のstderrで確認）
- G3 決定論性: 公式ROM側、各腕2走とも記録(cell_count/ok_relative_row/
  sha256)が完全一致
- G4 陰性対照: 何も打たない走（起動settleのみ）で、差分（文字域・属性域
  とも）が0件（`l4-c2c`と同じく既存の陰性対照を使い回し、専用のものは
  追加しない）
- G5 自作ROM側の`tools/l4_basic_selftest.sh`と`tools/l3_main_selftest.sh`
  が、測定時HEADでともにrc=0（自作側の照合を行う腕についてのみ。
  `not_implemented_yet`の腕はG5の対象から外れる——その群の実装自体が
  無いため）
- **G8 出力完了の確認**: 「後」の写しで、出力行の後に`Ok`行が現れて
  いること（`ok_relative_row`相当の値が得られること）。現れない腕は
  `gate_failed`とし、「写しが早すぎた」とだけ記述する（`l4-s4d`追補と
  同一の関門。写しの時刻を`dump=line_end+300`へ延長した後も、念のため
  この関門で確認する）

## 検出力の自己検査（`tools/conform_l4.sh`が常に実行する。公式環境不要）

`l4-c2c`分の自己検査a〜dと同じ構造を、浮動小数点用の記録に対しても
行う（器具の担当が実装する。本ノートは要件のみ定める）。

- a. 自作ROM側の記録を模した対照データの1バイトを変えるとSHA-256が
  変わる（検出力の確認）
- b. 正しい記録は期待値と`conform`、壊した記録は`not_conform`
- c. 期待値の1行の`cell_count`または`ok_relative_row`を壊すと、正しい
  記録との照合でも`not_conform`になる（件数不一致の検出）
- d. 期待値の1行のSHA-256を壊すと`not_conform`になる（ハッシュ不一致
  の検出）

## 判定後の行き先

- 公式側の期待値25腕すべてが固定できたら（G1〜G4・G8を満たし、各腕
  2走の記録が一致）、`tests/conformance/expected_l4_float.tsv`を
  コミットする。この時点では自作ROM側は`not_implemented_yet`のままで
  よい。
- 自作ROM側の単精度（FS）実装が完了した時点で、FS群の17腕を照合し、
  `conform`/`not_conform`の判定に移す。倍精度（FD）も同様に、実装完了
  後に照合する。
- いずれかが`not_conform`なら、原因を結果ノートに記述し次の作業の
  入力にする。

## 結果ノート

`docs/notes/l4-c3-float-print-conformance-scene-results.md`に書く。
関門・判定名・数え方は本ノートから動かさない。

## 根拠リンク

[l4-c2c-print-conformance-scene-preregistration.md](l4-c2c-print-conformance-scene-preregistration.md)
（`0a2117f`、比べるもの・記録する内容・期待値ファイルの作法・判定名・
関門G1〜G5・自作ROM側二層方針の直接の原型）・
`tools/conform_l4.sh`（`fb72104`、既存の適合テストランナー）・`90ab7ce`
（l4-c2cの測定、公式環境あり/なし両方でconform）・
[l4-s4d-double-small-value-format-switch-preregistration-addendum.md](l4-s4d-double-small-value-format-switch-preregistration-addendum.md)
（`e80a55b`、写し時刻を全腕一律+300へ延長する扱い・関門G8の原型）・
`docs/spec/l4-basic.md`第3.3版（`4df3908`、第5節。単精度・倍精度の
固定⇔指数切替規則が確定した根拠）・`tools/l4_print_conform_record.py`
（正規化・ハッシュ化の既存実装、`l4-c2c`で新設・流用）・
`tools/l4_vram_probe.py`（差分モード・`--count-only-rows`）。
