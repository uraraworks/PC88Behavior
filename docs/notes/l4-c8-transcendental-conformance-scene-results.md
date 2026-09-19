# l4-c8 — 超越関数(SIN/COS/TAN/ATN/EXP/LOG/SQR)単精度適合の場面固定・結果

実施日: 2026-09-20
事前登録: [l4-c8-transcendental-conformance-scene-
preregistration.md](l4-c8-transcendental-conformance-scene-preregistration.md)
（本ノートと同じコミットに器具(`tools/conform_l4.sh`のTRANS場面追加)
とともに収録）。

## 実施内容

事前登録どおり、公式ROM(`PC88_REF_ROM_DIR`、コマンドごとに環境変数で
付与、`private/rom`)で59腕(SIN1〜5・COS1〜5・TAN1〜5・ATN1〜12・
EXP1〜14・LOG1〜14・SQR1〜4)を各2走(計118走)実施した。写し(前)は
全腕690固定、写し(後)・走行フレームは`docs/notes/l4-s6g-away-
rounding-transcendentals-preregistration.md`・`docs/notes/l4-s6h-atn-
exp-log-more-arms-preregistration.md`・`docs/notes/l4-s6a-
transcendental-functions-preregistration.md`の表の値をそのまま使用
(打鍵文字列は変更していない)。

## 関門

- G1(器具の自己検査): `tools/conform_l4.sh`のTRANS場面用検出力自己
  検査(a〜d・群の印切り替えe)が全てOK
- G2(取りこぼし0・打てない文字の警告0): 59腕×2走=118走全てで打てない
  文字の警告0件
- G3(決定論性): 59腕全てでrun1/run2の記録(cell_count/ok_relative_row/
  sha256)が完全一致
- G4(陰性対照): 既存の陰性対照(何も打たない走)を流用、変化0件
- G8(出力完了の確認): 59腕全てで`ok_relative_row`=2(`Ok`行が出力の
  2行後に現れた)を確認

G1〜G4・G8すべて真。gate_failed腕は無し。

## 期待値の採用

59腕全てでG3(2走一致)を満たし、その記録を`tests/conformance/
expected_l4_trans.tsv`に採用した(値は含めずcell_count/
ok_relative_row/sha256のみ、CLAUDE.md禁止事項4・禁止事項7を遵守。
本ノートの数値はいずれも自分で打った式(`print cdbl(<関数>(<引数>))`
または`print sqr(<引数>)`の引数)の直接の結果であり、画面本文・エラー
表示は含めていない)。見出しコメントは、SIN/COS/TAN/ATN/EXP/LOGの6群
が`# group <NAME> selfmade=not_implemented_yet`、SQR群のみ`# group
sqr selfmade=implemented`(理由は次節)。

再導出(`PC88_REF_ROM_DIR`つきで自分で実行)でも59腕全て`conform`
(自作ROM側と無関係に、公式側の記録自体が再現することを別途確認)。

## SQR群の実装順序の逸脱、およびその確認で見つかった新規の食い違い

事前登録に記載したとおり、SQRは本場面の期待値固定より**先に**
`src/l4_basic`の拡張ROMバンク0に実装済みだった(`a3fb09e`)。この
順序の逸脱を隠さず記録する。

`a3fb09e`時点の検証根拠は、`tools/l4_sqr_bank_selftest.sh`
(`tools/l4_sqr_bank_conform.py`)による**バンクルーチン単体の
バイト照合**(`EXT_BANK0_SQR_ENTRY`をZ80として直接実行し、予測器
`tools/l4_mbf_oracle_v10_m9.py`のsqr_implと突き合わせる。故障注入
つきで不一致0)であり、**BASIC側の呼び出し経路
(`src/l4_basic/interp.asm`の`FTNF_DO_SQR`→`EXT_BANK_CALL`、拡張ROM
バンクの中継)を通してのend-to-end照合ではなかった**
(`tools/l4_basic_selftest.sh`にもSQRの直接モードPRINT実行を含む
検査は無かった)。

本場面は、その呼び出し経路を初めて公式ROMの実機出力と直接照合する
機会になった。結果:

- **公式側の期待値固定(SQR1〜SQR4)は問題なく完了した**(上記のとおり
  59腕全てG1〜G4・G8を満たし、公式ROM側は再導出でも`conform`)。
- **自作main ROM側(`SELF_ROMDIR`、`selfmade=implemented`)の照合は
  SQR1〜SQR4の4腕全てG8(出力完了の確認)で`gate_failed`になった。**
  `tools/conform_l4.sh`が使う走行フレーム(`run=dump+200`、dumpは
  824/824/832/864)では`Ok`行が現れなかった。

切り分けのため、`tools/lib_l3_measure.sh`の`run_q88measure_retry`を
直接呼び、走行フレームを大きく緩めて(最大6000フレーム、通常の
run値の約6倍)`print sqr(2)`を再走行したが、**それでも出力セルの
変化は1件も検出されなかった**(VRAM写しが打鍵前後で完全に同一)。
一方、同じ自作ROM・同じ器具で`print cdbl(1!+1!)`(ARITH場面の腕)は
通常のフレームで正しく差分が検出できており、器具・打鍵経路自体は
健全であることを確認済み。また`src/l4_basic/interp.asm`の`FTNF_
TABLE`(関数名テーブル)・`tokens.asm`のトークン項目には`SQR`が
正しく登録されている(配線自体は存在する)ことも確認した。

以上から、**`FTNF_DO_SQR`から`EXT_BANK_CALL`を経由してバンク0の
`EXT_BANK0_SQR_ENTRY`へ実際に到達する経路のどこかで、直接モード
PRINT経由の呼び出しが完了しない(ハング、または初期画面と区別が
付かない形でのリセットのいずれか)という、`a3fb09e`のバイト照合
(バンクルーチン単体)では見えていなかった新規の食い違いが見つかった。**
これはCLAUDE.md「測定コミットが実装コミットに先行する」原則の逸脱が
まさに顕在化した例であり、隠さず記録する。

**本タスクの範囲(測定・期待値固定のみ、実装はしない)を超えるため、
`FTNF_DO_SQR`/`EXT_BANK_CALL`の修正はここでは行わない。** 群の印は
実態(ソースに実装コードが存在する)に合わせて`selfmade=implemented`
のまま維持し、`gate_failed`という結果をそのまま`expected_l4_trans.tsv`
の外(結果ノート)に記録する。修正は別タスクへ切り出す。

## 自作main ROM側の照合(SIN/COS/TAN/ATN/EXP/LOG、6群)

見出しコメントのとおり6群とも`not_implemented_yet`のため、55腕
(SIN5・COS5・TAN5・ATN12・EXP14・LOG14)は判定外(`na`)表示で`rc`に
含まれない(l4-c3のFS/FDと同じ作法)。実装は本コミットでは行わない。

## 自分で回した rc

- `PC88_REF_ROM_DIR=private/rom bash tools/conform_l4.sh`:
  **rc=1**(公式ROM側は59/59・既存場面も全てconform。自作ROM側の
  SQR1〜4がgate_failedのため全体のrcは1になる。他の場面
  (echo11/print16/float25/program8/arith40)は自作・公式とも全項目
  conform、TRANS場面もSIN〜LOGは判定外・公式側は59/59conform)。
- `bash tools/conform_l4.sh`(公式環境なし、自作ROM側のみ): **rc=1**
  (同じくSQR1〜4のgate_failedが原因。他の全場面は自作側も全項目
  conformのまま)。
- `bash tools/run_all_selftests.sh`: **rc!=0(末尾`NG: 上記のいずれかが
  ロケール不一致または期待rcとの不一致。詳細は表を参照。`)。**
  `tools/conform_l4.sh`単体のNG行に加え、これを内部で呼ぶ
  `l4_basic_selftest`・`ext_bank_selftest`・
  `tools/vsync_regcheck_selftest.sh`(C/UTF-8双方のロケール)もNGに
  なった。**全て同じ根本原因(SQR1〜4のgate_failed)による連鎖であり、
  独立した別の不具合ではない**(`tools/l4_sqr_bank_selftest.sh`は
  この一連の実行中も一貫して`OK`のまま——バンクルーチン単体は健全
  で、interp.asmの呼び出し経路だけが壊れていることの追加根拠)。

## 判定後の行き先

- SIN/COS/TAN/ATN/EXP/LOGの実装(`src/l4_basic`への追加、拡張ROM
  バンクの空き容量次第で分割実装もありうる)は、本コミットより後の
  別コミットで行う。実装後、群の印を`implemented`へ切り替えて自作側
  の照合を行う(l4-c3・l4-c7と同じ運用)。
- SQRの呼び出し経路(`FTNF_DO_SQR`→`EXT_BANK_CALL`)の修正は、本場面が
  見つけた新規の食い違いへの対応として、別タスクへ切り出す
  (`mcp__ccd_session__spawn_task`で提案済み)。

## 生データの扱い

写し(vram.bin)・分類結果・stdout/stderr、および切り分け用の追加測定
(SQRの走行フレームを緩めた再走行)はリポジトリ外の作業ディレクトリ
(scratchpad配下)に置き、本ノートを書いたあと削除する。コミットする
のは本ノートと`tests/conformance/expected_l4_trans.tsv`・
`tools/conform_l4.sh`の変更のみ。
