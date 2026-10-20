# l4-f1 順次ファイル 第1回 結果

2026-10-20、記録担当。最初に CLAUDE.md を読み遵守。根拠は [事前登録](l4-f1-seqfile-preregistration.md)（ea1e01f、書き換えない）と、親が測定済みの `tmp/f1-work/official.tsv`（90腕×独立2走、180行）・`official-measure.log`（腕ごとの pass/gate_failed のみ）。記録担当は公式ROMを実行せず、画面本文・公式ディスク由来のバイト列を扱っていない。書かれたファイルの中身は候補ID・長さ・SHA-256でのみ記し、生のバイト列は書かない。src変更・git commit・run_allなし。

## 関門と採否

全体関門は器具の `gates()` と各腕の `valid()`＋2走一致で再検算した（結果は `tmp/f1-work/p3-analyze.py` が再現）。

|条件|成否|
|---|---|
|較正（cal-poke・cal-error）|成立|
|陽性対照 disk-positive（ERR0・比較印1・種別00・ok-crlf-sub 完全一致）|成立|
|一様誤りでない（較正・陽性以外の最初のERRが複数種）|成立|
|2走一致|90腕すべて一致（関門落ちの4腕も2走は同一）|
|取りこぼし0|86腕で成立、2腕（finish-run・flush-run）で不成立|
|全腕の器具関門成立（passedの条件）|90腕中86腕のみ。4腕が偽のため `passed=false`、測定全体のrc=1|

陽性対照が通っているので、期待値は作れる。ただし器具の仕様どおり、4腕の関門落ちで `passed` は偽のままなので、`official.tsv` の180行は全行 `gate_failed` と記録されている（86腕が各自では成立していても全体関門が1腕の失敗で落ちる設計）。期待値は、4腕を腕IDで明示的に除外し、残り86腕を各自の関門（有効性・2走一致）から再検算したうえで作る。除外の仕組みは「器具の変更」の節。

## 4腕の関門落ち

いずれも RUN か LOAD で制御を渡したあとに観測する腕。偽だった条件は腕ごとに次のとおり（値・本文は出さない）。

|腕|偽の条件|根拠|
|---|---|---|
|finish-run|取りこぼし0（入出力ログ）|入出力ログの先頭区間が上限8388608件に達し、取りこぼし502323件。後続区間は0件|
|flush-run|取りこぼし0（入出力ログ）|同上。取りこぼし434825件|
|finish-load|メモリ書込ログの関門（安定／論理印のどちらか）|取りこぼしは0件。観測にはGateErrorと誤り履歴だけが残る|
|flush-load|メモリ書込ログの関門（安定／論理印のどちらか）|取りこぼしは0件。誤り履歴は空|

- run系2腕は2走とも同じ件数で、再現する。RUN後に入出力ログの先頭区間が上限に張り付く（原因の特定は未了。区間の中身は見ていない）。メモリ書込ログ側の成否は、観測に残る情報（誤り履歴のみ）からは区別できない。
- load系2腕は、器具が失敗後に保持する情報（誤り履歴のみ）では「安定」と「論理印」を区別できない。器具はどちらも同じGateErrorで落とす。
- 参考（関門落ちなので採用しない）：finish-load の誤り履歴は段3で 53 (File not found) → 60（errors.tsv に名称なし）の2件。段3の再読で OPEN が見つからなかったことを示唆するが、LOAD の振る舞いとして確定しない。

### 追補1で測り直す案（器具は今回変えない）

1. 入出力ログの開始を、lifecycle腕では `run`／`load` の打鍵フレームの直前にする（`--io-log-from-frame`）。上限到達の原因は未確定なので、まず区間の件数だけを段ごとに数えて当たりを付ける。RUN後の待ち（schedule の 18000 フレーム）自体は、メモリ側が安定した時点で十分かを、flush-end（取りこぼし0）の記録から見積もる。
2. load系2腕は LOAD 後の待ちを延ばす（mlcall の a2/a3 腕はこの待ちを 36000 フレームにしている。ここは 18000）。待ちを延ばしても落ちるなら、LOAD後に継続プログラムを打つ経路が壊れている可能性があるので、段3の再読ではなく flush-load と同じ最小経路で先に確かめる。
3. 失敗時に、どの関門条件（安定／論理印／取りこぼし）で落ちたかを観測へ残す（値は入れない）。今回の切り分けがここで止まった。
4. 追補の4腕は期待値に入れる前に、同じ全体関門（較正・陽性・非一様・2走・取りこぼし0）を通す。

## 予測ごとの判定

事前登録の予測は仮説。2択（「AまたはB」）で登録した腕は、どちらに入ったかを書き、的中とは数えない。総合的中率は出さない。誤り番号は [errors.tsv](../../src/l4_basic/errors.tsv) の英語名を併記する。

### 較正・陽性対照

|腕|公式の段順誤り|判定|
|---|---|---|
|cal-poke|0（誤りなし）|cal=213、的中|
|cal-error|13 (Type mismatch)|段2・回数1、的中|
|disk-positive|0（誤りなし）|比較印1・種別00・ok-crlf-sub完全一致、的中|

### OPEN

|腕|公式|判定|
|---|---|---|
|open-number-0|52 (Bad file number)|「範囲外は52」は的中（受理域の予測は下の行で外れ）|
|open-number-1, -2|0（誤りなし）、空ファイルを作成|受理は的中|
|open-number-3〜16|52 (Bad file number)|1..15受理の予測は外れ（受理は1と2だけ）|
|open-number-256|5 (Illegal function call)|52の予測は外れ。256は別の誤り|
|open-range-sweep|最後に受理=2、最初に拒否=3、拒否253件（誤りは常に52）|最大15の予測は外れ。受理域は1..2|
|open-output／-input／-append／-nohash|0（誤りなし）|的中。INPUT・APPENDは既存ファイルを変えない（候補 alpha-crlf-sub と一致のまま）|
|open-short-o／-short-i／-short-a|2 (Syntax error)|「0または2」の2側。短縮形 `open "o",#1,"名前"` は受理されない|
|open-bad-mode|2 (Syntax error)|的中|
|open-short-bad|2 (Syntax error)|「5または2」の2側|
|open-omit-drive|61 (File write protected)|ERR0の予測は外れ。drive2にファイルは作られない（的中）|
|open-double-number|54 (File already open)|的中|
|open-double-name|54 (File already open)|的中（別番号で同名）|
|open-wrong-type|0（誤りなし）、媒体は変化なし|59か64の予測は外れ。種別01のファイルもINPUTで開ける|
|open-missing|53 (File not found)|的中|

### 書込（PRINT／WRITE）

全腕ERR0。媒体の完全一致候補（形はすべて 自作入力から生成した候補ID）：

|腕|一致候補|長さ|判定|
|---|---|---|---|
|write-string|plain-crlf-sub|8|行末CRLF＋SUB、的中|
|write-empty|empty-crlf-sub|3|的中|
|write-positive|both-crlf-sub|7|数値は前後に空白（正数は前に空白）|
|write-negative|right-crlf-sub|7|負数は前の空白なし・後ろに空白|
|write-semi|joined-crlf-sub|5|`;` は詰めて連結|
|write-comma|zone13-crlf-sub|18|`,` は次の14桁ゾーンまで空白で埋める（間の空白13個）|
|write-trailing-semi|single-none-sub|2|行末なし・SUBのみ。末尾`;`は改行を出さない|
|write-trailing-comma|zone13-crlf-sub|18|末尾`,` の後の次のPRINTが同じ行のゾーン14桁目から続く|
|write-blank|empty-crlf-sub|3|`print #1,` は空行1行|
|write-mixed|spaces-crlf-sub|11|数値の前後空白あり|
|write-write-string|quoted-crlf-sub|10|文字列は引用符つき|
|write-write-mixed|quoted-crlf-sub|15|カンマ区切り・空白なし・空文字は引用符のみ|
|write-write-quote|raw-crlf-sub|7|内部の引用符は二重化されない|
|write-using|field-crlf-sub|6|ERR0（USINGのERR2対立候補は外れ）。`###` は3桁・前詰めの空白、後ろ空白なし|

### 読込（INPUT／LINE INPUT）

|腕|公式|判定|
|---|---|---|
|read-string／-number／-negative／-comma／-quote|0、比較印1|的中。引用符内のカンマ保持も的中|
|read-line-comma／-line-quote／-empty-line／-two-lines|0、比較印1|的中。LINE INPUT はカンマ・引用符を保持し、CRLFを除去|
|read-number-string|0、比較印1|的中（数字列を文字列変数で受けると文字列）|
|read-bad-number|0（誤りなし）|13の予測は外れ。文字列を数値変数へINPUTしても誤りにならない（受けた値は未測定）|
|read-past-end／-line-past-end|0（誤りなし）|55の予測は外れ。SUBの手前まで読んだあとの再読は誤りにならない（受けた値は未測定）|
|read-input-output|55 (Input past end)|「54または60」の予測は外れ。OUTPUTで開いた空ファイルからINPUTすると55|
|read-print-input|0（誤りなし）、媒体が変化|「54または60」の予測は外れ。入力で開いたファイルへPRINT#が受理され、先頭3バイトが書いた行（入力した文字＋CRLF）で上書きされた。長さ8は不変|

### EOF・LOC・LOF

|腕|p21（下位）|判定|
|---|---|---|
|eof-before／-middle|0|0の予測は的中|
|eof-last／-long|0|-1の予測は外れ。最後の行を読み終えた直後でもEOFは0|
|loc-before|0|読む前は0|
|loc-middle／-last／-long|1|128B単位の予測は外れ。204バイト（long）まで読んでも1|
|lof-before／-middle／-last|1|7バイトのファイルで1|
|lof-long|2|307バイトのファイルで2|

上位バイト p22 はすべて0。

### CLOSE・終了・KILL・追記

|腕|公式|判定|
|---|---|---|
|close-hash／-all／-list|0、比較印1、alpha-crlf-sub|的中|
|finish-end／-new|0、比較印1、alpha-crlf-sub|的中。ENDもNEWも開いたファイルを閉じて書き出す|
|flush-end／-new|媒体 alpha-crlf-sub|的中。CLOSEなしでもEND・NEWで媒体に出る|
|finish-run／-load, flush-run／-load|関門落ち|不明（4腕の扱い参照）|
|kill-open|54 (File already open)、媒体は alpha-crlf-sub|的中|
|append-existing|0（誤りなし）、比較印0、媒体は元の fixture と一致|ERR0は的中。追記の読戻し（印1・joined）は外れ。追記した行は論理本体（最初のSUBまで）に現れなかった|

## 確定した事実（公式・独立2走一致・器具関門成立の86腕）

### OPEN
- 受理される形：`open "2:名前" for output|input|append as #N`、`as N`（#省略）。短縮形 `open "o|i|a",#N,"名前"` と未知のモード語は 2 (Syntax error)。
- ファイル番号：この起動構成（`clear ,&hbfff`、ファイル数の指定なし）で受理は 1 と 2 だけ。0 と 3〜16 は 52 (Bad file number)、1..255 の全走査でも最初の拒否は3。256 は 5 (Illegal function call)。
- 同じ番号の再OPEN、別番号での同名の再OPENはいずれも 54 (File already open)。
- OUTPUTのOPENで、書かずにCLOSEすると、種別00・長さ0（SUBなし）のエントリが残る。
- ドライブ省略はdrive1へ向かい 61 (File write protected)（この構成のdrive1は参照媒体）。drive2にはファイルが作られない。
- INPUTで開いた種別01（バイナリ相当）のファイルも誤りなく開ける。無いファイルは 53 (File not found)。

### 書かれたファイルの形
- 行末はCRLF、論理終端はSUB（0x1A）。CLOSEで書き出される。
- 末尾が `;` のPRINTは行末を出さず、CLOSEで直接SUBが続く。
- PRINT の数値は正数が「前に空白・後ろに空白」、負数が「前の空白なし・後ろに空白」。
- `,` は14桁ゾーンの区切り（直前の欄に空白13個を足して次のゾーンの頭へ）。末尾 `,` のあとの次のPRINTも同じ行のゾーンから続く。
- WRITE は文字列を引用符で囲み、項目の間をカンマ（空白なし）、数値は前後の空白なし。内部の引用符は二重化されない。
- PRINT USING `###` は幅3・前詰めの空白で出る。

### 読込
- INPUT は文字列・正数・負数・2項目（カンマ区切り）・引用符内カンマを読める。LINE INPUT は引用符・カンマを保持し、行末のCRLFを除く。
- 文字列を数値変数へINPUTしても誤りにならない。SUBの手前を読み尽くしたあとの再読も誤りにならない。空ファイルからのINPUTは 55 (Input past end)。
- 入力で開いたファイルへのPRINT#は受理され、読み位置の先頭から上書きされる。

### EOF／LOC／LOF
- EOF は読む前・途中・最後の行を読んだ直後のすべてで 0。
- LOC は読む前に 0、読み始めたあとは 1（204バイトまで読んでも 1）。256Bセクタ単位に整合し、128B単位とは整合しない。
- LOF は7バイトで 1、307バイトで 2。256Bセクタ数に一致し、128B単位とは整合しない。

### CLOSE と終了
- `close #n`、`close`、`close n,m` はいずれも書き出し、同じ内容（alpha-crlf-sub）が再読できる。
- END、NEW はCLOSEなしでも開いたファイルを書き出す（再読も可）。
- 開いているファイルの KILL は 54 (File already open)。ファイルは壊れない。

## 未解決

- RUN・LOAD の直後に開いているファイルがどうなるか（4腕）。
- EOF が -1 になる条件。最後の行を読んだ直後でも 0。SUBに到達する読込（read-past-end の再読）は誤りにならないので、その直後の値は未測定。
- read-bad-number・read-past-end で変数が受けた値（誤りにならない読込の中身）。
- append-existing で追記した行が現れなかった理由。仮説：追記は既存のSUBを置換せず、その後ろへ書かれ、器具が最初のSUB以降を観測から外すため見えない。この観測系では区別できず、仮説のまま。
- OPENの最大番号が2であるのは、この起動構成の既定の値か。ファイル数を変える手段（MAXFILES相当）は今回未測定。
- 誤り 60 の名称（errors.tsv に収録なし）は、finish-load の参考情報にしか出ていない。

## 器具の変更

`tools/l4_seqfile_measure.py` の `expected`／`check` に `--exclude 腕ID=理由`（繰り返し可）を足した。

- 除外指定が無いときの振る舞いは変えない。公式の `official.tsv` に除外なしで `expected` を掛けると、従来どおり拒否される（陰性対照として確認済み）。
- 除外は腕IDの明示だけ。理由が空・未知の腕ID・較正2腕と disk-positive・各自の関門を通った腕は除外できない（拒否）。除外した場合も、残りの腕は有効性・2走一致を観測から再検算し、較正・陽性・非一様の全体関門を緩めない（非一様の判定は除外腕を数えない）。
- 除外の理由は期待値ファイルの `exclusions` 列に残る。`check` は同じ `--exclude` を要求し、記録と一致しなければ拒否する。
- 合成自己検査に、除外の陰性対照（除外なし拒否、別の腕の除外で拒否、通った腕の除外で拒否、較正腕・未知腕の除外で拒否、理由なしの拒否、2腕目の失敗で拒否、除外外の腕の2走不一致で拒否、除外つき期待値を除外なしで検査して拒否）を追加した。

## 期待値と照合

- `tests/conformance/expected_l4_seqfile.tsv`：86腕（除外4腕：finish-run・finish-load・flush-run・flush-load）。
- 公式自身との照合：86腕中86腕一致、不一致0腕。
- 現行の自作（HEAD のビルド）との照合：`check` の出力は一致0腕・不一致86腕。自作はOPENなど順次ファイル命令が未実装で、最初の誤りは2 (Syntax error) が84腕、較正のcal-errorが13、cal-pokeが0。陽性対照 disk-positive が成立せず全体関門が落ちるため、`check` は観測を採らず全腕を不一致にする。参考に腕ごとの観測だけを比べると、一致は較正2腕（cal-poke・cal-error）のみで、残り84腕は不一致。作業ツリーの現行ビルドの試走（`tools/l4_seqfile_selftest.sh`、90腕すべて器具関門pass）でも同じ。

再現（作業・入出力は tmp/f1-work/ 内の絶対パス）：

```sh
python3 tools/l4_seqfile_measure.py expected --out "$PWD/tmp/f1-work/expected.tsv" \
  --exclude 'finish-run=<理由>' --exclude 'flush-run=<理由>' \
  --exclude 'finish-load=<理由>' --exclude 'flush-load=<理由>' "$PWD/tmp/f1-work/official.tsv"
python3 tools/l4_seqfile_measure.py check --expected "$PWD/tmp/f1-work/expected.tsv" \
  --measured "$PWD/tmp/f1-work/official.tsv" （同じ --exclude）
```

理由の文面は期待値ファイルの `exclusions` 列と完全に一致させる。
