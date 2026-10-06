# l4-s9m 結果 — DEFINT・DEFSNG・DEFDBL・DEFSTR（型宣言文）

記録日: 2026-10-06
事前登録: [l4-s9m-deftype-preregistration.md](l4-s9m-deftype-preregistration.md)（052bcd8、候補 G_GW）
追補: [l4-s9m-addendum1-short-forms.md](l4-s9m-addendum1-short-forms.md)（画面からあふれた3腕の短縮）
器具: `tools/l4_deftype_measure.py`（3cc2f69。追補1の差し替えは次のコミット）。
公式測定: `../tmp/s9m-work/official_round1.tsv`（111腕×2走）、`official_round2.tsv`（追補1の再測定：新腕3＋対照11腕）、
`official_merged.tsv`（merge）→ `official_final.tsv`（rejudge、222行）。
観測は自作プログラムが出した印と整数、誤り番号の包含真偽だけ。画面本文は扱っていない。観測後の候補追加・予測変更なし。

## 判定

- 1回目は `exist-int-return`・`array-before-def`・`array-erase` の3腕だけ関門失敗（直接モードの行数が多く、先頭の印が画面の上へ流れた。
  観測の失敗であって予測の外れではない。印の値の並びは予測と同じに見えていた）。追補1で文を1行にまとめた `-s` 腕へ差し替え、
  2回目は14腕×2走が関門通過、新腕3腕は全て agree。merge → rejudge で **111腕×2走すべて関門通過（222行）**。対照11腕は既知値一致、2走の観測は全腕で一致。
- 本体100腕: **予測あり96腕のうち95腕が G_GW と agree、1腕が differ**、予測なし4腕は unpredicted。
- 期待値: `tests/conformance/expected_l4_deftype.tsv`（予測あり107腕＝本体96＋対照11。列 prediction は agree の腕のみ、differ の腕は
  prediction を空にして公式の観測を observation 列に置いた）。`python3 tools/l4_deftype_measure.py check --predicted-only --expected tests/conformance/expected_l4_deftype.tsv --measured ../tmp/s9m-work/official_final.tsv` が rc=0。
  予測なし4腕の観測は `expected_l4_deftype_unpredicted.tsv`（照合には使わない）。

## 観測から読める規則（実装の根拠）

宣言の本体（予測どおり）:
- `DEFINT`・`DEFSNG`・`DEFDBL`・`DEFSTR` は、英字（範囲 `a-c`・列挙 `a,c,e`・組合せ `a-b,x-z`・1文字・`a-z`・空白入り `a - c , e`）の**1文字目**で
  型を決める。名前が長くても1文字目だけで引く（`defstr a` の後の `abc` は文字列、`defint a` の後の `ba` は単精度）。同じ文字を後から宣言し直すと後が勝つ。
- 整数: 代入は CINT と同じ丸め（2.6→3、2.5→3、−2.5→−3、2.4→2、1/3→0、32767.4→32767）。範囲外（40000・32767.5）は **ERR 6** で変数は変わらない。
  整数どうしの演算が収まらなければ単精度へ昇格（300*300=90000、20000+20000=40000）、`/` は単精度（3/2*10=15）。
- 単精度・倍精度: 倍精度へ入れた 1/3# は 1/3# と等しい、単精度へ入れると等しくない、倍精度へ単精度の 1/3 を入れても 1/3# とは等しくならない。
  9桁の定数 123456789 は単精度変数で 123456792 に丸まる（−123456780 が12）、倍精度では9。
- 文字列: `defstr a` の後の `a` は `a$` と同じ変数（長さ・先頭文字コード・連結・`a$="xyz"` の後の宣言）。数値の代入は **ERR 13** で変数は変わらない。他の文字（`b`）は影響を受けない。
  `a%`・`a!`・`a#`・`a$` の接尾辞は常に既定に優先し、同名でも型ごとに別の変数（`a=7:a!=2.6` の両方が残る）。

誤りの文（直接モード、全て ERR 2 の包含）:
- `defint c-a`（逆順）・`defint a-`・`defint 1`・`defint`（空）は構文の誤りで**何も変えない**（後の `a=2.6` は単精度の26）。
- `defint a,`・`defint a,1`・`defint a,d-c`・`defint ab`・`defint a b` は構文の誤りだが、**そこまでの a は整数になっている**（`a=2.6` が3）。
- プログラム中の `defint c-a`・`defint` も ON ERROR で捕捉でき ERR 2。

変数の存在（型ごとに別）: 宣言の前に作った `a=2.6` は、`defint a` の後では見えず `a` は0、`a!` は26 のまま。再び `defsng a` すれば元の `a`（26）が戻る。
整数の `a=2.6` を作ってから `defsng a` で見ると0、`defint a` へ戻すと3。

宣言が戻る・残る条件（l4-s9g の規則と一致）:
- 戻らない（宣言が効いたまま）: 代入（`b=5`）・LIST・存在しない行番号だけの入力（ERR 8）・STOP→CONT・プログラム中の宣言が END のあとの直接モード。
- 単精度へ戻る: プログラム行の挿入・削除・置換、CLEAR、NEW、RUN（直接の RUN と、プログラム中の `clear`・`run 40`）。
  したがって直接モードで入力した宣言は、その後に行を打つか RUN すると消える。STOP のあとに行を編集すると戻る。
- プログラムは**実行のたびに型を引く**: 同じ文 `a=2.6:print a*10` が、宣言の前は26・宣言の直後に別変数で0・宣言のあと30になる。
  FOR のなかで途中に宣言しても次の周回から変わる（26, 30）。`if 1 then defint a` は宣言が働き、`if 0 then …` は働かない。
- 配列も型ごとに別（`dim a(3)` の単精度配列があっても、宣言後の `a(1)=5` は別の整数配列で ERR 10 にならない）。
  `dim a%(3)` のあと `defint a:dim a(3)` は ERR 10（同じ配列）。整数配列の 40000 は ERR 6、文字列配列への数値は ERR 13。
  `defint a` のあとの `erase a` は、単精度の配列があっても ERR 5（整数の `a` の配列が無い）。`defsng a` へ戻せば消せて、`dim a(5)` も通る。

関連する文:
- **DEF FN の関数名の型は `FN` の次の文字（`fna` なら a）の宣言で決まる**: `defint a` なら `fna(7.5)` は整数で `*2` が6、
  `defint f`（FN の `f`）・宣言なしは5。仮引数 x も宣言に従い、`defint x` の `fna(2.6)` は3。`defstr a` なら `fna` は文字列を返す。
- READ: 整数変数へ `2.6` を読むと3、文字列変数へ `12` を読むと長さ2、**整数変数へ数字でない DATA を読むと ERR 2**（予測どおり）。
- SWAP: 型が違えば ERR 13（変数は変わらない）。`defint a` の後の `swap a,b%` は交換できる。文字列どうし（交換後の長さ3）・整数どうしも通る。
- FOR: 文字列の制御変数は ERR 13。

## 予測と観測が食い違った1腕

| 腕 | 予測 | 観測 |
|---|---|---|
| for-dbl-step（`defdbl i` の `for i=1 to 2 step .5`） | 繰り返し3回 | **ERR 13**（p=0。誤りの捕捉、FOR の入口で止まる） |

規則: **倍精度の FOR の制御変数は ERR 13**（文字列と同じ）。予測は書き換えない。

## 予測なし4腕の観測（規則の候補。予測の外ではないので記述のみ）

- for-int-limit（`defint i`、`for i=1 to 2.6`）: 繰り返し **3回**（上限は CINT と同じ四捨五入で3）。
- for-int-step（`defint i`、`for i=1 to 2 step .5`）: 繰り返し **2回**（刻み .5 は1へ丸められ、1,2）。
- for-int-edge（`defint i`、`for i=32766 to 32767`）: **ERR 6**（32767 を終えて 32768 へ進むときの整数の桁あふれ。p=1）。
- read-dbl（`defdbl a`、`read a` に DATA 2.6）: `a=2.6#` が真（−1）。DATA は倍精度として読まれる（単精度に丸めてから広げていない）。

## 自作ROMの現状（実装前の基準、同じ器具で測定）

自作ROM（`src/build_main_rom.py` のビルド、実装は変更していない）を同じ111腕×2走で測定。対照11腕は全て通過。
本体100腕のうち**公式の観測と一致するのは10腕**、31腕は自作側の誤り行で画面があふれ先頭の印が流れて関門失敗、59腕は不一致。
自作は型宣言文を未実装（`defint` 等の行で ERR 2 が出る）ため、宣言を使う腕は全て宣言なしの動作（単精度）の値になる
（`defint a:a=2.6` の後が26、`defstr a:a$="hi"` の長さ0など）。プログラム中の腕は ERR 2 で止まる。一致する10腕は宣言の効果が見えない腕
（sng-default・err-reverse/dash-open/digit/empty・prog-reverse/empty・prog-if-false・fn-def-none・read-text-into-int。いずれも自作の ERR 2 や単精度の既定が公式と同じ結果になる）。自作側の改善は次段（実装）で行う。
作業置き場: `../tmp/s9m-work/own_baseline.tsv`（コミットしない）。
