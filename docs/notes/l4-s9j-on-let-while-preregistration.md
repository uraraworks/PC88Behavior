# l4-s9j — ON 式 GOTO/GOSUB・LET・WHILE/WEND の事前登録

状態: **測定前**（2026-10-05）。公式ROMはこの作業では実行しない。
本登録は器具とともに公式測定より先に固定する。候補の追加、観測後の予測変更、
予測なしの腕に予測を与えることは、追補の事前登録を要する。

## 資料と候補

規律は `CLAUDE.md`、器具の手本は `tools/l4_editinv_measure.py`。
`docs/notes/l4-s9g-addendum1-rejudge.md` と
`docs/notes/contamination-2026-10-05-print-using-empty-format.md` の教訓を適用する。
既存仕様は `docs/spec/l4-program.md`・`l4-basic.md` のGOSUB/RETURN、FOR/NEXT、
誤り番号の一致箇所だけをrgで確認した。丸ごとの読み込みはしていない。

公開GW-BASICソースは `rg -a -n` で入口を探し、次の範囲を読んだ。
検索の0件を機能不存在の根拠にしない。コードは転載しない。

| ファイル（`../refs/GW-BASIC/` 配下） | 読んだ行範囲 | 手順の散文要約 |
|---|---|---|
| GWMAIN.ASM | 2267–2425、2440–2510 | LETは変数または配列要素を求め、等号と右辺を読み、代入先の型へ変換して格納する。暗黙代入と同じ入口を使う。ONは式の値をバイト範囲へ変換し、GOTOかGOSUBを識別して、選択位置まで列挙した行番号を読み飛ばす。選択位置に到達したら通常の分岐入口へ進み、列挙の終端まで選択されなければ次の文へ進む。読んだ範囲の割り込み系ONとRESUMEは本段の仕様化には用いない。 |
| GWEVAL.ASM | 1595–1640 | 式を整数へ変換した後、上位部分が0でなければ範囲の誤りに進む。整数変換そのものの丸めと大きい値の変換はこの範囲だけでは決めない。 |
| FIVEO.ASM | 39–167 | WHILEはまず対応するWENDを探す。同じWENDに対応する既存の状態があればそこまで取り除き、条件を評価する。0ならWENDの後へ、非0なら本体へ進む。WENDでは保存した条件位置に戻して再評価する。探索時にはFORの状態を読み飛ばす。対応がなければ誤りとなる。 |
| GWMAIN.ASM | 3415–3505 | 対応するWENDの探索は入れ子を数え、引用符内の文字とREM・DATAを読み飛ばす。プログラム終端まで対応がなければ、条件の評価や本体の実行より前に誤りとなる。 |

候補 **G_GW** は上記の手順と既存仕様の誤り番号対応を組み合わせた候補であり、
PC88の観測結果ではない。誤り番号は範囲5、型13、存在しない行8、構文2、
WHILEなしのWEND30、WENDなしのWHILE29を予測する。番号の割り当ては
GWの番号をそのまま採用したものではなく既存 `l4-basic.md` の表による。
ONの非整数と大きい値、LETの整数型への2.6の変換は **予測なし**。
丸めの小候補は今回追加しない。真偽値は数値の符号判定（0のみ偽）を予測する。

## 腕の一覧と値の予測

器具の `arms()` に本体88腕、`controls()` に対照12腕を固定する。
全腕は独立した起動で **2走**。`predict` が腕ID・打鍵列・値までの予測をTSVに固定する。
印は短い独立行で、自作PRINTの整数のみを取り出す。正数の先頭空白を許容する。
以下の値列は `s9jv 1 値` の順序。捕捉誤りは `s9je 1 ERR p`。

| ID群（各接尾辞が1腕） | 数・内容 | G_GWの値または誤り予測 |
|---|---|---|
| `on-goto-` / `on-gosub-` + `one,two,three,zero,beyond` | 各5腕。k=3、選択値1,2,3,0,4 | GOTOは1/2/3/0/0。GOSUBは1,0 / 2,0 / 3,0 / 0 / 0（0は次の文）。 |
| 同 + `negative,byte-over,string` | 各3腕。-1、256、文字列 | ERR 5/5/13、p=1。本体・次文の値なし。 |
| 同 + `large,f14,f15,f25,fm05,f05` | 各6腕。1000000000、1.4、1.5、2.5、-0.5、0.5 | 予測なし。分岐の印・ERR・次文を採る。 |
| 同 + `expr` | 各1腕。a=1、a+1 | GOTOは2、GOSUBは2,0。 |
| 同 + `unselected-missing` | 各1腕。1を選択、100,777、後ろにコロン文 | GOTOは1、GOSUBは1,8,9。存在しない未選択行は誤りなし。 |
| 同 + `selected-missing` | 各1腕。2を選択、100,777 | ERR 8、p=1。 |
| 同 + `duplicate` | 各1腕。2を選択、100,100,100 | GOTOは1、GOSUBは1,8,9。 |
| 同 + `single, single-zero-colon, single-over, colon-return` | 各4腕。k=1、選択1/0/2/1、コロンなし/あり/なし/あり | GOTOは1 / 8,9 / 9 / 1。GOSUBは1,9 / 8,9 / 9 / 1,8,9。RETURNの同じ行のコロン文への復帰を分離する。 |
| `let-{program,direct}-{number,string,array,integer}-{let,plain}` | 16腕。a=1、a$="x"、b(2)=3、a%=2.6、LETありとなし | 1、len(a$)=1、b(2)=3。整数型4腕は予測なし。文字列の中身は採らず長さで確認。 |
| `let-{program,direct}-bad-{empty,equals,missing-equals,type}` | 8腕。let、let =1、let a、let a="x" | ERR 2/2/2/13。プログラムはp=1で捕捉、直接モードは番号包含で採る。 |
| `while-normal,false,false-nested,false-rem,false-string` | 5腕。通常3回、初回偽、偽本体の入れ子/REM/文字列 | 通常1,2,3、ほか7だけ。本体の99は出ない。 |
| `while-nested,for-outer,while-outer` | 3腕。WHILEの入れ子、FORの中にWHILE、WHILEの中にFOR | 1,2,11,12 / 11,12,21,22 / 1,2,11,12。 |
| `while-reenter` | 1腕。GOTOで外へ出て同じWHILEへ再入場 | 1,2,7。 |
| `while-orphan-wend,missing-true,missing-false,string` | 4腕。対応なし、WENDなし（真/偽）、文字列条件 | ERR 30/29/29/13、全てp=1。後続のp=2と99には到達しない。 |
| `while-one-line` | 1腕。コロン区切りのWHILE/WEND | 1,2,3,7。 |
| `while-condition-{neg,one,two,half,neg-half,zero}` | 6腕。-1、1、2、0.5、-0.5、0 | 非0は1,7、0は7。本体で条件変数を0にして有限で終わる。 |

ON44腕、LET24腕、WHILE20腕。本体の予測あり72腕、予測なし16腕。
対照は `control-values`（17,-1）、`control-goto`（7）、`control-gosub`（7,8）、
`control-for`（3）、`control-if`（9）、`control-trap`（ERR5,p=4）、
`control-direct-{5,8,17}`、`control-program-{1,3,5}`。
最後の6腕はON ERRORで捕捉せず、probe-entry方式で誤り番号の包含を確認する。
自己検査の自作ROMでは対照12腕とLETなしの既知値6腕だけを走らせる。
ON式、明示LET、WHILEの未実装機能を対照に含めない。

## 採取・関門・照合

- 各腕でNEWとプログラム投入、CLS、準備印 `s9jp 1 1` の採取、CLS、
  操作印 `s9jo 1 1` の採取、CLS、RUN（LET直接腕と直接対照は直接実行）、
  終端印 `s9jz 1 1` の順。結果の先頭印は `s9jb 1 1`。
  誤りの前に代入したpとERRをPRINTし、誤りの発生時点を本体実行と区別する。
- 打鍵は小文字ASCII、改行を除き1行80文字未満、@なし。
  直接実行の文を数字で始めない。準備がカーソル位置を動かすため、位置の
  決め打ちで誤りを読まずprobe-entryの番号包含を使う。
- 画面本文、印のあいだの未知の中身、フロントエンドstdout/stderrは出力しない。
  記録は自作PRINT印と整数、番号包含とexactの真偽、その他の行の件数のみ。
  不完全な印はinvalid扱い。診断でも中身は取り出さず有無・長さ・位置だけに限る。
- **exactは予測比較・期待値比較・2走一致・関門のいずれにも使わない。**
  形式検査では真偽値であることだけを確認し、保存しても判定には用いない。
  手本の追補で残していたexactの2走一致要求も今回の器具では採用しない。
- 2走の採取成功、exactを除いた観測一致、準備・操作印の既知値一致、
  結果先頭印と終端印の一意性・順序、PRINT印の型・整数個数を関門とする。
  対照12腕が欠けず全て既知値に一致することを全体校正の条件とする。
- 関門通過だけは予測一致の合格を意味しない。予測ありは既知値との比較で
  agree/differ、予測なしはunpredicted。checkは予測なし（null）、SKIP、
  観測のみを合格にしない。陰性対照は採取形・校正を通過してdifferへ届くことも確認する。
- VRAM写しは複数枚なら `.f<6桁フレーム>` 付き、1枚なら元の名前。
  採取後は削除する。生の画面写しを成果物にしない。
- rejudgeは保存TSVの腕・走番号・打鍵計画・失敗フラグを検査し、旧判定列を
  信用せず観測から共通emitで再判定する。入力と出力は別ファイル。

器具: `tools/l4_onwhile_measure.py`（predict / measure / check / rejudge / selftest）。
作業置き場の既定は `../tmp/l4s9j-work`。selftestはOS一時ディレクトリで自作ROMを
一時ビルドする。公式パスはmeasureの `--official` と環境変数 `PC88_REF_ROM_DIR`
からのみ受け取り、器具へ焼き込まない。本作業の実行は次だけに限定する。

```sh
bash tools/l4_onwhile_selftest.sh < /dev/null
```

## 今回決めないこと

ON TIME/KEY/STOP等の割り込み系ON、ON COM、CHAIN、行の編集との相互作用
（l4-s9g）、WHILEの深さの上限（メモリ配置の別段）。公式の測定結果・実装・仕様の
確定は本登録の成果物に含めない。src/・tests/を変更せず、run_allは実行せず、
git add・コミットはしない。

## 器具の検証（公式測定ではない）

指定のselftestは **rc=0**。固定予測、取り出しの陽性・陰性、本文非出力、
exactだけの2走差の許容、値・番号違いの比較到達、SKIP・予測なし・観測のみの拒否、
保存TSVの再判定と破損拒否、自作ROMの一時ビルドと既知値対照18腕×2走、
期待値改変拒否を確認した。公式ROMの実行と保存済み公式観測の再判定はしていない。
