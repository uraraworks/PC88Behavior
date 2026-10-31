# B22: G1 で公式と自作の受け取りが違う箇所の値を記録する — 事前登録

記録日: 2026-11-01
位置づけ: [追補4](goal-b-policy-addendum4-two-reply-bytes-2026-11-01.md) の範囲での測定。
**このノートは測定より先にコミットする。**

## 1. 問い

`IN $FC` の違う 2 箇所は、それぞれ公式と自作で何の値か。どの要求の応答か。

## 2. 条件

OO・SS 各 1 走の `--io-log`（SS は `impl/l3-sub-load-run` deb0265 の系列のビルド）。条件は B18 と同じで、クラウドの実行環境で行う。B18 と同じ対照を通す。実装は `tools/b22_differing_replies.py`。

## 3. 求め方

B6 と同じ開始の行から後の main 節で、`IN $FC` を番号順に両者の共通の範囲で比べる。違う箇所が 8 以下のときだけ出力する。

## 4. 記録の白リスト

- `# 識別子: G1` / `# 比較: <A>-<B>`
- `compared=N differ=N`
- `diff index=<N> official=<2桁16進> self=<2桁16進> request=<2桁16進|none>`（`request` は、その `IN $FC` の直前の `OUT $FD` の連続の先頭バイト）
- 8 を超えたら `too-many` の 1 行だけ

## 5. 判定（事前に決める）

値と要求をそのまま書く。次の測定（自作のプローブでその要求の応答を測る）の対象を決める。ここでは働きを決めない。

## 6. 結果の置き場

`measurements/b22-g1-differing-replies.txt`、`docs/notes/b22-g1-differing-replies-results.md`
