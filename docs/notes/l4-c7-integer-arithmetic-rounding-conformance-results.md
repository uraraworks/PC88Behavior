# l4-c7 — 整数オペランドのみの四則演算丸め、適合場面固定・結果

実施日: 2026-09-20
事前登録: [l4-c7-integer-arithmetic-rounding-conformance-
preregistration.md](l4-c7-integer-arithmetic-rounding-conformance-preregistration.md)
（本ノートと同じコミットに器具（`tools/conform_l4.sh`のARITH場面追加）
とともに収録）。

## 実施内容

事前登録どおり、公式ROM（`PC88_REF_ROM_DIR`、コマンドごとに環境変数で
付与、`private/rom`）で40腕（K1〜K8・L1〜L8・M1〜M16・N1〜N8）を各2走
（計80走）実施した。写し(前)は全腕690固定、写し(後)・走行フレームは
`docs/notes/l4-s7b-integer-only-rounding-preregistration.md`の表の値を
そのまま使用（打鍵文字列は変更していない）。

## 関門

- G1（器具の自己検査）: `tools/conform_l4.sh`のARITH場面用検出力自己
  検査（a〜d・群の印切り替えe）が全てOK
- G2（取りこぼし0・打てない文字の警告0）: 40腕×2走=80走全てで打てない
  文字の警告0件
- G3（決定論性）: 40腕全てでrun1/run2の記録（cell_count/
  ok_relative_row/sha256）が完全一致
- G4（陰性対照）: 既存の陰性対照（何も打たない走）を流用、変化0件
- G8（出力完了の確認）: 40腕全てで`ok_relative_row`=2（`Ok`行が出力の
  2行後に現れた）を確認

G1〜G4・G8すべて真。gate_failed腕は無し。

## 期待値の採用

40腕全てでG3（2走一致）を満たし、その記録を`tests/conformance/
expected_l4_arith.tsv`に採用した（値は含めずcell_count/
ok_relative_row/sha256のみ、CLAUDE.md禁止事項4・禁止事項7を遵守。
本ノートの数値はいずれも自分で打った式(`print cdbl(...)`の引数)の
直接の結果であり、画面本文・エラー表示は含めていない）。見出し
コメントは`# group arith selfmade=not_implemented_yet`（自作main ROM
側の実装（`src/l4_basic/mbf_single.asm`のawayタイブレークへの変更）
はこのあとの別コミットで行う）。

興味深い性質として、加算腕(K1〜K8)と対応する減算腕(L1〜L8、`A!-
(-B!)`の形で数学的にはK群と同じ`A+B`を計算する)は、cell_count・
sha256とも完全に一致した（K1==L1、K2==L2、…、K8==L8）。これは公式
ROMが両方の式で同じ数値結果を出したことの直接の証拠であり、l4-s7bの
away丸め結論（K/L群はいずれもtie_disc/tie_ctrl/controlで同じ規則が
働く）と整合する。

## 判定後の行き先

`src/l4_basic/mbf_single.asm`のMBF_ADD/MBF_SUB/MBF_MUL/MBF_DIVを
`docs/spec/l4-basic.md`5.3a節に合わせて直したあと、群の印を
`implemented`へ切り替えて自作側の照合を行う（後続コミット）。

## 追記: 実装・自作側照合（後続コミット、同日）

### 実装

`src/l4_basic/mbf_single.asm`:
- `MBF_ADD`（`MBF_SUB`も同経路）の`_add_round`: 真のタイ（guard=0x80・
  sticky=0）を偶数丸めからaway（常に切り上げ）へ変更。桁借り
  (`WK_BORROW`)ありの非タイ場面（sticky!=0）の分岐は変更していない
  （away/evenの違いが影響しない場面のため）。
- `MBF_DIV`は`_add_round`を共有するため、この変更をそのまま継承する
  （DIV専用の変更は加えていない）。
- `MBF_MUL`の既定入口を、粗いROUNS再現(`WK_MUL_ROUNDMODE=0`)から、
  既存の`MBF_MUL_HALFUP`（REP01用に先行実装済みのaway丸め、guardバイト
  のbit7だけで判定——スティッキー無しでも数学的にawayと厳密に同値、
  下位ビット(`MUL_R1`/`MUL_R0`)の破棄が丸め結果に影響しない設計は
  既存コメントの解析どおり）と同じ経路(`WK_MUL_ROUNDMODE=1`)へ切り替えた。
  旧既定(mode=0)の分岐コードは`_mbfmul_body`内に残置（どこからも
  到達しないが、丸め規則の変遷を追える形として削除しなかった）。

`src/l4_basic/interp.asm`: **CDBL関数が未実装だった**ことが本場面の
自作側照合で判明した（`tokens.asm`にトークン項目(0x93)はあったが、
関数名テーブル`FTNF_TABLE`（`FACTOR_TRY_NUM_FUNCS`がIDENT_BUFの文字列
と直接比較する経路）には登録されておらず、`print cdbl(1000000!)`が
`Overflow`、`print cdbl(5!)`が`0`を返していた——l4-s7a/l4-s7b以来
`print cdbl(<式>)`を測定の直接プローブに使ってきたが、自作main ROM側で
実際に呼んだのは本場面が初めてだったため今まで見つからなかった）。
`FTNF_DO_CDBL`を追加し、既存の`VAL_PROMOTE_CUR_TO_DOUBLE`（run.asmの
#変数代入が既に使っている、型を問わず倍精度へ厳密に揃える処理、丸め
不要）をそのまま呼ぶ形にした。二重実装はしていない。

### FIN/FOUTへの影響の確認

`MBF_FOUT`の内部スケーリング（10進の桁合わせで`MBF_MUL`/`MBF_DIV`を
直接CALLしている）は、この変更後も無条件に新しい丸め(away)を使う
（FOUT専用の互換入口は作らなかった）。`tools/conform_l4.sh`の既存
場面（打鍵エコー11腕・直接モードPRINT16腕・浮動小数点PRINT(FS/FD)
25腕・代表プログラム集8腕、いずれも公式ROM実測のSHA-256と照合）が
この変更後も全腕`conform`のままだったため、桁生成(FOUT)専用の互換
入口は不要と判断した。`MBF_FIN`（定数読み取り、REP01）は元々
`MBF_MUL_HALFUP`・`FIN_ACC_TO_SINGLE_AWAY`という別入口でaway丸めを
使っており、本変更の影響を受けない。

`docs/notes/l4-fin-model-search.md`（REP01モデル、57件中55件一致）の
残り2件について、予測器上で確認した所見: REP01は元々「半分は絶対値の
大きい側」（away相当のタイブレーク）を採用済みであり、本タスクの
MBF_ADD/SUB/MUL/DIVのaway化はこの2件を新たに説明しない。同ノートが
既に記録しているとおり、残り2件は正指数側の定数読み取り値そのものの
1ULP差であり、タイ丸め方向(even/away)の問題ではない
（`$FADDS`/`$FSUBS`相当の命令単位実装でも解消しなかったことを同ノートが
確認済み）。規則は変えていない。

### 自作main ROM側の照合

群の印を`# group arith selfmade=implemented`へ切り替え、
`tools/conform_l4.sh`（公式環境不要）で40腕を照合した。40腕全て
`conform`（`not_conform`/`gate_failed`とも0）。加算腕(K1〜K8)・
減算腕(L1〜L8)のtie_disc腕は予測どおり`away`側（切り上げ）の値になった
（`docs/notes/l4-s7b-integer-only-rounding-preregistration.md`の予測表
どおり）。

既存の適合が壊れていないことも確認した:
- `tools/l4_basic_selftest.sh`: rc=0（内部で`tools/l3_main_selftest.sh`・
  `tools/conform_l4.sh`を含む）
- `tools/conform_l4.sh`: rc=0（打鍵エコー11/11・PRINT16/16・
  FLOAT25/25・PROGRAM8/8・ARITH40/40、いずれも`conform`）
- `tools/check_cleanroom.sh`: 全項目OK
- `tools/ext_bank_selftest.sh`: rc=0（拡張ROMバンクから常駐部の
  `MBF_ADD`をCALLする経路も含め全項目OK）

### ROM容量

メインROM(N88.ROM、32768バイト)の末尾埋め草(FILL)からの残りバイト数:
本セッション開始時(コミット`f9ead65`時点)1816バイト→本変更後
1804バイト（away丸めへの変更とCDBL新設を合わせて正味12バイトの消費、
拡張ROMバンクのSIN/COS/TAN実装に向けた余地は十分残っている）。

## 生データの扱い

写し(vram.bin)・分類結果・stdout/stderrはリポジトリ外の作業ディレク
トリ(scratchpad配下)に置き、本ノートを書いたあと削除する。コミット
するのは本ノートと`tests/conformance/expected_l4_arith.tsv`のみ。
