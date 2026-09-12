# m7lv — 事前登録への追補（条件4の強化、測定前）

## 位置づけ

元の事前登録（[m7lv-no-disk-drive-wait-implementation-preregistration.md](m7lv-no-disk-drive-wait-implementation-preregistration.md)、
コミット`51b96dd`）の合格条件4は次のとおりだった。

> **no_disk**: +0以降のFDCコマンド名の先頭3つが`SEEK`・`SENSE INTERRUPT STATUS`・
> `SENSE DRIVE STATUS`で、`READ DATA`が0件、`SENSE DRIVE STATUS`が1000件以上、
> frame 760以降のsubのPIO入出力が0件。

**この条件は先頭3つのコマンド名しか見ていない。** そのため、`SEEK`（`SENSE
INTERRUPT STATUS`込み）を`SENSE DRIVE STATUS`のたびに毎回出し直す誤った実装
（＝1へ戻って繰り返す実装）でも、先頭3つの並びだけは`SEEK`・`SENSE INTERRUPT
STATUS`・`SENSE DRIVE STATUS`になり得るため、この条件を素通りしてしまう。

これは`docs/spec/l3-subrom.md` 1.63節の手順2の曖昧さ（「1へ戻って繰り返す」が
`SEEK`ごとの反復とも読めた）と表裏の問題であり、仕様側は第212版で
「`SENSE DRIVE STATUS`だけを繰り返す（`SEEK`・`SENSE INTERRUPT STATUS`は
繰り返さない）」に訂正済みである。事前登録の合格条件も、その訂正後の規則を
実際に強制できる形へ、**測定を始める前に**そろえておく。

## 追補する条件（条件4b）

条件4に加えて、次を満たすことを合格の条件とする（条件4はそのまま残す）。

**4b. no_disk**: +0以降のFDCコマンド名のうち、`SEEK`がちょうど1件、
`SENSE INTERRUPT STATUS`がちょうど1件であること（`SENSE DRIVE STATUS`は
条件4のとおり1000件以上の反復でよい）。

## 根拠

[m7lu](m7lu-no-disk-sub-drive-wait-diagnosis.md)の観測（1.62節）で確認した
公式の形——+0以降のFDCコマンドは`SEEK`・`SENSE INTERRUPT STATUS`が1回ずつ、
以後は`SENSE DRIVE STATUS`だけの反復——に合わせる締め方であり、公式の観測に
根拠がある。既存の条件を緩めるものではなく、先頭3つしか見ていなかった条件4の
抜け道を塞ぐ追加条件である。

## 言えないこと（元の事前登録から変わらない）

- 候補はまだ測っていない。本追補は**測定前**のコミットであり、測定結果は
  一切含まない。
- 元の事前登録に書かれた「言えないこと」（エミュレータ上の振る舞いであること、
  公式の判定規則がbit3だとは言わないこと、待ちの途中で媒体を差した後の続きは
  測れていないこと）はそのまま引き継ぐ。
- 元の事前登録のほかの条件（1・2・3・5〜9）、記述として載せるもの、
  結果ノートの置き場は変更しない。
