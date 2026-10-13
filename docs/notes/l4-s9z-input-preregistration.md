# l4-s9z INPUTの完成とLINE INPUT — 第1回事前登録

2026-10-13。CLAUDE.md全文を最初に読み、クリーンルーム規律を適用する。公式ROMの実行・バイト列閲覧・保存観測閲覧はしない。src/変更、commit、run_all実行はしない。今回の改訂器具と事前登録は作業先内に置く。親が採用時に本ノート（事前登録）と器具を別コミットにする。作業ファイルは `tmp/s9z-work/` 内のみ。他のtmpは開かない。

## 出所

許可された `docs/spec/l4-program.md` 4.13（727〜745行）と、第8節INPUTの未確定事項18/19の該当行だけを仕様根拠とする。既知なのは数値1変数と2変数の正常代入、要求表示の存在まで。リンク先の公式観測は読まない。器具の型は `docs/notes/l4-s9y-dim-preregistration.md`、`tools/l4_dim_measure.py`・selftest/conformから採る。署名の設計は `check_l3_screen_output.py` と `check_l3_entry_screen.py` を参照。外部マニュアル・Web・ROM内部資料は今回読まない。以下の予測は依頼にある一般的なBASIC言語仕様による仮説で、確定仕様と混ぜない。

## 仮説と判定

INPUTのセミコロン区切りの文字列プロンプトには疑問符と空白、コンマ区切りには接尾なし、プロンプトなしには疑問符と空白を弱く予測する。先頭セミコロンは入力後の改行抑止を予測。LINE INPUTでは文字列プロンプトの接尾なし、行のコンマ・引用符・先頭末尾空白の保持を予測する。

型は通常数値・整数%・単精度!・倍精度#・文字列$・配列要素を受理し、1〜8個を左から代入すると予測。数値は符号・小数・E/D指数を受理すると弱く予測。基数表記は予測なし。文字列は引用符を除去し、引用符内のコンマと空白を保持、非引用の両端空白は除去と弱く予測。RETURNだけは数値0・空文字と弱く予測し、初期値12/seedの保持と区別する。

不足時は追加要求、余剰・型違いは再入力を弱く予測する。余剰を無視して正常終了する可能性も独立に判定する。桁あふれの再入力とERR6は予測なし。LINE INPUTの数値変数はERR13、区切り/変数欠落はERR2、直接モードはERR12と弱く予測。長さ上限255は仮説。79/80/81、127/128/129、254/255/256/260の固定点でINPUT/LINE INPUT両方を試す。打鍵は長行許可モードと十分なフレームを使い、LENが短いだけで言語上限と断定しない。

すべての変数を入力前に12またはseedで初期化する。値は既存段と同じ自作ラベル付き整数結果行だけを抽出する（生画面行は出力しない）。数値はFIX、1.25だけ100倍。1e100の桁あふれ腕だけは指数表示の数値を画面から採らず、SGN、絶対値が32768を超えるかの0/1、範囲内ならFIX値（範囲外は作業印0）を採る。符号と範囲フラグで「巨大な値を受理」と「再入力/ERR」を区別し、巨大値の正確な仮数は測らない。文字列はLEN、先頭/末尾ASC（空は器具の空白32）、全文字ASCの和を記録する。和は末尾に器具用空白を1個足して全長+1回ループし、最後に32を引くため、空文字でもASCへ空部分文字列を渡さず、FORの空範囲仕様に依存しない。この組は一般の文字列に対して一意ではないので、任意の本文を復元・断定しない。固定した短い入力での仮説比較、長い同一文字入力の長さ判定に使う。ERR、誤り件数、終了印も必須。INPUT完了直後に自作継続印を出し、その位置の署名で改行の有無を分離する。INPUT待機中の内部変数領域は調べない。再入力途中の一時的な部分代入は今回の器具では不明、完了または捕捉エラー後の全変数の値だけを判定する。

## 要求確認と画面比較

腕ごと独立起動・独立作業先、2走以上。最大3腕を別プロセスで同時進行するが、各腕の操作・入力・採取フレームは同じ固定値であり壁時計時間を判定に使わない。打鍵は小文字。固定入力列は最大2回、勝手な入力の追加や待機時間延長はしない。入力前に、現在までの操作を別起動で再現し、300フレーム離れた2枚が一致、入力直前の自作到達印が存在、終了印なしを確認する。プログラムがINPUT直前に到達したことと安定した要求状態を確認してから、同じ操作列を再現して固定3000フレーム待ち後に入力を送る。ライブ停止再開ではなく前段再現方式である。再現自体が2走一致しない場合は採用しない。未対応構文等がすでに捕捉エラーで完了した場合、余分な入力は送らない。直接モードのエラーはハンドラから診断へGOTOし、受理した腕だけ固定入力後にGOTOで診断する。診断の文字列を入力値として使わない。

画面比較対象は0〜13行、各80桁、行座標と空白を保存した署名（行数14、文字数1120、SHA-256）。入力直前の到達印は14行、結果行は15行以降に置き比較から除く。属性は対象外。同じROMで独立したCLS/PRINT/待機ループを2走し（各走2時点一致）、同一操作の較正済み署名を同じ測定内で再利用する。PRINT対照は候補ごとに独立起動して2走し、各走2時点一致と14行の自作到達印を要求する。先行候補のGOTO待機中に後続NEW/RUNを打鍵する方式は後続が実行されないため廃止する。長い固定PRINT文字列は24文字ごとのPRINTへ分割し、最後だけ予定の改行を出す。大文字候補はCHR$で作り、小文字打鍵と分離する。候補として、接尾候補4種類（疑問符+空白、疑問符のみ、空白のみ、なし）、再入力候補、追加要求候補を比較する。候補は器具作者が事前作成した入力文字列であって画面からの転記ではない。全入力腕にも同じ接尾候補を用意する。出力は署名、行ごとの文字数・非空白セル数、入力文字の変化セル数、候補ID、一致/不一致だけ。候補ゼロ一致は不明として残し、関門を緩めず本文を調査しない。PRINT候補の署名そのものを別ROMへ期待値として強制せず、同じROM内の一致分類をcheckする。

## 関門と自己検査

全結果キー各1個、整数だけ、ERR 0〜255、非負誤り件数、終了印1個、要求確認、2走観測完全一致。較正腕cal-num/cal-errorは公式でも必須であり免除コマンドを設けない。要求/完了不明、固定入力列で完了しない腕は欠測としてgate_failed、言語仕様の負例としない。

追加関門（公式未実行の第1回・追加修正その2）: 従来関門（診断印の形・終了印・各段の2時点一致・要求印・独立した2走一致・較正）と、画面比較限定の関門を分離する。候補署名の相異・入力文字セルの2関門は、画面比較欄だけを「比較不能」にする。値印・ERR番号・誤り件数・終了印・入力回数は従来関門を通れば有効のまま保持し、期待値の生成・照合に使う。入力前にERRで終了した腕も、ERR等を捨てない。予測の一致は測定の関門にしない。

画面比較はvalid（有効）/incomparable（比較不能）/excluded（対象外）の3状態を保存する。有効な比較には、同じ腕・同じ段で比較に残した全候補の署名の相異を要求し、一致候補は0個（候補外・不明）または1個になる。重複が1組でもあれば画面比較のみ比較不能。未入力（段0）のみ、末尾空白が未使用空白セルと同じになる既知の等価組「q-space/q」「space/none」を事前除外し、q-spaceとspaceを代表として残す。ほかの組を観測に合わせて自動除外しない。

入力列がある腕の有効な画面比較には、実際に送った入力文字（空白を除く）の少なくとも1セルが比較範囲0〜13行に含まれ、直前段の同座標からその文字へ変化したことを要求する。各入力後に該当変化セル数を記録し、全入力段の合計1以上かつ入力回数1以上を要求する。診断行15行以降や要求記号だけでは通さない。ERRで入力まで到達しない腕では画面のみ比較不能にし、ERR・初期値の値印・誤り件数・入力回数0は有効に残す。

空入力のnumber-empty・string-empty・line-emptyは、今回カーソル位置を使わず、画面比較全体を事前登録で対象外にする。区別できない候補組は「q-space/q」「space/none」（入力文字がなく末尾空白の差をセル本文署名で識別できない）。この3腕は観測によらず対象外。較正・構文エラーなど画面候補計画のない腕も対象外とし、line-numericは候補計画ありとして判定する。対象外でも数値診断を照合する。

checkは各欄の期待値側の有効性に従う。値印・ERR・誤り件数・終了印・入力回数は有効な期待値と必ず照合し、測定の関門落ち・欠落はNG。期待値で有効な画面比較欄が測定側で比較不能・対象外・欠落ならNG。期待値が比較不能・対象外なら画面欄だけを照合せず、ほかの欄は照合する。有効な画面分類は同じROM内のPRINT候補一致で比較し、ROM間で生署名を比較しない。候補ゼロ一致は候補外の有効分類であり、比較不能と区別する。

自己検査には候補同一化と範囲ずらしの陽性/陰性対照を含める。陰性でも従来関門は通り、画面のみ比較不能になることを確認する。期待値で有効な画面を測定側で比較不能・欠落にしたTSVはcheckでNG（rc≠0）。期待値の比較不能画面は照合されないこと、その場合も値印の誤りがNGになること、空入力の対象外を確認する。本文は出力しない。

measure実行の毎回冒頭に合成自己検査を埋め込む。陽性、陰性（非整数/重複/欠落/不正署名/不安定/要求欠落/較正不一致/2走差/反復番号重複/関門落ち）、本文漏洩検査、従来関門を壊したTSVからの期待値生成拒否、画面のみ比較不能なTSVの期待値採用、合成expected/checkを確認する。selftestでは現行srcの自作ROMをビルドし全腕2走する。値の予測一致は自作試走の関門にしない。生VRAMは成功・失敗ともfinallyで消し、プロセス出力は捕捉し固定エラーに置換する。保存対象は数値・署名・候補ID・関門判定（TSVと中断再開用JSON）だけ。腕ごとに独立2走の結果を原子的に保存し、中断再開時には器具署名・自作ROM署名・固定腕・従来関門・2走一致を確認した保存結果だけを再利用する。公式未実行のため本追補は事前登録の範囲。

## 第2回

親の指示でのみ公式を実行する。公式ROMは `PC88_REF_ROM_DIR` からのみ受け取る。ディスク命令を使わないので `PC88_REF_DISK_DIR` / `PC88_REF_DISKB` は未使用（公式ディスクの書込みや閲覧はしない）。全腕の従来関門通過を要求し、落ちた腕は事前登録追補を確定してから再測定する。画面限定の比較不能・対象外は数値欄の期待値採用を妨げない。第1回では公式期待値TSVを作らない。

```sh
W="$PWD/tmp/s9z-work"
# 第2回は公式禁止ガードを親が解除した器具でのみ実行
python3 "$W/l4_input_measure.py" measure --official --work-dir "$W/ref" --out "$W/ref.tsv"
python3 "$W/l4_input_measure.py" expected --out tests/conformance/expected_l4_input.tsv "$W/ref.tsv"
# conformは改訂器具を呼ぶ版を親が採用する
# 測定済み自作を直接照合する場合
python3 "$W/l4_input_measure.py" check --expected tests/conformance/expected_l4_input.tsv --measured "$W/repair2-rerun/selfrun.tsv"
```

測らないもの: STOP/CTRL-C、ファイルINPUT、INPUT#、編集キー、国際文字、ROM内部配置、速度、再入力待機中の内部変数、格子間の厳密境界。src実装や仕様確定は第2回以降。

## 固定腕一覧

完全な操作列は器具program/base_plan、入力列はarmsで固定しTSVへ保存する。以下は器具describeと同じ事前入力と予測。これは観測画面の転記ではない。

- `cal-num`: `a=0:b=-32768:c=32767` 入力=[] 予測=0,-32768,32767
- `cal-error`: `error 13` 入力=[] 予測=ERR13、初期値12
- `prompt-semi`: `input "ab";a` 入力=["1"] 予測=semiは接尾?と空白、commaは接尾なし、plainは?と空白。nonewlineは改行抑止
- `prompt-comma`: `input "ab",a` 入力=["1"] 予測=semiは接尾?と空白、commaは接尾なし、plainは?と空白。nonewlineは改行抑止
- `prompt-plain`: `input a` 入力=["1"] 予測=semiは接尾?と空白、commaは接尾なし、plainは?と空白。nonewlineは改行抑止
- `prompt-nonewline`: `input; a` 入力=["1"] 予測=semiは接尾?と空白、commaは接尾なし、plainは?と空白。nonewlineは改行抑止
- `count-1`: `input a` 入力=["1"] 予測=左から1..1
- `count-2`: `input a,b` 入力=["1,2"] 予測=左から1..2
- `count-3`: `input a,b,c` 入力=["1,2,3"] 予測=左から1..3
- `count-4`: `input a,b,c,d` 入力=["1,2,3,4"] 予測=左から1..4
- `count-5`: `input a,b,c,d,f` 入力=["1,2,3,4,5"] 予測=左から1..5
- `count-6`: `input a,b,c,d,f,g` 入力=["1,2,3,4,5,6"] 予測=左から1..6
- `count-7`: `input a,b,c,d,f,g,h` 入力=["1,2,3,4,5,6,7"] 予測=左から1..7
- `count-8`: `input a,b,c,d,f,g,h,j` 入力=["1,2,3,4,5,6,7,8"] 予測=左から1..8
- `type-default`: `input a` 入力=["23"] 予測=文字列xyz、数値23
- `type-int`: `input a%` 入力=["23"] 予測=文字列xyz、数値23
- `type-single`: `input a!` 入力=["23"] 予測=文字列xyz、数値23
- `type-double`: `input a#` 入力=["23"] 予測=文字列xyz、数値23
- `type-string`: `input a$` 入力=["xyz"] 予測=文字列xyz、数値23
- `type-array`: `input a%(1)` 入力=["23"] 予測=文字列xyz、数値23
- `type-mixed`: `input a%,b!,c#,d$,a%(1)` 入力=["1,2,3,xy,4"] 予測=型別に1,2,3,xy,4
- `number-sign`: `input a` 入力=["-12"] 予測=数値変換。空入力は0と弱く予測、基数表記は予測なし
- `number-plus`: `input a` 入力=["+12"] 予測=数値変換。空入力は0と弱く予測、基数表記は予測なし
- `number-decimal`: `input a` 入力=["1.25"] 予測=数値変換。空入力は0と弱く予測、基数表記は予測なし
- `number-exp`: `input a` 入力=["1e2"] 予測=数値変換。空入力は0と弱く予測、基数表記は予測なし
- `number-dexp`: `input a` 入力=["1d2"] 予測=数値変換。空入力は0と弱く予測、基数表記は予測なし
- `number-hex`: `input a` 入力=["&h10"] 予測=数値変換。空入力は0と弱く予測、基数表記は予測なし
- `number-oct`: `input a` 入力=["&o10"] 予測=数値変換。空入力は0と弱く予測、基数表記は予測なし
- `number-spaces`: `input a` 入力=["  12  "] 予測=数値変換。空入力は0と弱く予測、基数表記は予測なし
- `number-empty`: `input a` 入力=[""] 予測=数値変換。空入力は0と弱く予測、基数表記は予測なし
- `string-bare`: `input a$` 入力=["xy"] 予測=引用符を除去、引用符内コンマ/空白保持。非引用空白は除去、空は空文字と弱く予測
- `string-quoted`: `input a$` 入力=["\"xy\""] 予測=引用符を除去、引用符内コンマ/空白保持。非引用空白は除去、空は空文字と弱く予測
- `string-comma`: `input a$` 入力=["\"x,y\""] 予測=引用符を除去、引用符内コンマ/空白保持。非引用空白は除去、空は空文字と弱く予測
- `string-spaces`: `input a$` 入力=["  xy  "] 予測=引用符を除去、引用符内コンマ/空白保持。非引用空白は除去、空は空文字と弱く予測
- `string-quoted-spaces`: `input a$` 入力=["\" xy \""] 予測=引用符を除去、引用符内コンマ/空白保持。非引用空白は除去、空は空文字と弱く予測
- `string-empty`: `input a$` 入力=[""] 予測=引用符を除去、引用符内コンマ/空白保持。非引用空白は除去、空は空文字と弱く予測
- `retry-short`: `input a,b` 入力=["1", "2"] 予測=shortは追加要求、excess/型違いは再入力、桁あふれは再入力またはERR6（予測なし）。完了後全変数を取得
- `retry-excess`: `input a,b` 入力=["1,2,3", "4,5"] 予測=shortは追加要求、excess/型違いは再入力、桁あふれは再入力またはERR6（予測なし）。完了後全変数を取得
- `retry-bad-first`: `input a,b` 入力=["x,2", "4,5"] 予測=shortは追加要求、excess/型違いは再入力、桁あふれは再入力またはERR6（予測なし）。完了後全変数を取得
- `retry-bad-last`: `input a,b` 入力=["1,x", "4,5"] 予測=shortは追加要求、excess/型違いは再入力、桁あふれは再入力またはERR6（予測なし）。完了後全変数を取得
- `retry-overflow`: `input a` 入力=["1e100", "4"] 予測=shortは追加要求、excess/型違いは再入力、桁あふれは再入力またはERR6（予測なし）。完了後全変数を取得
- `retry-int-overflow`: `input a%` 入力=["32768", "4"] 予測=shortは追加要求、excess/型違いは再入力、桁あふれは再入力またはERR6（予測なし）。完了後全変数を取得
- `line-semi`: `line input "ab";a$` 入力=[" x,\"y\"  "] 予測=コンマ・引用符・両端空白を保持、semiは接尾なし、nonewlineは改行抑止
- `line-plain`: `line input a$` 入力=[" x,\"y\"  "] 予測=コンマ・引用符・両端空白を保持、semiは接尾なし、nonewlineは改行抑止
- `line-nonewline`: `line input; a$` 入力=[" x,\"y\"  "] 予測=コンマ・引用符・両端空白を保持、semiは接尾なし、nonewlineは改行抑止
- `line-empty`: `line input a$` 入力=[""] 予測=空文字
- `line-numeric`: `line input a` 入力=[] 予測=ERR13と弱く予測
- `syntax-input-separator`: `input "ab" a` 入力=[] 予測=ERR2と予測
- `syntax-input-missing`: `input` 入力=[] 予測=ERR2と予測
- `syntax-input-variable`: `input "ab";` 入力=[] 予測=ERR2と予測
- `syntax-line-separator`: `line input "ab" a$` 入力=[] 予測=ERR2と予測
- `syntax-line-missing`: `line input` 入力=[] 予測=ERR2と予測
- `syntax-line-variable`: `line input "ab";` 入力=[] 予測=ERR2と予測
- `direct-input`: `input a` 入力=["7"] 予測=ERR12と弱く予測、受理なら値も取得
- `direct-line`: `line input a$` 入力=["7"] 予測=ERR12と弱く予測、受理なら値も取得
- `length-input-79`: `input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-line-79`: `line input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-input-80`: `input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-line-80`: `line input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-input-81`: `input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-line-81`: `line input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-input-127`: `input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-line-127`: `line input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-input-128`: `input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-line-128`: `line input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-input-129`: `input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-line-129`: `line input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-input-254`: `input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-line-254`: `line input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-input-255`: `input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-line-255`: `line input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-input-256`: `input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-line-256`: `line input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-input-260`: `input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
- `length-line-260`: `line input a$` 入力=["xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"] 予測=上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離
