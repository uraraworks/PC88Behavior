# B44: `F=0xC1` で移る自作 ROM で G1 のスペース後を確かめる — 事前登録

記録日: 2026-11-01
位置づけ: [B43](b43-sub-entry-flags-results.md) の次段。**このノートは測定より先にコミットする。**

## 1. 問い

自作の `0x0D` で第230版の `F=0xC1` にすると、G1 のスペース後の `IN $FC` の違いと移る回数は変わるか。

## 2. 条件

腕 F の 4800 フレーム。OO 2 走、SS 2 走。自作 ROM は実装コミットの配布ビルド。クラウドの実行環境で行う。

関門: OO どうし、SS どうしの記録が一致する。OO の `IN $FC` の回数が B42 と同じ 112426 である。

## 3. 記録の白リスト

`row self fc-diff=<N> first=<N|none> run=<N> left=<N> right=<N> cross=<N> screen=<same|differ>`（B42 と同じ形）。**値は出さない。**

## 4. 判定（事前に決める）

- `fc-diff=0` で `cross=71`、`screen=same` なら、この腕の 4800 フレームは公式と一致したと書き、14400 フレームまで別に確かめる
- 変わったが一致しないなら、新しい行をそのまま書き、次を別のノートで決める
- B42 の行と同じなら、F はこの違いの原因ではないと書く

## 5. 結果の置き場

`measurements/b44-g1-entry-flags.txt`、`docs/notes/b44-g1-entry-flags-results.md`
