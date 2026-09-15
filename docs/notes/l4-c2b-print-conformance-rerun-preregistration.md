# l4-c2b — 直接モードPRINT適合テスト再測定 — 事前登録

記録日: 2026-09-15
状態: 事前登録、測定前

## 位置づけ

`l4-c2`（事前登録 `39eeb53`、結果ノート `4f774fb`
[l4-c2-print-conformance-results.md](l4-c2-print-conformance-results.md)、
追記 `734b490`）で、全18腕が不一致だった件の測り直し。原因は2つに
切り分いており、扱いが異なる。

- P1〜P5（16腕）: 自作ROMがSPACEキーでカーソルを前進させない実装だった
  ことによる1桁ずれ。`fc69064`（M7: SPACEキーのエコー前進を実装、
  仕様書`l3-main.md`第3.1版第9節`1439d78`）で修正済み。**本ノートで
  測り直す**
- P6（2腕、構文の誤り）: エラー行の署名不一致は、診断（`70de1bd`）と
  マニュアル確認（`1e1c119`・`02f30d6`）を尽くしても理由が特定できず、
  開発者判断（2026-09-15、`734b490`）により**当面、適合の比較の対象
  から外す**（バナーの行・最下行と同じ扱い）。本ノートではP6を比べない
  ——ただし件数（非空白セル件数）と署名（SHA-256）は引き続き記録し、
  今後の切り分けに使えるようにする

腕・打鍵文字列・フレーム計算式・原点定義・自作ROMの組み立て方は
`l4-c2`の事前登録から変えない。変えるのは自作ROMのHEAD（`fc69064`
以降で1回だけ組み立て直す）と、P6の扱い（比べない・記録のみ）だけ。

## 比べるもの（判定の定義はこの節を参照する）

- **P1〜P5（16腕、比べる）**: 出力の行（打った行の次の行から、`Ok`の行
  まで）のうち「前が空白だったセル」の(相対の行, 相対の桁, 文字コード)
  の並び。原点は打った行の先頭のセル（`l4-c2`と同じ定義）。加えて
  `Ok`の行の相対の行
- **P6（2腕、比べない・記録のみ）**: エラーの行（原点+1、`l4-c2`の
  診断`70de1bd`で確認済みの相対位置）の非空白セル件数とSHA-256だけを
  両ROMについて記録する。**判定は付けない**（`error_signature_matches`
  /`differs`のいずれも使わない）。一致・不一致の評価自体を今回は行わない
  ——理由は上記「位置づけ」節のとおり、開発者判断でこの2腕を比較対象から
  外したため
- 比べない: バナーの行、最下行（ファンクションキー表示行、`l4-c2`と
  同じ理由）、位置の絶対値（row0そのもの）

## 腕（`l4-c2`と同一、18本）

- P1 整数: `print 1`・`print 0`・`print -5`・`print 32767`・`print -32768`
- P2 式: `print 2*(3+4)`・`print 1+2*3`・`print -(4)`
- P3 文字列と区切り: `print "q7z"`・`print 1;2`・`print "a";"b"`・
  `print "a","b"`・`print 1,2`
- P4 行末の区切り: `print "a";:print "b"`・`print "a",:print "b"`
- P5 省略形: `? 7`
- P6 構文の誤り（比べない・記録のみ）: `print 1+`・`printx 1`

腕の総数: P1(5) + P2(3) + P3(5) + P4(2) + P5(1) + P6(2) = **18腕**
（内、比べるのはP1〜P5の16腕）。

## 条件・フレーム

`l4-c2`事前登録と同一。

- 起動settle`--type-at 300 --type '\n'`、実打鍵開始`--type-at 700`
- 1文字あたり`hold+gap=8`フレーム/文字
- フレーム計算式:
  ```
  line_end(k) = 700 + 8 * (その腕で打った文字数の累計、\n も1文字)
  dump(k)     = line_end(k) + 20
  run(k)      = dump(k) + 200
  ```
- 写しは打鍵前（`--type-at`の10フレーム前）と`dump(k)`の後の2枚を
  `--diff-before`/`--diff-after`に渡す（P1〜P5）。P6は`dump(k)`後の
  1枚のみを`--row-signature`に渡す（`l4-c2-error-signature-diagnosis.md`
  の作法と同じ、生差分は使わない）
- **自作main ROMは、測定開始時のHEAD（`fc69064`以降）で
  `python3 src/build_main_rom.py <新規dir>`により1回だけ組み立て、
  以後の全走で複製して使い回す**（`l4-c2`と同じ作法。並行担当の
  途中変更の影響を受けないようにするため）
- 公式ROM一式は`PC88_REF_ROM_DIR`から走ごとに新しいROMディレクトリへ
  `cp -p`するだけ（中身は読まない）。ディスク無し

## 記録する内容

- P1〜P5（16腕）: 腕ごと・両ROMごとに、原点セル・相対セル列・`Ok`の
  相対行と、判定（`print_matches`/`print_differs`）
- P6（2腕）: 腕ごと・両ROMごとに、エラー行の非空白セル件数と
  row_sha256（値は出さない）。**判定は付けない**（記録のみ）
- 機械可読な表で結果ノート
  （`docs/notes/l4-c2b-print-conformance-rerun-results.md`）に記載する

## 本文を出さない取り扱い

`l4-c2`と同一。

- 自分が打った数・文字列・演算結果として妥当な数値の出力は値を出して
  よい
- P6のエラー行は件数とSHA-256だけを記録し、文字コードの並びそのもの・
  文言は一切出さない（禁止事項7）
- 前が空白でなかったセル・最下行は件数だけを記録し、位置・値は出さない

## 関門

`l4-c2`と同一（G1〜G5）。

- G1 器具の自己検査: 測定時HEADで`tools/harness/vram_dump_selftest.sh`・
  `tools/harness/vram_dump_dynamic_selftest.sh`・
  `tools/harness/mem_write_log_selftest.sh`・
  `tools/harness/key_matrix_selftest.sh`・
  `tools/screen_content_leak_selftest.sh`の全項目がOK
- G2 取りこぼし0・打てない文字の警告0（全走のstderrで確認）
- G3 決定論性: 各腕2走とも、写し・記録のsha256が一致（公式側・自作側
  とも）。P6は`row_sha256`がrun1=run2で一致することを決定論性の確認に
  使う
- G4 陰性対照: 何も打たない走（起動settleのみ）で、差分（文字域・属性域
  とも）が0件
- G5 自作ROM側の`tools/l4_basic_selftest.sh`と`tools/l3_main_selftest.sh`
  が、測定時HEADでともにrc=0

## 判定（本事前登録で定めた名前だけを使う。「比べるもの」節を参照する）

- `print_matches`/`print_differs`: P1〜P5各腕、「比べるもの」節の原点
  セル・相対セル列・`Ok`の相対行が両ROMで完全に一致すれば`print_matches`、
  一致しなければ`print_differs`
- P6: **判定を付けない。** 件数とSHA-256を記録するだけで、一致・不一致
  の評価自体を行わない（「位置づけ」節・「比べるもの」節に明記のとおり、
  開発者判断でP6を比較対象から外したため）
- `gate_failed`: 関門（G1〜G5）のいずれかが偽だった腕。判定に含めず、
  理由を記述する
- 最下行は判定に含めない

## 判定後の行き先

- P1〜P5の16腕すべてが`print_matches`なら、
  `tests/conformance/expected_l4_print.tsv`（原点セル・相対セル列・
  `Ok`の相対行のみを持つ新規ファイル）を作り、`tools/conform_l4.sh`に
  l4-c2の場面として追加登録する準備を整える。ただし**追加登録の実作業
  自体は本ノートの担当範囲外**（依頼に基づき、親が別途決める）
- 16腕のいずれかが`print_differs`を含む場合は、原因を記述し次の作業への
  入力とする
- P6は記録のみで完結し、行き先を分岐させない（比較対象外のため）

## 結果ノート

`docs/notes/l4-c2b-print-conformance-rerun-results.md`に書く。関門・
判定名・数え方は本ノートから動かさない。

## 根拠リンク

[l4-c2-print-conformance-preregistration.md](l4-c2-print-conformance-preregistration.md)
（`39eeb53`、腕・条件・フレーム式・原点定義・関門・記録項目の原型）・
[l4-c2-print-conformance-results.md](l4-c2-print-conformance-results.md)
（`4f774fb`、追記`734b490`。P1〜P5原因とP6診断の要約、開発者判断）・
[l4-c2-error-signature-diagnosis.md](l4-c2-error-signature-diagnosis.md)
（`70de1bd`、P6署名の診断、`--row-signature`の使い方）・
`fc69064`（SPACEキーのエコー前進の修正）・
[l3-main.md](../spec/l3-main.md)第3.1版`1439d78`（SPACEの仕様根拠）・
`tools/l4_vram_probe.py`（差分モード・`--count-only-rows`・
`--row-signature`）・`tools/conform_l4.sh`（二層方針の既存実装）。
