# l4-f1 順次ファイル 第1回事前登録

2026-10-20。公式測定前に固定。CLAUDE.mdを先に読み、クリーンルーム規律を適用した。今回は事前登録・器具・自己検査・自作ROM試走まで。公式ROMを実行しない。器具には時限禁止を入れない。

## 資料の範囲

マニュアルは読んでいない（ページ番号: 該当なし）。仕様は docs/spec/l3-disk-format.md のエントリ欄・種別、名前の大小文字、割当単位・鎖・終端、ASCII本体の節と、docs/spec/l4-basic.md の誤り番号表（895〜915行付近）・未実装語の表（1385〜1400行付近）だけを参照した。型として tools/l4_bsave_measure.py、tools/build_blank_data_disk.py、tools/l4_portio_measure.py、tools/l4_mlcall_measure.py の印・ログ関門、および docs/notes/l4-t4-addendum1-preregistration.md を参照した。

## 凍結署名

PLAN_SHA: `e9531797224d19bdae81978a4cc4091c92036014c8ea1fdccd69d9655a048816`
PROGRAM_SHA: `8ee7416ce43f7e7fe4a2ff8aa0d1250f6a446217877168e822759a86bd5c9d0a`
PLANは全腕定義（候補本体はSHA-256へ置換）の正規JSON（キー順、空白なし）。PROGRAMは全打鍵列のJSON（空白なし）。候補生成規則の識別子・長さ・SHA-256も下表で固定する。器具の全コマンド冒頭で署名を照合し、selftest/measureでは合成検査でも照合する。

## 媒体構成と情報経路

公式測定のドライブ1は追補1と同じ: PC88_REF_DISK_DIR と M6FF_FROZEN_CONFIG（既定tools/m6ff_frozen.tsv）のreference_disk欄から作業コピーを作り、ドライブ2へbuild_blank_data_disk.build()で生成した自作空データ媒体を置く。ドライブ1はコピー操作にのみ使い、内容の解析・照合・ハッシュ・出力はしない。各走のfinallyで両コピーを削除する。公式は参照媒体不足なら起動前に拒否。公式ROMパスはPC88_REF_ROM_DIR経由のみ。
自作も参照媒体があれば同構成。今回PC88_REF_*未指定なので自作試走だけdrive1に同じ自作空媒体を代用する。この代用では公式のディスクBASIC成立を主張しない。全体関門の免除は設けない。自作試走の自己検査成否は器具関門と全体測定有効性を分けて報告する。
読込腕は生成した空データ媒体へ公開ディスク形式で既知fixtureを一件だけ置く。通常は種別00、wrong-type腕だけ01。FAT3面を同じにし、単位72から必要セクタ数だけ割り当てる。書込先・読込先は小文字2:f1own（打鍵は小文字）。2:f1twoはCLOSE複数番号用、2:f1progはLOAD用自作プログラム。ドライブ省略腕だけ既定ドライブへの書込を測るためdrive2非生成を予測する。
媒体観測はdrive2のディレクトリの名前一致→当該エントリ→FATの0..159中の当該鎖→そのセクタだけ。単位74/75・循環・不正終端は拒否する。ASCIIのSUB以後は候補照合・ハッシュから除外する。SUBが無い場合のlengthは鎖で割り当てられたセクタ長であり、terminated=falseを併記して論理文字数を確定扱いしない。出力はfound/type00/長さ/SHA-256/候補識別子/終端有無のみ。未知本文・他ファイル本文・媒体全体のハッシュを採らない。
画面は取得せず、読戻しはBASICの等値比較を診断域C300〜C35FへPOKEする。値比較印はp65。EOF/LOC/LOFはBASICが返す数値をp21（下位）/p22（上位）へ16bitで記録する。負数は65536を足す。最大番号走査はp21=最後に受理された番号、p22=最初に拒否された番号（1..255、0は該当なし）。その領域以外のメモリ読出しはしない。
入出力ログと印ログは打鍵開始から取り、取りこぼし0を要求する。終了印後600フレーム安定。入出力ログのデータポートFB/FC/FDは既存redact_iolog.pyを通し、伏字後gzipで保存し、生ログをfinallyで削除する。フロントエンド標準出力・標準エラーは捕捉し、画面本文を出さない。公式ROMはバイト列を読まない。

## 段・関門・既知の差

各腕は独立起動2走。段1=準備、段2=主刺激、段3=後処理/比較。各段の最初・最後のERR、全体の最初/最後ERRと段、誤り件数、ERROR_FLAG、段復帰印を残す。RESUME NEXTにより段内の後続命令へ進むので、準備で誤った腕の読戻し印を正常仕様と解釈しない。開始197・初期化95欄・準備151・終了163・全段復帰77の順と件数を検証する。
cal-pokeは段1の較正213とERR0、cal-errorはERR13@段2が必須。陽性対照disk-positiveはOPEN OUTPUT→PRINT→CLOSE→OPEN INPUT→INPUTの誤りなし、BASIC読戻印1、drive2の種別00とok-crlf-sub候補の完全一致が全て必須。両ドライブ空媒体等でERR33となる起動を有効にしない。
cal-poke/cal-error/disk-positive以外の全腕・全走の最初ERRが一種類なら全体無効（ERR0一様も含む）。較正・陽性・非一様・全腕2走一致・取りこぼし0の全てを通って初めてexpectedへ昇格できる。関門落ちでも採れたERRを保存する。不明や未完了は正常受理に読み替えない。
既知差辞書は空。将来差を認める場合も腕IDだけで除外せず、理由・期待値全体・観測全体の三条件一致が必要。公式観測に合わせて今回の予測・署名・候補を変更しない。
END/RUN/NEW/LOAD腕は段2で制御を渡した後、別打鍵で7000番以降の継続プログラムと同じ誤りハンドラを登録してGOTO 7000する。CLEAR/NEW/RUNを継続時に追加しない。RUNは入口で診断域の段2を検知して7000番の観測部へ分岐し、追加のENDや初期化を実行しない。RUN腕の観測部は初回RUN前からプログラム内に置き、再RUN後の直打ち入力を必要としない。LOAD用プログラムは段1前に自己SAVE,Aで作る。転送後は段2復帰印→段3→再読比較→終了印を必須にする。

## 候補規則

出力の論理本体を丸ごと候補と比較する。部分一致は受理しない。各自作内容候補につき行末CRLF/CR/LF/なしと終端SUB/なしの直積を生成する。PRINTの数値前後空白・カンマのゾーン幅、WRITEの引用符・カンマは別候補。セミコロンによる連結に加え、最後のPRINTが末尾セミコロンのままCLOSEされる腕で改行の有無を比較する。候補外は不一致として長さ・ハッシュだけを残す。生バイト列はノート・ログに載せない。

## 腕一覧と予測

全90腕、各2走。予測は仮説であり、外れたときも番号・段をそのまま記録する。

|腕|段1 / 段2 / 段3|予測|入力SHA-256|
|---|---|---|---|
|cal-poke|`poke &hc310,213 / rem calibration / rem calibration`|cal213・ERR0|6ab09edb8fff53ecff7146e9f0ba8b8c90dfa0d771076d6fde8d64dffae9c02e|
|cal-error|` / error 13 / rem calibration`|ERR13@段2|d27287c900817b0319d123bc08d22c4373e293e7ce4bbfb5900ac20bb6a74e43|
|disk-positive|` / open "2:f1own" for output as #1; print #1,"ok"; close #1; open "2:f1own" for input as #1; input #1,a$; poke 49985,abs(a$="ok"); close #1 / rem done`|ERR0・比較印1・種別00・ok-crlf-sub|45ea3e75736d3702a81ce4059d124f2c965c421006edd72a30fddd521e639acb|
|open-number-0|` / open "2:f1own" for output as #0 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|f8581f4f868723357672cf446ab2fd57bc512da53ef1021ed2b697061e1017ee|
|open-number-1|` / open "2:f1own" for output as #1 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|3e5063e3aee2de69ab33c2284b4d1203d2f25b61181304f8f45d0061d96b3976|
|open-number-2|` / open "2:f1own" for output as #2 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|904c31c6a5c4bfc9f0651a69944055e43b91e11d8d4896dd4e65147e9ae9e245|
|open-number-3|` / open "2:f1own" for output as #3 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|1f05cb0e3ef81ff80bad1f388397a5d2a3a88c808a7e9a9dcc31f7b1fe6cabe3|
|open-number-4|` / open "2:f1own" for output as #4 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|8090030094b5313e87470f450b58de4c28e14264f4968bdbc1837793a87da579|
|open-number-5|` / open "2:f1own" for output as #5 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|7d94fc0f1eb61027c920b8b8c325b429d88fb71fdcf6aa9e3296e0aa329b5bb5|
|open-number-6|` / open "2:f1own" for output as #6 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|159c3d6267b727f824d47665b80c08140655ead7aeb61d5cc75d064885c8c6a5|
|open-number-7|` / open "2:f1own" for output as #7 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|d8af8cc12bb5a0658aed67a2ebf57d000920382d9acb37b9080bca78769329f9|
|open-number-8|` / open "2:f1own" for output as #8 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|df6e0c0506214218fcd6405e39cf6ca74e826f22e03a5f35c7424dc9c0c75234|
|open-number-9|` / open "2:f1own" for output as #9 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|b6321d6970a219b128cd29218d5eb1c7363817c1f071118c2dea13fb84ba0eb4|
|open-number-10|` / open "2:f1own" for output as #10 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|d84d301facbe9d05a8c741d24b5d5327ee61086b0626f9e9ca24f81038422bc1|
|open-number-11|` / open "2:f1own" for output as #11 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|db3c9d5359167ab9423b3d887f3281c80b9995b6cf447d9b2c331d2600fe95da|
|open-number-12|` / open "2:f1own" for output as #12 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|52cd8a66110f11317cac3d4898cc9297e17d7bc5a77b67b280d91c60315f470f|
|open-number-13|` / open "2:f1own" for output as #13 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|14d8dc8c7aa5b3b0def09c85f5c73d3cae6b93f94cb43fe92443d8cd1eeba56c|
|open-number-14|` / open "2:f1own" for output as #14 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|b90fb33027a0189e1d58d6b6fc749a809de6a052dc8437d32af24ad7a591f52b|
|open-number-15|` / open "2:f1own" for output as #15 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|200e05fe68b970c027c4ee75cbaf5e9e7cb153995045f1ffc01d5ae8f77790b9|
|open-number-16|` / open "2:f1own" for output as #16 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|3aa361be3248afdeadca048611a9c76616d81dd5d4db6045f73bf1b86d972e6c|
|open-number-256|` / open "2:f1own" for output as #256 / close`|1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定|9c7b62ab00911bde5f764b9fe0a2ac913afb88811dc0bddc1b6d1ae1c963000a|
|open-range-sweep|` / for n=1 to 255; q=0; open "2:f1own" for output as #n; if q=0 then poke 49941,n:close #n; if q<>0 and peek(49942)=0 then poke 49942,n; next n / rem sweep closed individually`|最大15・最初拒否16を予測。1..255全走査、256腕と合わせ最大を測る|466c7748f3488601a18a47b7b4d098c790a8feda5233c4b5e2360ee837c01e74|
|open-output|` / open "2:f1own" for output as #1 / close`|ERR0|3e5063e3aee2de69ab33c2284b4d1203d2f25b61181304f8f45d0061d96b3976|
|open-input|` / open "2:f1own" for input as #1 / close`|ERR0|47c8a9b1a4f9cc59ba6f5e13866e9868ef5199cac549242f3534d617019a2f1a|
|open-append|` / open "2:f1own" for append as #1 / close`|ERR0|c9349817b7aaadc1b39e20c12e2698b7f9f3881d3aa5599e2d7390f4dc4ce594|
|open-nohash|` / open "2:f1own" for output as 1 / close`|ERR0|5ab3499910a09a07d7b01087b49caa459bc3ac61fa991e4370d3e30e491a5e13|
|open-short-o|` / open "o",#1,"2:f1own" / close`|ERR0またはERR2|d9ebfae761f541752a5a10e8246da2895ffc9efc8336a85539b8d92ba2d295b9|
|open-short-i|` / open "i",#1,"2:f1own" / close`|ERR0またはERR2|501708367274954496569dbafac9696e2e84509aff572867a8d2154feb501445|
|open-short-a|` / open "a",#1,"2:f1own" / close`|ERR0またはERR2|4b7d838558b7502e0c6d3578ee569c5bdaf8d3cd52b5dff625d8b5ba7d2e2812|
|open-bad-mode|` / open "2:f1own" for banana as #1 / close`|ERR2|ff3d4c27132ce9fcbbc834765465227e33ed64b4ac7e44550b76cc02c3d9c1ac|
|open-short-bad|` / open "x",#1,"2:f1own" / close`|ERR5またはERR2|29d585f6c8aa64d0ca256628f2371b88e7e306641e28c14245a6adaf6e0c5567|
|open-omit-drive|` / open "f1own" for output as #1 / close`|既定drive1、ERR0。drive2非生成を予測|f9656c42c45fd1f8890e0aa116a2c55203630d349805d4340d102c12d0fa818b|
|open-double-number|`open "2:f1own" for output as #1 / open "2:f1own" for output as #1 / close`|ERR54|cf1d2f7cf4b6c9e47669567b3824b1b5744efb0c5d3991ae70720773f3c36de1|
|open-double-name|`open "2:f1own" for output as #1 / open "2:f1own" for output as #2 / close`|ERR54|c0c0daf5ee5afd6def4b1d64b7f73d15f70fdfcfe614d86b7284341abdcbf253|
|open-wrong-type|` / open "2:f1own" for input as #1 / close`|ERR59またはERR64|47c8a9b1a4f9cc59ba6f5e13866e9868ef5199cac549242f3534d617019a2f1a|
|open-missing|` / open "2:f1own" for input as #1 / close`|ERR53|47c8a9b1a4f9cc59ba6f5e13866e9868ef5199cac549242f3534d617019a2f1a|
|write-string|`open "2:f1own" for output as #1 / print #1,"alpha" / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|7c149f593f0475309d6e1232fb4b6cabd9050a071f1ad5b2ceda13d567b4c100|
|write-empty|`open "2:f1own" for output as #1 / print #1,"" / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|ac102ac64a26994b0bdf181ef77991f438cbc0dc02e5e46552daa38359d6d286|
|write-positive|`open "2:f1own" for output as #1 / print #1,12 / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|a170cd734d408e689fc3797700910476d5f6665dff2f1766ad0007d2088c1e45|
|write-negative|`open "2:f1own" for output as #1 / print #1,-12 / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|1812987077dced37750d80cd8af5ba4d4a35c1ed0eab39eb7ddcb2a6d6760354|
|write-semi|`open "2:f1own" for output as #1 / print #1,"a";"b" / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|cc5dbc7501b949f9244c217353ef0e1e44a3688391075bc16cbb8654346f71cf|
|write-comma|`open "2:f1own" for output as #1 / print #1,"a","b" / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|edf9da213a5f91ef0495d2c29e39b3cab720f641c5206d70b049ddb6c4565c53|
|write-trailing-semi|`open "2:f1own" for output as #1 / print #1,"a"; / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|138a60ba03f093fdd4b6552a85b8261b56d81917b2f80ae6edb4ff03abce36fa|
|write-trailing-comma|`open "2:f1own" for output as #1 / print #1,"a",:print #1,"b" / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|43f578508572cb6f206686fc16bd61b6d9ac04ac071bcef43aeaf82c680e149d|
|write-blank|`open "2:f1own" for output as #1 / print #1, / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|3ce8a086a6422f61b9829042b47b722ecf730c6d5f3010d7ab732a4ac30413a2|
|write-mixed|`open "2:f1own" for output as #1 / print #1,12;"a";-3 / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|d93e9d44df4e8b0dc12ab498c41a96fb34a3c65cce96bc3df24e1c09bb95dd96|
|write-write-string|`open "2:f1own" for output as #1 / write #1,"alpha" / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|f4f8a1393c9da082515c5b1ede88013700ce5e7be650dee963e9ec28222ca646|
|write-write-mixed|`open "2:f1own" for output as #1 / write #1,"a",12,-3,"" / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|035ff58185c84501c57316f7513af7e5d2440b102d493eaf39268b84778eaf86|
|write-write-quote|`open "2:f1own" for output as #1 / write #1,chr$(34)+"a" / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|b16027dac3654e4644d08874682c7a7a08b6d533425621e504ab2bb1e299eac5|
|write-using|`open "2:f1own" for output as #1 / print #1,using "###";12 / close #1`|ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補|c19669351ba6ca2e26da9c29483851a7c7fae50a8dd0a5969da3ef2e7eee57ba|
|read-string|`open "2:f1own" for input as #1 / input #1,a$; poke 49985,abs(a$="alpha") / close`|ERR0・印1|12fcfe526ac382e50bb653392512672df368afe0c25a79eae2f649db7b246dec|
|read-number|`open "2:f1own" for input as #1 / input #1,a; poke 49985,abs(a=12) / close`|ERR0・印1|58f366978f173af8af510bccbc7004395ebd0cc9027b97c98a6f6aeb0528c38d|
|read-negative|`open "2:f1own" for input as #1 / input #1,a; poke 49985,abs(a=-12) / close`|ERR0・印1|282d4bf0583af65996ae38af961930e76224fd84fe52f3716208539cec0f2438|
|read-comma|`open "2:f1own" for input as #1 / input #1,a$,b$; poke 49985,abs(a$="a" and b$="b") / close`|ERR0・カンマで2値|9204d4950cd888c30647d30920bd20c78993edd6153701924a840d9975f608a3|
|read-quote|`open "2:f1own" for input as #1 / input #1,a$; poke 49985,abs(a$="a,b") / close`|ERR0・引用符内カンマ保持|127980b8bb2ca7ed95ba6f51b94f04189600262721f1e1dc07a2de7ebd399be4|
|read-line-comma|`open "2:f1own" for input as #1 / line input #1,a$; poke 49985,abs(a$="a,b") / close`|ERR0・カンマ保持|fda3df91dd8fc3de1b99cda6c447a5903dc73630a9956cc249c66b940e242135|
|read-line-quote|`open "2:f1own" for input as #1 / line input #1,a$; poke 49985,abs(a$=chr$(34)+"a,b"+chr$(34)) / close`|ERR0・引用符保持|8810dcde8a7a7eab1c825b35fb53ab7e43aa8549de516c7ec1eb0c7c9f16887d|
|read-empty-line|`open "2:f1own" for input as #1 / line input #1,a$; poke 49985,abs(a$="") / close`|ERR0・空文字|797d58a1cb19fef0d8c773baff3164ed24c35e368bf84c8d530163eb4ae17cf2|
|read-two-lines|`open "2:f1own" for input as #1 / line input #1,a$; line input #1,b$; poke 49985,abs(a$="a" and b$="b") / close`|ERR0・CRLF除去|a85391b501d1760bb3f710b595bf07e099b5e6956ea7f929b8458730bd7cd396|
|read-bad-number|`open "2:f1own" for input as #1 / input #1,a / close`|ERR13を予測|8a7e206f796999a265ed2e6809fbbb7fdc13f0e6fd1741e752ea015768b77632|
|read-number-string|`open "2:f1own" for input as #1 / input #1,a$; poke 49985,abs(a$="12") / close`|ERR0・文字列12|5e5e05ede2d1bfb55472ac03fe2a3e486985101653aa21d398c37fe7f110ee76|
|read-past-end|`open "2:f1own" for input as #1 / input #1,a$; input #1,b$ / close`|ERR55|3177c1a827de75b5b6774713b2daa1035d21c9b7c78c97dc67c8ff90142a6476|
|read-line-past-end|`open "2:f1own" for input as #1 / line input #1,a$; line input #1,b$ / close`|ERR55|9fbcfb6337314776121f9cf72e9d8a448e09f79b72539882ce508e0371a55c29|
|read-input-output|`open "2:f1own" for output as #1 / input #1,a$ / close`|ERR54またはERR60|2a24957576e3bd5107c79989bc340eaac0a1aa96aea6d6664bf77302eea9d480|
|read-print-input|`open "2:f1own" for input as #1 / print #1,"x" / close`|ERR54またはERR60|2283f05b7dd2e5c60fd1c217d05d02449a00f60361faf877a16a53e4b6284208|
|eof-before|`open "2:f1own" for input as #1 / v=eof(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|EOF before/middle=0、last/long=-1|c4fc9611a5f911c79c6b2d3d5b78b7b87ac7f4ce063ba898562dc845565d741b|
|eof-middle|`open "2:f1own" for input as #1 / line input #1,a$; v=eof(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|EOF before/middle=0、last/long=-1|529efc24a1862d81613b9c57f66e970f154b399ae6e764720e3c6922438365f7|
|eof-last|`open "2:f1own" for input as #1 / line input #1,a$; line input #1,b$; v=eof(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|EOF before/middle=0、last/long=-1|98300e429e99e838e31dc76c78dfb99b75518f21bb5da3d5a1d53b2c7eeb0601|
|eof-long|`open "2:f1own" for input as #1 / line input #1,a$; line input #1,b$; v=eof(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|EOF before/middle=0、last/long=-1|98300e429e99e838e31dc76c78dfb99b75518f21bb5da3d5a1d53b2c7eeb0601|
|loc-before|`open "2:f1own" for input as #1 / v=loc(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|LOCは128B単位、LOFはセクタ割当量を仮説。実値16bitと候補比較で単位判定|1eea061e042cc517a013cd771585f388051ee454f91591c333535b95c4608fbe|
|loc-middle|`open "2:f1own" for input as #1 / line input #1,a$; v=loc(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|LOCは128B単位、LOFはセクタ割当量を仮説。実値16bitと候補比較で単位判定|14491c9ea4798d6170f50cf86bf949c8d5ccf38cdd3d2807c98f0a0a08d8f276|
|loc-last|`open "2:f1own" for input as #1 / line input #1,a$; line input #1,b$; v=loc(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|LOCは128B単位、LOFはセクタ割当量を仮説。実値16bitと候補比較で単位判定|186181f4459a2b1011977a62c04da950939d0ceae7275b62a42e0275ca0370a4|
|loc-long|`open "2:f1own" for input as #1 / line input #1,a$; line input #1,b$; v=loc(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|LOCは128B単位、LOFはセクタ割当量を仮説。実値16bitと候補比較で単位判定|186181f4459a2b1011977a62c04da950939d0ceae7275b62a42e0275ca0370a4|
|lof-before|`open "2:f1own" for input as #1 / v=lof(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|LOCは128B単位、LOFはセクタ割当量を仮説。実値16bitと候補比較で単位判定|491e088e8ea50573f6500a3bea01ac0875f601fc98cadafff6d05435e678e599|
|lof-middle|`open "2:f1own" for input as #1 / line input #1,a$; v=lof(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|LOCは128B単位、LOFはセクタ割当量を仮説。実値16bitと候補比較で単位判定|1c3a13bf3fcf8db3228665ef7eda8be52e63adb7b11392b9bd78349cb9425a30|
|lof-last|`open "2:f1own" for input as #1 / line input #1,a$; line input #1,b$; v=lof(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|LOCは128B単位、LOFはセクタ割当量を仮説。実値16bitと候補比較で単位判定|47f89cf8cbe99d0ba6a9f4f499c21a6288fc080fa34421e267567b65e8040ff3|
|lof-long|`open "2:f1own" for input as #1 / line input #1,a$; line input #1,b$; v=lof(1); if v<0 then v=v+65536; poke 49941,v-256*int(v/256); poke 49942,int(v/256) / close`|LOCは128B単位、LOFはセクタ割当量を仮説。実値16bitと候補比較で単位判定|47f89cf8cbe99d0ba6a9f4f499c21a6288fc080fa34421e267567b65e8040ff3|
|close-hash|`open "2:f1own" for output as #1; print #1,"alpha" / close #1 / open "2:f1own" for input as #1; input #1,a$; poke 49985,abs(a$="alpha"); close`|ERR0、比較印1を予測（仮説）|af60f91034222de4f6619cd0a735b121fb77698ceee9111c249f5d9270163f6a|
|close-all|`open "2:f1own" for output as #1; print #1,"alpha" / close / open "2:f1own" for input as #1; input #1,a$; poke 49985,abs(a$="alpha"); close`|ERR0、比較印1を予測（仮説）|aadbe33fceeca91db520bd5fa70be96c9b673949fef6dd3ab5d76150c10d3587|
|close-list|`open "2:f1own" for output as #1; print #1,"alpha"; open "2:f1two" for output as #2; print #2,"b" / close 1,2 / open "2:f1own" for input as #1; input #1,a$; poke 49985,abs(a$="alpha"); close`|ERR0、比較印1を予測（仮説）|ec7d848b3fe2119426f39f0dc65874a0d8915c8e72ab89d8cd9a55c08ef1f790|
|finish-end|`open "2:f1own" for output as #1; print #1,"alpha" / end / open "2:f1own" for input as #1; input #1,a$; poke 49985,abs(a$="alpha"); close`|転送成立・再読印1・alpha-crlf-subを仮説|a5fb6fb6eb04f78fac7904f689f38c72f5336290f27fde4113a6a18b5531f883|
|finish-run|`open "2:f1own" for output as #1; print #1,"alpha" / run / open "2:f1own" for input as #1; input #1,a$; poke 49985,abs(a$="alpha"); close`|転送成立・再読印1・alpha-crlf-subを仮説|0ced83519a03e9aef78de58902feb64d4391794bc868abf5e6f4f8e35ae86d18|
|finish-new|`open "2:f1own" for output as #1; print #1,"alpha" / new / open "2:f1own" for input as #1; input #1,a$; poke 49985,abs(a$="alpha"); close`|転送成立・再読印1・alpha-crlf-subを仮説|75ade77ab9891724a3ab63a544fef63a374dd37066ed1c5e1a359a897670f22b|
|finish-load|`open "2:f1own" for output as #1; print #1,"alpha" / load "2:f1prog" / open "2:f1own" for input as #1; input #1,a$; poke 49985,abs(a$="alpha"); close`|転送成立・再読印1・alpha-crlf-subを仮説|fdbd81cf79244640bd30ccb4e358e5312f8602a6420911a322d81ad2c00f2ef8|
|flush-end|`open "2:f1own" for output as #1; print #1,"alpha" / end / rem no close before media observation`|イベント直後の媒体がalpha-crlf-subに一致を予測。再読はfinish系列で独立観測|bffd73c7d8d82d9f36084ea144c13d0defec5959f787417c0ff7cc8f1c9b52e9|
|flush-run|`open "2:f1own" for output as #1; print #1,"alpha" / run / rem no close before media observation`|イベント直後の媒体がalpha-crlf-subに一致を予測。再読はfinish系列で独立観測|78e53f5dbcd2f5f0bcefae9103766428cd0aaf920e234618929cbfebdfe0db71|
|flush-new|`open "2:f1own" for output as #1; print #1,"alpha" / new / rem no close before media observation`|イベント直後の媒体がalpha-crlf-subに一致を予測。再読はfinish系列で独立観測|96b30595729c1ae70a3cd7b34d39b5e75ca3d99591de88380fd095286a20d0d6|
|flush-load|`open "2:f1own" for output as #1; print #1,"alpha" / load "2:f1prog" / rem no close before media observation`|イベント直後の媒体がalpha-crlf-subに一致を予測。再読はfinish系列で独立観測|0874096432e7c97ff92727374b5c84e70298086960ba0ad5d0c70fc44c636def|
|kill-open|`open "2:f1own" for output as #1; print #1,"alpha" / kill "2:f1own" / close`|ERR54を仮説|94d23902e52063c4540b2cd33c88e6337496ef7bc0d1c9b301f622cccb6a4127|
|append-existing|`open "2:f1own" for append as #1 / print #1,"beta" / close #1; open "2:f1own" for input as #1; line input #1,a$; line input #1,b$; poke 49985,abs(a$="alpha" and b$="beta"); close`|ERR0・既存SUBを置換して末尾追加・読戻印1|7a9518d1bbb1e1cfdcd65c0a7fd41ab1fcee4dc32b721c69194191e6e54efd11|

## 既知fixture署名

|fixture|長さ|SHA-256|
|---|---:|---|
|alpha|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|number|5|2551184c1d6802840aa7cf43d32d1f0293b98216196ecda07bcc8b8b8865ac2a|
|negative|6|c02324b52234fb9f24e80b89d0162f384c911ced13cefab537869657ad6a1b22|
|comma|6|29c2bd5ee0478a4a2a09e010b9549b79b7d92b4cbe1fb180a7272c2df94abaca|
|quote|8|aa7d6b0f699f9adf1c69a7d88f881bd02d05d31cd7c18dd5fc5f7ae1c7a97c1f|
|empty|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|two|7|0cbe5f7fe544d69c439e35cae65ab3375b283a713e59fdea8b5e528c9096b2dc|
|long|307|ced65d29c61974351d29aed88ece2880d3cd6e150272fbfa4b65f938fceeb1cd|
|binary|4|b763fdb6ef0edd02bceec6308858dff1f2f66fa1e67116ee912f510431394429|

## 各腕の完全一致候補署名

|腕|候補|長さ|SHA-256|
|---|---|---:|---|
|disk-positive|ok-crlf-sub|5|874a2fb236324a6bfc86c949737c14cafdaa68a53244591c359ce0b92021d837|
|disk-positive|ok-crlf-none|4|9f2a59a60e65fbcd5a3e1b7248adf92890ce3a32b19e43fb4751c2657196de13|
|disk-positive|ok-cr-sub|4|a77634ca6ec857258adc41c6ace08753f443e52ad7ed6054eca30a289520d45d|
|disk-positive|ok-cr-none|3|7d1a6f2d6c0b82620cb7d807b0b682d9c6ab88aff383d3e46cc98cffa7a1181b|
|disk-positive|ok-lf-sub|4|9500ff185f4366e3152c13363f449ebb35d22fe096a8c177dff5492fb0c54155|
|disk-positive|ok-lf-none|3|dc51b8c96c2d745df3bd5590d990230a482fd247123599548e0632fdbf97fc22|
|disk-positive|ok-none-sub|3|61236bb7fb0dd4d9fde5547e23943683f76b48005220674147141e52c4891640|
|disk-positive|ok-none-none|2|2689367b205c16ce32ed4200942b8b8b1e262dfc70d9bc9fbc77c49699a4f1df|
|open-number-0|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-0|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-0|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-0|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-0|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-0|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-0|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-0|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-1|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-1|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-1|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-1|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-1|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-1|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-1|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-1|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-2|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-2|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-2|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-2|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-2|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-2|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-2|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-2|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-3|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-3|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-3|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-3|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-3|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-3|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-3|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-3|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-4|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-4|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-4|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-4|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-4|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-4|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-4|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-4|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-5|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-5|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-5|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-5|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-5|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-5|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-5|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-5|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-6|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-6|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-6|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-6|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-6|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-6|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-6|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-6|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-7|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-7|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-7|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-7|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-7|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-7|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-7|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-7|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-8|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-8|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-8|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-8|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-8|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-8|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-8|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-8|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-9|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-9|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-9|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-9|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-9|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-9|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-9|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-9|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-10|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-10|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-10|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-10|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-10|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-10|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-10|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-10|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-11|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-11|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-11|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-11|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-11|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-11|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-11|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-11|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-12|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-12|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-12|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-12|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-12|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-12|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-12|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-12|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-13|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-13|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-13|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-13|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-13|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-13|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-13|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-13|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-14|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-14|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-14|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-14|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-14|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-14|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-14|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-14|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-15|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-15|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-15|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-15|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-15|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-15|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-15|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-15|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-16|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-16|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-16|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-16|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-16|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-16|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-16|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-16|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-number-256|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-number-256|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-number-256|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-number-256|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-number-256|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-number-256|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-number-256|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-number-256|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-range-sweep|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-range-sweep|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-range-sweep|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-range-sweep|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-range-sweep|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-range-sweep|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-range-sweep|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-range-sweep|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-output|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-output|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-output|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-output|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-output|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-output|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-output|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-output|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-output|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-output|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-output|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-output|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-output|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-output|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-output|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-output|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-input|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-input|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-input|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-input|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-input|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-input|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-input|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-input|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-input|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-input|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-input|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-input|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-input|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-input|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-input|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-input|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-append|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-append|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-append|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-append|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-append|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-append|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-append|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-append|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-append|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-append|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-append|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-append|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-append|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-append|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-append|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-append|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-nohash|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-nohash|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-nohash|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-nohash|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-nohash|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-nohash|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-nohash|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-nohash|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-nohash|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-nohash|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-nohash|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-nohash|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-nohash|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-nohash|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-nohash|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-nohash|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-short-o|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-short-o|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-short-o|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-short-o|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-short-o|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-short-o|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-short-o|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-short-o|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-short-o|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-short-o|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-short-o|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-short-o|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-short-o|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-short-o|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-short-o|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-short-o|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-short-i|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-short-i|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-short-i|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-short-i|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-short-i|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-short-i|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-short-i|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-short-i|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-short-i|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-short-i|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-short-i|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-short-i|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-short-i|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-short-i|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-short-i|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-short-i|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-short-a|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-short-a|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-short-a|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-short-a|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-short-a|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-short-a|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-short-a|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-short-a|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-short-a|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-short-a|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-short-a|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-short-a|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-short-a|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-short-a|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-short-a|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-short-a|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-bad-mode|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-bad-mode|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-bad-mode|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-bad-mode|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-bad-mode|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-bad-mode|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-bad-mode|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-bad-mode|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-bad-mode|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-bad-mode|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-bad-mode|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-bad-mode|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-bad-mode|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-bad-mode|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-bad-mode|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-bad-mode|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-short-bad|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-short-bad|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-short-bad|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-short-bad|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-short-bad|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-short-bad|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-short-bad|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-short-bad|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-short-bad|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-short-bad|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-short-bad|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-short-bad|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-short-bad|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-short-bad|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-short-bad|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-short-bad|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-omit-drive|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-omit-drive|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-omit-drive|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-omit-drive|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-omit-drive|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-omit-drive|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-omit-drive|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-omit-drive|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-omit-drive|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-omit-drive|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-omit-drive|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-omit-drive|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-omit-drive|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-omit-drive|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-omit-drive|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-omit-drive|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-double-number|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-double-number|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-double-number|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-double-number|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-double-number|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-double-number|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-double-number|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-double-number|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-double-number|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-double-number|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-double-number|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-double-number|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-double-number|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-double-number|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-double-number|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-double-number|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-double-name|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-double-name|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-double-name|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-double-name|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-double-name|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-double-name|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-double-name|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-double-name|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-double-name|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-double-name|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-double-name|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-double-name|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-double-name|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-double-name|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-double-name|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-double-name|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-wrong-type|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-wrong-type|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-wrong-type|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-wrong-type|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-wrong-type|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-wrong-type|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-wrong-type|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-wrong-type|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-wrong-type|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-wrong-type|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-wrong-type|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-wrong-type|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-wrong-type|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-wrong-type|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-wrong-type|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-wrong-type|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|open-missing|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|open-missing|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|open-missing|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|open-missing|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|open-missing|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|open-missing|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|open-missing|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|open-missing|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|open-missing|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|open-missing|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|open-missing|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|open-missing|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|open-missing|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|open-missing|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|open-missing|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|open-missing|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|write-string|plain-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|write-string|plain-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|write-string|plain-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|write-string|plain-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|write-string|plain-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|write-string|plain-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|write-string|plain-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|write-string|plain-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|write-empty|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|write-empty|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|write-empty|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|write-empty|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|write-empty|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|write-empty|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|write-empty|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|write-empty|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|write-positive|both-crlf-sub|7|4dc96782d94c1a2fd6615ebd5bb3d481b92c4875132e0dd6f3edc441487dbb5c|
|write-positive|both-crlf-none|6|640d15fda18d5d1dc01b64d1958c7eb0cb580c46a5220483ca9649d87a279dbe|
|write-positive|both-cr-sub|6|b6c1cc220cd3219fee0e3da37e7b89074a7530fa630111d1afd4f2b5268b2e24|
|write-positive|both-cr-none|5|df7577a575019bd55f2eb354853c961534a3deb6eb4e36ff16f9becadeba0b54|
|write-positive|both-lf-sub|6|7858ba13b77d35ba9a2f24d05c1c20244ac31e675e5bb102fa0bad10fca7c137|
|write-positive|both-lf-none|5|c4776c73800a168d585169971a963f207ae997d8d9e94afceb8bfb679445c5b6|
|write-positive|both-none-sub|5|45e62faf8bc73b75a2d4f7d071946f36216611cb26f911be33132f0e0b40de35|
|write-positive|both-none-none|4|17868c4cc3e107391dc6cfdfe51835ed8121456665676e3ee3d2ea8de0a2482f|
|write-positive|right-crlf-sub|6|8ec17ad4b237de70b4e55727926d24baad4e8b876cf6b692d113ba5a71fe8f8e|
|write-positive|right-crlf-none|5|fb985afd52f5f886d1198ad4d00eaa19fb46f3f88c4d286d6c9be047c7838715|
|write-positive|right-cr-sub|5|f0859e0fb7fbca6c02d852be875606562765013992aef4b3ae507651d065554c|
|write-positive|right-cr-none|4|7fdfd815cf5478437a62e6d715e9934514a0eb90ca266e15f4acb5ab94fdf82a|
|write-positive|right-lf-sub|5|4782a086889d85ccf597d3aa490cd1e30a53addc77495963008e032d7f4c4677|
|write-positive|right-lf-none|4|6cd5dd763dec7b2089cd9b59bd11e23e63438ce9bb2512433b0cca3dd441dfff|
|write-positive|right-none-sub|4|629424352d2f74053a37cf9b1a61532922e66821faaba2346aede934ebb0c4a5|
|write-positive|right-none-none|3|a50eab9333a59d648039f387b1ab3d3d5e1ed7e330f5df1875834d27f3e346c6|
|write-positive|none-crlf-sub|5|2551184c1d6802840aa7cf43d32d1f0293b98216196ecda07bcc8b8b8865ac2a|
|write-positive|none-crlf-none|4|f2bf6cb915ec521520920f625e9a641f22bae7808a5f5db7867c431c1a79440f|
|write-positive|none-cr-sub|4|8160b86aed3b03046e48e796bec748071532a19bfd961bc6966a5eb2cf7cd75d|
|write-positive|none-cr-none|3|baac70299f466efde18b87f5aa05b3eaee8eacf2ecb26e175a26de1a1fe8d6b4|
|write-positive|none-lf-sub|4|946fff39090b662d4cb64703181582ffe3e97294c26742f67703e9fc13f2cd9b|
|write-positive|none-lf-none|3|a1fb50e6c86fae1679ef3351296fd6713411a08cf8dd1790a4fd05fae8688164|
|write-positive|none-none-sub|3|7f66e66889924acd32b58618d51dfb0bfe5bc34838d23c71f1c301c5e1637bfd|
|write-positive|none-none-none|2|6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918|
|write-negative|right-crlf-sub|7|233342326747bd7583a6755f5d70571f36aa1a423e043b7e8cefa17d09157859|
|write-negative|right-crlf-none|6|56bdce0803be1f5c4da86a74837ad3857d36b62ba66848c0491ba619320b6e42|
|write-negative|right-cr-sub|6|d48c25737ea183544664eb5cd81db127f622cce3bd000065bfe37ce09247064c|
|write-negative|right-cr-none|5|8075b0b85a42f2d719b85b0023a62bdbbedf7cc25ddb12d07441342b096c49d1|
|write-negative|right-lf-sub|6|b477c96f0123f2084426e14c6bcb2652f2c11a16136dbaf9838b01dcb9315e50|
|write-negative|right-lf-none|5|f73fc713e4b93f7e5214c93e9ee82695c40f6a741fded2c3032272eeb93f76e8|
|write-negative|right-none-sub|5|7a351b43b2e3687dd7a5e3debf2facd82d2324e2e8a97986f1810e60ce71e9c9|
|write-negative|right-none-none|4|96150b6205c0a1361520cc9740cebffcd3cb02a5cd4cf9f515aed6df26aa8c11|
|write-negative|none-crlf-sub|6|c02324b52234fb9f24e80b89d0162f384c911ced13cefab537869657ad6a1b22|
|write-negative|none-crlf-none|5|0fd31d95e9e3b5eab789145183f544f5d8b999a0c066a1638a4fa5bc7f4f553c|
|write-negative|none-cr-sub|5|371df80b11cfc7872d16938dea5946e36eadf21617711f0740e4620ac4cad1e7|
|write-negative|none-cr-none|4|a75cde53ccd759b3b8d55dee4dae71c6491dd7502acdeae477a18eadc2a6cddb|
|write-negative|none-lf-sub|5|57bf40d1697c4b96e923dff23828a3ae8f9bc09a603a3fa9c2a04908d1570640|
|write-negative|none-lf-none|4|dc9eee73793d61ce685b4b629d7c94155dc77744eb2e3d9b44d7a2336d7a068a|
|write-negative|none-none-sub|4|2cc1d211f2b5f10cb78983f72af885a7f34ba22ef9c02fe089141cfc0a007baf|
|write-negative|none-none-none|3|7ed00270e394c3e190d18a977f5d0e1ed889bdc03a637e8fe35f00946841b0bf|
|write-semi|joined-crlf-sub|5|d296ebe92e52fcb5487120b20a71368425641259c1a3474ff14b7f610b38fd77|
|write-semi|joined-crlf-none|4|c7c0875507bd96d407f116eaf706de057c9f1f0255f07ff8f57d0f8a527d7a50|
|write-semi|joined-cr-sub|4|9198541d03c6dd1b4d4938800fb7f78453d0c876f7062fe3ab392a972d194397|
|write-semi|joined-cr-none|3|8575fe6058bdae536796911772b66e07f93000e10b88b0c24b3e52d4d1d8b195|
|write-semi|joined-lf-sub|4|941ab43735d4913e32127294a488e97dd25265304838c816fde150afeffa4f92|
|write-semi|joined-lf-none|3|a63d8014dba891345b30174df2b2a57efbb65b4f9f09b98f245d1b3192277ece|
|write-semi|joined-none-sub|3|4ee6ce06691156c2e8bf3fdc168c2abebf02734f16f3dbf613b5f43cabf61c86|
|write-semi|joined-none-none|2|fb8e20fc2e4c3f248c60c39bd652f3c1347298bb977b8b4d5903b85055620603|
|write-semi|space-crlf-sub|6|04e5c87c0c944584d36ab2632fed39e724454c8dd00ffbc08f5ef7c589f41c6f|
|write-semi|space-crlf-none|5|4ae1198f28938d4a755c7a46a662f0f5729aca3cb714cae4e37d60b84c4ee9cc|
|write-semi|space-cr-sub|5|55f8f3e6f22ea42ff863d5fc026459cbfbc94f1c184685c058559d806aac1804|
|write-semi|space-cr-none|4|2d2c2342dbfb13424aba768588a0a140c31ed20e19d91bbe2693124b23962710|
|write-semi|space-lf-sub|5|78b03673421c7f67bfc1dedebe02677e1b307551e1b0ff36bf0893eb5ce148fc|
|write-semi|space-lf-none|4|01186fcf04b4b447f393e552964c08c7b419c1ad7a25c342a0b631b1967d3a27|
|write-semi|space-none-sub|4|6079e5cca768c3c85b4171e5479c027663f55c6064c6c2f742d888312ecc1f7b|
|write-semi|space-none-none|3|c8687a08aa5d6ed2044328fa6a697ab8e96dc34291e8c2034ae8c38e6fcc6d65|
|write-comma|zone0-crlf-sub|5|d296ebe92e52fcb5487120b20a71368425641259c1a3474ff14b7f610b38fd77|
|write-comma|zone0-crlf-none|4|c7c0875507bd96d407f116eaf706de057c9f1f0255f07ff8f57d0f8a527d7a50|
|write-comma|zone0-cr-sub|4|9198541d03c6dd1b4d4938800fb7f78453d0c876f7062fe3ab392a972d194397|
|write-comma|zone0-cr-none|3|8575fe6058bdae536796911772b66e07f93000e10b88b0c24b3e52d4d1d8b195|
|write-comma|zone0-lf-sub|4|941ab43735d4913e32127294a488e97dd25265304838c816fde150afeffa4f92|
|write-comma|zone0-lf-none|3|a63d8014dba891345b30174df2b2a57efbb65b4f9f09b98f245d1b3192277ece|
|write-comma|zone0-none-sub|3|4ee6ce06691156c2e8bf3fdc168c2abebf02734f16f3dbf613b5f43cabf61c86|
|write-comma|zone0-none-none|2|fb8e20fc2e4c3f248c60c39bd652f3c1347298bb977b8b4d5903b85055620603|
|write-comma|zone1-crlf-sub|6|04e5c87c0c944584d36ab2632fed39e724454c8dd00ffbc08f5ef7c589f41c6f|
|write-comma|zone1-crlf-none|5|4ae1198f28938d4a755c7a46a662f0f5729aca3cb714cae4e37d60b84c4ee9cc|
|write-comma|zone1-cr-sub|5|55f8f3e6f22ea42ff863d5fc026459cbfbc94f1c184685c058559d806aac1804|
|write-comma|zone1-cr-none|4|2d2c2342dbfb13424aba768588a0a140c31ed20e19d91bbe2693124b23962710|
|write-comma|zone1-lf-sub|5|78b03673421c7f67bfc1dedebe02677e1b307551e1b0ff36bf0893eb5ce148fc|
|write-comma|zone1-lf-none|4|01186fcf04b4b447f393e552964c08c7b419c1ad7a25c342a0b631b1967d3a27|
|write-comma|zone1-none-sub|4|6079e5cca768c3c85b4171e5479c027663f55c6064c6c2f742d888312ecc1f7b|
|write-comma|zone1-none-none|3|c8687a08aa5d6ed2044328fa6a697ab8e96dc34291e8c2034ae8c38e6fcc6d65|
|write-comma|zone12-crlf-sub|17|f213fe898ed32a822c6e148c1f6570a3677eced88bcd2865ea639c0bd1253a43|
|write-comma|zone12-crlf-none|16|6e431a9a47bd4904a88e4f4e27ec1d222920cd34dfe86fdcbe9a354f28397702|
|write-comma|zone12-cr-sub|16|c3e9191ba4fd54df5c069d9496ce1d912b42dc6e5b5e3f7f9f9422087c708849|
|write-comma|zone12-cr-none|15|8626156a68cc260dbc544ce138dff7ef2467eb73413b880098eeed67b9e7e9a8|
|write-comma|zone12-lf-sub|16|e38038bed2bfc2813564c594d8ee3a5b80c882d7391b418e7c09f32bab86425f|
|write-comma|zone12-lf-none|15|b240f8c44053435948143a0fcabbb6eadd2d1329442be4c8c7eec9b999346351|
|write-comma|zone12-none-sub|15|b80cf5e9280c700df1c4b618d1fc531d44e7c7a9db0855aaea6b2ac5d2e9b234|
|write-comma|zone12-none-none|14|de283b90560a6d40998d40d3cb76b196c11222d236e97cfdb6bf1c73a00e529b|
|write-comma|zone13-crlf-sub|18|5f80aae28b64422257257c6fa698f8a2cc855c4fc27d3d1368cb54fa5010afd6|
|write-comma|zone13-crlf-none|17|1fe1b6bb856556dbd6935e4600da7987b6b3f326eabdd6a30e6808c02c335f52|
|write-comma|zone13-cr-sub|17|e5c728043b0b2c6a65b90b8e5a8ef775a6a71a6ec260990174b8975b574035d9|
|write-comma|zone13-cr-none|16|575be097d212e92ab6c9dd159edbf761f61bd4ef853fd433409f336bc44ce79d|
|write-comma|zone13-lf-sub|17|e244475dacc9c00b9790521049466e4dea10a9c73fe8bc13bb944448f216f2aa|
|write-comma|zone13-lf-none|16|2194cc140a8ecded79a8f13f48053e12ce9efbf297a7cf4ba274692a84ef9d63|
|write-comma|zone13-none-sub|16|c19470931adb6c49b24df1ba796a2a6e078bd8c63ba85112d9e940d8707a3713|
|write-comma|zone13-none-none|15|f79acc039b83a875eee908296765e87338b0814e2f5913515af6899a0c1abcf3|
|write-comma|zone14-crlf-sub|19|1c7d6238e595f1abddfbe9a2267779aee648ca15633a545532591c05bc180e67|
|write-comma|zone14-crlf-none|18|e7dc58a8439d6071c327669e53eaeb0fd2771ec002f7131cde8a573fb5c9b76c|
|write-comma|zone14-cr-sub|18|ac135db2725f0811ce8da80519445d0dc251dd1b7e89e4b77d20182c87678449|
|write-comma|zone14-cr-none|17|f4cfdeacb7592420c959a8b956d6297057b7467c888a1c2b25cfae24faa40b6e|
|write-comma|zone14-lf-sub|18|26b2bcaba3ab5a2768af75d102943427ea7938aa2f14705e1dd7c663dfc4193c|
|write-comma|zone14-lf-none|17|b4f142e6920ef43677dc9ec53e80c47d00a53f72e4bb29953cb5dca97fbec8a5|
|write-comma|zone14-none-sub|17|d9a79d892fec749ca75cdefe771c6b197c9fce823771b779c4c96ca9d0d2cf68|
|write-comma|zone14-none-none|16|461145cad961bd6ceb61a4ca6a4e4e38ec8966e7249701adc9f234ff52e62295|
|write-comma|zone15-crlf-sub|20|16fb34c2f25f1ac67a05fb737b58ec111cebc6e938decb553d70adbc5daf9498|
|write-comma|zone15-crlf-none|19|b6831328c2c98168a7e47fdbdff807aab97496b7bce72a6679bf5c5b290d7622|
|write-comma|zone15-cr-sub|19|27adc1debcc86e7df60713bec982a2c7327111646e29575d96c61fe7d8fca735|
|write-comma|zone15-cr-none|18|5c283e06e780ef60d7376754e1d2424c60f5178475b23342c8de26bea8b7a73a|
|write-comma|zone15-lf-sub|19|9949e137e9bd81867d986269590d28786d9db1657078cfe2aec3b87b3c522367|
|write-comma|zone15-lf-none|18|d4d8e8a322a2c05d090701af97a45858ba521275c6a6b489a140c2ae98d01476|
|write-comma|zone15-none-sub|18|81f5af5812aa2520b438203ccc246bf5d5355262ee90f13aea681dd2e3cb0c35|
|write-comma|zone15-none-none|17|0433288bb01d4d0d996416bfea956b90342640d36fa199be75a98bc2c3766748|
|write-trailing-semi|single-crlf-sub|4|83f2fbaf1648a2ab3c9a30319da4f83532931bf79f2f7cef531f21d06f5c0af9|
|write-trailing-semi|single-crlf-none|3|8e4621379786ef42a4fec155cd525c291dd7db3c1fde3478522f4f61c03fd1bd|
|write-trailing-semi|single-cr-sub|3|5daa7a41509aab8872646ce4aa47ae16d74d8bc15980ba7ad2f38116729c46f2|
|write-trailing-semi|single-cr-none|2|961a57df036f6c4f44ca8a054271c45e823f469bcc439f0255c40974c3e3d131|
|write-trailing-semi|single-lf-sub|3|319146ac8ceef38b00bfa4fd68e632f08b4e1fa01a666615ee7699cc0403f17f|
|write-trailing-semi|single-lf-none|2|87428fc522803d31065e7bce3cf03fe475096631e5e07bbd7a0fde60c4cf25c7|
|write-trailing-semi|single-none-sub|2|400e9493cd2c7e3325be67cafd225ae3a80a82f903e20ab0f9f05f1604e9a537|
|write-trailing-semi|single-none-none|1|ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb|
|write-trailing-comma|zone0-crlf-sub|5|d296ebe92e52fcb5487120b20a71368425641259c1a3474ff14b7f610b38fd77|
|write-trailing-comma|zone0-crlf-none|4|c7c0875507bd96d407f116eaf706de057c9f1f0255f07ff8f57d0f8a527d7a50|
|write-trailing-comma|zone0-cr-sub|4|9198541d03c6dd1b4d4938800fb7f78453d0c876f7062fe3ab392a972d194397|
|write-trailing-comma|zone0-cr-none|3|8575fe6058bdae536796911772b66e07f93000e10b88b0c24b3e52d4d1d8b195|
|write-trailing-comma|zone0-lf-sub|4|941ab43735d4913e32127294a488e97dd25265304838c816fde150afeffa4f92|
|write-trailing-comma|zone0-lf-none|3|a63d8014dba891345b30174df2b2a57efbb65b4f9f09b98f245d1b3192277ece|
|write-trailing-comma|zone0-none-sub|3|4ee6ce06691156c2e8bf3fdc168c2abebf02734f16f3dbf613b5f43cabf61c86|
|write-trailing-comma|zone0-none-none|2|fb8e20fc2e4c3f248c60c39bd652f3c1347298bb977b8b4d5903b85055620603|
|write-trailing-comma|zone1-crlf-sub|6|04e5c87c0c944584d36ab2632fed39e724454c8dd00ffbc08f5ef7c589f41c6f|
|write-trailing-comma|zone1-crlf-none|5|4ae1198f28938d4a755c7a46a662f0f5729aca3cb714cae4e37d60b84c4ee9cc|
|write-trailing-comma|zone1-cr-sub|5|55f8f3e6f22ea42ff863d5fc026459cbfbc94f1c184685c058559d806aac1804|
|write-trailing-comma|zone1-cr-none|4|2d2c2342dbfb13424aba768588a0a140c31ed20e19d91bbe2693124b23962710|
|write-trailing-comma|zone1-lf-sub|5|78b03673421c7f67bfc1dedebe02677e1b307551e1b0ff36bf0893eb5ce148fc|
|write-trailing-comma|zone1-lf-none|4|01186fcf04b4b447f393e552964c08c7b419c1ad7a25c342a0b631b1967d3a27|
|write-trailing-comma|zone1-none-sub|4|6079e5cca768c3c85b4171e5479c027663f55c6064c6c2f742d888312ecc1f7b|
|write-trailing-comma|zone1-none-none|3|c8687a08aa5d6ed2044328fa6a697ab8e96dc34291e8c2034ae8c38e6fcc6d65|
|write-trailing-comma|zone12-crlf-sub|17|f213fe898ed32a822c6e148c1f6570a3677eced88bcd2865ea639c0bd1253a43|
|write-trailing-comma|zone12-crlf-none|16|6e431a9a47bd4904a88e4f4e27ec1d222920cd34dfe86fdcbe9a354f28397702|
|write-trailing-comma|zone12-cr-sub|16|c3e9191ba4fd54df5c069d9496ce1d912b42dc6e5b5e3f7f9f9422087c708849|
|write-trailing-comma|zone12-cr-none|15|8626156a68cc260dbc544ce138dff7ef2467eb73413b880098eeed67b9e7e9a8|
|write-trailing-comma|zone12-lf-sub|16|e38038bed2bfc2813564c594d8ee3a5b80c882d7391b418e7c09f32bab86425f|
|write-trailing-comma|zone12-lf-none|15|b240f8c44053435948143a0fcabbb6eadd2d1329442be4c8c7eec9b999346351|
|write-trailing-comma|zone12-none-sub|15|b80cf5e9280c700df1c4b618d1fc531d44e7c7a9db0855aaea6b2ac5d2e9b234|
|write-trailing-comma|zone12-none-none|14|de283b90560a6d40998d40d3cb76b196c11222d236e97cfdb6bf1c73a00e529b|
|write-trailing-comma|zone13-crlf-sub|18|5f80aae28b64422257257c6fa698f8a2cc855c4fc27d3d1368cb54fa5010afd6|
|write-trailing-comma|zone13-crlf-none|17|1fe1b6bb856556dbd6935e4600da7987b6b3f326eabdd6a30e6808c02c335f52|
|write-trailing-comma|zone13-cr-sub|17|e5c728043b0b2c6a65b90b8e5a8ef775a6a71a6ec260990174b8975b574035d9|
|write-trailing-comma|zone13-cr-none|16|575be097d212e92ab6c9dd159edbf761f61bd4ef853fd433409f336bc44ce79d|
|write-trailing-comma|zone13-lf-sub|17|e244475dacc9c00b9790521049466e4dea10a9c73fe8bc13bb944448f216f2aa|
|write-trailing-comma|zone13-lf-none|16|2194cc140a8ecded79a8f13f48053e12ce9efbf297a7cf4ba274692a84ef9d63|
|write-trailing-comma|zone13-none-sub|16|c19470931adb6c49b24df1ba796a2a6e078bd8c63ba85112d9e940d8707a3713|
|write-trailing-comma|zone13-none-none|15|f79acc039b83a875eee908296765e87338b0814e2f5913515af6899a0c1abcf3|
|write-trailing-comma|zone14-crlf-sub|19|1c7d6238e595f1abddfbe9a2267779aee648ca15633a545532591c05bc180e67|
|write-trailing-comma|zone14-crlf-none|18|e7dc58a8439d6071c327669e53eaeb0fd2771ec002f7131cde8a573fb5c9b76c|
|write-trailing-comma|zone14-cr-sub|18|ac135db2725f0811ce8da80519445d0dc251dd1b7e89e4b77d20182c87678449|
|write-trailing-comma|zone14-cr-none|17|f4cfdeacb7592420c959a8b956d6297057b7467c888a1c2b25cfae24faa40b6e|
|write-trailing-comma|zone14-lf-sub|18|26b2bcaba3ab5a2768af75d102943427ea7938aa2f14705e1dd7c663dfc4193c|
|write-trailing-comma|zone14-lf-none|17|b4f142e6920ef43677dc9ec53e80c47d00a53f72e4bb29953cb5dca97fbec8a5|
|write-trailing-comma|zone14-none-sub|17|d9a79d892fec749ca75cdefe771c6b197c9fce823771b779c4c96ca9d0d2cf68|
|write-trailing-comma|zone14-none-none|16|461145cad961bd6ceb61a4ca6a4e4e38ec8966e7249701adc9f234ff52e62295|
|write-trailing-comma|zone15-crlf-sub|20|16fb34c2f25f1ac67a05fb737b58ec111cebc6e938decb553d70adbc5daf9498|
|write-trailing-comma|zone15-crlf-none|19|b6831328c2c98168a7e47fdbdff807aab97496b7bce72a6679bf5c5b290d7622|
|write-trailing-comma|zone15-cr-sub|19|27adc1debcc86e7df60713bec982a2c7327111646e29575d96c61fe7d8fca735|
|write-trailing-comma|zone15-cr-none|18|5c283e06e780ef60d7376754e1d2424c60f5178475b23342c8de26bea8b7a73a|
|write-trailing-comma|zone15-lf-sub|19|9949e137e9bd81867d986269590d28786d9db1657078cfe2aec3b87b3c522367|
|write-trailing-comma|zone15-lf-none|18|d4d8e8a322a2c05d090701af97a45858ba521275c6a6b489a140c2ae98d01476|
|write-trailing-comma|zone15-none-sub|18|81f5af5812aa2520b438203ccc246bf5d5355262ee90f13aea681dd2e3cb0c35|
|write-trailing-comma|zone15-none-none|17|0433288bb01d4d0d996416bfea956b90342640d36fa199be75a98bc2c3766748|
|write-blank|empty-crlf-sub|3|6f864b1705ae269c03903f630181ca89b5372a25f0d17147bc9d98a5c84f72be|
|write-blank|empty-crlf-none|2|7eb70257593da06f682a3ddda54a9d260d4fc514f645237f5ca74b08f8da61a6|
|write-blank|empty-cr-sub|2|92eba1beb1495a99b1b25d8dbfa926208a9a98e3ff2ec3d968014e6a56c5dae8|
|write-blank|empty-cr-none|1|9d1e0e2d9459d06523ad13e28a4093c2316baafe7aec5b25f30eba2e113599c4|
|write-blank|empty-lf-sub|2|43ded0605302a9607913c5e2b54699ffd34653bf23f4f2339b472cf87cffeda1|
|write-blank|empty-lf-none|1|01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b|
|write-blank|empty-none-sub|1|58f7b0780592032e4d8602a3e8690fb2c701b2e1dd546e703445aabd6469734d|
|write-blank|empty-none-none|0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855|
|write-mixed|spaces-crlf-sub|11|44226185dbcc9f26e469dbc7f2970584012d354f47bdbb2761b3bb58be46ff52|
|write-mixed|spaces-crlf-none|10|603f5a961b23eefe4eb917408af94ce77f21d31efeec75604054dd4ef013c3a2|
|write-mixed|spaces-cr-sub|10|c122468ef6a4f84516e882ae6dc9b19d95db0bc4ba4c8e0d0623e15dcb2d914d|
|write-mixed|spaces-cr-none|9|b81d4de3e294972dd941c38c4ffdfa895df3bde4324c6832ada4d9aa15ac237e|
|write-mixed|spaces-lf-sub|10|0f059bf0e4df988d1e24f0e0faa17ffe34bfbecbbf7dca8dc2a94edb1dcd3628|
|write-mixed|spaces-lf-none|9|15a4924f61ea274a7cf3c74776c08545496bdcec9cf92ee67bd9d0a62276442b|
|write-mixed|spaces-none-sub|9|5a521bc78ee08386c965eac82bf073a6c5c5ff98ed096820a1771e5a95059741|
|write-mixed|spaces-none-none|8|591e5c9d15e288b3f773acdd787b00538e3ab7f7eb0586927035ca9c1edb32a5|
|write-mixed|compact-crlf-sub|8|b24f002fb3c88ff5a1cb22efe996b091e41259ce2a9ce10469a86bf3ae0a06f5|
|write-mixed|compact-crlf-none|7|d08f3fe9db22bb586132c46bb2d4e06c994037c5a13b0fc3a8f212730468eed8|
|write-mixed|compact-cr-sub|7|44441621ec3e36e8767536405a6afe3770713d0213dd19da5e70558d253f9aea|
|write-mixed|compact-cr-none|6|8b42311e44141d409c9724eacb1b0b737c1a2faec723dc60a2dc28810f28c3ca|
|write-mixed|compact-lf-sub|7|b263b4a839e693cf40b92ff41e21e44f90b59c6ee1f7fc12b743996ecee42e1b|
|write-mixed|compact-lf-none|6|07ce155f5825f388606f66bc059430895cd8ad39443b997cda22baaee86dc029|
|write-mixed|compact-none-sub|6|4615350a043fecf12e7be1cce7268c335aa8623109b2df532f1dfcf5bda898b6|
|write-mixed|compact-none-none|5|14b916354a346f4f2fe1b643bab9a1d5dc122a9c524b33a0ac97a6ebc8b29d2e|
|write-write-string|quoted-crlf-sub|10|95f6140129517c233e0b42f01a7c23f88ccbedbb1d48deaee36f5d0747bbfedd|
|write-write-string|quoted-crlf-none|9|ebca5eb3316a36a4a011a49e557e3c99e3bcfdc4c34fac29fd264029546e555b|
|write-write-string|quoted-cr-sub|9|22225946688b1f187afdbd3f50777c6621fe2ebfd7b4776eb6eca1bb0e06c5a9|
|write-write-string|quoted-cr-none|8|5eef995d47434118f79688cfa2a2ea9af49f6a66c74371cf62458e9eff925243|
|write-write-string|quoted-lf-sub|9|74220dc1d87ff3676f3e949a4975f2f1195816e1dc60a729e6968066bcad2daf|
|write-write-string|quoted-lf-none|8|b4c0620510cba2b064dc9e4f72007eca5a9e87a025988e60f71384567bc41e00|
|write-write-string|quoted-none-sub|8|def9bb44477650b41a22c435c4b02165fac4b8c6132f82e86c13c4961143d78f|
|write-write-string|quoted-none-none|7|902cf2b465fb076229183b408aad4014266eb9eb72d448754227adc1eeac49b9|
|write-write-string|plain-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|write-write-string|plain-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|write-write-string|plain-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|write-write-string|plain-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|write-write-string|plain-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|write-write-string|plain-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|write-write-string|plain-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|write-write-string|plain-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|write-write-mixed|quoted-crlf-sub|15|96f4091048eb14d9f0efa31d7b60c4868e51f506a9767b367f7764ec595a71cf|
|write-write-mixed|quoted-crlf-none|14|b1500fbccbb74cb79905c3c3832f9ff3046ad9e430cc262e2e5f209424f915b9|
|write-write-mixed|quoted-cr-sub|14|a15ca1d779bfa0d4d21e340b756112dc8ffae43614d298a8d91c3cff7300bb26|
|write-write-mixed|quoted-cr-none|13|e5b40fcbaede89bee09929d8587e743fd73a7b0ed410c82789a811d0c249b783|
|write-write-mixed|quoted-lf-sub|14|3bac6c1a13db889569966e16488ab371b78e43b2d5471a06effda850fd808680|
|write-write-mixed|quoted-lf-none|13|981b2db531565f3ad84653cb389c763a674f435af42ac4496690f299cde1b6d2|
|write-write-mixed|quoted-none-sub|13|49a07c16ffa12b8ae69b2d8e1b475d5e0be6ecc58a7b38c7fb5872d94e27250e|
|write-write-mixed|quoted-none-none|12|3b762eee4b4c5a025a081e8947aef148bd289001664b1a57bae76892be3c7a5c|
|write-write-mixed|spaces-crlf-sub|18|41074ecd28de855ca477a8f06954ac92d32367f09d1fd33699544e64573959ac|
|write-write-mixed|spaces-crlf-none|17|33821f84129ce2ec63cd43c602cc87f88393db8e006a1bd7809f1449d9813b5d|
|write-write-mixed|spaces-cr-sub|17|f866bfb2189e6562cb1e42b103f2aa255be14479a80fdd63945c739fdf045e7b|
|write-write-mixed|spaces-cr-none|16|a8588ab7d9699d55632898a95dce91034c9b7d6e9f4f90492279fe9b12b31eab|
|write-write-mixed|spaces-lf-sub|17|6fbbef2fc23e3491e4d60cfff6cc81155772fe10e73e1f516f93e463ad177cc5|
|write-write-mixed|spaces-lf-none|16|c0bafc5e80d50c0d71f3f1ded3dda3d27d4e3cdba8fa856a7c0ffca862135f88|
|write-write-mixed|spaces-none-sub|16|b2a14b8e72e6aa060c05810dd29e250b23009e4c75531efdd1df96fc5db1e9cd|
|write-write-mixed|spaces-none-none|15|afb09b7002e61b0b0dc82884c1e1acc57df2432868ad2569a16402c3f74b7d8c|
|write-write-quote|raw-crlf-sub|7|d355eca7f3b93f8e7797cfe4ad146a6c4fc4b2672919c62e1f6ecc4e26325b93|
|write-write-quote|raw-crlf-none|6|6decf7e981ff056d47f8b232f264f4fe84a987f60a25f9a28875322ae509ffc1|
|write-write-quote|raw-cr-sub|6|7be7258d7b056f1be8729162495fc44e32bf0e4bf319a90e34df5fd321d7b319|
|write-write-quote|raw-cr-none|5|2875b7e30f777cbd409e15399b4e2d7ada686f68ae748f7aaba44b52701cc4c0|
|write-write-quote|raw-lf-sub|6|0e5e7680fb04a120d8a58c49f07c05577feb53d3b19d38ba5676c17afda12af9|
|write-write-quote|raw-lf-none|5|8c62a1ec9d4d04f38a84d090f40d66515b8819649e7e3185a99304df08c27b06|
|write-write-quote|raw-none-sub|5|e3bd6a5c2106aafc96d11d2b5ed1850bb74558eeee78e0ec701b6b9a1d46c2d4|
|write-write-quote|raw-none-none|4|d38b864c9fac120f520cbc4fe01a5a6d5245c58928510035ead2c32a07802217|
|write-write-quote|double-crlf-sub|8|7453583cc8bdf3691ab88245e1eb035262ec07fa2ecabf56d367f936cbe49f9f|
|write-write-quote|double-crlf-none|7|fe2058b533f7742e4377d65325c88580972037b5dfc3bb96fc6940c285710725|
|write-write-quote|double-cr-sub|7|ca1fa5926d72fa6cec8515dd6c39b7fbdf27edad850e2681607cd9dd09f9da50|
|write-write-quote|double-cr-none|6|9bd56c3af8fc7ce1a864e172de9b44fce1c5c674700801e983fda6a6391bedcb|
|write-write-quote|double-lf-sub|7|fa2b595376af34ed38643c652396cd20a835d61ac1d97ad5ba29f0977f7278fe|
|write-write-quote|double-lf-none|6|e365947a79bc05d5433d85e2702c35966f68f448ec244af1827db9cd0928abf1|
|write-write-quote|double-none-sub|6|b09161ba521497dc59e95015151c28dafd05add0e0c8fe43a141859d063f5453|
|write-write-quote|double-none-none|5|d2953f43fb9456088dbc2c5d44006b18769fa2813d0f9ef3b14c5d341b806a8e|
|write-using|field-crlf-sub|6|701c8dd354d33d1043700a7c06566cc5d858b7a7eeef805bf20fedf4d10938cd|
|write-using|field-crlf-none|5|327170088d3dd288a3588a56e827a67a3fb30f5939da238cc00d225769bfc96f|
|write-using|field-cr-sub|5|cd52fa33e068680c4d0180ee279073857cd6b961df1c09b18bca004c728774fa|
|write-using|field-cr-none|4|9a4735387b0d2029060b319937ef2a3da048eaa979c6037f20ea4f041c9e87ee|
|write-using|field-lf-sub|5|9fae4fda1b22688955750ff748d5d51c29144890c22a989965a80eca60535f1a|
|write-using|field-lf-none|4|a547830c7965a34805fc013318a66d8543ac0dd350541b2cad38d001dbf2f961|
|write-using|field-none-sub|4|41e1831fe175b9bd4842d441870dfeebdc0e0a3b827a939e4301c4c25701d4a1|
|write-using|field-none-none|3|32c75a5e4c4b1959030416ac620d7246fdab47556b7280d2510f971078d4b925|
|write-using|right-crlf-sub|6|8ec17ad4b237de70b4e55727926d24baad4e8b876cf6b692d113ba5a71fe8f8e|
|write-using|right-crlf-none|5|fb985afd52f5f886d1198ad4d00eaa19fb46f3f88c4d286d6c9be047c7838715|
|write-using|right-cr-sub|5|f0859e0fb7fbca6c02d852be875606562765013992aef4b3ae507651d065554c|
|write-using|right-cr-none|4|7fdfd815cf5478437a62e6d715e9934514a0eb90ca266e15f4acb5ab94fdf82a|
|write-using|right-lf-sub|5|4782a086889d85ccf597d3aa490cd1e30a53addc77495963008e032d7f4c4677|
|write-using|right-lf-none|4|6cd5dd763dec7b2089cd9b59bd11e23e63438ce9bb2512433b0cca3dd441dfff|
|write-using|right-none-sub|4|629424352d2f74053a37cf9b1a61532922e66821faaba2346aede934ebb0c4a5|
|write-using|right-none-none|3|a50eab9333a59d648039f387b1ab3d3d5e1ed7e330f5df1875834d27f3e346c6|
|write-using|both-crlf-sub|7|4dc96782d94c1a2fd6615ebd5bb3d481b92c4875132e0dd6f3edc441487dbb5c|
|write-using|both-crlf-none|6|640d15fda18d5d1dc01b64d1958c7eb0cb580c46a5220483ca9649d87a279dbe|
|write-using|both-cr-sub|6|b6c1cc220cd3219fee0e3da37e7b89074a7530fa630111d1afd4f2b5268b2e24|
|write-using|both-cr-none|5|df7577a575019bd55f2eb354853c961534a3deb6eb4e36ff16f9becadeba0b54|
|write-using|both-lf-sub|6|7858ba13b77d35ba9a2f24d05c1c20244ac31e675e5bb102fa0bad10fca7c137|
|write-using|both-lf-none|5|c4776c73800a168d585169971a963f207ae997d8d9e94afceb8bfb679445c5b6|
|write-using|both-none-sub|5|45e62faf8bc73b75a2d4f7d071946f36216611cb26f911be33132f0e0b40de35|
|write-using|both-none-none|4|17868c4cc3e107391dc6cfdfe51835ed8121456665676e3ee3d2ea8de0a2482f|
|close-hash|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|close-hash|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|close-hash|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|close-hash|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|close-hash|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|close-hash|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|close-hash|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|close-hash|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|close-all|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|close-all|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|close-all|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|close-all|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|close-all|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|close-all|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|close-all|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|close-all|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|close-list|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|close-list|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|close-list|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|close-list|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|close-list|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|close-list|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|close-list|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|close-list|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|finish-end|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|finish-end|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|finish-end|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|finish-end|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|finish-end|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|finish-end|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|finish-end|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|finish-end|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|finish-run|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|finish-run|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|finish-run|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|finish-run|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|finish-run|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|finish-run|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|finish-run|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|finish-run|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|finish-new|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|finish-new|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|finish-new|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|finish-new|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|finish-new|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|finish-new|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|finish-new|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|finish-new|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|finish-load|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|finish-load|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|finish-load|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|finish-load|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|finish-load|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|finish-load|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|finish-load|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|finish-load|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|flush-end|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|flush-end|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|flush-end|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|flush-end|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|flush-end|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|flush-end|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|flush-end|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|flush-end|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|flush-run|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|flush-run|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|flush-run|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|flush-run|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|flush-run|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|flush-run|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|flush-run|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|flush-run|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|flush-new|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|flush-new|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|flush-new|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|flush-new|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|flush-new|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|flush-new|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|flush-new|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|flush-new|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|flush-load|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|flush-load|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|flush-load|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|flush-load|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|flush-load|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|flush-load|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|flush-load|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|flush-load|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|kill-open|alpha-crlf-sub|8|94bca135a0ec930131f974b2f3323c6f8c6419de8049ed9ce1200a1ffc3fa336|
|kill-open|alpha-crlf-none|7|4a31f8a329cdbbab944056fc992eeb5ab5c0b4a78c3bc34e6d7c4a59fd6cf3b6|
|kill-open|alpha-cr-sub|7|fdd5d66a56f24f59e23570342451560235922fba2be7be44132c7366eceaaac2|
|kill-open|alpha-cr-none|6|07be3cf443e4bf62a5793ec9f8440fef3931d23e9aa20d150ac1b70557ece2f7|
|kill-open|alpha-lf-sub|7|274c3f150a2054dd1c894f0b015a0b4ef26f655d6b310f65fd311aea2dafc063|
|kill-open|alpha-lf-none|6|b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060|
|kill-open|alpha-none-sub|6|6320b8381d356f63a285a9fd26744e6c392baa76117961b4831af2034f7bc187|
|kill-open|alpha-none-none|5|8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8|
|append-existing|joined-crlf-sub|14|c9f03ebbab5503004f10b30f83e50b25a4cbd78c7c2d41f2b24842e185a7eb7f|
|append-existing|joined-crlf-none|13|98ab4d3aeab1e120560e942e2df6a0db1147bf94bafcf1590000ffb3c2b6fc80|
|append-existing|joined-cr-sub|13|2045e1f360ccf608ef94a5fc017e267bc817538ac5c64ab3b1011d2029c9f11b|
|append-existing|joined-cr-none|12|9f582519fb21e19307c20b3c7734a71fc7631d4ae779b8c219e361eb8c40271c|
|append-existing|joined-lf-sub|13|7dfd8483c7ad2cb76dd208575836c0cf64b6d4032b03e447c53aa30dd3165681|
|append-existing|joined-lf-none|12|4f85d1b0cff7bb76f0c9a58366030c6dc1eb8e1243e3709c72452278ddce7c13|
|append-existing|joined-none-sub|12|a925348c789accdc0d5441bd1a9a8dec13ea913b310d26837474abd7435b1015|
|append-existing|joined-none-none|11|4854aaef74503959fd26363306e2ef967a9d50bdda90d033a3a4acacbbd57547|

## 自己検査の範囲

実capture経路に合成フロントエンドを接続し、公開規則で作った起動可否の印だけから正常構成と両空媒体構成を切り替える。正しい媒体で陽性通過、空媒体でERR33かつ陽性拒否を確認する。実公式ROMを呼ぶ検査ではない。I/Oとメモリのログ開始フレームを打鍵開始に一致させ、標準出力・標準エラーの合成秘密文字列を漏らさず、媒体コピーと生ログが削除されることも検証する。

## 除外範囲と第2回手順

書込み禁止媒体・満杯媒体は測らない（追補）。src/変更、git commit、run_all、他のtmp/の閲覧をしない。既存のsrc/等の作業差分には触れない。
第1回は tools/l4_seqfile_selftest.sh のみ実行する。作業・ログ・報告はtmp/f1-work/内。公式測定は親が第2回に環境変数を設定して実行する。

```sh
python3 tools/l4_seqfile_measure.py measure --official --work-dir "$PWD/tmp/f1-work/official" --out "$PWD/tmp/f1-work/official.tsv"
python3 tools/l4_seqfile_measure.py expected --out "$PWD/tmp/f1-work/expected.tsv" "$PWD/tmp/f1-work/official.tsv"
python3 tools/l4_seqfile_measure.py check --expected "$PWD/tmp/f1-work/expected.tsv" --measured "$PWD/tmp/f1-work/official.tsv"
```

公式は180起動を逐次実行。フレーム予定はdescribeとscheduleで再現可能。各起動240秒の壁時計上限、上限12時間。自作試走の実時間と集計をtmp/f1-work/p1-report.mdに残す。

第1回自己検査中の器具調整: 全番号が拒否される自作試走で255件となった後、不要な最終CLOSEの誤りを加えると件数欄の1バイト上限を越えるため、番号走査腕の段3をREMにした。受理した番号は各反復内で閉じる。公式観測に基づく変更ではない。他腕の打鍵は不変。初期試走の署名はPLAN c0663383fbf0feae28582ca5b3be91621aca1d2c20b382925858e89dd5e62e07 / PROGRAM d1877ba2547f96d96a1130fb760878cc754dde8d37db8802b9d303096041c423。最終署名は冒頭の値。初期試走は保存し、変更腕のみ最終定義で再試走して集計する。

同じ自己検査でlong fixtureは100文字×3行とし、長行による文字列長制限と切り分けた。EOF/LOC/LOFのlong腕は2行（204文字位置）を読んでから観測し、128Bと256Bの単位候補を区別する。これら3腕も最終定義で再試走する。

公式測定前の網羅性点検でwrite-trailing-semiを「後続PRINTとの連結」から「単独の末尾セミコロンをCLOSE」に修正した。改行が抑止されたまま終端する場合を直接区別する。セミコロン連結はwrite-semiで測る。この1腕も最終定義で2走する（変更は合計5腕）。

終了時のフラッシュを後処理のCLOSEと混同しないため、flush-end/run/new/loadの4腕を追加し、重複する番号32/64/255/-1腕と置換した（90腕を維持、番号1..255走査と0/256腕は維持）。flush腕はイベント後にPOKEだけで完了印を作り（RUN以外は直打ち、RUNはプログラム内の観測部）、再RUN・NEW・END・OPEN・CLOSEせず媒体を観測する。finish系列のBASIC再読とは独立の同一前半刺激である。RUNの再入口はプログラム内の観測部へ分岐し、追加ENDによる閉鎖を避けた。flush-runの観測部はPOKEと終了後の待機ループのみ。初期試走から変更した計10腕を最終定義で各2走する。

継続セッションの自作試走でRUN腕のCLEARがON ERROR登録の後にあり、最初の未実装OPENで診断ハンドラを失っていた。初回だけ再入口判定→CLEAR→開始/初期化→ON ERROR→準備の順へ修正した。再RUN時は7000番へ直接移り、履歴を初期化しない。PROGRAM署名とRUN 2腕の入力署名を更新し、現行90腕を全て再試走する。公式測定に基づく変更はない。

全体passedにも全腕の器具関門成立を直接要求し、較正・陽性・非一様が保たれていても1腕の器具関門を落とすと全体不成立となる合成陰性検査を追加した。RUNの初回CLEARがON ERRORより前であること、および再RUN観測部が初回打鍵時点から存在することも自己検査する。

結果へ: [l4-f1-seqfile-results.md](l4-f1-seqfile-results.md)
