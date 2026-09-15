# l4-s4a 事前登録 追補 — 予測v2の照合・範囲外腕の照合規則の具体化

記録日: 2026-09-15
状態: 事前登録の追補、測定前
対象: [l4-s4a-float-print-preregistration.md](l4-s4a-float-print-preregistration.md)
（コミット`d8cf563`）を上書きする形で追補する。本体は書き換えない。

## 位置づけ

本体の予測表`docs/notes/l4-s4a-gwbasic-predictions.tsv`（以下v1、
コミット`1444cb4`）は、予測器の近似6件を含む。別担当が近似をなくした
v2予測表`docs/notes/l4-s4a-gwbasic-predictions-v2.tsv`（列: id, typed,
kind, predicted, approx）を並行で作成中である。**v1・v2いずれも中身は
読まない・触らない**（別担当の作業ファイルであり、CLAUDE.md上の
「委譲」の原則どおり、本作業の担当範囲外）。

## 1. v1・v2それぞれに対する照合

本体「判定」節の「予測との照合」の規則・判定名（`predicted_match`/
`predicted_differs`、kind=errorの腕については後述の第3節で置き換える）
は、v1・v2の**両方に対して別々に**適用する。1つの腕について
v1照合の結果とv2照合の結果を両方求め、どちらか一方だけで判定を打ち
切らない。

結果ノートでは、v1照合の表とv2照合の表を分けて掲載する（同じ腕が
2つの表にそれぞれ1行ずつ現れる形）。

v2の`approx`列に印がある腕は、その腕のv2照合結果の判定名の横に
「(approx)」と併記する。判定名そのものは変えない（`predicted_match`
のままか`predicted_differs`のままかは実測とv2の`predicted`列の一致で
決まり、approx印の有無では変えない）。

## 2. G6のv2への適用

本体の関門G6（予測表が測定開始より前のコミットに存在し、その後変更
されていないこと）を、v1に加えてv2にも同様に適用する。

- v1: `git log --follow -- docs/notes/l4-s4a-gwbasic-predictions.tsv`
  で、測定開始（結果記録の走行）より前のコミットに存在し、以後変更
  されていないことを確認する（本体どおり）。
- v2: `git log --follow -- docs/notes/l4-s4a-gwbasic-predictions-v2.tsv`
  で同様に確認する。

**v2のコミットが測定開始の時点で存在しない場合、測定は始めない。**
v2が未着手・未コミットのままではG6(v2側)を満たせないため、全体の
測定を待機する。v1のみでG6を満たして測定を始めることはしない
（v1・v2の両方に対する照合を行う方針〔第1節〕のため）。

## 3. 範囲外腕（X1・X2）の照合規則の具体化

本体228〜232行（「out_of_range群は予測表のkindがerrorであることを
前提に上記と同じ規則で照合する」「predicted側にも文言を出さない比較法を
別途定める」）を、本追補で以下のとおり具体化する。「別途定める」は
この節で定めたことを指す。

X1・X2それぞれについて、v1・v2の予測表のkind列（numeric または
error）と、本体「判定」節で定めた実測の分類（`numeric_output`または
`non_numeric_output`）を突き合わせる。**predicted列の文字列（具体的な
数値・エラー文言）は一切参照しない**——kind列（numeric/errorの2値）
だけを使うため、文言を出さずに比較できる。

- kind=numeric かつ 実測が`numeric_output` → 整合
- kind=error かつ 実測が`non_numeric_output` → 整合
- 上記以外の組み合わせ（kind=numericなのに`non_numeric_output`、または
  kind=errorなのに`numeric_output`）→ 不整合

判定名は、本体の`predicted_error_consistent`/`predicted_error_inconsistent`
を流用しない（本体のその2名はkind=errorの腕専用の定義であり、X1・X2は
kindがnumeric・errorのどちらもあり得るため意味が異なる）。本追補で
新しく次の判定名を定義する。

- **`range_kind_consistent`**: 予測のkindと実測の分類が上記の意味で整合
- **`range_kind_inconsistent`**: 整合しない

X1・X2はv1・v2それぞれについてこの2値のいずれかを判定し、結果ノードの
v1表・v2表それぞれに記載する（第1節の「v1・v2それぞれに対する照合」の
一部として扱う）。`gate_failed`の腕（本体の関門G1〜G6のいずれかが偽）は
本節の照合も行わない。

## 変更しないもの

- 本体の腕・条件・器具・フレーム式・原点定義・記録する内容・「本文を
  出さない取り扱い」・関門G1〜G5・decimal〜error_view群の判定規則は
  変更しない。
- 本体の`numeric_output`/`non_numeric_output`/`gate_failed`の分類規則
  （「判定」節）も変更しない。本追補が変えるのは、X1・X2に対して
  「予測との照合」をどう行うかだけである。

## 結果ノートへの反映

`docs/notes/l4-s4a-float-print-results.md`に、v1照合表・v2照合表を
分けて掲載する。X1・X2の行には`range_kind_consistent`/
`range_kind_inconsistent`を使う（v1・v2それぞれ）。

## 根拠リンク

[l4-s4a-float-print-preregistration.md](l4-s4a-float-print-preregistration.md)
（`d8cf563`、本体の判定名・関門G1〜G6の原型）。
