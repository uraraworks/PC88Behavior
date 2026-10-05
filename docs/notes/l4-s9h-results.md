# l4-s9h 結果 — PRINT USING（U_N88 が残る）

2026-10-05。記録担当。公式ROMは測定済みで、本作業は既存TSVの集計と仕様・期待値の編集のみ。
自作プログラムの PRINT 出力の文字コード列と ERR 番号だけを使った。src/ は触っていない。

事前登録: [l4-s9h-print-using-preregistration.md](l4-s9h-print-using-preregistration.md)、
固定予測表: [l4-s9h-print-using-predictions.tsv](l4-s9h-print-using-predictions.tsv)、
追補1（再判定）: [l4-s9h-addendum1-rejudge.md](l4-s9h-addendum1-rejudge.md)、
追補2: [l4-s9h-addendum2-preregistration.md](l4-s9h-addendum2-preregistration.md)。
元TSVはリポジトリ外 `../tmp/l4s9h-work/`（`official_round1_rejudged.tsv`・`official_add2.tsv`）。

## 経緯

1. **1回目**（140腕×2走）: 全280行が gate_failed。原因は折り返す定数対照2腕（control-wrap・control-long）の
   観測が器具の仮定（80桁まで書く）と違ったこと。2走は一致していた。
2. **追補1の再判定**: 折り返し2腕を関門から外し観測のみ（observed_only）にした。規則は観測を見直す前に固定した。
3. **追補2**: 指数形式の繰り上がり（carry-01〜10）と空の書式・書式文字の無い書式。関門4腕を再測した。

## 数え上げ（TSV から数え直した。親の数え上げと一致、食い違いなし）

### 1回目の再判定（140腕、`official_round1_rejudged.tsv` 280行）

| 区分 | 腕数 | 内訳 |
|---|---:|---|
| 両候補（U_GW・U_N88）と一致 | 99 | pass・agree/agree（198行） |
| U_GW 不一致・U_N88 一致 | 37 | pass・differ/agree（74行） |
| 両候補と不一致 | 1 | scientific-07 |
| 採取失敗（gate_failed） | 1 | format-empty（2走とも観測 null） |
| 観測のみ | 2 | control-wrap・control-long |
| 合計 | 140 | |

U_N88 が一致したのは 99+37=**136腕**（本体133腕のうち131腕＋定数対照5腕）。
U_GW 不一致の37腕は、通貨記号が円（`\\###.#`・`**\###.#`、amp/at 系の書式差）と文字列全体の書式、
および `$$` 系の扱いに限られる: amp-01〜03・amp4-01〜03・at-01〜03・slash2-01〜03・slash4-01〜03・
dollar-01〜08・stardollar-01〜08・yen-01〜03・staryen-01〜03。

### 追補2（22腕、`official_add2.tsv` 44行）

- 関門4腕（gate-hash-02・gate-scientific-02・gate-control-empty・gate-control-spaces）: 全通過。
- carry-01〜10: 全10腕が S_KEEP と一致。S_NORM は carry-06（繰り上がらない対照）・09・10 のみ一致、
  carry-01〜05・07・08 の**7腕**で不一致。
- xonly-lit・xonly-lit-probe: 出力 x のあと ERR 5（予測一致）。probe-present・probe-absent: 予測一致。
- 空の書式4腕（empty-lit・empty-var・empty-lit-probe・empty-var-probe）: 器具の採取失敗（観測 null）。

## 候補判定

- **U_N88 を採る**。U_GW は37腕で不一致、U_N88 は136腕で一致。
- **scientific-07 は S_KEEP で説明される**。999.5 を `##.##^^^^` に入れた観測は carry-03（同値・同書式の再現）と
  同一で、S_KEEP の予測と一致する。1回目の期待値（U_N88 の予測）が外れた理由は「繰り上がりの正規化をしない」規則
  を知らなかったため。
- format-empty は追補2の空の書式として扱う（下記）。

## 書式ごとの規則の要約（仕様書第23節が正。ここは要約）

- `#` 右詰め・`.` 小数点・0を含め表示・半端は絶対値の大きい側へ丸め（1.125→1.13、-2.5→-3）。
  欄あふれは `%` を前置して実際の桁数で出力。
- `+` は前置なら数の直前へ浮く、後置なら末尾。後置 `-` は負のときだけ `-`。`**` は余白の星埋め。
- 円記号2個（`\\`）は浮動通貨で数の直前へ浮く。`**\` は星埋め＋浮動円。`$$` は通貨ではなく**リテラル**。
- `,` は整数部の3桁区切り（1000未満は空白）。`^^^^` は E+nn 形式で、先頭の `#` は符号セル。
- 繰り上がり（S_KEEP）: 仮数が丸めで桁あふれしても指数を上げず、桁が伸びる。
- 文字列: `!` は1文字（空文字列は空白1）、`&  &`（幅n+2）は切り詰め・空白埋め、`@` は全文字列。
  `&` 単独・`\  \` は書式文字ではなくリテラル扱いで ERR 5、`\\` は数値の通貨欄なので文字列に ERR 13。
- `_` は次の文字をリテラルにする。書式は値が余れば繰り返す。

## 折り返し対照の観測（規則は未確定のまま）

control-wrap（72文字）・control-long（95文字）は、80桁まで書かず印の行頭から75桁目で行を折り、
空白5セルを挟んで次の行へ続いた（終了位置は次の行の8桁目・27桁目、追補1の記録）。
これは PRINT USING ではなく**素の PRINT の行端の折り返し**の差で、2腕だけの観測。
厳密な規則（70文字目で折る理由、空白5セルの意味、スクリーンエディタとの関係）は
別の段で測る。`l4-program.md` 第8節25項に追記した。

## 空の書式の扱い

書式が空文字列の4腕は器具で採取に失敗した。親セッションが器具外で確認した際に公式の出力の中身を見てしまい、
その件は [contamination-2026-10-05-print-using-empty-format.md](contamination-2026-10-05-print-using-empty-format.md)
に記録した。**中身はこの記録にも仕様書にも書かない**（調べもしない）。
書いてよい事実は次の3つだけ:

1. 印のあいだに**出力があった**（有無）。
2. そのあと **ERR 5**。
3. 変数で渡した形（empty-var）は出力が**2行にまたがった**。

自作は空の書式で**何も出力せず ERR 5** にする（公式の出力は再現しない）。
書式文字の無い書式（xonly-lit）は出力 `x` のあと ERR 5 で、これは通常の観測として書く。

## 期待値ファイル

- `tests/conformance/expected_l4_pusing.tsv`: 136腕（U_N88 の予測、観測と一致したもの）。
- `tests/conformance/expected_l4_pusing_add2.tsv`: 追補2の関門4腕・carry-01〜10・xonly-lit(-probe)・
  probe-present/absent と scientific-07（観測値を S_KEEP として）の計19腕。
- 器具の `check` は `gate` 列と `prediction` を要求する。再判定TSVは `status` 列のため、`status` を `gate` へ
  写した作業用TSV（リポジトリ外）に対して `python3 tools/l4_pusing_measure.py check --expected ... --measured ...`
  を実行し、**2ファイルとも rc=0（照合一致）**。期待値の1件を改変した陰性対照は rc=1。
