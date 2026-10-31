# B36: スペース後の G1 で、サブの入力の値が最初に違う所を、値を出さずに探す — 結果

記録日: 2026-11-01
規則: [b36-g1-sub-port-values-preregistration.md](b36-g1-sub-port-values-preregistration.md) どおり。測定はクラウドの実行環境で腕 F の 4800 フレーム、取りこぼしなし。値は出していない。

```
port IN 00F8 raw compared=24 differ=0 first=none left=11 right=0
port IN 00FA collapsed compared=264 differ=0 first=none left=121 right=0
port IN 00FB raw compared=123096 differ=5088 first=117968 left=56419 right=0
port IN 00FE collapsed compared=145980 differ=4 first=145467 left=69201 right=0
first-difference: IN 00FB 117968 fdc=95
```

## 読み方

- RAM 上のコードの入力は、FDC の番号 95 の読みまで公式と同じである。違いの 5088 バイトは 1 トラック分に近い
- FDC の命令の最初の違いは番号 93 だった（B30）ので、ここは B30 の分かれ目の後である
- つまり `IN $FC` の 257 件の違いは、RAM 上のコードの入力の違いからは出ていない（**推定**）。ROM 側のコードが返している可能性がある。B34 は RAM 上のコードの読みしか数えていないので、これは見えていない
