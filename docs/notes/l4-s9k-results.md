# l4-s9k 結果 — DEF FN・SWAP・ERASE

記録日: 2026-10-05
事前登録: [l4-s9k-deffn-swap-erase-preregistration.md](l4-s9k-deffn-swap-erase-preregistration.md)（3b1af61、候補 G_GW）
器具: `tools/l4_deffn_measure.py`（8bab986）。公式測定: `../tmp/l4s9k-work/official_round1.tsv`（59腕×2走）。
観測は自作プログラムが出した印と整数、誤り番号の包含真偽だけ。画面本文は扱っていない。観測後の候補追加・予測変更なし。

## 判定

- 全59腕×2走が関門通過（118行すべて gate=pass）。**予測あり55腕（本体44＋対照11）が全て G_GW と agree、不一致0。** 予測なし4腕は unpredicted（下記の観測のみ）。2走の観測は全腕で一致。
- 期待値: `tests/conformance/expected_l4_deffn.tsv`（予測あり55腕、`predict` の出力から予測なしを除いたもの）。
  `python3 tools/l4_deffn_measure.py check --predicted-only --expected tests/conformance/expected_l4_deffn.tsv --measured ../tmp/l4s9k-work/official_round1.tsv` が rc=0（照合一致）。
- 事前登録の予測表と観測が食い違った腕は無い（誤り番号 18/2/13/12/5/9/10 も予測どおり。E_table の修正は不要だった）。

## 予測あり55腕の観測（G_GW 一致）

値は `s9kv` の印の整数列、誤りは捕捉した番号とその時点の p。

| 群 | 腕 | 観測 |
|---|---|---|
| DEF FN 基本 | fn-one / two / none / string | 7 / 23 / 3（括弧なし）/ 3,97（文字列関数） |
| 束縛 | fn-scope | 6,9,4（仮引数 x は呼出し中だけ。大域 x=9 は不変。本体の g は大域 4 を参照） |
| 入れ子・再定義 | fn-nested / fn-redefine | 8 ／ 4,5（再定義で更新） |
| 名前 | fn-names / fn-long-names / fn-space | fnab と fnac、fnabc と fnabd は別の関数（4,5）。`fn a(1)` は fna として呼べる（3） |
| DEF FN の誤り | fn-undefined / fn-before-def | ERR 18、p=1（DEF 行より前の呼出しも 18） |
|  | fn-too-few / fn-too-many | ERR 2、p=1 |
|  | fn-type-number / fn-type-string | ERR 13、p=1 |
|  | fn-direct | 直接モードの DEF は番号 12 の包含 |
| SWAP | number / integer / single / double | 各 7,3 |
|  | string | 3,120,2,97 |
|  | array / array-scalar / same | 7,3 ／ 7,3 ／ 7 |
|  | type-string / type-integer | ERR 13、p=1（整数と単精度も 13） |
|  | undefined-first-number / string | 7,0 ／ 2,0（第1だけ未設定なら新設して交換） |
|  | undefined-second / both（数値・文字列） | ERR 5、p=1 |
|  | one | ERR 2、p=1 |
| ERASE | redim / auto-ten / multiple / preserve / string | 0,9 ／ 0,9 ／ 0,0 ／ 8,9 ／ 0,122 |
|  | auto-eleven | ERR 9、p=1 |
|  | redim-without | ERR 10、p=1 |
|  | missing / scalar / empty | ERR 5 ／ ERR 5 ／ ERR 2（いずれも p=1） |
| 対照11腕 | control-* | 全て既知値どおり |

## 予測なし4腕の観測（記述のみ、規則の根拠として使う）

| 腕 | プログラム | 観測 |
|---|---|---|
| fn-integer-round | `def fna%(x)=x/3`、5 / 7.5 / -7.5 | 2, 3, -3 |
| fn-integer-type | 同、98304（結果 32768） | ERR 6、p=1 |
| fn-argument-integer | `def fna(x%)=x%`、2.5 / -2.5 | 3, -3 |
| fn-recursion | `def fna(x)=fna(x)` を呼ぶ | ERR 7、p=1（終端印は出る） |

5/3=1.67→2、7.5/3=2.5→3、-2.5→-3、2.5→3、-2.5→-3 で、CINT と同じ四捨五入（0.5 は絶対値の大きい方へ）と整合する。
結果が整数に収まらない（32768）と ERR 6。無条件再帰は ERR 7（メモリ不足）で止まり、無限ループにはならなかった（深さの正確な値は未測定）。
