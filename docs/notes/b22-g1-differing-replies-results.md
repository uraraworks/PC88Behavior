# B22: G1 で公式と自作の受け取りが違う箇所の値を記録する — 結果

記録日: 2026-11-01
規則: [b22-g1-differing-replies-preregistration.md](b22-g1-differing-replies-preregistration.md)（cb66133）どおり。測定はクラウドの実行環境で 008d75f。対照は一致。記録: `measurements/b22-g1-differing-replies.txt`。

## 結果

```
compared=8962 differ=2
diff index=3840 official=00 self=31 request=02
diff index=3841 official=14 self=31 request=02
```

## 読み方

- 違うのは track 0 の 15 セクタ（3840 バイト）の**直後の連続した 2 バイト**で、後ろの 5120 バイトのデータは一致している。データの本体ではなく応答と読めるので、記録は破棄しない
- `request=02` は、この 2 バイトの前の `OUT $FD` の連続が、先頭 `0x02`・長さ 10 の 1 本であることを示す。読み要求は 5 バイトと `0x06`・`0x12` で 7 バイトなので、**同じ連続の中に残り 3 バイトの別の要求がある**（推定）。その要求が 2 バイトを返しているように見える
- 自作は `0x31` を 2 回返していて、要求を解釈できていないように見える（推定）
