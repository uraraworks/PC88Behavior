# B52c: 要求 `0x16` でサブ RAM のどこが変わるかを測る — 結果

記録日: 2026-11-01
規則: [b52c-sub-request-16-ram-diff-preregistration.md](b52c-sub-request-16-ram-diff-preregistration.md) どおり。公式の 2 走は一致し、対照の行 5 に変化は無い。G1 は使っていない。記録は `measurements/b52c-official-1.txt`・`-2.txt`。

## 結果

- 行 1〜3: 変わるのは番地 A・A+1 の 2 バイトだけ（`p0`・`p1`）
- 行 4（L=256）: 同じ 2 バイトのほかに、`7F1B-7F1F` と `7F25` が変わる。記号は模様の偶然の一致の可能性があり、ROM の作業域とスタックの範囲である。本体が書かれたとは言わない

## 分かったこと

`0x16` の本体の 3 バイト目以降は、RAM に書かれない。**番地 A へ 2 バイト書く要求である。** 仕様は `docs/spec/l3-subrom.md` 1.36c 節（第231版）。実装は G1 で確かめる（B53）。
