# B32: 違う 257 バイトの正体を確かめる — 事前登録

記録日: 2026-11-01
位置づけ: [追補6](goal-b-policy-addendum6-differing-block-2026-11-01.md) の範囲。**このノートは測定より先にコミットする。**

OO・SS 各 1 走、腕 F の 4800 フレームの `--io-log`（再利用してよい）と G1 の D88。実装は `tools/b32_differing_block.py`。

1. `IN $FC` を番号順に比べ、最初に違う番号 K と、K から連続して違う区間の長さ N を求める
2. K の前の `OUT $FD` の連続を取る（公式と自作で同じか比べ、末尾 64 バイトまで）
3. **公式の K 以降の値と、K+1 以降の値それぞれの先頭 256 バイトを、D88 の全セクタの本体の中から探す。** 自作の値も同じように探す
4. 公式か自作のどちらかがディスクの中身と一致するなら、**値を一切出さず** `body=disk` と座標だけを出す。要求の連続の出力は 2 の結果に従う
5. どちらも一致しないときだけ、先頭 8 バイトの値を公式と自作で出す

白リスト: `# 識別子: G1`、`first-diff index=<N> run=<N>`、`request same=<yes|no> length=<N> bytes=<2桁16進の並び>`、`official body=<disk C H R offset|none>`、`self body=<同>`、`official head=<2桁16進×8>`、`self head=<2桁16進×8>`。

判定: 値と座標をそのまま書く。次の測定の対象を決める。ここでは働きを決めない。

結果は `measurements/b32-g1-differing-block.txt`、`docs/notes/b32-g1-differing-block-results.md`。
