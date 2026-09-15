# l4-c2-error-signature-diagnosis — P6エラー行の署名照合（診断）

記録日: 2026-09-15
位置づけ: `l4-c2`（事前登録 `39eeb53`、結果ノート `4f774fb`
`docs/notes/l4-c2-print-conformance-results.md`）のP6で、公式ROMと自作ROMの
エラー行署名が不一致だった件の**診断のみ**。事前登録の判定（`error_signature_
matches`/`differs`）は動かさない。値（画面文言そのもの）は一切出さない。

## やったこと

1. 公式ROM一式のみで、P6の2腕（`print 1+`・`printx 1`）を測り直した。
   条件は`l4-c2`事前登録と同一: 起動settle`--type-at 300 --type '\n'`、
   実打鍵`--type-at 700`、両腕とも打鍵9文字（`\n`込み）につき
   `line_end=772, dump=792, run=992`。写しは`dump`の1枚のみを
   `tools/l4_vram_probe.py --vram-dump ... --row-signature`に渡した。
   **生の差分（`--diff-before`/`--diff-after`）はエラー行に対して一度も
   使っていない**（測定スクリプトは使い捨て、`git status`に残らない
   作業ディレクトリで実行、写しは記録後に削除）。
2. 打った行の絶対行(row0)は、`l4-s3a-print-format-results.md`・
   `l4-c1-echo-conformance-results.md`が既に記録している公式ROM側の値
   `row0=6`（同一起動条件での既知の構造的事実、画面文言ではない）を使う
   前提を置いた。この前提を**自分で打った文字列の正規化ハッシュ**と
   突き合わせて確認した: `row0=6`の`row_sha256`が、自分の入力文字列
   （`print 1+`・`printx 1`、事前登録「本文を出さない取り扱い」節で
   出してよいとされた範囲）を0桁目から書いた80バイト行の正規化ハッシュと
   両腕とも一致した。よって`row0=7`（相対+1）がエラー行であるという
   前提は自己検証済み。
3. `row0=7`の署名だけを取得した: 非空白件数とSHA-256（16進、値そのものは
   出さない）。
4. `docs/spec/l4-basic.md`6.1節のエラーメッセージ一覧51件について、
   `tools/l4_error_message_candidates.py`（本コミットで新規、`tools/`に
   常設）で候補の署名を作った。生成規則:
   - 各文言について4通りの表記ゆれ候補を作る:
     `plain`（一覧の表記そのまま）、`plain_upper`（全て大文字）、
     `qmark`（先頭に`?`を付加。実機BASICの直接モードエラー表示が
     `?`始まりであることが多いという一般知識に基づく変形）、
     `qmark_upper`（`?`付き全て大文字）
   - 各候補文言を80バイト行の0桁目から書き、残りを空白で埋める
   - 正規化は`tools/l4_vram_probe.py`の`normalize_row_for_signature`と
     **同一処理**（末尾の空白(0x20)をrstrip、先頭は保持）をこの道具の
     中に複写して使う。同一であることは`--selftest`で確認した
     （`normalize_row_for_signature`に既知の無害な文字列3種を通し、
     `l4_vram_probe`本体の同名関数の出力とバイト単位で一致することを見る。
     公式ROM・候補文言のどちらも使わない自己検査）。`main()`は候補照合の
     前に必ずこの自己検査を通し、失敗したら照合自体を中止する設計
   - 51件×4表記ゆれ＝204候補のSHA-256を作り、公式ROM側の2つの
     `row_sha256`（16進文字列のみを引数で受け取る。この道具自身は
     公式ROMにも写しにも一切触れない）と突き合わせる

## 結果

- 公式ROM側: `P6-syntax`（非空白15件）・`P6-unknown`（非空白12件）とも、
  204候補のいずれとも`row_sha256`が一致しなかった。
- **結論: この一覧の文言（表記ゆれ4通り込み）だけの行ではない。**
  一致が取れなかった理由は複数考えられる（実機の実際の文言が一覧と
  微妙に異なる、`?`以外の前置き、大文字小文字の混在、末尾の追加文字など）
  が、禁止事項7により文言そのものを見て切り分けることはできないため、
  本ノートでは特定しない。

### 件数の一致という偶然（記述のみ、同一性の主張ではない）

非空白件数だけで見ると、一覧の候補の中に**件数が偶然一致するもの**が
複数ある（文言はすべて自分で作った候補＝マニュアルの資料の記載であり、
公式ROMの画面文言そのものではないため記載してよい）。

- `P6-syntax`（非空白15、`l4-s3a`が既に記録した列範囲0〜15＝16列ぶんとも
  整合する候補）: 番号22「Missing operand」の`qmark`（`?Missing operand`、
  全16文字・非空白15）、番号31「Duplicate label」の`qmark`
  （`?Duplicate label`、全16文字・非空白15）、番号32「Undefined label」の
  `qmark`（`?Undefined label`、全16文字・非空白15）。ほかに全長17文字の
  `qmark`候補（番号1・11・26・70）や全長17文字`plain`候補（番号54）も
  非空白15件になるが列範囲16列と矛盾するため除外した。
- `P6-unknown`（非空白12）: 番号2「Syntax error」の`qmark`
  （`?Syntax error`、全13文字・非空白12）、番号7「Out of memory」の
  `qmark`、番号13「Type mismatch」の`plain`、番号53「File not found」の
  `plain`、番号55「Input past end」の`plain`、番号56「Bad file name」の
  `qmark`、番号60「File not OPEN」の`qmark`、番号62「Disk offline」の
  `qmark`、番号64「Disk I/O error」の`plain`。

いずれも**件数が一致するだけ**であり、`row_sha256`は一致していない。
件数の一致は文言の同定を裏づけない（本ノートの主張はここまで）。

## 禁止事項7について

公式ROM側について本ノート・本コミットの器具が扱った・出力した値は
「非空白件数」（15・12、いずれも`l4-c2-print-conformance-results.md`が
既に安全な形で公開済みの値と同一）と「row_sha256（16進文字列）」だけ。
公式ROMの画面文言・文字コードの並びそのものは、測定の道具
（`tools/l4_vram_probe.py --row-signature`）から一度も出力していない
（`--diff-before`/`--diff-after`によるエラー行の生差分は今回も一切使って
いない）。ノート中に書いた文言（「Missing operand」等）はすべて
`docs/spec/l4-basic.md`6.1節（マニュアルのエラーメッセージ一覧、資料の
記載）から自分で作った候補であり、公式ROMの画面表示を見て書き写したもの
ではない。写し・作業ディレクトリ・自作ROM一式は記録後に削除した。

## 生データ

写し・自作した候補生成の中間出力は使い捨ての作業ディレクトリ
（`/Users/haruurara/MyProject/_emulator/PC88/tmp/l4-c2-diag/`）で扱い、
本ノートの記録後に削除した。恒久的に残すのは本ノートと
`tools/l4_error_message_candidates.py`のみ。
