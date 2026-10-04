# l4-s9g — 行編集・NEW・CLEAR による保存状態の無効化

状態: **測定前**（2026-10-05）。公式ROMは本作業では実行しない。
自作ROMによる器具検査は公式の仕様を確定する根拠にしない。

[RAM配置計画](memory-map-redesign-plan.md)の段C。段Dで本文を動かす前に、
変数・配列・文字列、CONTの再開位置、GOSUBの戻り先、FORの再開位置、
DATAの読み位置、ON ERRORの設定、RESUMEの保存位置の扱いを分離して測る。
器具は [l4_editinv_measure.py](../../tools/l4_editinv_measure.py)。
印の名前は段名とずらして `s9h` 系を使用する。

## 読んだ範囲と候補の由来

- [CLAUDE.md](../../CLAUDE.md)全文。公式ROMの読出し・逆アセンブル・画面本文の
  転記はしない。記録する画面由来の値は自作PRINTの数値と、エラー表への一致の2値、
  その他の行数だけ。
- 手本 `tools/l4_hexconst_measure.py`、`tools/l4_strcmp_measure.py` の腕定義、
  印行抽出、ON ERROR、2走、定数対照、一時ビルド、check、selftest。
  `tools/l4_listnum_measure.py` の `entry_error_numbers`、`entry_message_status`、
  `probe_entry`、`probe_entry_status`（本作業では既存関数を呼んで起動しない）。
- [l4-basic.md](../spec/l4-basic.md)第14.5〜14.7節と
  `l4-s5i-round2-results-and-addendum2-preregistration.md`、
  `l4-s5i-round3-results-and-addendum3-preregistration.md` の入力時探り。
  完全一致だけでは末尾付きの表示を見逃すため、包含と完全一致を別々に記録する。
- [l4-program.md](../spec/l4-program.md)第3.1〜3.3節、第4.2〜4.4節、
  第4.4d〜4.5節、第4.10〜4.11節、第6.1〜6.3節。
  CLEARについては同文書の索引・未確定の項と l4-basic 第20節への参照を確認。
  既存の観測はSTOP/CONT、FOR、GOSUB、配列、READ/RESTOREの基本動作であり、
  今回の編集後の状態はそこから確定しない。NEWの本文消去は既存器具の準備にも使われる。

GW-BASICはローカルの `../refs/GW-BASIC/` にある1983年公開ソース（MIT）だけを読む。
`rg -a` でラベルと呼出しを探し、次の範囲を実際に読んだ。検索0件を不存在の証拠にしない。
公式PC-88 ROM内部の経路・番地は参照しない。

| ファイル | 読んだ行 | 用途 |
|---|---|---|
| README.md | 1〜29 | 公開物の由来とMIT |
| GWMAIN.ASM | 350〜430、470〜545、580〜820 | 直接入力、編集・削除・挿入、誤り、FINI |
| GWMAIN.ASM | 1665〜1710、2016〜2208 | 文の実行境界、RUN、GOTO、GOSUB、RETURN |
| GWMAIN.ASM | 2330〜2455、2470〜2539、3310〜3348 | ON ERROR、RESUME、編集前のポインタ処理 |
| BIMISC.ASM | 164〜314、540〜665、780〜890 | NEW、CLEAR、変数・スタックの初期化、RESTORE、STOP、CONT |
| GWDATA.ASM | 1240〜1310 | ON ERROR、RESUME、CONT、変数表、DATAの状態の用途 |
| GIO86.ASM | 736〜778 | キーボードからの直接命令の入口 |
| GWLIST.ASM | 279〜325、816〜864 | LISTと行の削除 |
| NEXT86.ASM | 1〜115 | FORの保存状態、NEXTの対応照合 |

GWの成功した編集は、行参照の変換と行の削除／挿入、リンクの修正を経て、
FINIからRUNC、CLEARC、STKINIへ進む。位置がSTOPより前か後かはこの経路の
初期化条件になっていない。同じ本文の打ち直しも既存行を削除して挿入する経路を通る。
削除時には変数と配列の終端も本文末尾へ戻し、挿入前にはエラートラップを切る。

CLEARCは単純変数と配列の領域を空にし、文字列領域を解放する。
ON ERRORの行と捕捉中のフラグ、CONTの保存位置を消し、RESTOREを呼んでDATAを先頭へ戻す。
STKINIはFOR/GOSUBの文脈を捨てる。NEWは先に本文を空にして同じ初期化へ進み、
引数なしCLEARも同じ初期化へ進む。RESUMEは捕捉中フラグを必要とするため、
このフラグを消した後は保存位置のバイトが残るかにかかわらず再開できない。
今回測るのは利用者から見える無効化であり、内部保存領域の消去方法ではない。

存在しない行番号だけの入力は、通常のキーボード入力では編集成功のFINIより前に
誤りへ進む。この経路はCLEARCを呼ぶ経路とは異なる。
直接代入とLISTも編集成功の初期化を通らず、LISTはCONT情報を変えないよう直接状態にする。
ただし捕捉中のRESUME、およびON ERROR設定中の存在しない行の削除は、
誤り処理そのものが状態を変える。これら3腕は値までの予測を登録せず記述測定にする。
これ以外の候補 **E_GW** は、上の公開ソースの経路をPC-88で反証する仮説である。

## 腕と自作プログラム

14操作×10検査＝**本体140腕**、定数・誤り分類対照10腕、全150腕を**各2走**。
各腕・各走を別の起動にし、同じ停止状態から1操作だけを行う。
変数のPRINTが配列を作ったり、CONTの失敗がスタックに影響したりする交絡を避ける。
全打鍵計画は器具の `predict` がTSVへ出力する。

共通の準備は次の自作行。実際は検査ごとに30以降を下表の内容へ替えてからRUNする。
STOPは100行で、実行中の位置の前後は数値行番号と本文の順序の双方で分ける。

```basic
10 rem before
20 dim b(3):a=17:b(2)=23:c$="abc"
25 print "s9hb";1;a;b(2);len(c$)
30 goto 100
100 print "s9hp";1;1:stop
110 print "s9hc";1;1
120 end
150 rem after
```

| 操作ID | STOP後に打つ行 | 目的 |
|---|---|---|
| none | 操作なし | 停止状態の陽性対照 |
| insert-before | `15 rem inserted` | 別番号の行を停止位置より前へ挿入 |
| insert-after | `155 rem inserted` | 別番号の行を停止位置より後へ挿入 |
| delete-before | `10` | 前の既存行の削除 |
| delete-after | `150` | 後の既存行の削除 |
| replace-stop | `100 print "s9hp";1;1:stop:rem changed` | 停止した行そのものの置換 |
| replace-before | `10 rem changed before and longer` | 前の既存行を長い本文へ置換 |
| replace-after | `150 rem changed after and longer` | 後の既存行を長い本文へ置換 |
| replace-identical | `150 rem after` | 同一番号・同一本文の打ち直し |
| missing | `777` | 存在しない行の削除入力、誤りを独立に採取 |
| new | `new` | 本文と状態の消去 |
| clear | `clear` | 本文を保持する状態消去 |
| assign | `a=29` | 直接モードの代入だけ |
| list | `list` | 表示だけ |

共通PRINT `s9hb 1 17 23 3` とSTOP直前の `s9hp 1 1` が準備の関門。
DATA腕はこの間に最初のREADの印 `s9ha 1 11` も必要。

| 検査ID | 準備の差と操作後の診断 | 成功時に自作PRINTが出す値 |
|---|---|---|
| vars | 直接 `print "s9h";1;a;b(2);len(c$)` | `[1,17,23,3]` |
| cont | 共通準備から `cont` | `s9hc [1,1]` |
| gosub | 30でGOSUB 100、110でRETURN、40で印、50でEND。診断はCONT | `s9hr [1,71]` |
| for | 30でk=0とFOR i=1 TO 3、40でkを加算、50でk=1だけ100へ。60で110へ。110でNEXT i、120で印とEND。診断はCONT | `s9hf [1,3,4]`（総本体回数3・最終i=4） |
| data | 900にDATA 11,22,33。30でREAD d、35で最初の値の印を出して100へ。110でREAD d、115で印。診断はGOTO 110 | `s9hd [1,22]` |
| onerror | 30でON ERROR GOTO 800を設定して100へ。110でERROR 5。800でERRの印とRESUME 120、120で終了印とEND。診断はGOTO 110 | `s9he [1,5]`、`s9hn [1,1]` |
| return-goto | gosubと同じ準備。診断だけGOTO 110 | `s9hr [1,71]` |
| next-goto | forと同じ準備。診断だけGOTO 110 | `s9hf [1,3,4]` |
| resume | 30でON ERROR GOTO 800、40でERROR 5。800から100へ行ってSTOP。110でRESUME NEXT、50で印とEND。診断はCONT | `s9hu [1,83]` |
| resume-goto | resumeと同じ準備。診断だけGOTO 110 | `s9hu [1,83]` |

補助GOTO腕はCONTの無効化とFOR/GOSUB/RESUMEの無効化を分離する。
ON ERRORを診断の直前に設定し直すことはしない。
RESUMEは誤り処理に入った後のSTOPから、元の誤りの次へ戻る位置の保持を調べる。

## E_GWの固定予測

`none`・`list`・`assign`は保持。`missing`もエラートラップのない検査では保持し、
操作直後に番号8の包含／完全一致=`true,true`を予測する。
`assign`のvarsだけは `[1,29,23,3]`。そのほかの保持値は前表の成功値。
捕捉中のRESUMEとON ERRORに対するmissing（3腕）は**予測なし**。

すべての挿入・削除成功・置換（同一本文を含む）とCLEAR、NEWは初期化する。
値と誤りの予測は以下。誤り本文は記載しない。

| 検査 | 編集成功・CLEAR | NEW |
|---|---|---|
| vars | `s9h [1,0,0,0]` | 同左 |
| cont、gosub、for、resume | 番号17、包含／完全一致=`true,true` | 同左 |
| data | `s9hd [1,11]`（先頭へ） | GOTO対象なし: 番号8、`true,true` |
| onerror | 捕捉されず番号5、`true,false` | GOTO対象なし: 番号8、`true,true` |
| return-goto | 番号3、`true,false` | 番号8、`true,true` |
| next-goto | 番号1、`true,false` | 番号8、`true,true` |
| resume-goto | 番号20、`true,false` | 番号8、`true,true` |

操作が初期化したとき、操作段階ではPRINT印以外の数値印・誤りは予測しない。
準備・操作・診断の付帯打鍵（CLSと定数PRINT）が状態を保持する前提は、無操作対照で検証する。

## 採取・関門・照合

準備のRUN/STOP直後を採取し、CLS、対象操作、定数の `s9ho [1,1]`、採取、
CLS、診断、定数の `s9hz [1,1]`、採取の順。
操作直後の誤りを後のCONT/GOTOの誤りと混ぜない。
印を打つ前後に、カーソル位置を仮定する打鍵・画面編集は行わない。
小文字ASCII、各入力80文字未満、`@`なし。直接命令は数字で始めず、
行入力・削除操作だけ意図して数字で始める。PRINTの正数の先頭空白を必須にする。

VRAMは25行・1行120バイトのうち先頭80セルを内部で調べる。
印で始まる行だけを全行一致の整数PRINTとして取り出す。壊れた印はinvalidにし、
その他の行へ逃がさない。印の値と項数、準備の既知値、段階の終端印を検査する。
印以外は非空行の件数だけ。誤りは既存 `entry_message_status` を全エラー番号へ適用し、
番号と包含／完全一致の2値だけ保存する。該当のない番号は暗黙に `false,false`。
画面本文、未知の文字、未知の行番号やメッセージの断片は出力しない。
フロントエンドstdout/stderrと例外本文も出さない。写しは採取後にfinallyで削除する。
複数採取の `.f<6桁フレーム>` と単枚の元名を区別する。

10対照はvars・FOR回数・READ・ERR捕捉印を10進定数で出す4腕と、
直接の番号5/8/17、プログラム内の番号1/3/5を起こす6腕。
番号20の包含／完全一致は合成写しで陽性陰性を検査する。
誤りの包含だけの形と完全一致の形を実行で校正する。
全対照の既知値一致が必要で、1腕の欠落・失敗でも全体関門は失敗。
全腕は2走の採取成功・一致と妥当な印の形を必要とする。
E_GWとの不一致はdiffer、予測なしはunpredictedとして残し、仕様確定・適合合格にしない。
measureのrc=0は採取の関門通過を意味する。仮説への適合合格はcheckで既知値と
全対象腕が一致した場合だけ。SKIPはなく、不足や予測nullをcheckの合格にしない。
checkは対照一式、腕の集合、2走の番号1/2、失敗フラグ、各段階の値を再検査する。
凍結観測TSVもcheckの期待値入力にできるが、本事前登録では公式期待値を作らない。

```sh
python3 tools/l4_editinv_measure.py predict --out <作業先>/prediction.tsv
python3 tools/l4_editinv_measure.py measure --official --out <作業先>/measured.tsv
python3 tools/l4_editinv_measure.py check --expected <凍結期待値.tsv> --measured <測定.tsv>
bash tools/l4_editinv_selftest.sh < /dev/null
```

公式ROMは将来のmeasureで環境変数 `PC88_REF_ROM_DIR` だけから受け取る。
自作測定は `--rom-dir`。測定の作業先既定は `../tmp/l4s9g-work`。
selftestはOSの一時ディレクトリを既定として自作ROMをビルドし、成果物を片付ける。
`--work-dir` で一時作業先を変更できる。

selftestは全予測の固定値・採取の陽性陰性・短い写し・印の破損・包含と完全一致・
2走不一致・採取欠落・対照欠落・対照値破損・SKIP相当のgate失敗・期待値改変を検査する。
自作ROMでは定数・誤り分類10腕と無操作のvars/CONT/GOSUB/FOR/READ、
RETURN/NEXTへのGOTOの7腕、計17腕×2走だけを使う。
編集後の自作動作、ON ERROR保持、RESUME保持は自作合格の条件にしない。
`src/`・`tests/`は変更せず、実行する検査は上記selftestだけ。

器具作成中の自作検査では、READとPRINTを同じ行にした2回目のREADが番号2に
なったため、READとPRINTを別行にした（初回も別行に統一）。この形の無操作DATA腕は
既知値22に一致した。番号20をRESUME NEXTまたはERROR 20で起こす自作対照も番号2に
なったため、既存機能だけを使う自作対照の範囲から外し、番号20の抽出は合成検査にする。
これらは公式の観測ではなく、期待値を番号2へ変えたりSKIPを合格にしたりしない。
公式のRESUME腕とそのE_GW予測は維持する。

最終の `bash tools/l4_editinv_selftest.sh < /dev/null` は **rc=0**。
固定予測、PRINTと誤り2値の陽性陰性、2走・欠落・対照破損の拒否、偽フロントエンドの
多枚採取名・打鍵順・写しの片付け・本文非出力、自作一時ビルドと17腕×2走、
checkの既知値一致と期待値改変拒否が通過した。run_all自体は実行していない。

## 決めないこと

LOAD・MERGE（ディスクを使う別段）、CHAIN、スクリーンエディタによる行の編集中の挙動。
内部ポインタの番地・消去バイト、CLEARの引数やメモリ容量、エラー表示の末尾文字、
乱数・イベント・ファイル・描画状態の初期化。本文ポインタの修復方式も公式測定前に決めない。
