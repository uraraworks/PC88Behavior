# l4-s9n — 括弧なしの比較式・WIDTH・BEEP の事前登録

状態: **測定前**（2026-10-07）。担当は測定器具のみ。公式ROMは実行しておらず、公式の保存観測も読まない
（自作ROMでの器具の自己検査は行った）。自作BASICの実装（src/）・仕様の確定は行わない。
候補の追加、観測後の予測変更、関門の変更には、追補の事前登録を要する。

## 出典と読んだ範囲

- `CLAUDE.md`、手本 l4-s9m 一式（`l4-s9m-deftype-preregistration.md`・`l4-s9m-results.md`・`l4-s9m-addendum1-short-forms.md`、
  `tools/l4_deftype_measure.py` と selftest・登録箇所）。
- `docs/spec/l4-program.md` 4.20（POS・TAB・SPC。POS は0始まり、TAB(n) は桁 n、SPC は n mod 80）、5.2・5.6（LOCATE・WIDTH。WIDTH 40 の
  VRAMの並びは未確定）、`l4-basic.md` 4.1（折り返し W_GW。項目の前改行・コンマ56規則）・21（文字列の比較。括弧なし `and`/`or` と連結は測定済み。連鎖は未測定）。
  公式の保存観測（`tests/conformance/` の期待値・`../tmp` の生TSV）は読んでいない。
- MIT公開ソース `../refs/GW-BASIC/` を `grep -a -n` で WIDTH・BEEP・SCNINT から探した。本文を読んだ範囲:
  `GWEVAL.ASM` 395–480（関係演算子の集積と適用の優先順位）、`GIO86.ASM` 228–290（WIDTH 文の入口。数値は GWWID へ、文字列・LPRINT は装置幅）、
  `GWSTS.ASM` 180–225（GWWID: 桁・行の省略値、後続の検査、変化なしなら何もしない）・856–870（BEEP の入口）。
  SWIDTH（画面の幅の機種依存部分）は PC 版の部分が公開ソースに無く、画面の実際の動きは読めていない。
  公式ROM由来のコードは読まない。公開ソースのコードを本ノート・器具へ転載しない。検索0件を不存在の根拠にしない。
- N88-BASIC リファレンスマニュアル（言語仕様。`../refs/manual.txt` の `WIDTH` 項〔ページ 2-244〕と `BEEP` 項〔ページ 2-9〕の2か所だけ）。
  ハードウェア資料（ポート仕様）は読んでいない。BEEP のポートは「どのビットが動くかを測る」ことで調べる（下記）。

GWの手順とマニュアルの記述を散文で整理する。

**関係演算子。** 式の評価で `>` `=` `<` が続く間、その種別を印の集合（`<`=1…を含む3ビット）へ集め、**同じ記号が2回出れば構文の誤り**（`1==1`・`1<<2`）。
3種そろえた `<=>` は全ビットで常に真。集めた印は優先順位100の関係演算になり、**同じ段の演算は左から先に適用**する（連鎖 `1<2<3` は
`(1<2)` の結果 −1 を `<3` に渡す）。算術（`+` `*`）と単項マイナスは関係より先、`NOT` は関係より後（`not 1=2` は `not (1=2)`）、`and`/`or` はさらに後。
文字列どうしは文字列比較、左が文字列で右が数値（連鎖の2段目 `−1<"c"` を含む）は型の誤り（ERR 13）。結果は整数 −1/0。数値の左右の型が違えば高い型へ揃える
（単精度 1/3 と倍精度 1/3# は等しくない）。これらは公開ソースの手順の読みで、N88-BASIC が同じかは測るまで分からない。

**WIDTH。** マニュアル: 桁数は 40 か 80、行数は 20 か 25、行数を省略すると現在の行数のまま、**WIDTH 文を実行すると画面がクリアされスクロールウィンドウが初期化される**。
`WIDTH LPRINT n`・`WIDTH "装置",n`・`WIDTH #n,m` は装置・ファイルの桁数（1〜255）で、画面は変えない。GW の GWWID は桁・行とも省略可（`width ,20`・`width 40,`・`width` だけ）で、
指定が現在と同じなら何もせず、画面の変更は機種依存部分（SWIDTH）の失敗で FCERR（ERR 5）。後続に余分なものがあれば構文の誤り（ERR 2）。1バイトに収まらない値は ERR 5、
文字列の装置名が解釈できなければ「Bad file name」（ERR 56）。`LPRINT` の幅 0 は不正（ERR 5）。

**消去について予測が割れる。** マニュアルは「実行すると消える」、GW は「変化なしは何もしない」。本登録は**マニュアルを予測に採る**（同じ指定でも消える）。
観測で食い違えば結果ノートに両方を書く。

**桁数40の折り返し・コンマ・TAB・SPC（外挿）。** 80桁の既測値（l4-basic 4.1、l4-program 4.20.2）の幅だけを 40 に置き換える。
80桁ちょうどの直後は次行の桁0 → 40桁ちょうどの直後も次行の桁0。項目は現在桁＋長さが幅を超えるなら前改行。コンマは「次の14の倍数へ。次の区画が幅に収まらなければ改行」
（80桁の 56 は `(80÷14 の商 5 −1)×14`、40桁なら `(2−1)×14 = 14`）。TAB(n)・SPC(n) は n mod 幅。これは**外挿であって観測ではない**。

**BEEP。** マニュアル: `BEEP`（引数なし）は一定時間ブザー（`PRINT CHR$(7);` と同じ）、`BEEP 1` は鳴り続け、`BEEP 0` で止まる。
GW の BEEP は 800Hz・一定時間の単発で、スイッチの引数は持たない。スイッチの範囲（2・−1・256）、小数、余分な引数、文字列は読み切れず、文字列は型の誤り（ERR 13）、`beep 0,1` は構文の誤り（ERR 2）とだけ予測する。

## 採取形（WIDTH が画面を変えるための設計）

**WIDTH は桁数・行数を変え、40桁のテキストVRAMの並びは未確定（l4-program 5.6）なので、40桁・20行のまま印を採取しない。**
全腕、**印（`s9nb` 以降）を出す前に `width 80,25` へ戻す**。直接モードの腕は、width を含む行の中で最後に `width 80,25` を実行してから次の行で `s9nb` を出す
（その行が途中で誤りになっても幅が戻るよう、width の後に誤りになりうる文を置かない。width 自体が誤りの腕は幅が変わらない）。
プログラムの腕（`W`）は、本体の中で `on error goto 800` を張り、**790行（正常終了）・800行（誤りの捕捉）がともに `width 80,25` を実行してから `s9nb` を出す**
（`s9nb` は本体や10行では出さない）。観測値は本体が変数へ入れ、791行がまとめて印にする（`s9nv`）。誤りは 800行が `s9ne 1 番号 p` を出す。
器具の自己検査が、腕ごとに width 文を畳んで「印を出す時点の画面が 80,25」であることと、790・800行の形を静的に検査する（戻し忘れた腕を合成して落ちることも検査する）。

画面が消えたかは、width の前に `print "s9nq";1;5` を出しておき、**q印が採取に残るか**（残る＝消えていない）で見る。画面の本文は読まない。
カーソルの位置は `pos(0)` と、直前に取った `csrlin` との**差**（`csrlin` の起点は測っていないので絶対値を使わない）。

**BEEP のポート観測。** BEEP 腕は `--io-log` でメインCPUの `OUT 0x40` の値を記録し、本体の最初の行を打つフレームから終わりまでの窓の中で、**ビットごとに
立ち上がり・立ち下がりが1回でもあったか**だけを採る（値列は出力・保存しない。窓の手前 600 フレームから記録して、窓の最初の書き込みの比較相手を持つ。
窓の手前に書き込みが無ければ最初の書き込みは比較相手なしとして数えない）。ポート 0x40 の bit 5 がブザーだと予測するが、**どのビットが動くかも観測する**
（予測は bit 5 だけ、他のビットが動けば differ）。何も鳴らさない行 `rem` の対照（`control-port-silent`、自作ROMでも測る）で偽の変化が無いことを関門にする。
陽性対照（既知の音を鳴らす行）は自作ROMに無いので、集計の陽性・陰性は合成I/O記録の自己検査（窓の手前の変化・他ポート・サブCPU・IN を数えない、立ち上がり・立ち下がりを数える）で行う。
公式ROM由来のバイト列は扱わない（0x40 は制御ポートでデータポートではない。記録の生ファイルは作業置き場の一時ファイルで、採取後に消す）。

印は全腕に準備印 `s9np 1 1`、操作印 `s9no 1 1`、結果先頭印 `s9nb 1 1`、終端印 `s9nz 1 1`。観測は `s9nv 1 値`、誤りの印 `s9ne 1 番号 p`、画面消去の印 `s9nq 1 5`。
採取形は整数・真偽（−1/0）・位置の差だけ（単精度は6桁超で指数表記になり印にならない）。直接モードの行は1行に文をまとめ、本体は多くても4行にする
（先頭の印が画面の上へ流れた s9m の教訓）。誤り番号は包含で採り、exact は比較・関門・2走一致から外す。

## 候補と値の予測（G_GW）

候補は G_GW のみ（上の散文）。V は `print "s9nv";1;` の略、B は `print "s9nb";1;1` の略。表の打鍵は器具が実際に打つ本体で、`p=1:` は誤りの捕捉で p を見るための印。
プログラム(幅) の腕は 10行 `on error goto 800:p=0`、本体は20行から、790〜792・800行は上記の固定形。
「ERR n(p=1)」は800行が捕捉して `s9ne 1 n 1` を出し、続く値（a=0 のまま）を出す。

| 腕 | 打鍵（本体） | G_GW の予測 |
|---|---|---|
| cmp-num-eq-t | `直接: B / print "s9nv";1;1=1` | -1 |
| cmp-num-eq-f | `直接: B / print "s9nv";1;1=2` | 0 |
| cmp-num-lt | `直接: B / print "s9nv";1;1<2` | -1 |
| cmp-num-ne | `直接: B / print "s9nv";1;1<>2` | -1 |
| cmp-str-eq-t | `直接: B / print "s9nv";1;"a"="a"` | -1 |
| cmp-str-eq-f | `直接: B / print "s9nv";1;"a"="b"` | 0 |
| cmp-str-lt | `直接: B / print "s9nv";1;"a"<"b"` | -1 |
| cmp-str-gt | `直接: B / print "s9nv";1;"a">"b"` | 0 |
| cmp-str-ne | `直接: B / print "s9nv";1;"a"<>"b"` | -1 |
| cmp-str-le | `直接: B / print "s9nv";1;"a"<="a"` | -1 |
| cmp-str-ge | `直接: B / print "s9nv";1;"a">="b"` | 0 |
| cmp-and | `直接: B / print "s9nv";1;1<2 and 2<3` | -1 |
| cmp-or | `直接: B / print "s9nv";1;1>2 or 2<3` | -1 |
| cmp-add | `直接: B / print "s9nv";1;2+3=5` | -1 |
| cmp-add-before-lt | `直接: B / print "s9nv";1;1+1<2` | 0 |
| cmp-mul | `直接: B / print "s9nv";1;2*3<7` | -1 |
| cmp-concat | `直接: B / print "s9nv";1;"a"+"b"="ab"` | -1 |
| cmp-not | `直接: B / print "s9nv";1;not 1=2` | -1 |
| cmp-negconst | `直接: B / print "s9nv";1;-1=1` | 0 |
| cmp-chain-lt | `直接: B / print "s9nv";1;1<2<3` | -1 |
| cmp-chain-eq | `直接: B / print "s9nv";1;1=1=1` | 0 |
| cmp-chain-eq-m1 | `直接: B / print "s9nv";1;1=1=-1` | -1 |
| cmp-rel-le-rev | `直接: B / print "s9nv";1;1=<2` | -1 |
| cmp-rel-ge-rev | `直接: B / print "s9nv";1;2=>1` | -1 |
| cmp-rel-ne-rev | `直接: B / print "s9nv";1;1><2` | -1 |
| cmp-mixed-and-or | `直接: B / print "s9nv";1;1=1 and 2=3 or 4=4` | -1 |
| cmp-float | `直接: B / print "s9nv";1;1.5=1.5` | -1 |
| cmp-sd-third | `直接: B / print "s9nv";1;1/3=1/3#` | 0 |
| cmp-asg-num | `直接: B / a=1=1 / print "s9nv";1;a` | -1 |
| cmp-asg-num-f | `直接: B / a=1=2 / print "s9nv";1;a` | 0 |
| cmp-asg-str | `直接: B / a="b"="b" / print "s9nv";1;a` | -1 |
| cmp-asg-int | `直接: B / a%=2>1 / print "s9nv";1;a%` | -1 |
| cmp-asg-strvar-err | `直接: B / a$=1=1 / print "s9nv";1;len(a$)` | 0, 直接の誤り ERR 13 |
| cmp-vars | `直接: B / a=3:b=3 / print "s9nv";1;a=b` | -1 |
| cmp-chain-str-err | `直接: B / a="a"<"b"<"c" / print "s9nv";1;a` | 0, 直接の誤り ERR 13 |
| cmp-mixed-err1 | `直接: B / a="a"=1 / print "s9nv";1;a` | 0, 直接の誤り ERR 13 |
| cmp-mixed-err2 | `直接: B / a=1="a" / print "s9nv";1;a` | 0, 直接の誤り ERR 13 |
| cmp-print-mixed | `直接: B / print "a"=1 / print "s9nv";1;7` | 7, 直接の誤り ERR 13 |
| cmp-print-mixed2 | `直接: B / print 1="a" / print "s9nv";1;7` | 7, 直接の誤り ERR 13 |
| cmp-dup-eq | `直接: B / a=1==1 / print "s9nv";1;a` | 0, 直接の誤り ERR 2 |
| cmp-dup-lt-print | `直接: B / print 1<<2 / print "s9nv";1;7` | 7, 直接の誤り ERR 2 |
| cmp-rel-triple | `直接: B / print "s9nv";1;1<=>2` | -1 |
| w-ok-40 | `プログラム(幅): p=1:width 40:a=1  【表示 a】` | 1 |
| w-ok-80 | `プログラム(幅): p=1:width 80:a=1  【表示 a】` | 1 |
| w-ok-40-20 | `プログラム(幅): p=1:width 40,20:a=1  【表示 a】` | 1 |
| w-ok-80-20 | `プログラム(幅): p=1:width 80,20:a=1  【表示 a】` | 1 |
| w-ok-80-25 | `プログラム(幅): p=1:width 80,25:a=1  【表示 a】` | 1 |
| w-ok-40-25 | `プログラム(幅): p=1:width 40,25:a=1  【表示 a】` | 1 |
| w-ok-rows-only | `プログラム(幅): p=1:width ,20:a=1  【表示 a】` | 1 |
| w-ok-cols-trailing | `プログラム(幅): p=1:width 40,:a=1  【表示 a】` | 1 |
| w-ok-noargs | `プログラム(幅): p=1:width:a=1  【表示 a】` | 1 |
| w-ok-expr | `プログラム(幅): p=1:width 20*2:a=1  【表示 a】` | 1 |
| w-ok-lprint | `プログラム(幅): p=1:width lprint 40:a=1  【表示 a】` | 1 |
| w-err-0 | `プログラム(幅): p=1:width 0:a=1  【表示 a】` | ERR 5(p=1), 0 |
| w-err-39 | `プログラム(幅): p=1:width 39:a=1  【表示 a】` | ERR 5(p=1), 0 |
| w-err-41 | `プログラム(幅): p=1:width 41:a=1  【表示 a】` | ERR 5(p=1), 0 |
| w-err-81 | `プログラム(幅): p=1:width 81:a=1  【表示 a】` | ERR 5(p=1), 0 |
| w-err-256 | `プログラム(幅): p=1:width 256:a=1  【表示 a】` | ERR 5(p=1), 0 |
| w-err-rows-19 | `プログラム(幅): p=1:width 80,19:a=1  【表示 a】` | ERR 5(p=1), 0 |
| w-err-rows-24 | `プログラム(幅): p=1:width 80,24:a=1  【表示 a】` | ERR 5(p=1), 0 |
| w-err-rows-26 | `プログラム(幅): p=1:width 80,26:a=1  【表示 a】` | ERR 5(p=1), 0 |
| w-err-extra | `プログラム(幅): p=1:width 80,25,3:a=1  【表示 a】` | ERR 2(p=1), 0 |
| w-err-lprint-0 | `プログラム(幅): p=1:width lprint 0:a=1  【表示 a】` | ERR 5(p=1), 0 |
| w-err-str | `プログラム(幅): p=1:width "a":a=1  【表示 a】` | ERR 56(p=1), 0 |
| w-frac-404 | `プログラム(幅): p=1:width 40.4:a=1  【表示 a】` | 予測なし |
| w-frac-796 | `プログラム(幅): p=1:width 79.6:a=1  【表示 a】` | 予測なし |
| w40-wrap-39 | `プログラム(幅): width 40:c=csrlin / print string$(39,"a"); / a=pos(0):b=csrlin-c  【表示 a,b】` | 39, 0 |
| w40-wrap-40 | `プログラム(幅): width 40:c=csrlin / print string$(40,"a"); / a=pos(0):b=csrlin-c  【表示 a,b】` | 0, 1 |
| w40-wrap-41 | `プログラム(幅): width 40:c=csrlin / print string$(41,"a"); / a=pos(0):b=csrlin-c  【表示 a,b】` | 1, 1 |
| w40-wrap-45 | `プログラム(幅): width 40:c=csrlin / print string$(45,"a"); / a=pos(0):b=csrlin-c  【表示 a,b】` | 5, 1 |
| w40-wrap-85 | `プログラム(幅): width 40:c=csrlin / print string$(85,"a"); / a=pos(0):b=csrlin-c  【表示 a,b】` | 5, 2 |
| w80-wrap-80 | `プログラム(幅): width 80:c=csrlin / print string$(80,"a"); / a=pos(0):b=csrlin-c  【表示 a,b】` | 0, 1 |
| w80-wrap-85 | `プログラム(幅): width 80:c=csrlin / print string$(85,"a"); / a=pos(0):b=csrlin-c  【表示 a,b】` | 5, 1 |
| w80-after-40 | `プログラム(幅): width 40 / width 80:c=csrlin / print string$(85,"a"); / a=pos(0):b=csrlin-c  【表示 a,b】` | 5, 1 |
| w40-item-wrap | `プログラム(幅): width 40:c=csrlin / print string$(30,"a");string$(15,"b"); / a=pos(0):b=csrlin-c  【表示 a,b】` | 15, 1 |
| w40-item-exact | `プログラム(幅): width 40:c=csrlin / print string$(30,"a");string$(10,"b"); / a=pos(0):b=csrlin-c  【表示 a,b】` | 0, 1 |
| w40-num-wrap | `プログラム(幅): width 40:c=csrlin / print string$(37,"a");12345; / a=pos(0):b=csrlin-c  【表示 a,b】` | 7, 1 |
| w40-comma-1 | `プログラム(幅): width 40:c=csrlin / print "a", / a=pos(0):b=csrlin-c  【表示 a,b】` | 14, 0 |
| w40-comma-2 | `プログラム(幅): width 40:c=csrlin / print "a","b", / a=pos(0):b=csrlin-c  【表示 a,b】` | 0, 1 |
| w40-comma-13 | `プログラム(幅): width 40:c=csrlin / print string$(13,"a"), / a=pos(0):b=csrlin-c  【表示 a,b】` | 14, 0 |
| w40-comma-14 | `プログラム(幅): width 40:c=csrlin / print string$(14,"a"), / a=pos(0):b=csrlin-c  【表示 a,b】` | 0, 1 |
| w40-tab-10 | `プログラム(幅): width 40:c=csrlin / print tab(10); / a=pos(0):b=csrlin-c  【表示 a,b】` | 10, 0 |
| w40-tab-39 | `プログラム(幅): width 40:c=csrlin / print tab(39); / a=pos(0):b=csrlin-c  【表示 a,b】` | 39, 0 |
| w40-tab-45 | `プログラム(幅): width 40:c=csrlin / print tab(45); / a=pos(0):b=csrlin-c  【表示 a,b】` | 5, 0 |
| w40-tab-back | `プログラム(幅): width 40:c=csrlin / print "xxxxxx";tab(5); / a=pos(0):b=csrlin-c  【表示 a,b】` | 5, 1 |
| w40-spc-45 | `プログラム(幅): width 40:c=csrlin / print spc(45); / a=pos(0):b=csrlin-c  【表示 a,b】` | 5, 0 |
| w40-spc-39 | `プログラム(幅): width 40:c=csrlin / print spc(39); / a=pos(0):b=csrlin-c  【表示 a,b】` | 39, 0 |
| w40-locate-pos | `プログラム(幅): width 40:c=csrlin / locate 5,2 / a=pos(0):b=csrlin-c  【表示 a,b】` | 5, 2 |
| w-home-80 | `プログラム(幅): cls:c=csrlin / locate 5,10:width 80,25:a=pos(0):b=csrlin-c  【表示 a,b】` | 0, 0 |
| w-home-40 | `プログラム(幅): cls:c=csrlin / locate 5,10:width 40:a=pos(0):b=csrlin-c  【表示 a,b】` | 0, 0 |
| w8025-loc-y23 | `プログラム(幅): p=1:locate 0,23:a=1  【表示 a】` | 予測なし |
| w8025-loc-y24 | `プログラム(幅): p=1:locate 0,24:a=1  【表示 a】` | 予測なし |
| w8025-loc-y25 | `プログラム(幅): p=1:locate 0,25:a=1  【表示 a】` | 予測なし |
| w8020-loc-y19 | `プログラム(幅): width 80,20 / p=1:locate 0,19:a=1  【表示 a】` | 予測なし |
| w8020-loc-y20 | `プログラム(幅): width 80,20 / p=1:locate 0,20:a=1  【表示 a】` | 予測なし |
| w4025-loc-x39 | `プログラム(幅): width 40 / p=1:locate 39,0:a=1  【表示 a】` | 予測なし |
| w4025-loc-x40 | `プログラム(幅): width 40 / p=1:locate 40,0:a=1  【表示 a】` | 予測なし |
| w8025-scroll | `プログラム(幅): width 80,25:c=csrlin / for i=1 to 30:print:next / a=csrlin-c  【表示 a】` | 予測なし |
| w8020-scroll | `プログラム(幅): width 80,20:c=csrlin / for i=1 to 30:print:next / a=csrlin-c  【表示 a】` | 予測なし |
| w4025-scroll | `プログラム(幅): width 40,25:c=csrlin / for i=1 to 30:print:next / a=csrlin-c  【表示 a】` | 予測なし |
| w4020-scroll | `プログラム(幅): width 40,20:c=csrlin / for i=1 to 30:print:next / a=csrlin-c  【表示 a】` | 予測なし |
| w-q-same | `直接: print "s9nq";1;5:width 80,25 / B / print "s9nv";1;7` | 7 |
| w-q-40 | `直接: print "s9nq";1;5:width 40:width 80,25 / B / print "s9nv";1;7` | 7 |
| w-q-err | `直接: print "s9nq";1;5:width 39 / B / print "s9nv";1;7` | q印が残る, 7, 直接の誤り ERR 5 |
| w-q-noarg | `直接: print "s9nq";1;5:width / B / print "s9nv";1;7` | 予測なし |
| w-q-rows | `直接: print "s9nq";1;5:width ,25 / B / print "s9nv";1;7` | 7 |
| w-q-lprint | `直接: print "s9nq";1;5:width lprint 40 / B / print "s9nv";1;7` | q印が残る, 7 |
| w-d-wrap40 | `直接: width 40:c=csrlin:print string$(45,"a");:a=pos(0):b=csrlin-c:width 80,25 / B / print "s9nv";1;a / print "s9nv";1;b` | 5, 1 |
| w-d-home | `直接: cls:c=csrlin:locate 5,10:width 40,20:a=pos(0):b=csrlin-c:width 80,25 / B / print "s9nv";1;a / print "s9nv";1;b` | 0, 0 |
| w-d-roundtrip-40 | `直接: width 40,20:width 80,25 / B / print "s9nv";1;7` | 7 |
| w-d-roundtrip-80 | `直接: width 80,20:width 80,25 / B / print "s9nv";1;7` | 7 |
| beep-plain | `直接: beep / B / print "s9nv";1;7` | 7, bit5 立ち上がり・立ち下がり |
| beep-0 | `直接: beep 0 / B / print "s9nv";1;7` | 7, ポート0x40変化なし |
| beep-1-0 | `直接: beep 1 / beep 0 / B / print "s9nv";1;7` | 7, bit5 立ち上がり・立ち下がり |
| beep-1-only | `直接: beep 1 / rem / B / print "s9nv";1;7` | 7, bit5 立ち上がりのみ |
| beep-2 | `直接: beep 2 / beep 0 / B / print "s9nv";1;7` | 予測なし |
| beep-neg | `直接: beep -1 / beep 0 / B / print "s9nv";1;7` | 予測なし |
| beep-256 | `直接: beep 256 / beep 0 / B / print "s9nv";1;7` | 予測なし |
| beep-str | `直接: beep "a" / B / print "s9nv";1;7` | 7, 直接の誤り ERR 13, ポート0x40変化なし |
| beep-extra | `直接: beep 0,1 / B / print "s9nv";1;7` | 7, 直接の誤り ERR 2, ポート0x40変化なし |
| beep-two | `直接: beep:beep / B / print "s9nv";1;7` | 7, bit5 立ち上がり・立ち下がり |
| beep-if | `直接: if 1 then beep / B / print "s9nv";1;7` | 7, bit5 立ち上がり・立ち下がり |
| beep-expr | `直接: a=1:beep a:beep a-1 / B / print "s9nv";1;7` | 7, bit5 立ち上がり・立ち下がり |
| beep-chr7 | `直接: print chr$(7); / B / print "s9nv";1;7` | 7, bit5 立ち上がり・立ち下がり |
| beep-prog | `プログラム: p=1:beep:beep 0 / print "s9nv";1;9` | 9 |
| beep-prog-str | `プログラム: p=1:beep "a"` | ERR 13(p=1) |

**予測なし17腕**: `beep-2`・`beep-neg`・`beep-256`（BEEP のスイッチの範囲）、`w-frac-404`・`w-frac-796`（WIDTH の小数）、`w-q-noarg`（引数なしの width が消すか。
マニュアルと GW が割れる）、`w8025-loc-y23/24/25`・`w8020-loc-y19/20`・`w4025-loc-x39/x40`（LOCATE の上限。起点とファンクションキー行が分からない）、
`w8025-scroll`・`w8020-scroll`・`w4025-scroll`・`w4020-scroll`（スクロールの下限）。予測なし腕から仕様を確定しない。観測は規則の候補として記述する。

**外挿の腕**: `w40-*`（40桁の折り返し・コンマ・TAB・SPC。80桁の既測値を幅だけ置き換えた予測）、`w-home-*`・`w-d-home`（マニュアルの「消えてカーソルが先頭へ」）、
`w-q-*`（消去の有無。マニュアルを採る）。外れたときは外れた腕を説明する規則（数値）を結果ノートに書く。

本体126腕（予測あり109・予測なし17）＋対照12腕（s9m と同じ11腕＋ポートの無音対照）、各2走。
予測は書き換えない。

## 打鍵・採取と関門

手本 `l4_deftype_measure` と同じ（腕ごとに起動して `new`、準備・操作・結果の3枚を採る。小文字ASCII、1行80文字未満、@なし、画面本文は扱わず印と整数だけ）。
関門は s9m と同じ（2走採取成功、形式、準備・操作の既知印、結果先頭・終端の一意性と順序〔q印は先頭印の前だけ・q を出す腕だけ〕、2走一致、対照12腕の既知予測一致）に、
ポートの観測が port を持つ腕にだけ付くことを加える。予測と違う値でも形式が正しければ関門を通して differ にする。
公式ROMの指定は環境変数 `PC88_REF_ROM_DIR` のみ。作業置き場は `../tmp/s9n-work`。器具は `tools/l4_widthbeep_measure.py`
（predict / measure / check / rejudge / merge / selftest、`--predicted-only`）。関門が落ちたら、器具を曲げず追補の事前登録を先にコミットしてから再測定する。

## 決めないこと

`SCREEN`・`CONSOLE`（スクロールウィンドウ）と WIDTH の関係、日本語BASICの行数10・12、`WIDTH #n,m`・`WIDTH "COM:"` の装置、BEEP の音の長さ・周波数、
`WIDTH` 実行後のファンクションキー表示行、40桁の漢字・全角の折り返し、画面本文の内容。
自作の実装状況は述べない。
