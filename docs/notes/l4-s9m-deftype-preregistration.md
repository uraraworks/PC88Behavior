# l4-s9m — DEFINT・DEFSNG・DEFDBL・DEFSTR（型宣言文）の事前登録

状態: **測定前**（2026-10-06）。担当は測定器具のみ。公式ROMは実行しておらず、
公式の保存観測も読まない。自作BASICの実装（src/）・仕様の確定は行わない。
候補の追加、観測後の予測変更、関門の変更には、追補の事前登録を要する。

## 出典と読んだ範囲

- `CLAUDE.md`、手本 l4-s9l 一式（`l4-s9l-tabspc-logic-csng-preregistration.md`・`l4-s9l-results.md`・
  `l4-s9l-addendum1-csng-digits.md`、`tools/l4_tabspc_measure.py` と selftest・登録箇所）。
- `docs/spec/l4-program.md` は 4.4〜4.4d（変数・整数変数の丸め）、4.10（配列）、4.17（行の編集・NEW・CLEAR のあとの状態）、
  4.19（DEF FN・SWAP・ERASE。型の関係は 4.19.2〜4.19.4）の本文を読んだ。`l4-basic.md` は今回読んでいない。
- MIT公開ソース `../refs/GW-BASIC/` を `grep -a -n` で DEFTBL/DEFINT/DEFSTR/DEFDBL/DEFSNG/CLEARC/GETFNM/ISLET から探した。
  本文を読んだ範囲: `GWMAIN.ASM` 1871–1925（DEFSTR〜DEFCON〜範囲の登録ループ）、`GWDATA.ASM` 1296–1312（DEFTBL の説明）、
  `BIMISC.ASM` 164–235（CLEARC と DEFTBL の初期化）・785–792（ISLET）、`BIPTRG.ASM` 150–175（変数の型の決定 TABTYP）、
  `GWEVAL.ASM` 1220–1236・1290–1340・1505–1520（DEF FN の名前取得と引数の束縛）。
  公式ROM由来のコードは読まない。公開ソースのコードを本ノート・器具へ転載しない。検索0件を不存在の根拠にしない。

GWの手順を散文で整理する。

**宣言の本体。** 型の既定は大文字小文字を区別しない26文字の表（DEFTBL）にあり、`DEFINT`=2（整数）・`DEFSTR`=3・`DEFSNG`=4・`DEFDBL`=8 の値を
表のなかの文字の範囲へ書く。文の書式は「英字 [`-` 英字] {`,` 英字 [`-` 英字]}」。英字でなければ構文の誤り（ERR 2）。範囲は
終わりが始めより前（`c-a`）なら構文の誤りで**何も書かない**。1つの範囲は検査してから書くが、**カンマの後ろで失敗しても、それまでの範囲は書き込み済み**
（ERR 2 でも前の範囲は有効）。範囲のあとに英字・カンマ以外の文字が続く場合（`defint ab`・`defint a b`）は、書き込み後に文末でないとして構文の誤りと読む。
空白は読み飛ばす。

**型の決定。** 変数は参照・代入が**実行されるたびに**名前から型を決める。接尾辞（`%` `!` `#` `$`）があればそれを、無ければ名前の**1文字目**で表を引く。
同じ名前でも型が違えば別の変数（a と a!、a と a%）。したがって宣言の前に作った `a`（単精度）は宣言後の `a`（整数）とは別物で、宣言後の `a` は0
（未設定の値）から始まり、`a!` は元の値を保つ。宣言を戻す（再び DEFSNG）と元の変数に戻る。配列も同じで、`a(…)` の配列も型ごとに別。

**整数・単精度・倍精度・文字列。** 整数変数への代入は CINT と同じ丸め（半端は絶対値の大きい側、2.6→3、−2.5→−3）で、範囲外（40000・32767.5）は
ERR 6、誤りのとき変数は変わらない。整数どうしの演算が整数に収まらなければ単精度へ昇格する（誤りにしない。300*300=90000）。整数の除算 `/` は単精度の結果。
DEFSTR した文字への数値代入は ERR 13、文字列変数は `a$` と同じ変数。単精度・倍精度は代入のときに型へ変換され、倍精度へ単精度の 1/3 を入れても 1/3# とは等しくならない。
9桁の整数定数は倍精度として読まれ、単精度変数へ入れると仮数の丸めで 123456789→123456792。

**宣言を戻す操作（実行のたびではなく、状態の初期化）。** CLEARC が表を全部単精度へ戻す。CLEARC は RUN・CLEAR・NEW と、プログラム行の
挿入・削除・置換（l4-s9g の規則どおり）から呼ばれると読む。代入・LIST・存在しない行番号だけの入力・STOP→CONT は呼ばない。
したがって直接入力した宣言は、その後の行の入力や RUN で消え、プログラム中の宣言は END のあとの直接モードに残る。

**DEF FN。** 関数名の型は `FN` トークンのあとの名前の1文字目（`fna` なら **a**。`FN` の `f` ではない）で表を引く（関数ビットを落として引く）。
`defint a` なら `fna` は整数、`defint f` は無関係。仮引数も同じく表で型が決まる（`defint x` なら x は整数、実引数は CINT の丸め）。
**READ**: 数値変数は DATA の数字を読む、文字列変数は何でも読む、数字でない DATA を数値変数へ読むと構文の誤りと読む（ERR 2）。
**SWAP**: 型が違えば ERR 13（4.19.3）。型は宣言後のものを使う。**FOR**: 文字列の制御変数は ERR 13。整数の制御変数の上限・刻みの丸めと、32767 付近の挙動は手順を読み切れず**予測なし**。
**READ の倍精度**（2.6 を倍精度変数へ読んだ値が 2.6# と等しいか）も手順を読み切れず予測なし。

誤り番号は l4-basic 7.1 の番号（2・5・6・10・13、直接モードの存在しない行 8）。直接モードの誤りは番号の包含だけを使う。

## 採取形（l4-s9l 追補1の教訓）

単精度の値は6桁を超えると指数表記になり整数の印にならない。そのため採取は整数・小さい値・真偽（−1/0）・LEN・ASC だけにする。
単精度の 2.6 は `a*10`（=26）、倍精度は `a=1/3#` の真偽、9桁は `a-123456780` の差で測る。印は全腕に準備印 `s9mp 1 1`、操作印 `s9mo 1 1`、
結果先頭印 `s9mb 1 1`、終端印 `s9mz 1 1`。観測は `s9mv 1 値` と誤りの印 `s9me 1 番号 p`。

## 候補と値の予測（G_GW）

候補は G_GW のみ（上の散文）。腕は直接モード（`new` のあと1行ずつ打つ）とプログラム（ON ERROR で捕捉。790行の正常終了と800行の捕捉の両方に終端印）の2種類。
直接モードの腕の誤りは、その行1つだけが誤りになる設計で、誤りのあとの行は実行される。V は `print "s9mv";1;` の略。

| 腕 | 打鍵（本体） | G_GW の予測 |
|---|---|---|
| int-round | 直接: defint a / a=2.6 / V a | 3 |
| int-half-pos | 直接: defint a / a=2.5 / V a | 3 |
| int-half-neg | 直接: defint a / a=-2.5 / V a | -3 |
| int-low | 直接: defint a / a=2.4 / V a | 2 |
| int-third | 直接: defint a / a=1/3 / V a | 0 |
| int-edge | 直接: defint a / a=32767.4 / V a | 32767 |
| int-over | 直接: defint a / a=40000 / V a | 0＋直接の誤り ERR 6 |
| int-over-half | 直接: defint a / a=32767.5 / V a | 0＋直接の誤り ERR 6 |
| int-mul-promote | 直接: defint a / a=300 / V a*300 | 90000 |
| int-add-promote | 直接: defint a / a=20000 / V a+a | 40000 |
| int-divide | 直接: defint a / a=3 / V a/2*10 | 15 |
| sng-default | 直接: a=2.6 / V a*10 | 26 |
| sng-explicit | 直接: defsng a / a=2.6 / V a*10 | 26 |
| sng-after-int | 直接: defint a / defsng a / a=2.6 / V a*10 | 26 |
| dbl-third | 直接: defdbl a / a=1/3# / V a=1/3# | -1 |
| sng-third | 直接: defsng a / a=1/3# / V a=1/3# | 0 |
| dbl-from-single | 直接: defdbl a / a=1/3 / V a=1/3# | 0 |
| dbl-big | 直接: defdbl a / a=123456789 / V a-123456780 | 9 |
| sng-big | 直接: defsng a / a=123456789 / V a-123456780 | 12 |
| str-len | 直接: defstr a / a="hi" / V len(a) | 2 |
| str-dollar-same | 直接: defstr a / a="hi" / V len(a$) | 2 |
| str-prior-dollar | 直接: a$="xyz" / defstr a / V len(a) | 3 |
| str-numeric | 直接: defstr a / a=1 / V len(a) | 0＋直接の誤り ERR 13 |
| str-concat | 直接: defstr a-b / a="x":b=a+"yz" / V len(b) | 3 |
| str-int-suffix | 直接: defstr a / a%=2.6 / V a% | 3 |
| str-long-name | 直接: defstr a / abc="hey" / V len(abc) | 3 |
| range-a-c | 直接: defint a-c / a=2.6:b=2.6:c=2.6 / V a+b+c / d=2.6 / V d*10 | 9, 26 |
| range-before | 直接: defint b-c / a=2.6 / V a*10 | 26 |
| range-after | 直接: defint b-c / d=2.6 / V d*10 | 26 |
| list-a-c-e | 直接: defint a,c,e / a=2.6:c=2.6:e=2.6 / V a+c+e / b=2.6 / V b*10 | 9, 26 |
| two-ranges | 直接: defint a-b,x-z / a=2.6:y=2.6 / V a+y / m=2.6 / V m*10 | 6, 26 |
| range-whole | 直接: defint a-z / q=2.6 / V q | 3 |
| range-spaces | 直接: defint a - c , e / a=2.6:e=2.6 / V a+e | 6 |
| later-wins-str | 直接: defint a / defstr a / a="hi" / V len(a) | 2 |
| err-reverse | 直接: defint c-a / a=2.6 / V a*10 | 26＋直接の誤り ERR 2 |
| err-dash-open | 直接: defint a- / a=2.6 / V a*10 | 26＋直接の誤り ERR 2 |
| err-digit | 直接: defint 1 / a=2.6 / V a*10 | 26＋直接の誤り ERR 2 |
| err-empty | 直接: defint / a=2.6 / V a*10 | 26＋直接の誤り ERR 2 |
| err-comma-end | 直接: defint a, / a=2.6 / V a | 3＋直接の誤り ERR 2 |
| err-comma-digit | 直接: defint a,1 / a=2.6 / V a | 3＋直接の誤り ERR 2 |
| err-second-reverse | 直接: defint a,d-c / a=2.6 / V a | 3＋直接の誤り ERR 2 |
| err-two-letters | 直接: defint ab / a=2.6 / V a | 3＋直接の誤り ERR 2 |
| prog-reverse | プログラム: p=1:defint c-a | ERR 2(p=1) |
| prog-empty | プログラム: p=1:defint | ERR 2(p=1) |
| suffix-single | 直接: defint a / a!=2.6 / V a!*10 | 26 |
| suffix-double | 直接: defint a / a#=1/3# / V a#=1/3# | -1 |
| suffix-string | 直接: defint a / a$="hi" / V len(a$) | 2 |
| suffix-int-under-single | 直接: defsng a / a%=2.6 / V a% | 3 |
| suffix-coexist | 直接: defint a / a=7:a!=2.6 / V a / V a!*10 | 7, 26 |
| exist-before | 直接: a=2.6 / defint a / V a / V a!*10 | 0, 26 |
| exist-return | 直接: a=2.6 / defint a / a=5 / defsng a / V a*10 | 26 |
| exist-int-return | 直接: defint a / a=2.6 / defsng a / V a / defint a / V a | 0, 3 |
| first-letter-only | 直接: defint a / ba=2.6 / V ba*10 / abc=2.6 / V abc | 26, 3 |
| keep-none | 直接: defint a / a=2.6 / V a*10 | 30 |
| keep-assign | 直接: defint a / b=5 / a=2.6 / V a*10 | 30 |
| keep-list | 直接: 10 end / defint a / list / a=2.6 / V a*10 | 30 |
| keep-missing-line | 直接: defint a / 20 / a=2.6 / V a*10 | 30＋直接の誤り ERR 8 |
| reset-insert | 直接: defint a / 10 end / a=2.6 / V a*10 | 26 |
| reset-delete | 直接: 10 end / defint a / 10 / a=2.6 / V a*10 | 26 |
| reset-replace | 直接: 10 end / defint a / 10 rem / a=2.6 / V a*10 | 26 |
| reset-clear | 直接: defint a / clear / a=2.6 / V a*10 | 26 |
| reset-new | 直接: defint a / new / a=2.6 / V a*10 | 26 |
| reset-run | 直接: 10 end / defint a / run / a=2.6 / V a*10 | 26 |
| reset-run-program | 直接: 10 a=2.6:V a*10 / defint a / run | 26 |
| program-persists | 直接: 10 defint a / run / a=2.6 / V a*10 | 30 |
| stop-cont | 直接: 10 defint a:stop / 20 a=2.6:V a*10 / run / cont | 30 |
| stop-edit | 直接: 10 defint a:stop / run / 20 end / a=2.6 / V a*10 | 26 |
| prog-clear | プログラム: defint a:clear:a=2.6:V a*10 | 26 |
| prog-run-line | プログラム: 20 defint a:run 40 / 40 a=2.6:V a*10:goto 790 | 26 |
| prog-runtime-type | プログラム: a=2.6:V a*10 / defint a:V a*10 / a=2.6:V a*10 | 26, 0, 30 |
| prog-loop | プログラム: for k=1 to 2:a=2.6:V a*10:defint a:next | 26, 30 |
| prog-if-true | プログラム: if 1 then defint a / a=2.6:V a*10 | 30 |
| prog-if-false | プログラム: if 0 then defint a / a=2.6:V a*10 | 26 |
| array-int | 直接: defint a / dim a(3) / a(1)=2.6 / V a(1) | 3 |
| array-before-def | 直接: dim a(3) / a(1)=2.6 / defint a / a(1)=5 / V a(1) / defsng a / V a(1)*10 | 5, 26 |
| array-redim-int | 直接: dim a%(3) / defint a / dim a(3) / a(1)=4 / V a(1) | 4＋直接の誤り ERR 10 |
| array-over | 直接: defint a / dim a(3) / a(1)=40000 / V a(1) | 0＋直接の誤り ERR 6 |
| array-str | 直接: defstr a / dim a(2) / a(1)="xy" / V len(a(1)) | 2 |
| array-str-numeric | 直接: defstr a / dim a(2) / a(1)=1 / V len(a(1)) | 0＋直接の誤り ERR 13 |
| array-erase | 直接: dim a(3) / defint a / erase a / defsng a / erase a / dim a(5) / a(5)=1:V a(5) | 1＋直接の誤り ERR 5 |
| for-int | プログラム: defint i:k=0:for i=1 to 3:k=k+i:next / V k | 6 |
| for-int-limit | プログラム: defint i:k=0:for i=1 to 2.6:k=k+1:next / V k | 予測なし |
| for-int-step | プログラム: defint i:k=0:for i=1 to 2 step .5:k=k+1:next / V k | 予測なし |
| for-int-edge | プログラム: p=1:defint i:k=0:for i=32766 to 32767:k=k+1:next / V k | 予測なし |
| for-dbl-step | プログラム: defdbl i:k=0:for i=1 to 2 step .5:k=k+1:next / V k | 3 |
| for-str | プログラム: p=1:defstr i:for i=1 to 2:next | ERR 13(p=1) |
| fn-def-a | プログラム: defint a:def fna(x)=x/3 / V fna(7.5)*2 | 6 |
| fn-def-f | プログラム: defint f:def fna(x)=x/3 / V fna(7.5)*2 | 5 |
| fn-def-none | プログラム: def fna(x)=x/3 / V fna(7.5)*2 | 5 |
| fn-param-int | プログラム: defint x:def fna(x)=x / V fna(2.6)*10 | 30 |
| fn-str | プログラム: defstr a:def fna(x)="hi" / V len(fna(1)) | 2 |
| read-int | プログラム: 20 defint a:read a:V a:goto 790 / 30 data 2.6 | 3 |
| read-text-into-int | プログラム: 20 p=1:defint a:read a:V a / 30 data hi | ERR 2(p=1) |
| read-num-into-str | プログラム: 20 p=1:defstr a:read a:V len(a):goto 790 / 30 data 12 | 2 |
| read-dbl | プログラム: 20 defdbl a:read a:V a=2.6#:goto 790 / 30 data 2.6 | 予測なし |
| swap-int-int | 直接: defint a,b / a=3:b=7 / swap a,b / V a | 7 |
| swap-int-single | 直接: defint a / a=3:b=7 / swap a,b / V a | 3＋直接の誤り ERR 13 |
| swap-int-suffix | 直接: defint a / a=3:b%=7 / swap a,b% / V a | 7 |
| swap-str | 直接: defstr a,b / a="ab":b="xyz" / swap a,b / V len(a) | 3 |
| swap-str-num | 直接: defstr a / a="x":b=7 / swap a,b / V len(a) | 1＋直接の誤り ERR 13 |

**予測なし4腕**: for-int-limit・for-int-step・for-int-edge（整数の FOR 変数の上限の丸め・刻み・32767 の端）、read-dbl（READ で倍精度へ読んだ 2.6 の精度）。

本体100腕（予測あり96・予測なし4）＋対照11腕、各2走。対照11腕は s9l と同じ（宣言文を使わない）。

## 打鍵・採取と関門

手本 l4_tabspc_measure と同じ（腕ごとに起動して `new`、準備・操作・結果の3枚を採る。小文字ASCII、1行80文字未満、@なし、画面本文は扱わず印と整数だけ）。
誤りは番号の包含で採り、exact は比較・関門・2走一致から外す。関門は s9l と同じ（2走採取成功、形式、準備・操作の既知印、結果先頭・終端の一意性と順序、
2走一致、対照11腕の既知予測一致）。予測と違う値でも形式が正しければ関門を通して differ にする。
公式ROMの指定は環境変数 `PC88_REF_ROM_DIR` のみ。作業置き場は `../tmp/s9m-work`。器具は `tools/l4_deftype_measure.py`
（predict / measure / check / rejudge / merge / selftest、`--predicted-only`）。

## 決めないこと

INPUT の受け皿、`DEF USR`・`DEF SEG`、`OPTION BASE`、CHAIN・MERGE（MRGFLG）による表の保持、WIDTH、大文字の宣言（打鍵は小文字のみ）、
宣言文の LIST の表示形式、EQV 等の論理演算との相互作用。予測なし腕から仕様を確定しない。自作の実装状況は述べない。
