# B13: 公式の上の G1 で、サブの FDC の命令とその発行元の領域を見る — 結果

記録日: 2026-10-31
規則: [b13-g1-sub-fdc-preregistration.md](b13-g1-sub-fdc-preregistration.md)（64660af）どおり。変更なし。
器具は 8878ff2 の版、自作は 2a4f910。測定はクラウドの実行環境で OO・SS 各 2 走、すべて rc=0。
対照: 境界記録と入出力の要約は OO が B1・B6 と、SS が B11 と一致。各腕の 2 走は差なし。
記録: `measurements/b13-g1-sub-*`。発行元は `lo`（`0x2000` 未満）と `hi` の 2 区分だけで、番地は記録していない。

## 判定: **RAM から**

OO の最初の N=3 の READ DATA（番号 26、C,H,R,N,EOT = 0,1,1,3,5）は `hi` から出ている。

```
fdc 21 sense_interrupt lo
fdc 22 sense_drive_status lo
fdc 23 read_data lo 0 0 2 1 16
fdc 24 seek hi
fdc 25 sense_interrupt hi
fdc 26 read_data hi 0 1 1 3 5
```

全体の集計（OO）: `read_data` hi 15・lo 2、`seek` hi 15・lo 4、`sense_interrupt` hi 15・lo 9、`recalibrate` lo 5、`sense_drive_status` lo 2、`specify` lo 1。

## SS との比較

最初に違うのは番号 24。OO は `seek hi`、SS は `sense_drive_status lo`。SS は `sense_drive_status lo` が 14464 回で、`hi` は 1 回も無い。

## 分かったこと

- **公式の上の G1 は、track 0 の読み（番号 23、`0,0,2,1,16`）のあと、サブの RAM 上のコードで FDC を動かす。** 1024 バイトのセクタはそのコードが読む
- N=3 の読みは 15 回で、公式 ROM の `0x02` の経路を通らない。B12 の観察と合う
- 自作サブでは G1 のコードがサブで動いていない

## 言えないこと

- コードがどの要求でサブへ渡り、どの要求で走り出すか。サブの RAM の内容も、要求の値も見ていない
- G1 のコードが公式サブ ROM の番地を呼ぶか。`hi` から `lo` への移動は記録していない。呼ぶなら、サブ側にも番地の需要が出る
- 位置 35721 の分かれ目がこれだけで説明できるかは、実装してみないと分からない
