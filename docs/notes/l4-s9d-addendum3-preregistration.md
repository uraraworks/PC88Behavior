# l4-s9d 追補3 事前登録 — NEXT付き入れ子 FOR の深さと、ERR 26 の性質

状態: **測定前**。本作業では公式ROMを実行しない。本登録は測定後に上書きしない。
src/・tests/ は変更しない。動機は追補1の FOR の腕
（[l4-s9d-addendum1-results.md](l4-s9d-addendum1-results.md)）で、入れ子に NEXT が1つも無く、
公式は全 n で ERR 26（FOR without NEXT）・深さ0だったこと。最初の FOR（l=0）の時点で誤っており、
公式は FOR の実行時に対応する NEXT の存在を調べていると考えられる。

## 資料

CLAUDE.md、追補1の事前登録と結果、器具 `tools/l4_memlimit_measure.py` を読んだ。
マニュアル・ROM内部の資料は追加で読んでいない。PEEK・POKE・機械語呼出しは生成しない。
画面本文は記録せず、自作PRINTの整数と ERR 番号だけを採る。

## 腕1: FOR の深さの測り直し（`a3-fornext-*`）

追補1と同じ n = 64・128・256・512・1024・第3引数なし（`clear ,49152[,n]`、CLEAR の後で
ON ERROR を張り直す）。追補1の入れ子（`for a0=0 to 0:l=1:for a1=...`、1行3段、段数は n÷8＋8、
既定は72）の**後ろに、対応する NEXT を逆順にすべて置く**（`next a(k-1),...,a0` を
1行14個ずつ複数行に分ける。1行80字未満）。入れ子は行1000から、NEXT行がそれに続き、
最後の行で `print "s9dv";2;l` して行800へ飛ぶ。溢れたら ON ERROR で `s9de 2 ERR` と
`s9dv 2 l`（l は最後に成功した段数＝深さ）を採る。誤りが出なければ上限到達（段数）で、
比例の検討に使わない。CLEAR 自体が誤りなら `s9de 1 ERR` のみ（未測定）。

**仮説 F_LIN**: 深さは n の一次式 d = floor((n − c) / f) で、GOSUB（追補1: c≈89〜92、f≈7）と
同じ形。1段の大きさ f は観測し、GOSUB と同じかは予測しない。上限到達（段数の上限が
深さより小さい）は水準が足りないという意味で、その水準は式の当てはめから外す。
溢れの ERR 番号も予測しない（GOSUB は 7）。

## 腕2: ERR 26 の性質（`a3-nonext` ほか）

仮説 **F_SCAN**: 公式は FOR を実行するときに、その先のプログラムを走査して対応する NEXT を探し、
無ければ**本体を実行する前に** ERR 26 にする。予測値は立てない（観測）。印は
`s9dv 2 1`＝FOR の本体を実行、`s9dv 2 2`＝FOR/NEXT の後の行へ到達、`s9de 2 ERR`＝誤り。

- `a3-nonext`: `for i=1 to 1:print(本体印)` の後に NEXT が全く無い。ERR 26 になるか、
  本体印が出る前か後か。F_SCAN なら本体印が出ず ERR 26。
- `a3-wrongvar`: `for i=1 to 2:(本体印)` の次行が `next j`（別の変数名）。ERR 26 か、
  NEXT without FOR（ERR 1）か。F_SCAN が「変数名を問わない NEXT の有無」だけを見るなら
  26 にならず本体印が出る。変数名まで照合するなら 26。どちらかは観測する。
- `a3-nextbefore`: NEXT がプログラム上 FOR より前の行にある（行30 `next i`、行40 `for`、
  行20 の `goto 40` で NEXT を踏まずに FOR へ入る）。F_SCAN（前方のみ走査）なら ERR 26。
- `a3-withnext`（陽性対照・観測）: NEXT が後ろにある通常の FOR。本体印が2回出て行へ到達するはず。
  これは関門に使わない。

## 関門と判定

各腕2走（2走の印列一致を採取の整合性検査とする）。関門は既知値への一致だけ:
定数対照2（PRINT 73、ERROR 5→ERR=5）と、追補1の公式観測を再現する既知1腕
（`a3-known-gosub-256`。`clear ,49152,256` の GOSUB 深さ、期待 ERR 7・深さ23。
打鍵行は追補1の `a1-gosub-256` と完全一致）。1腕でも不一致なら後続を停止し、
未実行も記録して全体 gate_failed にする。SKIP は合格にしない。観測腕は P_MANUAL=observe。
腕数: 関門3＋観測10＝13腕×2走。

## 器具と自己検査

`tools/l4_memlimit_measure.py` に `--addendum 3`（predict・measure）を足した。既存の腕・予測・
check は変更していない。実行する検査は `bash tools/l4_memlimit_selftest.sh < /dev/null` のみ
（追補3の合成陽性・陰性: 印の添字違い・順序違い・欠落・重複誤りの拒否、NEXT が FOR と過不足なく
逆順に対応すること、known 腕の打鍵行が追補1と一致、既知値ずれでの停止）。
公式測定・git add・コミットは行わない。
