# m7lv — 自作subにも、一般READ要求の5バイト目の後でST3 bit3=1になるまでSENSE DRIVE STATUSを繰り返させる — 事前登録

## 位置づけ

- [m7lu](m7lu-no-disk-sub-drive-wait-diagnosis.md)（1.62節）: 公式subは一般READ要求
  （先頭0x02・長さ5）の5バイト目を受けた後、FDCへSEEK→SENSE INTERRUPT STATUS→
  SENSE DRIVE STATUSを出し、以後SENSE DRIVE STATUSを繰り返す。mainに6バイト目の
  番が回ってこない。ユーザー判断で、自作subにも同じ待ちを持たせる方針にした。
- [m7lv（測定）](m7lv-st3-two-side-media-signal.md): このエミュレータ（QUASI88）では、
  SENSE DRIVE STATUSのST3 bit3（TWO SIDE）が媒体の有無を表す（bit3=1⇔媒体あり、
  入れ替え直後の1回を除く）。READYは媒体が無くても1のままで、待ちの終わり検出には
  使えない。

**m7krの更新の条件「規則が書けたとき」に当たる**——本稿はここまでの測定から、自作sub側の
規則として書ける最小の形を事前登録する。

## 何を変えるか（`src/`だけ。作り直しの内容）

現在、自作subは一般READ要求の5バイト目を受けた後、`SEEK`（SENSE INT込み）→
`SENSE DRIVE STATUS`→`READ DATA`を1回ずつ出して再アームへ戻る。これを

**`SEEK`（SENSE INT込み）→`SENSE DRIVE STATUS`を、ST3 bit3=1になるまで繰り返す→
（bit3=1になったら）従来どおり続ける**

に変える。bit3=0の間は再アームしない（＝6バイト目を受け取らない）。

候補は作業ツリー上の未コミットの変更として測る。採用なら「測定」コミットの後に
「実装」コミットする（`m7lq`と同じ順）。

## 合格条件（すべて真で採用。BASE＝実装前のHEAD）

1. **ビルド**: 生成器の窓の関門（窓を跨ぐ命令なし・到達可能コードが窓外になし）が通り、
   変種フラグを立てた全ビルドも関門を通る（変種の拒否0個）。
2. **門の全体**: `tools/run_all_selftests.sh`がrc=0、`tools/check_cleanroom.sh`がNG 0件
   （色コードを落として数える）。
3. **no_disk**: 混成の+0（frame 700以降で最初のmain→sub run）の長さが5で、+0の後に
   交換runがframe 900までに無い（公式と同じ形）。
4. **no_disk**: +0以降のFDCコマンド名の先頭3つが`SEEK`・`SENSE INTERRUPT STATUS`・
   `SENSE DRIVE STATUS`で、`READ DATA`が0件、`SENSE DRIVE STATUS`が1000件以上、
   frame 760以降のsubのPIO入出力が0件。
5. **no_disk**: frame 900の画面署名（`tools/check_l3_screen_output.py`の行数・文字数・
   SHA-256）が公式と一致する（1.49節の模倣が落ちた条件を、待つ位置を正して試す）。
6. **既存の適合テストが悪化しない**: `m7lf`（[m7lf](m7lf-judgment-line-identity-preregistration.md)）
   の同一性——(a)総合判定が適合、(b)BASEでOKの判定行が1本も失われない、
   (c)NGが増えない、(d)`--`が増えない。
7. **1.58節の失敗の形**（`m7lq`の条件4・5・8〜13と同じ媒体・同じ道具、
   `tools/compare_l3_entry_fdc.py`・`tools/make_l3_testdisk.py`）で、混成の件数・
   連続・最長・単位がBASEから変わらない。
8. `src/`以外を変えない。`src/`の差分は一般READ要求の該当箇所だけ。
9. **決定論性**: 候補を2回走らせて、判定行の集合と条件3・4の数が一致する。

## 記述として載せるもの（合否に使わない）

- no_diskの`SENSE DRIVE STATUS`の1フレームあたり件数（公式は毎フレーム1,295件で
  一定だった、`m7lu`）。
- **媒体のある場面で、最初のアクセスの`SENSE DRIVE STATUS`の回数を公式と混成で
  比べる。** QUASI88は入れ替え直後の1回だけbit3=0を返す（`m7lv`測定のソースの読み）
  ので、公式が本当にbit3で待っているなら、公式側は最初のアクセスで2回
  （bit3=0の1回＋bit3=1の1回）出るはずである。差が観測できれば推定の裏付けになる。
- サブROMの使用量と、生成器の窓までの余白。

## 言えないこととして先に書いておくこと

- **エミュレータ（QUASI88）上の振る舞いである。** QUASI88のTSの意味・実機での
  振る舞いには一般化しない。
- **公式の判定規則がbit3だとは言わない。** 言えるのは「このエミュレータ上ではbit3と
  媒体の有無が一致する」までである。
- **待ちの途中で媒体を差したあとの続き（再アーム・6バイト目以降）は測れていない**
  （途中で媒体を差す器具が無い）。
- 実機での振る舞いには一般化しない。

## 採用したら

測定のコミットを先にし、`src/`の変更を単独でコミットし、仕様1.63節を新設する
（1.62節の直後）。

## 結果ノート

`docs/notes/m7lv-no-disk-drive-wait-implementation-results.md`に書く。合格条件と
数え方を後から動かさない。

## 根拠リンク

[m7lu](m7lu-no-disk-sub-drive-wait-diagnosis.md)（**動機**・待つ位置）・
[m7lv測定](m7lv-st3-two-side-media-signal.md)（**終わり検出の規則**）・
[m7lf](m7lf-judgment-line-identity-preregistration.md)（**同一性の数え方**）・
`vendor/quasi88-libretro`の`src/fdc.c`（SENSE DEVICE STATUSのST3生成）。
