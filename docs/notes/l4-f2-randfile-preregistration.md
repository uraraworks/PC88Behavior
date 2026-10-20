# l4-f2 ランダムファイル 第1回事前登録

2026-10-20。CLAUDE.mdを最初に読み適用。今回は器具・自己検査・自作ROM試走まで。公式ROMは実行しない。公式ROMの内容を読む経路・画面取得は設けない。器具の `measure --official` は通常どおり利用でき、第2回に親が実行する。src変更・commit・run_allなし。

PLAN_SHA: `c5b23debb67cd48f1578a2c865fd4de544e72de82a133ade03832ae7104fbb68`

PROGRAM_SHA: `aad12fbae8b2fa83a6d64bf4d5bdc448a233a44ca506537b8d8bc3d3ba1bcde3`

署名はserial_planのJSON（キー整列、区切りカンマ/コロン、UTF-8）と、全腕program配列のJSONからSHA-256。候補の生データはplanでは各候補のSHA-256へ置換。

## 読んだ範囲

言語マニュアルは読んでいない（ページ番号: 該当なし）。docs/spec/l4-basic.md 第24節および第14.8節の該当表、docs/spec/l3-disk-format.md 第1.2・1.3節と第2.1〜2.5節を読んだ。docs/spec/l3-subrom.md は「ランダムアクセス需要入口」の第97版の該当行を確認（独立した同名見出しは見つからなかった）。同入口の参照先 docs/notes/m7cu-random-file-entry-conformance.md も読んだ。実装ソース本文・旧公式測定ログは読まない。既存順次器具、自己検査、run_all登録、計測フロントエンドの公開オプション、比較印検証器を読んだ。

取得範囲の逸脱: 初期の位置探索で `^## |^### |ランダムアクセス需要入口|種別|鎖` という広すぎるrgをl3-disk-format.md/l3-subrom.mdへ適用し、指定節外の見出し・改版行・種別/鎖に該当する本文断片も表示した。仕様全文は開いていない。これらを本測定の追加の仕様根拠にはしない。公式ROMバイト列・画面本文の取得は無い。以後は行範囲を限定した。

## 媒体・起動・記録

全腕でdrive1は参照媒体の作業コピー（PC88_REF_DISK_DIRと凍結設定から既存prepareが解決）。自作試走で参照環境変数が無ければ、自作空媒体に書込禁止印（18,1,13）を立てた代替媒体。drive2は毎起動、既存build_blank_data_diskから作る自作空データ媒体。ファイル名は打鍵どおり小文字 f2own、常に2:指定。書禁・満杯を測る腕は追補に回す。

clear ,&hbfff、番号数設定なし。各腕はsetup/target/closeの3段。ON ERRORで最初/最後/段別のERRと回数を印へ保存しRESUME NEXT。POKE診断域C300-C35Fのみ、数値21..29はLOC/LOF、65..73は自作比較の真偽。画面は取得せず、stdout/stderrは捕捉して本文を表示しない。LOAD後に観測プログラムを続ける経路なし。

作業rootは PC88_L4_RANDFILE_WORK（既定tmp/f2-work）、CLIの作業/入出力はその内側の絶対パスに限定。公式ROMはPC88_REF_ROM_DIRから測定フロントエンドに渡すのみ。今回PC88_REF_*は指定せず自作ROMだけをビルド・実行する。

共通部分はl4_seqfile_measureをimportする。BASIC program/error handler、boolean/number、打鍵schedule、媒体prepare、sectorアクセス、memory_conditions/io_counts、較正/陽性/一様誤りgates、synth、first_expected/first_check、parse_excludeを再利用する。expected/check呼出し中の定義束縛はcontext managerで復元し、実走とは並行しない。順次器具自体は変更しない。

## ログ区間と関門

各腕2独立走。各走は同じ打鍵計画を空媒体から2回再生する。前半は打鍵開始から最初のRUN直前まで実行・採取し、後半は同じ打鍵を再現して最初のRUN直前から終了まで採取する。窓はRUNの1フレーム前で接続し欠けない。前半に診断印が無くdrive2が初期媒体と完全一致すること、後半のRUN前にも診断印が無いことを要求する。起動コピー間の任意の内部状態の等価性を主張するものではない。

メモリログは打鍵開始から取得し、開始・ready・段1/2/3と各復帰・終端の順序、印以外の書込禁止、最後600フレーム安定、取りこぼし0を既存検証器で確認する。前半・後半のmain/sub入出力ログは両方取りこぼし0が必須。段別件数とポート種類だけを観測へ保存し、値/PCは保存しない。ログは既存伏字器を通してgzip、媒体とメモリ生ログは削除。

失敗時は stable/logical_marks/memory_no_loss/io_no_loss/prefix_no_loss/prefix_marks_absent/replay_equal/media_known を真偽または不明で観測へ残す。replay_equal は後半RUN前の印不在と前半媒体の初期状態一致を意味する。論理印が失敗した観測からERRを推定しない。例外時は失敗種別と不明条件を残す。

2走一致はvalues/writes/mediaの完全一致。conditionsは双方すべてtrueが必須、io_countsは件数として残すが時刻依存の件数差を論理不一致にはしない。較正cal-poke/cal-errorは合成期待と完全一致。disk-positiveは順次OPEN/PRINT/INPUTの往復印1、ERR0、種別00、ok-crlf-sub候補一致が必須。その他腕のfirst_errが一様なERR0/2/33等なら全体失敗。全採用腕の器具関門も必須。

expected/checkは全腕2走・署名・各関門・全体関門を再計算。--exclude ARM=理由は関門を通らない腕だけ、較正/陽性は除外不可。期待値に除外理由を記録しcheckで一致必須。既知差免除は空。未実装の誤りは予測差であり、それ自体を器具失敗としない。

## 自作候補と判定範囲

媒体はdrive2の自作ファイルf2ownのエントリを探し、そのエントリのFAT鎖だけを読む。案内としてD88ヘッダ・ディレクトリ・FATを使う。他ファイル本体、drive1本体は検査しない。種別00の真偽、割当セクタ長、SHA-256、完全一致候補IDだけ記録。ランダムは0x1Aで切らず鎖の使用セクタ全体を比べる。論理レコード長と割当量は区別する。候補不一致はunknownではなくmatches空、鎖破損など検査不能はmedia_known=falseで関門落ち。

候補はrecord_candidates: packed（連続LENバイト）またはsector（レコードごと256B切上げ）配置、未書込部分/最後のセクタを0・32・26で埋める直積。レコード内容は自作の文字列・LSET/RSETの空白規則から生成。disk-positiveだけはok+CRLF+SUBとゼロ余白の256B。空ファイル長0も鎖のC0から判定。候補が重なるときは一致した全IDを列挙。一致しなければ未確定、事後に候補を足して同じ事前登録と称さない。

数値候補: MKI$は16bit符号付き2の補数リトルエンディアン。MKS$/MKD$は4/8B MBF（隠れた先頭1・末尾指数+129・仮数最上位が符号）、0は全0。既存mem.mbf_integerを正整数に再利用し負数は符号bitを立てる。バイトを直接印に出さずFIELDへ書き媒体全体を候補比較。BASICではLENとCV*(MK*(x))=xを比較印にする。

LOC/LOFは開いている途中の値も16bitとして記録。LOC=最後のレコード番号とLOF=256Bセクタ数を仮説に置く。128B×2が1セクタかはrecord-size/put-next/roundtrip-twoの候補一致とLOFを合わせる。

## 腕一覧（全85腕、全腕に反証可能な事前予測）

印はBASIC比較式の真偽（1/0）。予測は仮説であり外れてよい。setup→target→cleanupを下表に固定する。

|腕|setup|target|cleanup|予測|候補ID|
|---|---|---|---|---|---|
|cal-poke|poke &hc310,213|rem calibration|rem calibration|cal213・ERR0|なし|
|cal-error|なし|error 13|rem calibration|ERR13@段2|なし|
|disk-positive|なし|open "2:f2own" for output as #1 ; print #1,"ok" ; close ; open "2:f2own" for input as #1 ; input #1,a$ ; poke 49985,abs(a$="ok") ; close|rem done|ERR0・印1・種別00・ok-crlf-sub|ok-crlf-sub|
|open-default|なし|open "2:f2own" as #1|close|ERR0・既定128|なし|
|open-len-128|なし|open "2:f2own" as #1 len=128|close|1..256受理、0/257はERR5を仮説|なし|
|open-len-256|なし|open "2:f2own" as #1 len=256|close|1..256受理、0/257はERR5を仮説|なし|
|open-len-1|なし|open "2:f2own" as #1 len=1|close|1..256受理、0/257はERR5を仮説|なし|
|open-len-0|なし|open "2:f2own" as #1 len=0|close|1..256受理、0/257はERR5を仮説|なし|
|open-len-257|なし|open "2:f2own" as #1 len=257|close|1..256受理、0/257はERR5を仮説|なし|
|open-short-128|なし|open "r",#1,"2:f2own",128|close|ERR2を仮説|なし|
|open-short-256|なし|open "r",#1,"2:f2own",256|close|ERR2を仮説|なし|
|open-short-1|なし|open "r",#1,"2:f2own",1|close|ERR2を仮説|なし|
|open-number-0|なし|open "2:f2own" as #0|close|1/2受理、0/3..255はERR52、256はERR5|なし|
|open-number-1|なし|open "2:f2own" as #1|close|1/2受理、0/3..255はERR52、256はERR5|なし|
|open-number-2|なし|open "2:f2own" as #2|close|1/2受理、0/3..255はERR52、256はERR5|なし|
|open-number-3|なし|open "2:f2own" as #3|close|1/2受理、0/3..255はERR52、256はERR5|なし|
|open-number-15|なし|open "2:f2own" as #15|close|1/2受理、0/3..255はERR52、256はERR5|なし|
|open-number-16|なし|open "2:f2own" as #16|close|1/2受理、0/3..255はERR52、256はERR5|なし|
|open-number-255|なし|open "2:f2own" as #255|close|1/2受理、0/3..255はERR52、256はERR5|なし|
|open-number-256|なし|open "2:f2own" as #256|close|1/2受理、0/3..255はERR52、256はERR5|なし|
|open-nohash|なし|open "2:f2own" as 1|close|ERR0|なし|
|open-double-number|open "2:f2own" as #1|open "2:f2own" as #1|close|ERR54|なし|
|open-double-name|open "2:f2own" as #1|open "2:f2own" as #2|close|ERR54|なし|
|field-width-127|open "2:f2own" as #1|field #1,127 as a$ ; poke 49985,abs(len(a$)=127)|close|128以下ERR0・長さ印1、129はERR50|なし|
|field-width-128|open "2:f2own" as #1|field #1,128 as a$ ; poke 49985,abs(len(a$)=128)|close|128以下ERR0・長さ印1、129はERR50|なし|
|field-width-129|open "2:f2own" as #1|field #1,129 as a$ ; poke 49985,abs(len(a$)=129)|close|128以下ERR0・長さ印1、129はERR50|なし|
|field-sum-exact|open "2:f2own" as #1|field #1,64 as a$,64 as b$ ; poke 49985,abs(len(a$)=64 and len(b$)=64)|close|ERR0・印1|なし|
|field-sum-over|open "2:f2own" as #1|field #1,64 as a$,65 as b$|close|ERR50|なし|
|field-multiple|open "2:f2own" as #1 ; field #1,128 as a$|field #1,4 as b$ ; lset b$="ab" ; poke 49985,abs(left$(a$,4)=b$)|close|ERR0・先頭を共有、印1|なし|
|field-let|open "2:f2own" as #1 ; field #1,4 as a$|a$="z" ; put #1,1 ; field #1,4 as b$ ; lset b$="xxxx" ; get #1,1 ; poke 49985,abs(a$="z") ; poke 49986,abs(b$="z   ")|close|LETで結合解除、a$保持印1・媒体z印0を仮説|なし|
|field-closed|なし|field #1,128 as a$|close|ERR60|なし|
|field-after-close|open "2:f2own" as #1 ; close|field #1,128 as a$|close|ERR60|なし|
|lset-short|open "2:f2own" as #1 ; field #1,4 as a$|lset a$="ab" ; poke 49985,abs(a$="ab  ") ; put #1,1|close|ERR0・長さ4、LSET右空白/RSET左空白、超過は先頭4・印1|short|
|lset-equal|open "2:f2own" as #1 ; field #1,4 as a$|lset a$="abcd" ; poke 49985,abs(a$="abcd") ; put #1,1|close|ERR0・長さ4、LSET右空白/RSET左空白、超過は先頭4・印1|equal|
|lset-long|open "2:f2own" as #1 ; field #1,4 as a$|lset a$="abcdef" ; poke 49985,abs(a$="abcd") ; put #1,1|close|ERR0・長さ4、LSET右空白/RSET左空白、超過は先頭4・印1|long|
|lset-empty|open "2:f2own" as #1 ; field #1,4 as a$|lset a$="" ; poke 49985,abs(a$="    ") ; put #1,1|close|ERR0・長さ4、LSET右空白/RSET左空白、超過は先頭4・印1|empty|
|lset-ordinary|a$="xxxx"|lset a$="ab" ; poke 49985,abs(len(a$)=4)|close|ERR0・元長保持・印1|なし|
|rset-short|open "2:f2own" as #1 ; field #1,4 as a$|rset a$="ab" ; poke 49985,abs(a$="  ab") ; put #1,1|close|ERR0・長さ4、LSET右空白/RSET左空白、超過は先頭4・印1|short|
|rset-equal|open "2:f2own" as #1 ; field #1,4 as a$|rset a$="abcd" ; poke 49985,abs(a$="abcd") ; put #1,1|close|ERR0・長さ4、LSET右空白/RSET左空白、超過は先頭4・印1|equal|
|rset-long|open "2:f2own" as #1 ; field #1,4 as a$|rset a$="abcdef" ; poke 49985,abs(a$="abcd") ; put #1,1|close|ERR0・長さ4、LSET右空白/RSET左空白、超過は先頭4・印1|long|
|rset-empty|open "2:f2own" as #1 ; field #1,4 as a$|rset a$="" ; poke 49985,abs(a$="    ") ; put #1,1|close|ERR0・長さ4、LSET右空白/RSET左空白、超過は先頭4・印1|empty|
|rset-ordinary|a$="xxxx"|rset a$="ab" ; poke 49985,abs(len(a$)=4)|close|ERR0・元長保持・印1|なし|
|put-omit|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|put #1 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|正番号/省略はERR0、LOC=対象番号・LOF=256Bセクタ数、0/負はERR63を仮説|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|put-one|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|put #1,1 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|正番号/省略はERR0、LOC=対象番号・LOF=256Bセクタ数、0/負はERR63を仮説|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|put-two|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|put #1,2 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|正番号/省略はERR0、LOC=対象番号・LOF=256Bセクタ数、0/負はERR63を仮説|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|put-large|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|put #1,33 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|正番号/省略はERR0、LOC=対象番号・LOF=256Bセクタ数、0/負はERR63を仮説|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|put-zero|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|put #1,0 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|正番号/省略はERR0、LOC=対象番号・LOF=256Bセクタ数、0/負はERR63を仮説|なし|
|put-negative|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|put #1,-1 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|正番号/省略はERR0、LOC=対象番号・LOF=256Bセクタ数、0/負はERR63を仮説|なし|
|get-omit|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|get #1 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|未書込GETはERR55、0/負はERR63を仮説|なし|
|get-one|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|get #1,1 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|未書込GETはERR55、0/負はERR63を仮説|なし|
|get-two|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|get #1,2 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|未書込GETはERR55、0/負はERR63を仮説|なし|
|get-large|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|get #1,33 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|未書込GETはERR55、0/負はERR63を仮説|なし|
|get-zero|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|get #1,0 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|未書込GETはERR55、0/負はERR63を仮説|なし|
|get-negative|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|get #1,-1 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|未書込GETはERR55、0/負はERR63を仮説|なし|
|put-next|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab"|put #1 ; put #1 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|ERR0・LOC2・LOF1・128Bを2個詰める|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|get-next|open "2:f2own" as #1 ; field #1,128 as a$ ; rset a$="ab" ; put #1,1 ; rset a$="cd" ; put #1,2 ; close ; open "2:f2own" as #1 ; field #1,128 as a$|lset a$="xx" ; get #1 ; poke 49985,abs(right$(a$,2)="ab") ; lset a$="yy" ; get #1 ; poke 49986,abs(right$(a$,2)="cd") ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256)|close|ERR0・2読戻印1・LOC2|なし|
|record-size-1|open "2:f2own" as #1 len=1 ; field #1,1 as a$ ; lset a$=string$(1,97)|put #1,1 ; put #1,2 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|ERR0・LOC2・LOF=ceil(2*LEN/256)、packed候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|record-size-128|open "2:f2own" as #1 len=128 ; field #1,128 as a$ ; lset a$=string$(128,97)|put #1,1 ; put #1,2 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|ERR0・LOC2・LOF=ceil(2*LEN/256)、packed候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|record-size-256|open "2:f2own" as #1 len=256 ; field #1,256 as a$ ; lset a$=string$(256,97)|put #1,1 ; put #1,2 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|ERR0・LOC2・LOF=ceil(2*LEN/256)、packed候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|roundtrip-two|open "2:f2own" as #1 ; field #1,128 as a$ ; rset a$="ab" ; put #1,1 ; rset a$="cd" ; put #1,2 ; close ; open "2:f2own" as #1 ; field #1,128 as a$|lset a$="xxxx" ; poke 49987,abs(right$(a$,2)<>"ab") ; get #1,1 ; poke 49985,abs(right$(a$,2)="ab") ; lset a$="yyyy" ; poke 49988,abs(right$(a$,2)<>"cd") ; get #1,2 ; poke 49986,abs(right$(a$,2)="cd")|close|ERR0・破壊2印と読戻2印がすべて1|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|overwrite|open "2:f2own" as #1 ; field #1,128 as a$ ; lset a$="ab" ; put #1,1|lset a$="cd" ; put #1,1 ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|ERR0・LOF1維持・cdに置換|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|loc-before|open "2:f2own" as #1|v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|ERR0・LOC0・LOF0|なし|
|loc-after-get|open "2:f2own" as #1 ; field #1,128 as a$ ; rset a$="ab" ; put #1,2|get #1,2 ; v=loc(1) ; if v<0 then v=v+65536 ; poke 49941,v-256*int(v/256) ; poke 49942,int(v/256) ; v=lof(1) ; if v<0 then v=v+65536 ; poke 49943,v-256*int(v/256) ; poke 49944,int(v/256)|close|ERR0・LOC2・LOF1|なし|
|mki-0|なし|b$=mki$(0) ; poke 49985,abs(len(b$)=2) ; poke 49986,abs(cvi(b$)=0) ; open "2:f2own" as #1 ; field #1,2 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ2印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|mki-1|なし|b$=mki$(1) ; poke 49985,abs(len(b$)=2) ; poke 49986,abs(cvi(b$)=1) ; open "2:f2own" as #1 ; field #1,2 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ2印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|mki-minus1|なし|b$=mki$(-1) ; poke 49985,abs(len(b$)=2) ; poke 49986,abs(cvi(b$)=-1) ; open "2:f2own" as #1 ; field #1,2 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ2印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|mki-12345|なし|b$=mki$(12345) ; poke 49985,abs(len(b$)=2) ; poke 49986,abs(cvi(b$)=12345) ; open "2:f2own" as #1 ; field #1,2 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ2印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|cvi-length-0|なし|x=cvi(string$(0,97))|close|短すぎる文字列ERR5、長い文字列は先頭の規定長を使用してERR0を仮説|なし|
|cvi-length-1|なし|x=cvi(string$(1,97))|close|短すぎる文字列ERR5、長い文字列は先頭の規定長を使用してERR0を仮説|なし|
|cvi-length-3|なし|x=cvi(string$(3,97))|close|短すぎる文字列ERR5、長い文字列は先頭の規定長を使用してERR0を仮説|なし|
|mks-0|なし|b$=mks$(0) ; poke 49985,abs(len(b$)=4) ; poke 49986,abs(cvs(b$)=0) ; open "2:f2own" as #1 ; field #1,4 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ4印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|mks-1|なし|b$=mks$(1) ; poke 49985,abs(len(b$)=4) ; poke 49986,abs(cvs(b$)=1) ; open "2:f2own" as #1 ; field #1,4 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ4印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|mks-minus1|なし|b$=mks$(-1) ; poke 49985,abs(len(b$)=4) ; poke 49986,abs(cvs(b$)=-1) ; open "2:f2own" as #1 ; field #1,4 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ4印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|mks-12345|なし|b$=mks$(12345) ; poke 49985,abs(len(b$)=4) ; poke 49986,abs(cvs(b$)=12345) ; open "2:f2own" as #1 ; field #1,4 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ4印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|cvs-length-0|なし|x=cvs(string$(0,97))|close|短すぎる文字列ERR5、長い文字列は先頭の規定長を使用してERR0を仮説|なし|
|cvs-length-3|なし|x=cvs(string$(3,97))|close|短すぎる文字列ERR5、長い文字列は先頭の規定長を使用してERR0を仮説|なし|
|cvs-length-5|なし|x=cvs(string$(5,97))|close|短すぎる文字列ERR5、長い文字列は先頭の規定長を使用してERR0を仮説|なし|
|mkd-0|なし|b$=mkd$(0) ; poke 49985,abs(len(b$)=8) ; poke 49986,abs(cvd(b$)=0) ; open "2:f2own" as #1 ; field #1,8 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ8印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|mkd-1|なし|b$=mkd$(1) ; poke 49985,abs(len(b$)=8) ; poke 49986,abs(cvd(b$)=1) ; open "2:f2own" as #1 ; field #1,8 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ8印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|mkd-minus1|なし|b$=mkd$(-1) ; poke 49985,abs(len(b$)=8) ; poke 49986,abs(cvd(b$)=-1) ; open "2:f2own" as #1 ; field #1,8 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ8印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|mkd-12345|なし|b$=mkd$(12345) ; poke 49985,abs(len(b$)=8) ; poke 49986,abs(cvd(b$)=12345) ; open "2:f2own" as #1 ; field #1,8 as a$ ; lset a$=b$ ; put #1,1|close|ERR0・長さ8印1・往復印1・整数LE/MBF候補|packed-pad0, packed-pad32, packed-pad26, sector-pad0, sector-pad32, sector-pad26|
|cvd-length-0|なし|x=cvd(string$(0,97))|close|短すぎる文字列ERR5、長い文字列は先頭の規定長を使用してERR0を仮説|なし|
|cvd-length-7|なし|x=cvd(string$(7,97))|close|短すぎる文字列ERR5、長い文字列は先頭の規定長を使用してERR0を仮説|なし|
|cvd-length-9|なし|x=cvd(string$(9,97))|close|短すぎる文字列ERR5、長い文字列は先頭の規定長を使用してERR0を仮説|なし|
|mixed-seq-random|なし|open "2:f2own" for output as #1 ; print #1,"ab"; ; close ; open "2:f2own" as #1 ; field #1,2 as a$ ; lset a$="xx" ; get #1,1 ; poke 49985,abs(a$="ab")|close|ERR0・印1|なし|
## 実行手順
`tools/l4_randfile_selftest.sh` で合成自己検査と自作ビルド・85腕各2走の試走一式を実施。自作ROMの未実装による結果と全体関門の成否はtmp/f2-work/p1-report.mdへ記録。
第2回: `python3 tools/l4_randfile_measure.py measure --official --work-dir "$PWD/tmp/f2-work/official" --out "$PWD/tmp/f2-work/official.tsv"`。公式測定の実行禁止を器具に追加しない。必要なPC88_REF_*は親が環境から渡す。
公式予定は85腕×2走×2区間=340起動。全フレーム数と自作試走壁時計に基づく逐次見積を第1回報告へ記載する。
