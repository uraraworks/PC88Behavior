# l4-t9 第1回・l4-t7 追補2・l4-t8 追補1 — 公式走の結果（器具の誤りの記録を含む）

2026-11-10。クラウドの測定環境で公式ROMに対して、器具を1本ずつ順に走らせた（725eae0＋c2b2eab・c0de716）。
3器具とも全腕が関門を通過し独立2走一致。記録は measurements/l4-t9/official-first.json、
measurements/l4-t7/official-addendum2.json、measurements/l4-t8/official-addendum1.json（署名・数値のみ）。

## l4-t9 第1回 — 器具の誤りで MERGE・CHAIN は測れていない
- `save "2:x",a` の応答行が、作者の候補文字列「Bad file name」の行署名と一致した。**1文字のファイル名は誤りになり、ファイルができなかった**。
  このため MERGE・CHAIN の全腕は、ファイルが無い状態を測っていた（merge と merge-missing の結果が同じ）。
- merge-program 腕は RUN が行10から始まり、行10の END で止まって MERGE まで届いていなかった（器具の誤り）。
- chain の6腕と common-program では、ON ERROR の印に ERR 33 が入った（CHAIN・COMMON の文で出たのか、ファイルが無いためかは切り分けられない）。
- 直接モードの `common a,b$` は参照外の1行を出した。
→ 追補1 で作り直す（ファイル名を `2:t9prog` 形に、ERR 33・56 の参照を追加、merge-program は goto で実行）。

## l4-t7 追補2 — auto ,n の開始番号
- `auto ,20` で最初に表示される行番号は、作者の候補 `0` の行署名と一致した（開始番号は 0）。
- ただし 0・20・40・60 と 10・30・50 のどの候補へ goto しても行が無かった（ERR8）。打った行が保存されたかは確かめられていない（番号0の行の扱いは未確定）。

## l4-t8 追補1 — 器具の誤りで測れていない
- 全腕で ON ERROR の印に ERR 2 → 5。プログラムを STOP で止め直接モードで F1 を押したため、展開された文字列が次に打った
  `key(1) on` とつながって構文の誤りになり、CONT も誤りになったと見られる。
→ 追補2 で、押下・待ち・`key(1) on` をすべてプログラムの中で行う形に作り直す。
