# l4-s4a: 直接モードPRINTの浮動小数点の出力の形を測った結果

実施日: 2026-09-15
事前登録: [l4-s4a-float-print-preregistration](l4-s4a-float-print-preregistration.md)（`d8cf563`）・
追補: [l4-s4a-float-print-preregistration-addendum](l4-s4a-float-print-preregistration-addendum.md)（`e4dcd7d`）。
測定時HEAD: `5735eb36d6845819d37254952ef7116b4bc62908`
（直前に器具コミット「器具: l4-s4a 浮動小数点PRINT分類器」を先に入れている）。
core sha256先頭 `6c915e832379`、frontend sha256先頭 `97e023e7ca6e`（l4-s3aと同一の
ビルド・未改変）。公式ROMは環境変数 `PC88_REF_ROM_DIR`（`private/rom`）経由で
コマンドごとに与え、リポジトリ内のスクリプト・ノートにパスは焼き込んでいない。

## 進め方

事前登録どおり、先に陰性対照(G4、起動settleのみ)・陽性対照(G5、`print 7717\n`)を
1走ずつ回して器具の形を確かめてから、decimal〜out_of_rangeの32腕を各2走、計
64走+対照2走=66走を実施した。1腕2走が数秒で終わるため、8腕ずつ(16走)に分けて
フォアグラウンドの逐次実行でこなした(1コマンドが2分の上限に収まるように分割)。

分類器(`tools/l4_s4a_float_classify.py`)は測定前に別コミット
「器具: l4-s4a 浮動小数点PRINT分類器」で先に入れ、
`tools/l4_s4a_float_classify_selftest.sh`の陽性対照・陰性対照(集合外コード混入・
押す前が空白でなくコードが読めないセル)・`--range-only`の4検査が全てOKであることを
測定前に確認した。

## 関門

| 関門 | 結果 | 根拠 |
|---|---|---|
| G1 器具の自己検査 | **真** | 測定時HEADで`vram_dump_selftest.sh`・`vram_dump_dynamic_selftest.sh`・`key_matrix_selftest.sh`・`type_untypable_selftest.sh`・`screen_content_leak_selftest.sh`の全項目OK |
| G2 取りこぼし0・打てない文字の警告0 | **真** | 66走全てのstderrで「untypable」「打てない」該当行0件 |
| G3 決定論性 | **真** | 32腕全てでrun1/run2の写し(前・後とも)のsha256が一致し、分類器の出力(JSON)もrun1=run2で一致。gate_failed腕は無い |
| G4 陰性対照 | **真** | 何も打たない走で文字域・属性域とも変化0件(`char_change_count=0`, `attr_change_count=0`) |
| G5 陽性対照 | **真** | `print 7717\n`の出力行(相対行+1)の相対列1-4に文字コード`37 37 31 37`(`7717`)が連続4セルとして出現(l4-s3aと同じ形) |
| G6(v1) 予測表の固定 | **真** | `git log --follow -- docs/notes/l4-s4a-gwbasic-predictions.tsv`で`1444cb4`(2026-09-15)のみ、測定時HEAD以前に存在し以後変更なし |
| G6(v2) 予測表の固定 | **真** | 同様に`docs/notes/l4-s4a-gwbasic-predictions-v2.tsv`で`f7e99d5`(2026-09-15)のみ、測定時HEAD以前に存在し以後変更なし |

G1〜G6(v1・v2)すべて真のため、`gate_failed`として除外した腕は無い。

## 原点

全32腕で、打った行の先頭セルは絶対位置 (row0=6, col0=0) で一致した(l4-s3aと同一)。
以下の相対行は「打った行」を相対行0とする。`Ok`行は decimal〜error_view の30腕で
相対行+2、out_of_range(X1・X2)の2腕だけ相対行+3(出力が2行にわたる)。

## 分類の数え上げ

- `numeric_output`: 30腕(decimal 5・digits 5・exp_large 5・exp_small 4・promote 5・
  double 4・error_view 2)
- `non_numeric_output`: 2腕(out_of_range: X1・X2)
- `gate_failed`: 0腕

## v1照合表（`docs/notes/l4-s4a-gwbasic-predictions.tsv`、`1444cb4`）

kind=numericの30腕。予測文字列を相対桁0から置いたときの非空白セル(相対桁,コード)の
並びが実測と完全一致すれば`predicted_match`。

| 腕 | 判定 |
|---|---|
| F1 | predicted_match |
| F2 | predicted_match |
| F3 | predicted_match |
| F4 | predicted_match |
| F5 | predicted_match |
| D1 | predicted_differs |
| D2 | predicted_differs |
| D3 | predicted_differs |
| D4 | predicted_match |
| D5 | predicted_match |
| E1 | predicted_match |
| E2 | predicted_differs |
| E3 | predicted_match |
| E4 | predicted_match |
| E5 | predicted_match |
| S1 | predicted_match |
| S2 | predicted_match |
| S3 | predicted_match |
| S4 | predicted_match |
| P1 | predicted_match |
| P2 | predicted_match |
| P3 | predicted_match |
| P4 | predicted_match |
| P5 | predicted_match |
| W1 | predicted_match |
| W2 | predicted_match |
| W3 | predicted_match |
| W4 | predicted_match |
| R1 | predicted_match |
| R2 | predicted_match |

kind=errorの2腕(out_of_range)。predicted列の文言は参照せず、kind列(numeric/error)と
実測の分類(numeric_output/non_numeric_output)だけを突き合わせる(追補第3節)。

| 腕 | v1 kind | 実測分類 | 判定 |
|---|---|---|---|
| X1 | error | non_numeric_output | range_kind_consistent |
| X2 | error | non_numeric_output | range_kind_consistent |

**v1数え上げ: predicted_match 26・predicted_differs 4・range_kind_consistent 2・
range_kind_inconsistent 0。**

## v2照合表（`docs/notes/l4-s4a-gwbasic-predictions-v2.tsv`、`f7e99d5`）

v2のpredicted列はv1と(生成元コメント2行を除き)完全に同一だった
（`diff <(cut -f2- v1) <(cut -f2- v2)`で本文差分0、確認済み）。v2の`approx`列は
32腕全てに印(`1`)が付いているため、判定名の横に一律`(approx)`を併記する
（追補第1節、判定名自体は実測とv2のpredicted列の一致で決まり、approx印の
有無では変えない）。

| 腕 | 判定 |
|---|---|
| F1 | predicted_match (approx) |
| F2 | predicted_match (approx) |
| F3 | predicted_match (approx) |
| F4 | predicted_match (approx) |
| F5 | predicted_match (approx) |
| D1 | predicted_differs (approx) |
| D2 | predicted_differs (approx) |
| D3 | predicted_differs (approx) |
| D4 | predicted_match (approx) |
| D5 | predicted_match (approx) |
| E1 | predicted_match (approx) |
| E2 | predicted_differs (approx) |
| E3 | predicted_match (approx) |
| E4 | predicted_match (approx) |
| E5 | predicted_match (approx) |
| S1 | predicted_match (approx) |
| S2 | predicted_match (approx) |
| S3 | predicted_match (approx) |
| S4 | predicted_match (approx) |
| P1 | predicted_match (approx) |
| P2 | predicted_match (approx) |
| P3 | predicted_match (approx) |
| P4 | predicted_match (approx) |
| P5 | predicted_match (approx) |
| W1 | predicted_match (approx) |
| W2 | predicted_match (approx) |
| W3 | predicted_match (approx) |
| W4 | predicted_match (approx) |
| R1 | predicted_match (approx) |
| R2 | predicted_match (approx) |

| 腕 | v2 kind | 実測分類 | 判定 |
|---|---|---|---|
| X1 | error | non_numeric_output | range_kind_consistent (approx) |
| X2 | error | non_numeric_output | range_kind_consistent (approx) |

**v2数え上げ: predicted_match 26・predicted_differs 4・range_kind_consistent 2・
range_kind_inconsistent 0（全件approx併記）。** v1・v2で判定名の数え上げは同一
(predicted列が同一のため)。

## 食い違った腕の形（観測）

以下は、実測と予測(v1・v2とも同一)の非空白セルの並びを直接比較して言える範囲の
記述。数字・記号は自分で打った式の直接の結果であり、禁止事項7の対象外
（事前登録「本文を出さない取り扱い」節）。

- **D1**(`print 1/3`): 予測は小数点以下7桁(`.3333333`)、実測は小数点以下6桁
  (`.333333`)。実測のほうが有効桁1桁少ない。
- **D2**(`print 2/3`): 予測は小数点以下7桁(`.6666667`、最終桁が丸め上げで7)、
  実測は小数点以下6桁(`.666667`、最終桁が丸め上げで7)。実測のほうが有効桁1桁
  少ない形は D1 と同じ。
- **D3**(`print 10/3`): 予測は整数部1桁+小数部6桁で有効桁7(`3.333333`)、実測は
  整数部1桁+小数部5桁で有効桁6(`3.33333`)。実測のほうが有効桁1桁少ない形は
  D1・D2 と同じ。
- **E2**(`print 9999999`): 予測は整数の固定表記のまま(`9999999`、7桁)、実測は
  指数表記(`1E+07`)。実測は「1」+`E`+符号`+`+2桁指数という指数表記の書式で、
  固定小数点表記ではなかった。

D1・D2・D3はいずれも「実測の有効桁数が予測より1桁少ない」という同じ形の食い違い。
E2は桁数ではなく「固定表記か指数表記か」という表記形式そのものの食い違いで、
D1〜D3とは種類が異なる。

## 観測（判定を動かさない記述）

- 正の数・0の出力は、打った行の相対桁0(符号位置)が変化せず元のまま(空白)で、
  数字は相対桁1から始まった。負の数(F3・P3等)は相対桁0に`-`が書かれた。
  l4-s3aのQ1で確認した「符号のための1桁を確保する」前置きの形と同じだった。
- W1(`print 1#/3`)とW4(`print 1/3#`)は出力の非空白セルの並びが一致した
  (`#`サフィックスと`#`分母のどちらでも同じ倍精度書式になった)。
- W2(`print 1d10`)の出力は整数の固定表記(`D`指数記号を使わない形)だった。
- E4(`print 1e10`)・S4(`print 1e-10`)の出力はいずれも`E`指数記号を使う指数表記
  だった。
- X1・X2の出力は2行にわたった(`Ok`行が相対行+3)。decimal〜error_view群の30腕は
  いずれも出力1行(`Ok`行が相対行+2)だった。
- R1(`print .1+.2`)・R2(`print 1/3*3`)は、いずれも予測(v1・v2とも)と一致した
  (誤差が見える形にはならなかった)。

## 禁止事項7の遵守について

本測定でツール出力・本ノートに載せたのは、(1)自分で打った式(`print`の引数)の
直接の結果である数値・記号(30腕、事前登録が明示的に許可)、(2)X1・X2の非空白
セルの件数と行ごとの列範囲(値・文字コードは含まない)、(3)ハードウェア設定に
相当するアドレス式・行/列番号のみ。X1・X2のエラーメッセージの文言・文字コードは、
分類器(`tools/l4_s4a_float_classify.py`)の内部処理でのみ扱い、標準出力・本ノートを
含め一度も外へ出していない(`--range-only`でセル列挙自体を抑止し、分類器の自己検査
で集合外コードが出力に現れないことを測定前に確認済み)。

## 判定後の行き先

`docs/spec/l4-basic.md`への浮動小数点PRINT書式規則の反映は親の判断に委ねる。
D1〜D3(有効桁が予測より1桁少ない)とE2(指数表記への切替閾値が予測と違う)は、
予測器(`tools/l4_mbf_oracle.py`・`tools/l4_mbf_oracle_v2.py`)の丸め桁数・
指数表記切替規則の見直しが必要になる可能性がある入力として、次の作業に渡す。

## 生データの扱い

写し(vram.bin)・iolog・stdout/stderr・results.tsvはリポジトリ外の作業ディレクトリ
(scratchpad配下)に置き、本ノートを書いたあと削除する。コミットするのは本ノートのみ
(器具は先に別コミット済み)。
