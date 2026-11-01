# B44: `F=0xC1` で移る自作 ROM で G1 のスペース後を確かめる — 結果

記録日: 2026-11-01
規則: [b44-g1-entry-flags-preregistration.md](b44-g1-entry-flags-preregistration.md) どおり。測定はクラウドの実行環境で OO・SS 各 2 走。関門 7 項目はすべて通った。値は記録していない。記録は `measurements/b44-g1-entry-flags.txt`。

## 結果

`fc-diff=257`、`first=76570`、`run=132`、`left=112426`、`right=76828`、`cross=30`、`screen=differ`。B42 の行と同じである。

## 読み方

**F はこの違いの原因ではない。** 実装は第230版の仕様に合わせたものとして残す。
