# m7fz: 交換#6経路のドライブビット故障注入・測定結果

実施日: 2026-09-04

## 位置づけ

本稿は[m7fy](m7fy-exchange6-drive-bit-preregistration.md)が事前登録した
合格条件・予測に対する測定である。実装はコミット`06a4523`で既に入っている
（`src/l3_service/make_subrom.py`の`break_exchange6_drive_bit_clear`／
`break_exchange6_drive_bit_set`／`break_exchange6_cylinder`の3フラグ）。
本稿では`src/`・`tools/`を変更していない。事前登録した合格条件・予測・
判定規則は測定後も動かしていない。

段番号は0起点で統一し、種別名を併記する。`tools/compare_l3_entry_fdc.py
--list-all-stages`は1起点で段を振るため、本稿で「段N」と書く箇所は
すべて**1起点（同ツールの出力そのまま）**であり、0起点換算をその都度
併記する。

## 測定条件

- ROM: `private/rom`（公式一式）にコミット`06a4523`時点の
  `src/l3_service/make_subrom.py`で生成した自作サブROMを差し替えた混成
  （`tools/lib_l3_measure.sh`の`build_mixed_rom`を使用。既存の
  `conform_l3.sh`/`diag_l3_mixed.sh`と同じ関数）。
- ディスク: `private/disk/N88_FE.D88`（diskA、`conform_l3.sh`と同一）。
- 実行: `q88measure --frames 1800`（`conform_l3.sh`の起動測定と同条件）。
- 4条件 × 各2run、計8回、すべて**フォアグラウンドで実行**した。
  並行して他の`git`操作・ファイル編集は行っていない。
- 4条件: ベースライン（全`break_*`=False）、`break_exchange6_cylinder`
  （陽性対照）、`break_exchange6_drive_bit_clear`、
  `break_exchange6_drive_bit_set`。

各条件のサブROM SHA-256は4条件とも相互に異なることを、ビルド直後と
全8回の測定終了後の両方で確認した（測定中にソース・ROMが変化していない
ことの確認。要求どおり、実際に`--rom-dir`へ渡したROMのSHAが期待SHAと
一致することを毎回検証した）。

## 段階1: 交換#6に対応する段の特定

`tools/compare_l3_entry_fdc.py --after-frame 0 --list-all-stages`で
ベースラインの起動区間FDCコマンド種別列を見ると、51件の内訳は
「初期化・キャリブレーション15件 + `READ単位`×9（各4件=SEEK・
SENSE INTERRUPT STATUS・SENSE DRIVE STATUS・READ DATA）」であり、
`READ単位`は1起点でコマンド16-19（unit#1）、20-23（unit#2）、
24-27（unit#3）、28-31（unit#4）、32-35（unit#5）、36-39（unit#6）、
40-43（unit#7）、44-47（unit#8）、48-51（unit#9）に区切れる
（0起点ではそれぞれ-1）。`m7fy`が挙げた候補（交換#3(1)・交換#6(1)・
交換#11(1)・交換#14(複数)=9）に、出現順で交換#3→交換#6→交換#11→交換#14
と当てはめると、**交換#6はunit#2、すなわち1起点コマンド20-23
（SEEK=20、SENSE INTERRUPT STATUS=21、SENSE DRIVE STATUS=22、
READ DATA=23。0起点では19-22）に対応する**という予測になる。

**この予測は測定で裏付けられた。** 陽性対照`break_exchange6_cylinder`
（`REQ_HDR+4`＝転記済みシリンダを変更）とのベースライン比較で、
FDCイベント内の最初の値差は「コマンド20件目(SEEK)のパラメータ2件目」、
`--list-all-stages`は「段20(SEEK): シリンダ指定 不一致」を示した。
`break_exchange6_drive_bit_set`（`REQ_HDR+2`のbit0を1へ）との比較でも、
最初の値差は同じく「コマンド20件目(SEEK)のパラメータ1件目」、
段としては「段20(SEEK): シリンダ指定 一致」だが直後の
「段21(SENSE INTERRUPT STATUS): 公式=A/head0、混成=B/head0、不一致」
として現れた。**シリンダを変える注入とunit/headビットを変える注入という
独立した2種類の故障注入が、いずれも同じ段20/21で最初に発現した。** これは
候補順の当てはめだけでなく、測定によって段の特定を検証したことになる
（`m7fy`が「特定できなくても止まらない、段階2の陽性対照で特定自体を
検証する」とした手続きどおり）。

**したがって、交換#6のSEEK/SENSE DRIVE STATUS/READ DATAは、1起点で
コマンド20（SEEK）・21（SENSE INTERRUPT STATUS）・22（SENSE DRIVE
STATUS）・23（READ DATA）、0起点で19・20・21・22と特定した。**

## 段階2: 陽性対照（`break_exchange6_cylinder`）

**通った。** ベースラインに対して、末端に大きな差が出た。

- FDCコマンド種別列: ベースライン51件・陽性対照263件。一致prefixは51件
  （全長不一致）。`READ DATA`発行件数はベースライン9件・陽性対照62件。
- 入口区間unit/head分類は、`READ DATA:A/head0`4→2件、`READ DATA:A/head1`
  5→60件など、大きく変化した。
- 画面出力: ベースライン3行・111文字・SHA一致、陽性対照1行・65文字・
  別SHA。`screen_compare=mismatch`。
- 陽性対照ROMのSHA-256はベースラインと異なることを確認した。
- q88measureへ実際に渡した`--rom-dir`内のサブROMのSHAが、全8run（各条件
  2run）で毎回ビルド直後の期待SHAと一致することを確認した（測定後の
  再ハッシュでも一致）。

## 段階3: 合格条件をベースライン同士へ先に当てる

**「差なし」と出た。** ベースラインrun1対run2に`compare_l3_entry_fdc.py
--after-frame 0 --list-all-stages`を適用したところ、FDCコマンド種別の
最初の差「なし（全長一致）」、FDCポート値列の最初の差「なし」、rc=0。
画面比較（`check_l3_screen_output.py --compare-report`）も
`screen_compare=match`、rc=0。判定規則自体は壊れていないことを確認した。

## 段階4: 本測定

### `break_exchange6_drive_bit_clear`（bit0を0へ）

**ベースラインと完全一致した。** FDCコマンド種別列51件対51件で一致
prefix51件（全長一致）、FDCポート値列も一致prefix13833件（最初の差
「なし」）、`READ DATA`発行件数9件対9件、入口区間unit/head分類は
カテゴリ・件数とも完全一致（`READ DATA:A/head0`×4、`READ DATA:A/head1`
×5、`SEEK:A/head0`×10、`SEEK:B/head0`×1、`SENSE DRIVE STATUS:A/head0`
×9、その他RECALIBRATE系も一致）。画面出力もSHA一致
（`screen_compare=match`、rc=0）。

### `break_exchange6_drive_bit_set`（bit0を1へ）

**ベースラインと大きく乖離した。** FDCコマンド種別列はベースライン51件・
本条件23件で一致prefix23件（コマンド24件目で混成側が先に終端）、
`READ DATA`発行件数は9件対2件。段20（1起点、SEEK）はシリンダ指定こそ
「一致」だが、直後の段21（SENSE INTERRUPT STATUS）でIC/unit/headが
「公式=A/head0、混成=B/head0」と不一致になり、以降のFDCコマンド種別列も
崩れた（コマンド15件目までの入口区間エラー結果は両条件一致していたが、
その先で構造が変わった）。画面出力は3行/111文字/あるSHA→1行/65文字/
別SHA、`screen_compare=mismatch`、rc=1。

### 判定

`clear`はベースラインと一致し、`set`はベースラインと大きく乖離した。
**`clear`と`set`は互いに異なる結果になった。** これは事前登録した
**H1（bit0が効く）**の予測「clearとsetで末端に差が出る、または互いに
違う結果になる」に合致する。機構として素直に解釈すれば、この測定条件
（diskA起動、交換#6の時点）では`REQ_HDR+2`のbit0はもともと0相当であり、
`clear`（0へ強制）は実効的な変化を生まず、`set`（1へ強制）だけが交換#6の
SEEK/SENSE DRIVE STATUS/READ DATAのunit/headを実際にB側へ変え、その結果
NOT READY相当のエラーへ落ちて以降のFDCコマンド列・画面出力が崩れた、
という説明と整合する。**ただし、これはこの1回の測定条件（diskA起動、
1800フレーム）についての観察であり、他の起動条件・ディスクでも同じ
方向に効くとは測っていない。**

## 段階5: 決定論性

ベースライン・陽性対照・`clear`・`set`の4条件とも各2run新規測定し、
`tools/redact_iolog.py`で伏せ字化した後のバイト列のSHA-256が、条件ごとに
run1とrun2で完全一致した（4条件とも自己一致）。**未確認の条件は無い**
（全4条件×2run、計8runすべて新規に測定した）。

## 言えること・言えないこと

**言えること:**

- 交換#6のSEEK/SENSE DRIVE STATUS/READ DATAは、1起点コマンド20-23
  （0起点19-22）に対応すると、独立した2種類の故障注入の最初の発現位置
  から測定的に特定できた。
- 陽性対照は明確に差を出し、測定器はこの経路を捉えている。
- 判定規則自体はベースライン同士では「差なし」を返す（偽陽性を作らない）。
- `break_exchange6_drive_bit_clear`はベースラインと区別できない
  （FDCコマンド種別列・ポート値列一致prefix・unit/head分類・画面出力の
  いずれでも差が無い）。
- `break_exchange6_drive_bit_set`はベースラインと明確に乖離する
  （交換#6のSEEK直後のSENSE INTERRUPT STATUSでunit/headがA→Bへ変わり、
  以降のFDCコマンド列・READ DATA件数・画面出力が崩れる）。
- 4条件とも決定論性が成立した（各2run自己一致）。

**言えないこと:**

- 他のディスク・起動シナリオ・打鍵条件での挙動は測っていない。
- `set`が引き起こす末端崩壊が、実機のRAM初期値やドライブ実装依存の
  挙動とどう対応するかは何も言わない（本ハーネス上の観察に限る）。
- `clear`が「ベースラインと一致した」ことは、「この経路でbit0が常に0で
  あるべき」という規範的判断ではない。今回の測定条件でたまたま0相当
  だったという観察である。
- 交換#6以外（#3・#7・#11・#14）のREAD単位が、`m7fy`の候補列挙どおりの
  対応関係にあるかどうかは、本稿では交換#6の位置だけを検証しており、
  他の交換の対応は検証していない。
- FDCポート値列そのもの（値）、画面本文、公式ディスクの実データは
  見ていない・記録していない。

## 開示

手順上の逸脱・汚染は無かった。測定はすべてフォアグラウンドで実行し、
測定中に`git stash`・ブランチ切替・ファイル編集は行っていない。作業用の
`redact_iolog.py`呼び出しを最初1回、引数の形（2引数取ると誤解していた）を
誤って`rc=2`で失敗させたが、これは出力ファイルが作られなかっただけで、
値を見る事故ではなかった。直後に`--help`で正しい引数形式（標準出力へ
書く1個以上のfiles引数）を確認し、リダイレクトで書き直して成功させた。

## 情報境界

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容は読んでいない。記録したのは公開FDCコマンド種別名、段番号、
unit/head分類の一致・不一致、件数、画面出力の行数・文字数・SHA-256、
SHA-256、rcだけである。データポート値列・画面本文・シリンダ値・PCN値は
表示も転記もしていない。生ログ・混成ROM一式はリポジトリ外
（`/private/tmp/claude-501/.../scratchpad/m7fz/`）に置き、コミットしない。

## 検証

`tools/check_cleanroom.sh`は全項目OK、rc=0。`git status`で`private/`由来の
混入・生ログ・ROM像が無いことを確認した。`src/`・`tools/`は本稿では
変更していない。

根拠: [m7fy](m7fy-exchange6-drive-bit-preregistration.md)・
[m7fw](m7fw-boot-drive-selector-adoption.md)・
[m7fx](m7fx-fdc-seek-propagation-callers-reading.md)・
[m7ex](m7ex-boot-region-drive-selector-difference.md)・
自作`src/l3_service/make_subrom.py`（コミット`06a4523`）・
`tools/compare_l3_entry_fdc.py`・`tools/check_l3_screen_output.py`・
`tools/redact_iolog.py`・`tools/lib_l3_measure.sh`。
