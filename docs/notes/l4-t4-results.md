# l4-t4 機械語連携・媒体保存 第1回＋追補1 結果

2026-10-18、記録担当。最初に CLAUDE.md を読み遵守。根拠は [第1回事前登録](l4-t4-machine-language-preregistration.md)、[追補1事前登録](l4-t4-addendum1-preregistration.md)、親が測定済みの `tmp/t4-work/{mlcall,bsave}-official{,-addendum1}.tsv`。記録担当は公式ROMを実行せず、ROMの内容・内部資料・画面本文を扱わない。src変更・git commit・run_allなし。作業はtmp/t4-work/のみ。

## 関門と採否

第1回mlcallは53腕×独立2走、全106行pass。追補1mlcallは17腕×2走のうち14腕pass、3腕は両走ともcapture-gateで不明。追補1bsaveは14腕×2走、全28行pass。採用腕の固定plan、反復番号、限定RAMの書込順と最終印、ERR履歴、2走一致、較正を器具で再検証した。除外腕でも全腕集合・反復番号・固定planは検証する。実行終了・打鍵・フレーム安定・取りこぼし等の実行時関門は測定済み記録に依拠し、公式を再走していない。復帰印77だけでは受理とせず、対応段の誤りなしと実行印213を併せて判断する。未使用段の初期値0は成功や観測値ではない。

第1回bsaveはTSV上13腕ともpassだが、較正2腕を除く全11腕の最初の誤りが33 (Feature not available)。両ドライブを空媒体にしたためディスクBASICが有効でない構成だった。これは媒体機能の測定として無効であり、較正を含め第1回bsave全腕を期待値に入れない。追補1はドライブ1を環境変数経由の参照媒体コピー、ドライブ2を自作空媒体とし、a1-cal-diskの保存成功・名前一致・disk2、および非一様の誤りを要求する。公式追補1は両方を満たした。参照媒体の内容は閲覧・照合・ハッシュ化しない。

`a1-call-minus1`、`a1-call-65535`、`a1-call-undefined` は各2走で完了関門不成立。捕捉された誤り履歴はcount=0だが、完了・復帰がないので正常受理とも誤りなしとも認定しない。固定実行枠／時間切れにおける「不明」としてノートだけに残し、暴走という期待値は作らない。未定義CALLの誤り5仮説は検証不能であり、外れや的中に数えない。

## 予測ごとの判定

以下は各腕の両走一致した結果。番号には [errors.tsv](../../src/l4_basic/errors.tsv) の英語名を併記する。範囲・型・誤り等を未確定として登録した腕に、観測後の的中判定を与えない。候補内は特定番号の的中とは区別し、総合的中率は出さない。

### 第1回mlcall

|腕|公式の段順誤り|印・予測判定|
|---|---|---|
|cal-poke|0（誤りなし）|cal=213、的中|
|cal-error|13 (Type mismatch)|段1・回数1、的中|
|call-decimal|2 (Syntax error)|定数構文で拒否。実行・破壊復帰・引数受理の予測は外れ／目的未測定|
|call-hex|2 (Syntax error)|定数構文で拒否。実行・破壊復帰・引数受理の予測は外れ／目的未測定|
|call-variable|0（誤りなし）|実行213・復帰77、的中|
|call-clobber|2 (Syntax error)|定数構文で拒否。実行・破壊復帰・引数受理の予測は外れ／目的未測定|
|call-args-one|2 (Syntax error)|定数構文で拒否。実行・破壊復帰・引数受理の予測は外れ／目的未測定|
|call-args-mixed|2 (Syntax error)|定数構文で拒否。実行・破壊復帰・引数受理の予測は外れ／目的未測定|
|call-minus1|2 (Syntax error)|誤り候補は範囲内だが定数構文で拒否。境界・丸め・型は未測定（追補1へ）|
|call-65535|2 (Syntax error)|誤り候補は範囲内だが定数構文で拒否。境界・丸め・型は未測定（追補1へ）|
|call-65536|2 (Syntax error)|誤り候補は範囲内だが定数構文で拒否。境界・丸め・型は未測定（追補1へ）|
|call-fraction|2 (Syntax error)|誤り候補は範囲内だが定数構文で拒否。境界・丸め・型は未測定（追補1へ）|
|call-string|2 (Syntax error)|誤り候補は範囲内だが定数構文で拒否。境界・丸め・型は未測定（追補1へ）|
|call-missing|2 (Syntax error)|誤り候補は範囲内だが定数構文で拒否。境界・丸め・型は未測定（追補1へ）|
|def-usr0|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-usr1|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-usr2|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-usr3|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-usr4|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-usr5|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-usr6|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-usr7|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-usr8|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-usr9|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-omitted|0（誤りなし）/0（誤りなし）|定義・実行213・復帰77、的中。引数1の照合印は偶然一致として比較除外|
|def-range|2 (Syntax error)/2 (Syntax error)|定義・呼出の両段で構文誤り。範囲誤り仮説と整合|
|usr-int|0（誤りなし）/0（誤りなし）|実行213、A=02。型観測。引数1のHL+6整数候補一致は偶然で比較除外|
|usr-mutate-int|0（誤りなし）/0（誤りなし）|実行213、戻り値書換一致p65=0。HL候補不一致で介入なし。追補2へ送り腕全体を除外|
|usr-single|0（誤りなし）/0（誤りなし）|実行213、A=04。型観測。引数1のHL+6整数候補一致は偶然で比較除外|
|usr-mutate-single|0（誤りなし）/0（誤りなし）|実行213、戻り値書換一致p65=0。HL候補不一致で介入なし。追補2へ送り腕全体を除外|
|usr-double|0（誤りなし）/0（誤りなし）|実行213、A=08。型観測。引数1のHL+6整数候補一致は偶然で比較除外|
|usr-mutate-double|0（誤りなし）/0（誤りなし）|実行213、戻り値書換一致p65=0。HL候補不一致で介入なし。追補2へ送り腕全体を除外|
|usr-string|0（誤りなし）/0（誤りなし）|実行213、A=03。型観測。引数1のHL+6整数候補一致は偶然で比較除外|
|usr-mutate-string|0（誤りなし）/0（誤りなし）|実行213、戻り値書換一致p65=0。HL候補不一致で介入なし。追補2へ送り腕全体を除外|
|varptr-result-type|0（誤りなし）/0（誤りなし）|USR入口A=02、整数対照と一致。型判定成立|
|usr-undefined0|5 (Illegal function call)|誤りの仮説と整合。具体番号は未確定予測|
|usr-undefined9|5 (Illegal function call)|誤りの仮説と整合。具体番号は未確定予測|
|varptr-int|0（誤りなし）/0（誤りなし）/0（誤りなし）|負印p66=1・上位範囲印p67=1・既知符号化/長さ印p68=1、的中|
|varptr-single|0（誤りなし）/0（誤りなし）/0（誤りなし）|負印p66=1・上位範囲印p67=1・既知符号化/長さ印p68=1、的中|
|varptr-double|0（誤りなし）/0（誤りなし）/0（誤りなし）|負印p66=1・上位範囲印p67=1・既知符号化/長さ印p68=1、的中|
|varptr-string|0（誤りなし）/0（誤りなし）/0（誤りなし）|負印p66=1・上位範囲印p67=1・既知符号化/長さ印p68=1、的中。参照先一致p69=1|
|varptr-array|0（誤りなし）/0（誤りなし）/0（誤りなし）|負・上位範囲印=1、単1の符号化一致p68=0。符号は的中、格納一致予測は外れ|
|varptr-difference|0（誤りなし）/0（誤りなし）/0（誤りなし）|差6（p74=6,p75=0）。候補2/4/8すべて不一致、予測外れ|
|varptr-undefined|5 (Illegal function call)|未定義作成/受理の可能性は外れ、誤り5|
|varptr-expression|2 (Syntax error)|誤り仮説と整合（番号は未確定）|
|varptr-constant|2 (Syntax error)|誤り仮説と整合（番号は未確定）|
|varptr-file|0（誤りなし）|受理。#1を誤りとする予測は外れ。返る値の意味は未測定|
|syntax-call-extra|2 (Syntax error)|構文2/22・型13の候補内|
|syntax-usr-noparen|2 (Syntax error)|構文2/22・型13の候補内|
|syntax-usr-extra|2 (Syntax error)|構文2/22・型13の候補内|
|syntax-def-string|13 (Type mismatch)|構文2/22・型13の候補内|
|syntax-varptr-bare|2 (Syntax error)|構文2/22・型13の候補内|
|syntax-varptr-extra|2 (Syntax error)|構文2/22・型13の候補内|

### 追補1mlcall

|腕|公式誤り|印・予測判定|
|---|---|---|
|cal-poke|0（誤りなし）|cal213、的中|
|cal-error|13 (Type mismatch)|段1・回数1、的中|
|a1-call-variable|0（誤りなし）|実行213・復帰77、的中（clobberも破壊後復帰）|
|a1-call-clobber|0（誤りなし）|実行213・復帰77、的中（clobberも破壊後復帰）|
|a1-call-args-one|0（誤りなし）|実行213・復帰77。受理/入口は未確定予測。下の候補位置を確定|
|a1-call-args-mixed|0（誤りなし）|実行213・復帰77。受理/入口は未確定予測。下の候補位置を確定|
|a1-call-minus1|不明|完了関門不成立。比較除外、ノートのみ|
|a1-call-65535|不明|完了関門不成立。比較除外、ノートのみ|
|a1-call-65536|6 (Overflow)|誤り6を観測。範囲変換は未確定予測|
|a1-call-fraction|0（誤りなし）|49152.4から実行213・復帰77。第1回の丸め仮説と整合、追補では未確定予測|
|a1-call-string|13 (Type mismatch)|文字列変数の型誤り13、的中|
|a1-call-undefined|不明|完了関門不成立。比較除外、ノートのみ|
|a1-usr-int|0（誤りなし）|実行213・復帰77、A=02は予測的中。異値整数候補の不一致も的中。所在地は別判定|
|a1-usr-single|0（誤りなし）|実行213・復帰77、A=04は予測的中。異値整数候補の不一致も的中。所在地は別判定|
|a1-usr-double|0（誤りなし）|実行213・復帰77、A=08は予測的中。異値整数候補の不一致も的中。所在地は別判定|
|a1-usr-string|0（誤りなし）|実行213・復帰77、A=03は予測的中。異値整数候補の不一致も的中。所在地は別判定|
|a1-usr-cross23456|0（誤りなし）|実行213・復帰77、A=02は予測的中。異値整数候補の不一致も的中。所在地は別判定|

### 媒体（第1回は全腕無効、以下は追補1）

|腕|公式の段順誤り|印・予測判定|
|---|---|---|
|cal-poke|0（誤りなし）|cal213、的中|
|cal-error|13 (Type mismatch)|段1・回数1、的中|
|a1-cal-disk|0（誤りなし）|保存・名前・disk2一致、陽性対照の予測的中|
|a1-bload-default|0（誤りなし）/0（誤りなし）/0（誤りなし）|p73=1（自作64B全一致）、第1回からの正常ロード仮説は的中|
|a1-bload-relocate|0（誤りなし）/0（誤りなし）/0（誤りなし）|p73=1（自作64B全一致）、第1回からの正常ロード仮説は的中|
|a1-bload-run|0（誤りなし）/0（誤りなし）/0（誤りなし）|実行213・復帰77、予測的中|
|a1-missing|53 (File not found)|具体番号を確定（追補の番号予測は未確定）|
|a1-zero|5 (Illegal function call)|長さ0は誤り5。受理有無は未確定予測|
|a1-overflow|0（誤りなし）|65530から長さ10を受理、ヘッダ候補・本体パターンとも一致なし。折り返し規則未確定|
|a1-save-missing|2 (Syntax error)|具体番号を確定（追補の番号予測は未確定）|
|a1-load-missing|22 (Missing operand)|具体番号を確定（追補の番号予測は未確定）|
|a1-drive|70 (Bad drive number)|具体番号を確定（追補の番号予測は未確定）|
|a1-extra|2 (Syntax error)|具体番号を確定（追補の番号予測は未確定）|
|a1-address-string|13 (Type mismatch)|具体番号を確定（追補の番号予測は未確定）|

## 確定した事実と観測の限界

CALLは測った形式では変数番地だけ実行し、十進/十六進の定数、定数の引数付き・境界値・不足は2 (Syntax error)。変数q=49152のCALLは実行印213と復帰77、A/BC/DE/HLを固定値で破壊した腕も復帰した（SP/IX/IY破壊は測らない）。q=49152.4も同じ機械語入口を実行するので整数への丸めと整合する。q=65536は6 (Overflow)、文字列変数は13 (Type mismatch)。負数・65535・未定義変数へのCALLの結果は不明であり、一般の番地範囲は確定しない。

CALL引数の識別値12345!ではHL+0に単精度候補が一致（p33=33）。混合引数ではHL+0に整数12345（p32=33）、DE+0に文字列記述子（p43=33）、HL+6にも記述子（p37=39）、DE-6に整数（p38=27）。これはHLが第1引数の値、DEが第2引数の文字列記述子を指す観測である。HLとDEの距離6はこの配置における観測であって、一般の番地配置を自作へ要求しない。

DEF USR0〜9と番号省略を受理し、呼出し実行213・復帰77。USR10の定義/呼出しはともに2 (Syntax error)。未定義USR0/9は5 (Illegal function call)。入口Aは整数02・単精度04・倍精度08・文字列03で、追補1の識別値でも再確認。VARPTR結果を直接USRへ渡したA=02は整数対照と一致する。

追補1USR文字列ではDE+0に記述子（p43=33）、BC+30にも記述子（p49=63）。文字列そのものの候補一致はない。整数12345・単12345!・倍12345#および整数23456の全数値候補はHLの±32で不一致。DE/BCはRAM外で照合しない255であり、その±32を読み尽くして不一致だったという意味ではない。したがって「HL・DE・BCの±32の許可された候補照合で数値引数が見つからなかった」以上の所在地は確定しない。交差候補12345↔23456も一致なし。第1回に全型で出たHL+6の整数1一致は所在地の証拠にしない。

VARPTRの整数・単・倍・文字列は負を返し、16bit番地に正規化すると0x8000以上。整数1・単1・倍1の既知符号化、文字列長5とその参照先の自作文字列の照合は一致した。x%とy%の番地差は6で2/4/8仮説は外れ。未定義変数は5 (Illegal function call)、式/定数は2 (Syntax error)。VARPTR(#1)は誤りなしだが、その返値の意味・ファイル状態は測っていない。

BSAVEは名前・種別0x01が一致。通常64B保存と実行用6B保存の媒体本体では開始番地の下位先2Bがoffset0、終了番地+1の下位先2Bがoffset2、自作パターン/機械語の全体がoffset4で一致した。先頭から4バイトをヘッダとする観測であり、内容はオフセット4（5バイト目）から始まる。a1-cal-diskは長さ1のため開始と包含終端の候補がともにoffset0で重なる。0x00本体候補の位置は空き領域にも一致し、比較に使わない。BLOAD既定・指定番地への再配置は64B全一致、,Rは実行213とBASIC復帰77で成立した。

## 未解決・次回へ送る事項

- 数値USR引数12345の置き場は上記窓内に見つからない。追補2で測る。usr-mutate-*の戻り値一致は0で、候補不一致のため介入なし。引数書換の効否を断定せず、全4腕を期待値から除いて追補2で測り直す。
  解決先：[追補2・3結果](l4-t4-addendum2-3-results.md)（入口での数値引数位置、3型の書換・返却型を確認。文字列書換等は未解決）。
- VARPTR配列a(3)は負の番地を返すが単1の既知符号化に不一致。setupにDIMとa(3)=1はある。代入漏れと決めつけず、理由未確定として残す。
- BSAVE 65530番地・長さ10は受理され、ファイルと種別は一致するが登録したヘッダ候補は不一致。器具のヘッダ候補は通常DATAとpattern長に固定されており、この腕の実開始/実終端を直接分類していない。折り返し・実際の保存番地・長さの規則は未確定。受理の観測を、予測したヘッダや単純な16bit折り返しの成立へ読み替えない。
- CALLの不明3腕は上記の扱いを維持。一般のUSR戻り値規則、他の引数個数・型、BSAVEの広い境界は未測定。

## 期待値と除外の実装

`tools/l4_mlcall_measure.py` の expected/check に明示 `--results` を追加した。通常モードの全欄比較は維持する。bsave器具は同モジュールの処理を共有する。全腕集合・plan・反復・2走一致・較正を確認したうえで、次だけを理由つき固定規則で除く。TSVのexclusions列に欄ごとの理由を保存し、checkは規則の拡大・理由の改変・非除外欄の欠落を拒否する。腕単位除外はexpected/checkのEXCLUDE出力に理由を残す。

- mlcallのusr-mutate-*全4腕と追補1不明3腕は比較しない。較正2腕は両回の完全一致を検証して第1回に一本化。53−4＋17−3−2=61腕。
- 第1回bsaveは全腕不採用。--resultsに入力すると媒体構成誤りという理由で拒否する。追補1のみ14腕。
- p22〜p29（BC/DE/HL/SPの生番地）は両器具で除外。A（p21）、実行印（p30）、復帰・誤り履歴は比較する。
- 第1回USR/DEF USRのp32〜p64候補照合は引数1の偶然一致として除外。追補1の識別値の候補・最初一致ずれは比較する。
- 媒体のheader/payloadのsha256は除外。header先頭16Bにも本体や末尾由来部分が含まれ、ハッシュを残すと同じ問題を再導入するため両方を除く。種別、ヘッダ一致位置、本体自作パターン一致位置、長さ等は比較する。ただしa1-cal-diskのpayload.matchesだけは0x00の弱さを理由に除外する。

これは誤り番号や機能差を既知差として免除する処理ではない。KNOWN_DIFFERENCESは空のまま。bsave自作専用の既存関門免除（ディスク較正と一様ERR2）も機能一致には数えない。関門落ち・本文キー・予定改変などは除外の対象外である。追加の合成自己検査で、理由改変拒否、入力順序不変、生番地だけの差の許容、実行印の差と非除外腕の関門失敗の検出を確認する。

### 追記（2026-10-18、変数領域の配置差を要求から除外）

上記は当初の記録として残す。今回、変数領域の配置に依存する次の欄だけを追加除外した。要求は指す先の形式と、HLが第1引数・DEが第2引数を指す関係であり、公式の変数の並び方ではない。

- 第1回 `varptr-difference` は差6のp74/75だけを除外する。同腕の誤り番号・符号p66・上位範囲p67・形式一致p68等は引き続き比較する。
- 追補1 `a1-call-args-mixed` は隣接配置に由来するHL+6の記述子p37・DE−6の整数p38だけを除外する。HL+0の第1引数p32・DE+0の第2引数p43、A・実行/復帰印・誤り番号は比較する。第1回 `call-args-mixed` は対象外。
- 追補2の変数経由USRの最初候補差も配置依存として除外する。詳細・追補用期待値は[追補2・3結果の追記](l4-t4-addendum2-3-results.md)に記す。

再現手順の `expected --results` で記録済み公式TSVから作り直し、作業域の生成物を `tests/conformance/expected_l4_mlcall.tsv` にコピーした。SHA-256は `12b060723f840c05cc05e440cce928412b44146180782ac8c00963ac11bb8564`。公式ROMは起動していない。

今回のcheckは公式自身が一致61腕、不一致0腕（終了0）、現行HEAD `921f476` から独立ビルドした自作が一致19腕、不一致42腕（終了1）。一腕の非除外欄すべてによる照合であり、機能差の免除はない。各ラウンドの `tools/l4_mlcall_selftest.sh` は終了0、全腕が2独立走で関門通過し、通常モードの全欄自己照合も全一致した。追加の合成検査は配置差のみの許容と、非除外の形式・引数参照関係・件数真偽・A・印・誤りの差の検出を確認した。

今回の自作再現コマンド（上記の期待値生成・公式checkの後）：

```sh
bash tools/l4_mlcall_selftest.sh --round first --work-dir "$PWD/tmp/t4-work/layout-first"
bash tools/l4_mlcall_selftest.sh --round addendum1 --work-dir "$PWD/tmp/t4-work/layout-addendum1"
python3 tools/l4_mlcall_measure.py check --results --expected "$PWD/tmp/t4-work/expected_l4_mlcall.tsv" --measured "$PWD/tmp/t4-work/layout-first/selfrun.tsv" "$PWD/tmp/t4-work/layout-addendum1/selfrun.tsv"
```

今回のログは `tmp/t4-work/layout-{first,addendum1}-selftest.log` と `layout-legacy-{official,self}-check.log`。期待値の変更は指定した差欄の除外だけで、他の比較値と既存理由は同一である。src/の閲覧・変更、資料参照、公式ROM実行、run_all、git commitは行っていない。

## 再現手順と証拠

作業先制約のためexpectedはtmp/t4-work内へ生成し、同一内容をtests/conformanceへコピーする。以下の公式自身のcheckは記録済みTSVを読むだけで、公式ROMを実行しない。

```sh
python3 tools/l4_mlcall_measure.py expected --results --out "$PWD/tmp/t4-work/expected_l4_mlcall.tsv" "$PWD/tmp/t4-work/mlcall-official.tsv" "$PWD/tmp/t4-work/mlcall-official-addendum1.tsv"
python3 tools/l4_bsave_measure.py expected --results --out "$PWD/tmp/t4-work/expected_l4_bsave.tsv" "$PWD/tmp/t4-work/bsave-official-addendum1.tsv"
cp tmp/t4-work/expected_l4_mlcall.tsv tests/conformance/expected_l4_mlcall.tsv
cp tmp/t4-work/expected_l4_bsave.tsv tests/conformance/expected_l4_bsave.tsv
python3 tools/l4_mlcall_measure.py check --results --expected "$PWD/tmp/t4-work/expected_l4_mlcall.tsv" --measured "$PWD/tmp/t4-work/mlcall-official.tsv" "$PWD/tmp/t4-work/mlcall-official-addendum1.tsv"
python3 tools/l4_bsave_measure.py check --results --expected "$PWD/tmp/t4-work/expected_l4_bsave.tsv" --measured "$PWD/tmp/t4-work/bsave-official-addendum1.tsv"
bash tools/l4_mlcall_selftest.sh --work-dir "$PWD/tmp/t4-work/results-mlcall-a1"
bash tools/l4_mlcall_selftest.sh --round first --work-dir "$PWD/tmp/t4-work/results-mlcall-first"
bash tools/l4_bsave_selftest.sh --work-dir "$PWD/tmp/t4-work/results-bsave-a1"
python3 tools/l4_mlcall_measure.py check --results --expected "$PWD/tmp/t4-work/expected_l4_mlcall.tsv" --measured "$PWD/tmp/t4-work/results-mlcall-first/selfrun.tsv" "$PWD/tmp/t4-work/results-mlcall-a1/selfrun.tsv"
python3 tools/l4_bsave_measure.py check --results --expected "$PWD/tmp/t4-work/expected_l4_bsave.tsv" --measured "$PWD/tmp/t4-work/results-bsave-a1/selfrun.tsv"
```

入力・成果物のSHA-256（ファイル同一性の記録。媒体本体のハッシュとは別）：

- `tmp/t4-work/mlcall-official.tsv`: `b96d69975099b4ac016b3e69567fe747701fb7ce6f7d1db72a0f8b7f1d1bf0f8`
- `tmp/t4-work/mlcall-official-addendum1.tsv`: `fd505991f927e3f2930799fbee9d3110ce4a85ee125f7aa2d1698c57c5b46df0`
- `tmp/t4-work/bsave-official.tsv`: `1467f252e1d31299053eb3df35754ec54ecdf8af27d21c072f8c029c4244b57c`
- `tmp/t4-work/bsave-official-addendum1.tsv`: `4f182744f3e19c36ce942de3168fe99c1dccaa39f9fceb18b92972680aef8309`
- `tests/conformance/expected_l4_mlcall.tsv`: `2d95600a70b1fc05c3a01ae974e449133ebb2201f2f41bb79050f45ba87bcef8`
- `tests/conformance/expected_l4_bsave.tsv`: `00b67ef93abb492f7bed4d0fb84dc9e6ffeef506b58b6acd2931d68f44d48e60`

自作は作業開始時のHEAD `2a84b81` のsrcから各selftestで独立ビルドした。ソース本文はerrors.tsvの番号表を除き参照せず、srcの変更もない。生成ROM・作業TSV・実行ログはtmp/t4-work内に置く。

## 最終検証と自作との差

|対象|期待値腕数|公式自身|自作HEADビルド|check終了コード（公式／自作）|
|---|---:|---|---|---|
|mlcall（第1回＋追補1）|61|61一致・0不一致|19一致・42不一致|0／1|
|bsave（追補1のみ）|14|14一致・0不一致|4一致・10不一致|0／1|

l4_mlcall_selftest.sh（第1回53腕・追補1 17腕）とl4_bsave_selftest.sh（追補1 14腕）は各終了0。全自作腕で関門通過、各2独立走。通常モードの自作専用期待値との自己照合もそれぞれ全一致した。最終コードの両selftestの合成検査も終了0、追加した結果除外の合成検査も両器具で通過。公式とのcheckの終了1は機能差の検出であり、自己検査の失敗ではない。

自作mlcallの一致腕: `cal-error`、`cal-poke`、`call-65535`、`call-65536`、`call-args-mixed`、`call-args-one`、`call-clobber`、`call-decimal`、`call-fraction`、`call-hex`、`call-minus1`、`call-missing`、`call-string`、`syntax-call-extra`、`syntax-usr-noparen`、`syntax-varptr-bare`、`syntax-varptr-extra`、`varptr-constant`、`varptr-expression`。

自作bsaveの一致腕: `a1-extra`、`a1-save-missing`、`cal-error`、`cal-poke`。

一致数は除外後の一腕全欄比較で、誤り番号だけの一致数ではない。自作のCALL/USRの実行・型/候補照合、VARPTR値/格納形式、媒体保存・ロードや誤り規則に残る差は免除していない。bsaveの長さ省略と過多引数は誤り2で一致するが、正常保存・ロードの成立を示すものではない。

ログは `tmp/t4-work/results-{mlcall,bsave}-{official,self}-check.log`、自己検査は `results-mlcall-{first,a1}.log` と `results-bsave-a1.log`。srcの変更なし、HEADは2a84b81のまま。git diff --check通過。成果物は本ノート、期待値2本、共有器具tools/l4_mlcall_measure.pyの変更のみで、コミットはしていない。

自作照合TSVのSHA-256：

- `tmp/t4-work/results-mlcall-first/selfrun.tsv`: `0f17e5c0a0ca16e28592fba02d69b3671bfc76f7e0aad0b97764421d70e76604`
- `tmp/t4-work/results-mlcall-a1/selfrun.tsv`: `cfcf6cf51f2cc9171c3911a7841df40e68340bdfce712c16315edfa9c50f9bc4`
- `tmp/t4-work/results-bsave-a1/selfrun.tsv`: `6bf41ec8a6e84a80eda04e8a8debd4904918e3bf40a789e749607661f1b19dea`
