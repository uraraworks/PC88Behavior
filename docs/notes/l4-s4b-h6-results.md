# l4-s4b: 仮説H6（単精度6桁で切替、6桁超で指数表記）の確認結果

実施日: 2026-09-15
事前登録: [l4-s4b-h6-single-precision-digits-preregistration](l4-s4b-h6-single-precision-digits-preregistration.md)
（`fac3cfa`）。l4-s4a本体（`d8cf563`）・追補（`e4dcd7d`）の条件・器具・記録・
「本文を出さない取り扱い」・関門G1〜G5をそのまま踏襲する。
測定時HEAD: `349e7ef`（予測表`docs/notes/l4-s4b-h6-predictions.tsv`のコミット、
以後このコミットへの変更なし）。core sha256先頭 `6c915e832379`、frontend
sha256先頭 `97e023e7ca6e`（l4-s4aと同一・未改変）。分類器は`5735eb3`の
`tools/l4_s4a_float_classify.py`をそのまま使用（二重実装なし）。公式ROMは
環境変数`PC88_REF_ROM_DIR`（`private/rom`）経由でコマンドごとに与え、
リポジトリ内のスクリプト・ノートにパスは焼き込んでいない。

## 進め方

事前登録どおり、先に陰性対照(G4、起動settleのみ)・陽性対照(G5、
`print 7717\n`)を1走ずつ回して器具の形を確かめてから、single_digits・
single_small・doubleの23腕を各2走、計46走+対照2走=48走を実施した。
7〜9腕ずつに分けてフォアグラウンドの逐次実行でこなした。

## 関門

| 関門 | 結果 | 根拠 |
|---|---|---|
| G1 器具の自己検査 | **真** | l4-s4aで確認済みの自己検査群(HEAD以後未改変)。`5735eb3`時点で全項目OK確認済み、本測定でツール・器具に変更なし |
| G2 取りこぼし0・打てない文字の警告0 | **真** | 48走全てのstderrで「untypable」「打てない」該当行0件 |
| G3 決定論性 | **真** | 23腕全てでrun1/run2の写し(前・後とも)のsha256が一致し、分類器の出力(JSON)もrun1=run2で一致。gate_failed腕は無い |
| G4 陰性対照 | **真** | 何も打たない走で文字域・属性域とも変化0件(`char_change_count=0`, `attr_change_count=0`) |
| G5 陽性対照 | **真** | `print 7717\n`の出力行(相対行+1)の相対列1-4に文字コード`37 37 31 37`(`7717`)が連続4セルとして出現 |
| G6 予測表の固定 | **真** | `git log --follow -- docs/notes/l4-s4b-h6-predictions.tsv`で`349e7ef`(2026-09-15)のみ、測定開始時点で存在し以後変更なし |

G1〜G6すべて真のため、`gate_failed`として除外した腕は無い。

## 原点

23腕全てで、打った行の先頭セルは絶対位置 (row0=6, col0=0) で一致した
(l4-s4aと同一)。全腕で`Ok`行は相対行+2(出力1行)だった。

## 分類の数え上げ

- `numeric_output`: 23腕(single_digits 11・single_small 6・double 6)全て
- `non_numeric_output`: 0腕
- `gate_failed`: 0腕

## 予測照合表（`docs/notes/l4-s4b-h6-predictions.tsv`、`349e7ef`）

全腕`approx`列に印があるため、判定名の横に一律`(approx)`を併記する
（判定名自体は実測と予測列の一致で決まる）。

### single_digits群（H6主対象、11腕）

| 腕 | 判定 |
|---|---|
| A1 | predicted_match (approx) |
| A2 | predicted_match (approx) |
| A3 | predicted_match (approx) |
| A4 | predicted_match (approx) |
| A5 | predicted_match (approx) |
| A6 | predicted_match (approx) |
| A7 | predicted_match (approx) |
| A8 | predicted_match (approx) |
| A9 | predicted_match (approx) |
| A10 | predicted_match (approx) |
| A11 | predicted_match (approx) |

### single_small群（H6、小さい側の切替規則、6腕）

| 腕 | 判定 |
|---|---|
| B1 | predicted_match (approx) |
| B2 | predicted_match (approx) |
| B3 | predicted_match (approx) |
| B4 | predicted_differs (approx) |
| B5 | predicted_match (approx) |
| B6 | predicted_differs (approx) |

### double群（参考、H6の判定に含めない、6腕）

| 腕 | 判定 |
|---|---|
| C1 | predicted_match (approx) |
| C2 | predicted_match (approx) |
| C3 | predicted_match (approx) |
| C4 | predicted_match (approx) |
| C5 | predicted_match (approx) |
| C6 | predicted_match (approx) |

**数え上げ: predicted_match 21・predicted_differs 2(B4・B6)。**
(single_digits 11/11一致、single_small 4/6一致、double 6/6一致)

## 仮説単位の判定

**h6_digits_only。**

- single_digits群(11腕)は**全11腕**が`predicted_match`
  → 6桁で切り替わるという桁数の規則そのものは支持される。
- single_small群(6腕)に`predicted_differs`が2腕(B4・B6)ある
  → 事前登録の定義により`h6_supported`の条件(全17腕一致)を満たさず、
  `h6_digits_only`(桁数規則は支持、小さい側の指数表記への切替規則は
  H6の記述だけでは説明できない)に該当する。

## 食い違った腕の形（観測）

以下は、実測と予測の非空白セルの並びを直接比較して言える範囲の記述。
数字・記号は自分で打った式の直接の結果であり、禁止事項7の対象外。

- **B4**(`print 1e-7`): 予測は指数表記(`1E-07`)、実測は固定小数点表記
  (`.0000001`、小数点以下7桁のゼロのあと`1`)。予測は指数表記へ切り替わる
  はずの大きさで、実測は固定表記のままだった。
- **B6**(`print 123456e-10`、値は`1.23456e-5`相当): 予測は固定小数点表記
  (`.0000123456`)、実測は指数表記(`1.23456E-05`)。予測は固定表記のまま
  のはずの大きさで、実測は指数表記に切り替わっていた。

B4とB6は予測とのズレの向きが逆(B4は「予測=指数、実測=固定」、B6は
「予測=固定、実測=指数」)で、単純に「予測の閾値を一律にずらせば揃う」
という形にはなっていない。

## 観測（判定を動かさない記述）

- single_digits群(A1〜A11)は、整数・分数・べき乗・掛け算・`!`サフィックス
  のいずれの経路でも予測と一致した。A1(`print 1234567`)とA10
  (`print 1234567!`)は打鍵文字列が違う(`!`の有無)にもかかわらず出力の
  非空白セルの並びが一致した。
- single_small群のうちB1・B2・B3・B5(`.0001`〜`.000001`、`1.5e-5`)は
  予測どおり固定表記のままだった。B4(`1e-7`)だけが固定表記のまま、
  B6(`1.23456e-5`)だけが指数表記になっており、指数の大きさの単純な
  大小関係だけでは切替点を説明できない(B5は1.5e-5で固定表記、B6は
  1.23456e-5で指数表記——指数の桁は同じ-5だが有効桁の桁数が違う)。
- double群(C1〜C6)は6腕全て予測と一致した。倍精度は単精度と異なる
  桁数(`.1428571428571429`のように16桁以上)で出力され、`D`指数記号を
  使う点も予測どおりだった。

## 禁止事項7の遵守について

本測定でツール出力・本ノートに載せたのは、(1)自分で打った式
(`print`の引数)の直接の結果である数値・記号(23腕全て、事前登録が
明示的に許可)、(2)ハードウェア設定に相当するアドレス式・行/列番号
のみ。本測定では`non_numeric_output`腕が無かったため、件数・範囲のみの
記述は発生しなかった。

## 判定後の行き先

`h6_digits_only`のため、仕様書`docs/spec/l4-basic.md`への反映は、
桁数の規則(単精度6桁)だけを確定させる形にとどめ、小さい側(指数が負の側)
の指数表記への切替条件は未確定のまま次の測定(l4-s4c等)に持ち越すことを
親の判断に委ねる。B4・B6の食い違いは、次の測定で切替条件を絞り込む
ための入力として残す。

## 生データの扱い

写し(vram.bin)・iolog・stdout/stderr・results.tsvはリポジトリ外の作業
ディレクトリ(scratchpad配下)に置き、本ノートを書いたあと削除する。
コミットするのは本ノートのみ。
