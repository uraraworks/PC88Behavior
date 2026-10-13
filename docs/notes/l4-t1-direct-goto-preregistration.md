# l4-t1 直接モードの GO TO / GO SUB — 第1回事前登録

2026-10-14。最初にCLAUDE.md全文を読み、クリーンルーム規律を適用した。公式ROMは第1回では実行せず、ROMバイト列・公式保存観測・画面本文を読まない。src変更・git commit・run_all実行はしない。器具本体はtools/、本事前登録はdocs/notes/へ直接作成する。作業ファイルはtmp/t1-work/だけに置き、他のtmp/配下は開かない。公式実行を一時禁止するガードは設けない。

## 出所と仮説

既存の確定事項はdocs/spec/l4-basic.md第14.1節（1205〜1265行付近）の保存/LIST時の詰めの規則だけ。`go`、空白ちょうど1個、`to`、名前文字でない境界を詰める。`go sub`のG_Hは別の詰め方をするが、直接モードの受理や飛び先はこの規則から確定しない。型はtools/l4_input_measure.pyのmeasure/selftest/describe/expected/check、較正・独立2走・本文非出力、およびdocs/notes/l4-s9z-input-preregistration.mdの構成。限定メモリ採取はハーネスのmem-write-logの書式を確認した。外部資料・Web・ROM内部資料は読まない。

公式の直接モードでも空白1個のGO TO/GO SUBが受理されると弱く予測する。空白2個、go to30、go toxはERR2と予測する。文の途中の3腕は受理と弱く予測する。存在しない99へのGO TOはERR8と弱く予測し、詰めたGOTO 99を対照にする。いずれも仮説であり、値の予測一致は観測の関門にしない。

## 固定操作と採取

全16腕（較正2腕を含む）、各腕2走、毎走独立した新規プロセス。小文字打鍵だけ。腕ごとNEWし、10は `poke &he600,10:end`、30は `poke &he601,30:end` を保存する。GO SUB腕のみ30の末尾をRETURNにし、同じ直接行の後続を `:poke &he608,4:poke &he602,77` とする。測る文の字句は変えず、同一行の戻り先の直前だけ段印を追加する。9000〜9013にERR/ERL採取ハンドラ、9020にENDを保存し、直接の `on error goto 9000` で設定する。RUNを使わず、直接コマンドを発行する。

変数aを0、診断域E609〜E615を事前にFORで0にしてからハンドラを設定する（この準備自体は診断対象外、失敗は初期化関門で欠測）。E608に段1をPOKEしてからE600〜E607をFORで0にする。段2を書いてready/phaseの前印、段3を書いて測る文を実行する。GO SUBから同一行の後続へ戻れば段4・returned=77。次の独立した直接行で段5、さらに次の行でnext_line=88、a診断POKEを実行し、段6を書いて完了印を出す。段5の印とnext_lineはRETURN後の同一行継続と別に観測する。全固定コマンドは器具のplanで定義する。

自作専用印の用途は以下。これらは公式ROMの内部ワーク領域の番地という主張ではなく、CLEARの既定領域外に置く測定用の小領域である。実際の初期化・到達を毎走検査し、衝突や余計な書込みは関門で排除する。

| 番地 | 名称 | 用途 |
|---|---|---|
| E600 | line10 | 10への到達印10 |
| E601 | line30 | 30への到達印30 |
| E602 | returned | RETURN後に同じ直接行の続きのPOKEが実行された印77 |
| E603 | a | コマンド終了後のa（colon腕の先行代入） |
| E604 | err | 最後の誤り番号（公開ERR関数） |
| E605 | cal | 既知数213のPOKE較正 |
| E606 | ready | 初期化後・コマンド前の到達印151 |
| E607 | phase | コマンド前162、診断後163 |

| E608 | stage | 現在段：1初期化FOR、2前印POKE、3測る文、4RETURN後の同一行POKE、5次直接行とa診断、6完了POKE |
| E609 / E60A | first_err / first_stage | 最初の誤り番号 / その段 |
| E60B | last_stage | 最後の誤りの段（番号はE604） |
| E60C | error_count | ハンドラ通過数。0なら今回が全走で最初。各段での最初の誤りは書込み列中の同じ段の初出で識別 |
| E60D / E60E | first_erl_lo / first_erl_hi | 最初のERL値（0〜255で採れた場合） / 未取得印（0=取得、255=範囲外） |
| E60F / E610 | last_erl_lo / last_erl_hi | 最後のERL値（0〜255で採れた場合） / 未取得印（0=取得、255=範囲外） |
| E611 | statement_err | 段3の最後のERR、発生なし0 |
| E612 | following_err | 段4〜6の最後のERR、発生なし0 |
| E613 / E614 | initialization_err / marker_err | 段1 / 段2の最後のERR、発生なし0 |
| E615 | next_line | 測る文の後の独立した直接行が実行された印88 |

公式の内部ERROR_FLAG番地は知らず、探さない。ハンドラ先頭で `e=err:l=erl` を採り、error_count=0のときだけfirst_err/first_stage/first_erlを記録する。毎回err/last_stage/last_erlと該当段のERR欄を書き、最後にerror_countを増やす。ERLは0〜255のとき公開値を直接POKEし、それ以外は値欄0・未取得印255とし結果表を「不明」にする。大小判定以外の数値変換は追加しない。直接モードのERLの値は予測せず、較正でも特定の値を要求しない。RESUME 9020でハンドラを解除し、ENDで直接モードへ戻る。最初と最後に加え全ハンドラ書込みが残るため、各段の初回・再発を復元できる。未発生の診断値は0を保持する。cal-errorのERROR 13が段3で1回記録される経路を較正し、失敗なら全腕の数値を採用せず、画面からERR番号を推定しない。測定の結論はON ERROR設定下で発行した直接コマンドに限定する。

診断域の準備FOR打鍵開始フレーム以降、main CPUのE600〜E615への書込みだけを一時mem-write-logで採る。PC・ROMパス等の見出しを報告や数値TSVへ写さず、番地を0〜21の指数にして数値だけを保存する。画面写し、画面比較、画面本文出力は使わない。一時ログは成功・失敗ともfinallyで削除し、プロセスのstdout/stderrは捕捉して固定エラー分類へ置換する。公式ROMは環境変数PC88_REF_ROM_DIRからのみハーネスへ渡し、器具から列挙・read_bytes・ハッシュ化しない。ディスクは指定しない。

打鍵開始は自作100フレーム、公式700フレーム（公式は300で空RETURN）。各コマンド後は文字数+RETURNの8倍と240フレーム、試験コマンドの後だけさらに1200フレーム待つ。全操作後600フレーム走らせ、完了印の最後の書込みが終了より300フレーム以上前であることを要求する。延長・追加入力・観測に合わせた腕変更はしない。

## 腕・予測

以下は事前に作った打鍵文字列であって画面の転記ではない。完全な固定操作列はtools/l4_directgoto_measure.pyのplan/schedule、腕はarmsで固定し、毎走TSVのplanへ保存する。

| 腕 | 直接コマンド（段印を除く） | 30の末尾 | 事前予測（従来文言を保持） | 追加予測：測る文ERR/後続ERR、同一行戻り/次行 |
|---|---|---|---|---|
| cal-poke | poke &he605,213 | END | cal=213、ERR0 | 0/0、0/88 |
| cal-error | error 13 | END | ERR13、飛び先なし | 13/0、0/88 |
| goto-packed | goto 30 | END | 30へ、ERR0 | 0/0、0/88 |
| goto-spaced | go to 30 | END | 30へ、ERR0（弱い） | 0/0、0/88 |
| gosub-packed | gosub 30:poke &he602,77 | RETURN | 30へ、戻り77、ERR0 | 0/0、77/88 |
| gosub-spaced | go sub 30:poke &he602,77 | RETURN | 30へ、戻り77、ERR0（弱い） | 0/0、77/88 |
| goto-two-spaces | go  to 30 | END | 飛び先なし、ERR2 | 2/0、0/88 |
| goto-adjacent | go to30 | END | 飛び先なし、ERR2 | 2/0、0/88 |
| goto-name | go tox | END | 飛び先なし、ERR2 | 2/0、0/88 |
| gosub-two-spaces | go  sub 30:poke &he602,77 | RETURN | 飛び先なし、ERR2 | 2/0、0/88 |
| colon-spaced | a=1:go to 30 | END | a=1、30へ、ERR0（弱い） | 0/0、0/88 |
| if-spaced | if 1 then go to 30 | END | 30へ、ERR0（弱い） | 0/0、0/88 |
| on-spaced | on 1 go to 30 | END | 30へ、ERR0（弱い） | 0/0、0/88 |
| goto-missing | go to 99 | END | 飛び先なし、ERR8（弱い） | 8/0、0/88 |
| goto-packed-missing | goto 99 | END | 飛び先なし、ERR8 | 8/0、0/88 |
| goto-line10 | goto 10 | END | 10へ、ERR0 | 0/0、0/88 |

## 関門・判定・自己検査

G0: measureは毎回先に合成自己検査を実行する。G1: ハーネス終了0、打鍵拒否なし。G2: 採取範囲E600〜E615、取りこぼし0、記録連番・総件数一致、全記録の番地と値の形が正しい。G3: 診断域の初期化、段1と8バイトの初期化書込み、段2とready=151/phase=162、段3を順序検査する。段1の誤りブロックも初期化と混同せず検査するが、初期化欠落は欠測。G4: 全22値が整数0〜255、終了時値と書込み列の最後の値が一致。G5: 段遷移は1→2→3→（4→）5→6だけ。段と各印の書込みを照合し、ハンドラの各ブロックに非0のERR、現在段と一致するfirst/last_stage、同じERL、段別ERR欄、順次増加するcountを要求する。全走の初回だけfirst欄への書込みを許す。次行印88を必須とし、a診断欠落は段5の誤り記録がある場合だけ許す。最後は段6のphase=163が1回、完了後300フレーム以上追加書込みなし。G6: 独立2走の値と論理書込み列が完全一致（フレーム・PCは期待値にしない）。G7: cal-pokeのcal=213と誤りなし、cal-errorの最初/最後ERR13・段3・回数1・statement_err13/following_err0、他の印とnext_line=88を確認。ERLの特定値は較正条件にしない。G7失敗時は全腕gate_failed。

関門通過と仮説一致は分離する。line10/line30で該当行到達、returned=77でRETURN後同一直接行の後続POKE、next_line=88で次の直接行到達、a=1で先行代入を区別する。statement_errが非0なら測る文の段で誤り、following_errが非0ならその後の段で誤りが出たと判定し、first_stage/last_stageと全書込み列で原因段を表示する。測る文の段3には飛び先実行とRETURNも含むため、段3の誤りだけで飛ぶ文自体の拒否と断定しない。新しい欄の予測は従来の仮説から追加したもの、ERLは無予測。公式未実行の事前登録であり、自作の観測を公式予測へ置き換えない。予想外の数値はそのまま残す。関門落ちは欠測であり言語仕様の負例ではない。

expectedは全腕・各2走・固定plan一致・関門・較正・2走一致を通ったTSVだけから全22値の期待値を作る。第1回は公式期待値を作らない。TSVにはstatement_err/following_err/returned/next_line/first_stage/last_stageも独立した欄として出す。read_passedは数値観測との整合を確認し、checkはこれらの欄を含む全22値を照合する。測定側の欠測・関門落ち・較正失敗はNG。ERLも採取値として照合し、無予測と照合除外を混同しない。書込み順は測定関門だがROM間の期待値にはしない。

合成自己検査は欠落・重複終了・非整数・安定偽・追加phase・重複ERR・到達印破壊・終了欠落・最後値不一致・取りこぼし・範囲破壊・総件数破壊・連番破壊・遅い完了・記録形破壊を拒否する。expected/checkの陽性と、2走差・較正破壊・関門落ち・腕欠落・plan破壊・反復番号重複・関門を通る数値変化の陰性を確認する。複数誤り（段3で再発、段5でも発生）の最初/最後・回数保持とERL範囲外から取得への遷移も陽性検査する。追加の「誤りの段番号の取り違え」は、段3のエラーを段5としてfirst/last両方と最終値を改変しても現在段との不一致で拒否する。さらに関門を通る段5の後続ERRへ変更した観測をcheckが拒否する対照を置く。偽フロントエンドのstdout/stderrにある秘密本文が外へ出ず、一時ログが削除されることも検査する。selftestは現行srcを作業先へビルドし全16腕×2走を試走する。今回はrun_allを回さない。

## 測らないこと

大文字小文字混在、保存時/LIST時の追加規則、GO SUB直後の文字消費の全境界、RUN中のGO TO/GO SUB、RETURNなし・多重GO SUB・スタック限界、速度、ハンドラなしのエラー画面応答、画面文言、公式内部配置、ディスク、編集キー。src実装・docs/specへの確定は第2回以降。

## 第2回で親が実行するコマンド

PC88_REF_ROM_DIRを設定済みとし、器具に変更なしで以下を実行する。

```sh
python3 tools/l4_directgoto_measure.py measure --official --work-dir "$PWD/tmp/t1-work/ref" --out "$PWD/tmp/t1-work/ref.tsv"
python3 tools/l4_directgoto_measure.py expected --out "$PWD/tmp/t1-work/official-expected.tsv" "$PWD/tmp/t1-work/ref.tsv"
python3 tools/l4_directgoto_measure.py check --expected "$PWD/tmp/t1-work/official-expected.tsv" --measured "$PWD/tmp/t1-work/追加修正/selfrun.tsv"
```

第1回の自作試走はtmp/t1-work/selfrun.mdに記録する。公式測定の関門が落ちた場合、事前登録を追補してから再測定する。

## 第1回の採取修正（公式実行前）

最初の自作試走では次の直接コマンドからERRを読む方法を試したが、全16腕の基本関門通過に対しERROR 13較正で0となり、値を採用しなかった。画面本文は調べず、ERR取得をハンドラ内POKEへ変更して再試走する。最初の試走TSVはtmp/t1-work/initial-selfrun.tsvとして保持する。本登録の固定計画と第2回器具はハンドラ方式である。

第1回完了時の自作試走は16腕×2走、較正を含む全関門通過。最終器具で全結果を再検証し、自作専用expected/checkも16腕一致。公式未実行。数値の予測一致は要求していない。詳細はtmp/t1-work/selfrun.md。

## 第1回追加修正（公式実行前）

旧自作試走では詰めたGOTO対照でも最終ERR2、GO SUB対照で戻り印0/ERR2となり、測る文と後続の誤りを分けられなかった。本追加は段印、最初/最後のERR・段・ERL、段別ERR、同一行戻り/次行の分離と陰性対照を追加する。既存の腕・予測文言は保持し、新欄の予測を追加した。旧器具の完了記述は旧試走の履歴であり、本追加の結果はtmp/t1-work/selfrun.mdを参照する。公式ROM未実行、src変更・commitなし。

追加器具の最初の自作較正ではERLをINTと除算で分割するハンドラが限定RAMに余計な書込みを生じ、関門不通過だった。画面本文・srcを調べず、その変換を除去し、1バイト内のERL取得と範囲外の不明印に限定して再較正・全腕再走する。これは公式ERL値の予測ではない。

追加修正完了時は全16腕×2走が較正・関門通過。追加修正/selfrun.tsvを基に自作専用expected/checkは16腕一致。段番号取り違えを含む合成自己検査も通過。自作の数値内訳はtmp/t1-work/selfrun.mdに記録し、公式予測は変更していない。
