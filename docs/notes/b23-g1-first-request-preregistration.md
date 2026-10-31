# B23: G1 の最初の要求の連続の中身を記録する — 事前登録

記録日: 2026-11-01
位置づけ: [追補5](goal-b-policy-addendum5-first-request-bytes-2026-11-01.md) の範囲。**このノートは測定より先にコミットする。**

OO・SS 各 1 走の `--io-log`（既存のものを再利用してよい）。実装は `tools/b23_first_request.py`。B6 と同じ開始の行から後の main 節で、最初の `OUT $FD` の連続の値を取る。長さが 10 でなければ値を出さず `length=N` だけを出して止まる。

記録の白リスト: `# 識別子: G1`、`# 走: <name>`、`first-run length=10 <2桁16進×10>`。

判定: OO と SS が一致するかを書く。読み要求の 5 バイトより後の要求の候補を挙げ、自作のプローブで働きを測る次の事前登録の対象にする。

結果は `measurements/b23-g1-first-request-<腕>.txt`、`docs/notes/b23-g1-first-request-results.md`。
