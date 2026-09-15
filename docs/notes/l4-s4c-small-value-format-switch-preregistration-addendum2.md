# l4-s4c 事前登録 追補2 — 判定は予測表v2、S0列の訂正

記録日: 2026-09-15
状態: 事前登録の追補、測定前
対象: [l4-s4c-small-value-format-switch-preregistration.md](l4-s4c-small-value-format-switch-preregistration.md)
（`b286b26`）・[追補](l4-s4c-small-value-format-switch-preregistration-addendum.md)
（`8bf86b0`）を上書きする形で追補する。本体・追補1は書き換えない。

## 位置づけ

予測表v1（`docs/notes/l4-s4c-candidate-predictions.tsv`、コミット
`0936808`）のS0列が、本体「候補」節で定義したS0（`-N < E`なら固定
表記）と一致していないことが確認された（LEN列は定義どおり）。別担当が
S0列を定義どおりに訂正したv2
`docs/notes/l4-s4c-candidate-predictions-v2.tsv`を作成中である。**v1・
v2いずれも中身は読まない・触らない**（訂正の事実だけを扱う。差分の
中身は見ない）。

## 1. 判定に使う予測表

以後、候補ごとの判定（`candidate_consistent`/`candidate_rejected`）・
型ごとのまとめ（`unique_survivor`/`multiple_survivors`/`no_survivor`）
は**v2の値だけ**を使って行う。v1は判定には使わない。

G6（予測表が測定開始より前のコミットに存在し、その後変更されていない
こと）は、以後v1ではなく**v2**に対して適用する。
`git log --follow -- docs/notes/l4-s4c-candidate-predictions-v2.tsv`で
確認する。**v2のコミットが測定開始の時点で存在しない場合、測定は
始めない**（本体・追補1と同じ扱い）。

## 2. v1のS0列は参考記録として残す

v1は判定には使わないが、**v1のS0列でも同じ手順で照合した結果**を
「参考（判定外）」として結果ノートに別表で記録する。目的は、定義と
違っていたv1のS0列が実測とどう食い違ったか（＝定義のどの部分をv1が
取り違えていたのかを、実測との突き合わせという形で残すこと）であり、
v1の値そのもの（S0列の中身）を書き写すのではない。記録する内容は次の
2点に限る（本体「記録する内容」「本文を出さない取り扱い」節の範囲内）。

- v1のS0列で照合したときの`candidate_consistent`/`candidate_rejected`
  相当の結果（腕ごと、型ごと）
- v2のS0列での結果との一致・不一致（型ごとに「一致」「不一致」とだけ
  書く。v1・v2どちらのS0列の文字列がどうだったかは書かない）

LEN7・LEN8・LEN9・LEN16の各列については、v1とv2で同一のはずなので
（下記G7）、参考記録の対象外とする（S0列だけが訂正の対象）。

## 3. 関門G7（新設）: 測定前にLEN列がv1・v2で一致することを確認する

測定を始める前に、予測表v1・v2のLEN7・LEN8・LEN9・LEN16列が完全に
一致することを確認する関門を追加する。

- **G7**: v1とv2の該当列（LEN7・LEN8・LEN9・LEN16、type列ごとに
  該当する列のみ）が、id単位ですべて一致する。

確認は、値を人間（担当のセッション）が読んで突き合わせるのではなく、
**列ごとの完全一致・不一致の真偽だけを返すスクリプト**（列の値そのもの
は標準出力・標準エラーへ出さない設計。既存の`tools/l4_s4a_float_
classify.py`・`tools/l4_vram_probe.py --row-signature`等と同じ「値を
出さず真偽・件数・署名だけを返す」流儀に倣う）で行う。測定担当は
このスクリプトの真偽の結果だけを見て、予測表v1・v2のLEN列の中身は
見ない。

**一致しなければ測定は始めない。** 不一致が出た場合は、どちらか
（またはどのidで）不一致だったかという事実（idの列挙のみ、値は含まない）
を結果ノートに記し、別担当へ差し戻す。

## 変更しないもの

本体の腕・候補の定義（`S0`・`LEN(T)`）・条件・器具・記録する内容・
本文を出さない取り扱い・関門G1〜G6（G6の適用対象がv1からv2に変わる点
を除く）・腕ごとの分類・候補ごとの判定名・型ごとのまとめの判定名・
器具の確認の結果・追補1（K10・K11の符号の扱い）の手順は変更しない。
本追補2が変えるのは、判定に使う予測表をv2に切り替えること、v1のS0列を
参考記録として残すこと、G7を追加することの3点だけである。

## 結果ノートへの反映

`docs/notes/l4-s4c-small-value-format-switch-results.md`に、
判定に使ったv2ベースの表に加えて、「参考（判定外）: v1のS0列」の表を
分けて掲載する。G7の確認結果（一致/不一致、不一致ならid列挙）も記載
する。

## 根拠リンク

[l4-s4c-small-value-format-switch-preregistration.md](l4-s4c-small-value-format-switch-preregistration.md)
（`b286b26`、本体の候補定義・判定名の原型）・
[l4-s4c-small-value-format-switch-preregistration-addendum.md](l4-s4c-small-value-format-switch-preregistration-addendum.md)
（`8bf86b0`、追補1）・`0936808`（予測表v1、S0列の訂正対象）。
