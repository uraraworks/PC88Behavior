# l4-f2 ランダムファイル 第3回 結果

2026-10-20、記録担当。最初にCLAUDE.mdを読み遵守。根拠は[事前登録](l4-f2-randfile-preregistration.md)（2ce2550、本文変更なし）、親が取得した `tmp/f2-work/official.tsv`（85腕×独立2走）および `official-measure.log`（全腕pass、rc=0）。公式ROMを実行せず、画面本文を取得・転記していない。src変更・git commit・run_allなし。作業ファイルは `tmp/f2-work/` 内のみ。

PLAN_SHA: `c5b23debb67cd48f1578a2c865fd4de544e72de82a133ade03832ae7104fbb68`

PROGRAM_SHA: `aad12fbae8b2fa83a6d64bf4d5bdc448a233a44ca506537b8d8bc3d3ba1bcde3`

## 関門と採否

器具 `l4_randfile_measure.py` の `valid()`・`comparable()`・`gates()`・`read_passed()` で再計算した。再現スクリプトは `tmp/f2-work/p3-analyze.py`、集計は `p3-gates.json`。

|条件|結果|
|---|---|
|較正 cal-poke / cal-error|成立。合成観測と2走とも完全一致|
|陽性対照 disk-positive|成立。誤りなし・往復印1・種別00・候補ok-crlf-sub、長さ256B|
|一様誤りでない|成立。対照以外でも最初の誤りは0・2・5・52・54・55・68と分かれる|
|2走一致|全85腕。values / writes / mediaを完全比較|
|取りこぼし0|全170観測。memory_no_loss / io_no_loss / prefix_no_lossすべて真|
|その他の器具条件|stable / logical_marks / prefix_marks_absent / replay_equal / media_knownも全170観測で真|
|全体 passed|真。各腕のvalidは170/170、各腕の関門は85/85|

全85腕を採用し、除外・既知差免除はない。関門成立は予測の的中を意味しない。候補ID不一致（matches空）は検査不能ではなく、事前の自作候補で内容を説明できない観測として残す。

## 予測ごとの判定

0は誤りなし。英語名は[src/l4_basic/errors.tsv](../../src/l4_basic/errors.tsv)による。60・63は同表に名称がないため英語名不明と記す。以下の誤りは特記以外すべて段2。各表の腕を合わせて85腕を網羅する。

### 較正・OPEN（23腕）

|腕|公式の結果|予測の判定|
|---|---|---|
|cal-poke|cal=213、誤りなし|的中|
|cal-error|13 (Type mismatch)、段2、1件|的中|
|disk-positive|誤りなし、往復印1、ok-crlf-sub|的中|
|open-default|誤りなし、種別00・長さ0B|受理は的中。既定128という予測は後述の転送結果と整合しない|
|open-len-1 / -128 / -256|2 (Syntax error)、ファイルなし|1..256受理の予測は外れ|
|open-len-0 / -257|2 (Syntax error)、ファイルなし|5 (Illegal function call)の予測は外れ。長さ範囲の検査に到達したとは言えない|
|open-short-1 / -128 / -256|2 (Syntax error)|的中|
|open-number-1 / -2|誤りなし、種別00・長さ0B|的中|
|open-number-0 / -3 / -15 / -16 / -255|52 (Bad file number)|測った番号では的中。3..255全域の走査はしていない|
|open-number-256|5 (Illegal function call)|的中|
|open-nohash|誤りなし、種別00・長さ0B|的中|
|open-double-number|54 (File already open)|的中|
|open-double-name|誤りなし、種別00・長さ0B|54 (File already open)の予測は外れ。別番号で同名のランダムOPENは受理|

### FIELD（9腕）

|腕|公式の結果|予測の判定|
|---|---|---|
|field-width-127 / -128|誤りなし、長さ比較印1|的中|
|field-width-129|誤りなし、長さ比較印1|50 (FIELD overflow)の予測は外れ|
|field-sum-exact|誤りなし、64+64の長さ比較印1|的中|
|field-sum-over|誤りなし（64+65）|50 (FIELD overflow)の予測は外れ。長さ比較印は設けていない|
|field-multiple|誤りなし、先頭共有比較印1|的中|
|field-let|誤りなし、a$保持印1・再読がzの右空白詰めになる印0|的中。媒体256B、比較候補なし。全内容は不明|
|field-closed / field-after-close|誤りなし|60（英語名不明）の予測は外れ。割当後の文字列状態・再利用可能性は未測定|

### LSET / RSET（10腕）

|腕|公式の結果|予測の判定|
|---|---|---|
|lset-short / -equal / -long / -empty|誤りなし、文字列比較印1|長さ4・右空白詰め・超過時は先頭4文字、的中|
|rset-short / -equal / -long / -empty|誤りなし、文字列比較印1|長さ4・左空白詰め・超過時は先頭4文字、的中|
|lset-ordinary / rset-ordinary|誤りなし、長さ4の印1|元長保持は的中。通常変数での内容は比較していない|

FIELD経由の8腕が書いた媒体はすべて種別00・長さ256B。ただし各事前候補 short / equal / long / empty は長さ128Bなので、完全一致候補はすべてなし。比較印で確認した4文字の値と、媒体全体の形の確認を区別する。媒体末尾を事後に推定して候補へ追加していない。

### PUT / GET・レコード・LOC / LOF（21腕）

数値は16bit印を復元した値。表のLOC/LOF欄は当該腕が両方を測った場合の値であり、測っていない数値印の0をLOC/LOFの観測値とは扱わない。

|腕|公式の結果|予測の判定|
|---|---|---|
|put-omit / put-one|誤りなし、LOC1・LOF1|的中。媒体256B、packed-pad0 / sector-pad0|
|put-two|誤りなし、LOC2・LOF2|LOCは的中。媒体512Bで候補一致なし。128Bを詰める予測のLOF1は外れ|
|put-large|誤りなし、LOC33・LOF33|番号33の受理とLOCは的中。媒体8448B、候補一致なし。LOFは128B詰めなら17という予測から外れる|
|put-zero|68 (Disk full)、LOC0・LOF0、媒体0B|63（英語名不明）の予測は外れ|
|put-negative|5 (Illegal function call)、LOC0・LOF0、媒体0B|63（英語名不明）の予測は外れ|
|get-omit / get-one / get-two / get-large|55 (Input past end)、LOC0・LOF0、媒体0B|的中。書いていない空ファイルに対するGET|
|get-zero|55 (Input past end)、LOC0・LOF0、媒体0B|63（英語名不明）の予測は外れ|
|get-negative|5 (Illegal function call)、LOC0・LOF0、媒体0B|63（英語名不明）の予測は外れ|
|put-next|誤りなし、LOC2・LOF2、媒体512B、sector-pad0|LOC2は的中、LOF1・128B連続配置は外れ|
|get-next|誤りなし、2読戻印とも1、LOC2、媒体512B（候補なし）|的中|
|record-size-1 / -128|最初2 (Syntax error)が段1、段2の最初60（英語名不明）、合計5件、媒体なし|ERR0とサイズ別packedの予測は外れ。LEN句の拒否後の連鎖誤りなので指定長の挙動は確定しない|
|record-size-256|最初2 (Syntax error)が段1、段2の最初60（英語名不明）、合計7件、媒体なし|同上。FIELD/STRING$を含む後続文の個々の原因は分離不能|
|roundtrip-two|誤りなし、破壊2印と読戻2印がすべて1、媒体512B、sector-pad0|往復の予測は的中。配置はsector側に確定しpacked側は外れ|
|overwrite|誤りなし、LOF1、媒体256B、packed-pad0 / sector-pad0|的中|
|loc-before|誤りなし、LOC0・LOF0、媒体0B|的中|
|loc-after-get|誤りなし、LOC2・LOF2、媒体512B（候補なし）|LOC2は的中、LOF1は外れ|

### MKI$ / MKS$ / MKD$・CVI / CVS / CVD（21腕）

各4値は0・1・-1・12345。媒体はいずれも種別00・長さ256B。値の生バイト列は記載せず、事前登録の自作数値表現候補との一致だけを採る。

|腕|公式の結果|予測の判定|
|---|---|---|
|mki-0 / -1 / -minus1 / -12345|誤りなし、長さ2印・CVI往復印とも1、packed-pad0 / sector-pad0|すべて的中。自作の16bit符号付き2の補数・リトルエンディアン規則と一致|
|mks-1 / -minus1 / -12345|誤りなし、長さ4印・CVS往復印とも1、packed-pad0 / sector-pad0|的中。自作の4B MBF規則と一致|
|mkd-1 / -minus1 / -12345|誤りなし、長さ8印・CVD往復印とも1、packed-pad0 / sector-pad0|的中。自作の8B MBF規則と一致|
|mks-0 / mkd-0|誤りなし、規定長印・往復印とも1、候補一致なし|長さ・往復は的中。「0は全0」の自作候補との完全一致は外れ。ゼロ表現・余白のどちらが原因かは未確定|
|cvi-length-0 / -1|5 (Illegal function call)|的中|
|cvs-length-0 / -3|5 (Illegal function call)|的中|
|cvd-length-0 / -7|5 (Illegal function call)|的中|
|cvi-length-3 / cvs-length-5 / cvd-length-9|誤りなし|長い文字列の受理は的中。先頭規定長を使うという値の予測は未検証（結果値を比較していない）|

自作MBF候補は隠れた先頭1、末尾指数+129、仮数最上位に符号を置く生成規則。今回の非ゼロ整数3値での一致であり、任意の小数・丸め・指数端まで確定したわけではない。

### 順次とランダムの混在（1腕）

|腕|公式の結果|予測の判定|
|---|---|---|
|mixed-seq-random|誤りなし、読戻印1。種別00・長さ256B、比較候補なし|的中。順次OUTPUT・PRINT・CLOSE後にランダムOPEN・FIELD・GETで先頭2文字を再読できる|

## 確定した事実と適用範囲

- この起動構成（`clear ,&hbfff`、ファイル数の指定なし）では `OPEN "2:名前" AS #1` と `AS 1` を受理。番号1と2は受理、0・3・15・16・255は52 (Bad file number)、256は5 (Illegal function call)。同番号の再OPENは54 (File already open)、別番号の同名ランダムOPENは誤りなし。
- 測った `AS #1 LEN=n`（n=0・1・128・256・257）と短縮形はすべて2 (Syntax error)。したがって「指定可能なレコード長の範囲」は不明。1..256を受理するという事前仮説は採れない。
- 既定の転送はPUT/GETの番号1つに256Bセクタ1つが対応する。2レコードのファイルは512Bでsector-pad0に完全一致する。FIELDの幅128は転送レコード長の指定にならない。既定128Bのpacked配置仮説は棄却。ただしFIELDバッファの最大長や明示長指定の別構文は不明。
- FIELD幅127・128・129のLEN比較はすべて真。64+65も誤りなしで、128境界では50 (FIELD overflow)にならない。上限や50の発生条件は測れていない。複数のFIELD定義が先頭を共有し、LET後の元変数は値を保つ。閉じた番号へのFIELDだけでは誤りなし。
- LSET/RSETはFIELD変数の長さ4を保ち、それぞれ右/左を空白で詰める。超過は両方とも入力の先頭4文字を使う。通常文字列変数の長さも維持する。
- PUTの番号省略は最初1、次は2。明示番号1・2・33を受理し、LOCはその番号になる。負番号は5 (Illegal function call)。空ファイルの番号0はPUTが68 (Disk full)、GETが55 (Input past end)で異なる。
- 空ファイルのGETは省略・1・2・33で55 (Input past end)。書込済み番号1・2はCLOSE・再OPEN後も指定/省略で区別して読み戻せる。書込済み後の飛び越した未書込レコードのGETは未測定。
- LOCはOPEN直後0、成功したPUT/GET後に対象レコード番号。LOFは直後0、1/2/33レコードの書込で1/2/33、上書きでも1を保つ。媒体長256/512/8448Bと対応する256Bセクタ数で、バイト数でも128B単位でもない。
- OPENだけでCLOSEすると種別00・長さ0B。PUT後も種別00。内容の確定は上表の一致候補と長さに限定する。packed-pad0とsector-pad0が同時一致する1レコード腕だけでは配置は分離できないが、put-nextとroundtrip-twoのsector-pad0単独一致で分離できる。
- MKI$/MKS$/MKD$の長さは2/4/8、4整数値のCVI/CVS/CVD往復は成立。非ゼロ値など上表の候補一致範囲で自作規則が支持される。短い文字列は5 (Illegal function call)、規定長より1長い文字列は受理される。
- 順次からランダムへCLOSEを挟んだ混在は成功。同時に開いたままの混在や逆向きは今回の範囲外。

## 未解決

- 受理される明示レコード長指定構文と長さの最小・最大。FIELDの最大幅・合計幅、50 (FIELD overflow)の発生条件。既定転送256Bとバッファの限界の区別。
- put-two / put-largeの候補不一致。飛び越した空隙の内容を新しい候補で検証しておらず、0・空白・SUBのいずれとも断定しない。
- LSET/RSETの媒体後半、field-letの媒体全体、mks-0 / mkd-0の不一致原因。媒体を再読して推定を足していない。
- PUT番号0が68 (Disk full)となる理由、空でないファイルでの番号0、最大レコード番号・番号の端数/範囲外、エラー時の位置更新一般。
- 60・63の英語名（errors.tsvに収録なし）。63は予測にのみ現れ、今回の観測で発生していない。
- record-size腕の連鎖誤りは最初/最後/段別・件数の記録のみで個々の文に帰属できない。指定長1/128/256の成功例として使わない。
- 長い文字列をCV*へ渡した際の値と余分な文字の扱い、数値変換の小数・極値・丸め・型不一致。通常変数へのLSET/RSETの内容。ファイル番号の全域と起動構成変更時の範囲。

## 期待値と照合入口

器具の `expected` で `tmp/f2-work/expected.tsv` を生成し、そのまま `tests/conformance/expected_l4_randfile.tsv` へ複製した（85腕、除外なし）。公式自身への `check` は一致85腕・不一致0腕。

```sh
python3 tools/l4_randfile_measure.py expected --out "$PWD/tmp/f2-work/expected.tsv" "$PWD/tmp/f2-work/official.tsv"
python3 tools/l4_randfile_measure.py check --expected "$PWD/tmp/f2-work/expected.tsv" --measured "$PWD/tmp/f2-work/official.tsv"
```

`tools/l4_conform_self.py` の表にrandfile（85腕、見積600秒）をseqfileと同形で追加した。workerはimport前に `PC88_L4_RANDFILE_WORK` を作業先へ設定し、checkの第3引数に期待値のexclusions（今回は空辞書）を渡す。元の器具・判定条件は変更していない。

入口の自己検査CLIはリポジトリ外の作業先しか受け付けず、指定された作業範囲では実行できなかったため、`tools/l4_conform_selftest.py` の合成検査だけリポジトリ内tmpを許可した。外部許可根の検査は合成のリポジトリ位置を使うようにして、作業場所に依存せず許可根・兄弟・symlink脱出・不正根の判定を維持した。実測入口の `external_work()` と器具の安全条件は変更していない。

`tools/run_l4_conform_self_selftest.sh --work-dir "$PWD/tmp/f2-work/conform-selftest-cli"` はrc=0。`python3 tools/l4_conform_self.py --list` もrc=0、randfile行とmeasure/checkの引数を確認した。ログは `tmp/f2-work/conform-selftest-cli.log` と `conform-list.log`。

追加の `tmp/f2-work/p3-route-selftest.py` でも、新規randfile行に公式TSVを再生して、import前の作業根設定・measure引数・check第3引数を実測なしで通し、OKを確認した。

### 現行自作（HEADのビルド）

HEAD `f1dc8fe329eb9595925e1d004db969e79034f7cf` のsrc/tools/docs/specを `tmp/f2-work/head/` へgit archiveで展開し、そのsrcから自作ROMをビルドした。別担当の作業ツリー上のsrc変更は含めていない。展開による既定フォントパス不成立を、既存vendorフォントの明示引数で解消してビルドrc=0。そのROMに対し `measure --rom-dir`（公式指定なし、PC88_REF_*を除いた環境）を実行した。

- 自作測定：85腕×独立2走、各腕の器具関門85/85、較正・陽性・非一様・全体passedすべて真、rc=0。
- `check`：**一致11腕・不一致74腕、rc=1**。免除なし。全体関門による一括不採用ではなく、採用された自作観測との実比較。
- 一致11腕：cal-poke、cal-error、disk-positive、open-len-1 / -128 / -256 / -0 / -257、open-short-1 / -128 / -256。較正・順次陽性対照の3腕と、公式も構文拒否する8腕。
- ランダムファイルは未実装であり、この11腕の一致はランダムI/Oの成功を示さない。残り74腕は不一致。最初の誤りの分布は0が2腕、2 (Syntax error)が61腕、13 (Type mismatch)が22腕。

```sh
python3 tools/l4_randfile_measure.py measure --rom-dir "$PWD/tmp/f2-work/head-rom" --work-dir "$PWD/tmp/f2-work/head-measure" --out "$PWD/tmp/f2-work/head.tsv"
python3 tools/l4_randfile_measure.py check --expected "$PWD/tmp/f2-work/expected.tsv" --measured "$PWD/tmp/f2-work/head.tsv"
```

測定・照合ログは `head-measure.log`（rc=0）・`head-check.log`（rc=1）、判定関数と参考の腕別完全一致の集計は `head-summary.json`。公式自身の照合ログは `official-check.log`（85/85、rc=0）。いずれも `tmp/f2-work/` 内。
