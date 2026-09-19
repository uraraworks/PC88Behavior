# 事前登録: l4-c8 — 超越関数(SIN/COS/TAN/ATN/EXP/LOG/SQR)単精度適合の場面固定

記録日: 2026-09-20
状態: 事前登録、測定・実装前。SIN/COS/TAN/ATN/EXP/LOG/SQRの実装より
**先に**入れる場面（CLAUDE.md「測定コミットが実装コミットに先行する」）。
ただしSQRだけは既に拡張ROMバンク0に実装済み(`a3fb09e`)であり、本場面の
測定が実装に先行していない唯一の例外である(「順序の逸脱」節参照)。

## 位置づけ

l4-s6a(数値関数の初期測定)・l4-s6g(候補M9=超越関数内部の単精度演算を
すべてround-half-awayにする案、35腕)・l4-s6h(ATN/EXP/LOGを腕数を
増やして再測定、42腕)で、SIN/COS/TAN/ATN/EXP/LOGの内部単精度演算は
いずれもround-half-away丸め(候補M9)で確定した
(`docs/spec/l4-program.md`第4.16a節・第4.16b節、`docs/spec/l4-basic.md`
第5.3a節に反映済み)。本ノートは、l4-c3/l4-c5/l4-c7と同じ作法で、この
確定結果を`tools/conform_l4.sh`の適合の場面(TRANS場面)として追加する
ための事前登録である。次の空き番号`l4-c8`を採る。

**公式側の期待値を実装より先に固定し、自作main ROM側はSIN/COS/TAN/
ATN/EXP/LOGの6群を`not_implemented_yet`から始める**(l4-c3・l4-c7と
同じ順序)。SQR群だけは既に実装済み(後述)のため`implemented`で始まり、
本場面の測定と同じコミットで自作側の照合も行う。

## 比べるもの・記録する内容・期待値ファイルの書式

`l4-c3`「比べるもの」「記録する内容」節の定義をそのまま引き継ぐ
(`tools/l4_print_conform_record.py`を無改変で使う。出力行の非空白
セル列の(相対行,列0,文字コード)の並び・`Ok`行の相対行のみを見る。
値そのもの・SHA-256以外は一切コミットしない)。

期待値ファイル: `tests/conformance/expected_l4_trans.tsv`。書式は
`l4-c3`・`l4-c7`と同一:
```
arm<TAB>cell_count<TAB>ok_relative_row<TAB>sha256
```
見出しコメント`# group <NAME> selfmade=<status>`を関数ごとに7本置く
(`sin`/`cos`/`tan`/`atn`/`exp`/`log`/`sqr`)。l4-c3のFS/FDと同じ、群
ごとの実装状態管理(`tools/conform_l4.sh`の`trans_group_status()`/
`trans_arm_group()`が読む)。

## 腕(59腕、7群)

腕・打鍵文字列・フレーム値は、いずれも既存の測定ノートの表と完全に
同一(打鍵文字列・フレーム値とも変更しない)。腕idだけ、関数名接頭辞+
通し番号(`SIN1`〜`SQR4`)へ付け替えた(元のZ/H/S番号のままでは
`trans_arm_group()`が接頭辞で群を判定できないため)。

- **SIN群(5腕、SIN1〜SIN5)・COS群(5腕、COS1〜COS5)・TAN群(5腕、
  TAN1〜TAN5)**: `docs/notes/l4-s6g-away-rounding-transcendentals-
  preregistration.md`「(ii)本命判定」表のZ01〜Z15と完全に同一。
  l4-s6gの結果で35腕中15腕(100%)がM9(away)と完全一致し、確定の
  直接根拠になった腕。
- **ATN群(12腕、ATN1〜ATN12)**: `docs/notes/l4-s6h-atn-exp-log-more-
  arms-preregistration.md`「腕」節のH03〜H14と完全に同一。**H01
  (`atn(1)`)・H02(`atn(-1)`)は除外する**(下記「除外」節)。
- **EXP群(14腕、EXP1〜EXP14)**: 同ノートのH15〜H28と完全に同一。
- **LOG群(14腕、LOG1〜LOG14)**: 同ノートのH29〜H42と完全に同一。
- **SQR群(4腕、SQR1〜SQR4)**: `docs/notes/l4-s6a-transcendental-
  functions-preregistration.md`「腕」節のS1〜S4と完全に同一
  (`print sqr(...)`、CDBLは使わない。l4-s6aで`predicted_match`が
  確認済みの単精度4腕)。**S5・S7は除外する**(下記「除外」節)。

腕idと式・写し(後)・走行フレームの対応は`tools/conform_l4.sh`の
`trans_arm_params()`に埋め込んだ(l4-s6g/l4-s6h/l4-s6aの表の
`line_end=700+8*打鍵文字数(\n込み)`・`dump=line_end+20`・
`run=dump+200`で既に導出済みの値をそのまま使い、再計算し直さない。
l4-c7のARITH場面と同じ方針)。写し(前)は全腕690固定。

## 除外

- **ATN(1)・ATN(-1)(H01・H02)**: `docs/notes/l4-s6h-atn-exp-log-more-
  arms-results.md`が記録済みの未解決の既知差。`|x|=1`ちょうどの
  分岐境界(`$ATAN`の`need_pi2`判定、`CMP AH,LOW 201`/`JB`)で、GW-BASIC
  ソース再読・分岐条件を変えた候補の両方を試しても解決せず、
  `docs/spec/l4-program.md`第8節に未解決のまま残っている。本場面の
  期待値には含めない(実装後もこの2値は既知の1ULP差として扱う)。
- **倍精度引数の腕(SQR(2#)等、l4-s6aのS5)**: `docs/notes/l4-s6a-
  transcendental-functions-results.md`「種類1」が記録済みの既知差
  (超越関数は`#`サフィックスの倍精度引数に対し倍精度のまま計算して
  倍精度で返す。実装は単精度前提のため、この経路は別途の設計課題として
  本場面の対象外とする)。同じ理由でS7(`sqr(-1)`、エラー系)も除外する
  (数値出力ではなくエラー表示のため、本場面の記録方式(数値セルの
  SHA-256)にそぐわない)。

## SQR群の実装順序の逸脱(隠さず記録する)

SQRは`src/l4_basic/mbf_single.asm`の拡張ROMバンク0に、本場面(l4-c8)の
公式側期待値固定より**先に**実装済みである(`a3fb09e`「SQR(第4.16b節)
を拡張ROMバンク0に実装。単精度、常駐倍精度演算でニュートン法」)。
これはCLAUDE.md「測定コミットが実装コミットに先行する」の原則に対する
**明確な順序の逸脱**であり、本ノートに隠さず記録する。

`a3fb09e`時点での検証根拠は、GW-BASICのSQR実装(ニュートン法反復)を
モデルにした予測器(`tools/l4_mbf_oracle_v3.py`のsqr_impl)との**バイト
照合**であり、コミットメッセージ・関連ノートによれば1900件(倍精度
定数読み取りを含む広い入力域)を故障注入つきで不一致0を確認済みだった
(公式ROMへの直接照合ではなく、予測器という「白箱」との一致)。本場面は、
その予測器の前提そのものを公式ROMの実機出力と初めて直接照合する
機会になる。SQR1〜SQR4の4腕について、公式側の期待値固定に加え、
自作main ROM側(`selfmade=implemented`)の実際の照合も同じコミットで
行い、予測器照合で見えていなかった食い違いが無いかを確認する。

## 測定方法・関門

l4-s6a/l4-s6g/l4-s6h以来と同一の条件・器具(公式ROM一式、ディスク無し、
コア既定N88 V2、起動settleは`--type-at 300 --type '\n'`、実打鍵は
`--type-at 700`、1文字あたり8フレーム/文字)。判定名は`l4-c7`と同一の
4つ(`conform`/`not_conform`/`gate_failed`/`not_implemented_yet`)。
関門は`l4-c7`のG1〜G5・G8と同一。

## 検出力の自己検査(`tools/conform_l4.sh`が常に実行する。公式環境不要)

`l4-c7`分の自己検査a〜dと同じ構造(合成VRAM写しでSHA-256の検出力・
期待値の件数/SHA-256改変の検出を確認)をTRANS場面用に追加する。群の
印切り替え自己検査eも同様に追加する(対象群は`sin`、`SIN1`腕を使う。
`sqr`は既にimplementedで走り続けているため、切り替えの自己検査には
使わない)。

## 判定後の行き先

- 公式側の期待値59腕すべてが固定できたら(G1〜G4・G8を満たし、各腕2走
  の記録が一致)、`tests/conformance/expected_l4_trans.tsv`を、SIN/COS/
  TAN/ATN/EXP/LOG=`not_implemented_yet`・SQR=`implemented`の状態で
  コミットする。
- SQR群は同じコミットで自作側の照合も行い、結果ノートに記録する
  (conform/not_conformいずれであっても隠さず記録する)。
- SIN/COS/TAN/ATN/EXP/LOGの実装(`src/l4_basic`への追加、拡張ROMバンク
  の空き容量次第で分割实装もありうる)は、本コミットより後の別コミット
  で行う。実装後、群の印を`implemented`へ切り替えて自作側の照合を行う
  (l4-c3・l4-c7と同じ運用)。
- 既存の適合(`l4-c1b`〜`l4-c7`・`tools/l4_basic_selftest.sh`・
  `tools/l3_main_selftest.sh`・`tools/ext_bank_selftest.sh`)が壊れて
  いないことも合わせて確認する。

## 結果ノート

`docs/notes/l4-c8-transcendental-conformance-scene-results.md`に書く。
関門・判定名・腕は本ノートから動かさない。

## 根拠リンク

`docs/notes/l4-s6a-transcendental-functions-preregistration.md`・
`docs/notes/l4-s6a-transcendental-functions-results.md`(SQR腕の原型・
predicted_match確認)・`docs/notes/l4-s6g-away-rounding-transcendentals-
preregistration.md`・`docs/notes/l4-s6g-away-rounding-transcendentals-
results.md`(SIN/COS/TAN腕の原型・away丸め確定)・`docs/notes/l4-s6h-
atn-exp-log-more-arms-preregistration.md`・`docs/notes/l4-s6h-atn-exp-
log-more-arms-results.md`(ATN/EXP/LOG腕の原型・away丸め確定・
atn(±1)未解決の記録)・`docs/notes/l4-c7-integer-arithmetic-rounding-
conformance-preregistration.md`(場面の作法の直接の原型)・
`tools/conform_l4.sh`(既存の適合テストランナー)・`docs/spec/l4-
program.md`第4.16a節・第4.16b節・第8節(丸め規則の確定根拠・未解決差の
記録)。
