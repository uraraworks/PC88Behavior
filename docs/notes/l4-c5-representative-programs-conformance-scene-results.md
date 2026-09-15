# l4-c5 — 代表プログラム集の適合場面固定 — 結果

事前登録: [l4-c5-representative-programs-conformance-scene-preregistration](l4-c5-representative-programs-conformance-scene-preregistration.md)
（`2837926`）＋
[追補1](l4-c5-representative-programs-conformance-scene-preregistration-addendum.md)
（`ebe29dc`）＋
[追補2](l4-c5-representative-programs-conformance-scene-preregistration-addendum2.md)
（`89b503e`）＋
[追補3](l4-c5-representative-programs-conformance-scene-preregistration-addendum3.md)
（`f0172d0`）。器具: `tools/conform_l4.sh`（PROGRAM_ARM_NAMES/
program_arm_bas・program_arm_input/run_program_arm_once/
check_program_record_against_expected/群"programs"の実装状態表示/
検出力自己検査a〜e）・`tests/conformance/expected_l4_programs.tsv`
のヘッダ・群状態表示（`b5c1b34`、本ノートの前のコミット）。記録の
正規化・ハッシュ化・打鍵計画の組み立ては既存の
`tools/l4_program_conform_record.py`・`tools/l4_program_typeplan.py`・
`tools/l4_program_run.sh`（追補2反映版`54a4cdc`・追補3反映版）をそのまま
使い、二重実装していない。判定名・記録項目・関門・数え方は事前登録＋
追補から動かしていない。

## 腕の入力

事前登録追補3どおり、測定を始める直前のコミットの`tests/programs`を
腕の入力にした。

- 参照コミット: `ae43aba`（`M7: 代表プログラム p03 を17行以内に`。
  P1〜P8の行数はP1=6・P2=10・P3=12・P4=8・P5=8・P6=10・P7=9・P8=3で、
  いずれも追補3の上限17行以内）
- G11（測定開始時の`tests/programs`と、本ノート・期待値ファイルを
  コミットする時点の`tests/programs`が同一であること）: 期待値ファイル
  （`tests/conformance/expected_l4_programs.tsv`）に上記コミットハッシュ
  を明記し、`git log -1 --format=%H -- tests/programs`が測定前後とも
  `ae43aba`のままであることを確認した（本ノートのコミットまで
  `tests/programs`に変更は無い）。真。

## 期待値作成（公式ROM、8腕×2走）

`tools/l4_program_typeplan.py`の打鍵計画（`new`→`cls`→各行→G9確認→
`cls`→前の写し→`run`→(P8のみ入力値`5,3`)→後の写し）どおりに
`tools/l4_program_run.sh --rom-dir "$PC88_REF_ROM_DIR"`で全8腕を2走ずつ
実施した。

- G1（器具の自己検査）: `tools/l4_program_conform_selftest.sh`（検査
  1〜12、`cls`挟み込み・G9「行番号で始まる行」判定・G10境界判定を含む）
  を全項目OKで確認済み（測定前）
- G2（取りこぼし0・打てない文字の警告0）: 全16走で`untypable_warning=0`
  （`tools/l4_program_run.sh`の標準出力で確認。真）
- G3（決定論性）: 8腕すべてでrun1=run2の記録
  （`cell_count`/`ok_relative_row`/`sha256`）が完全一致
- G8（出力完了の確認）: 8腕すべてで記録の`status=ok`（`ok_row_not_found`・
  `no_changes`・`insufficient_rows`は0件）
- G9（打鍵到達確認）: 8腕すべてで`check_keystroke_arrival`が真
  （行番号で始まる行の件数がプログラムの行数と一致。P3〔12行、追補3で
  17行以内に書き直し済み〕を含め全腕で成立）
- G10（画面に収まっていること）: 8腕すべてで`check_output_fits_screen`
  が真（`ok_relative_row+1 ≤ 20`）

G1〜G5・G8〜G11すべて真のため、`gate_failed`として除外した腕は無い。
8腕全てで2走の記録が完全一致し、この記録をそのまま
`tests/conformance/expected_l4_programs.tsv`に採用した（値そのものは
含めず、`cell_count`/`ok_relative_row`/`sha256`のみ）。

## `tools/conform_l4.sh` の実行結果

### 公式環境が無い場合（`PC88_REF_ROM_DIR`未設定）

期待値ファイルに8腕の記録を追加する前、器具コミット直後（`b5c1b34`）に
確認した:

- 既存の場面（打鍵エコー11腕・PRINT16腕・FLOAT25腕）: 振る舞いを変えず、
  引き続き全`conform`
- **PROGRAM場面（新設8腕）**: 自作ROM側 `not_implemented_yet: 8/8`
  （群"programs"が`not_implemented_yet`。`na()`による黄色`--`の判定外
  表示で、rcには含まれない）
- 検出力の自己検査a〜d(PROGRAM)・自己検査e(群の印の切替)は全項目OK
- 全体の終了コード: **0**

### 公式環境がある場合（`PC88_REF_ROM_DIR=private/rom`）

期待値ファイルに8腕の記録を追加する前の実行では、公式ROM側は
「G1〜G5・G8〜G11全て真・G3決定論性も一致」の状態まで進んだうえで、
`期待値に行が無い(gate_failed)`として8/8とも`gate_failed`表示になった
（この段階では期待値がまだヘッダのみだったため。想定どおりの挙動）。

期待値8行を`tests/conformance/expected_l4_programs.tsv`にコミットした
後の再実行は、**本ノート作成中に別セッションが`src/l4_basic/interp.asm`・
`src/l4_basic/run.asm`を並行編集していたため**（`git status`で確認、
本ノートの担当範囲外のファイル）、`python3 src/build_main_rom.py`が
`z80text アセンブルエラー: 行 532: 未定義ラベル: LOGIC_OR_EXPR`で
毎回失敗し、自作ROM一式の組み立てそのものが止まって
`tools/conform_l4.sh`本体を最後まで完走できなかった（5回試行、いずれも
同じ箇所・同じエラーで停止。本ノートが触ったファイルではなく、
`tests/programs`・`tools/conform_l4.sh`・
`tests/conformance/expected_l4_programs.tsv`のいずれにも変更は無い）。

そのため公式ROM側8腕の`conform`確認は、`tools/conform_l4.sh`を最後まで
完走させる代わりに、同スクリプトが内部で使うのと同じ道具
（`tools/l4_program_run.sh`・`tools/l4_program_conform_record.py`・
`tools/l4_program_typeplan.py`の`check_keystroke_arrival`・
`check_output_fits_screen`）を直接呼ぶ使い捨てドライバ（scratchpad配下、
本ノートの後に削除）で確認した。結果、8腕とも2走の記録が完全一致し
G8〜G10も真で、上記「期待値作成」節の記録がそのまま
`tests/conformance/expected_l4_programs.tsv`の8行と一致することを確認
済み（この時点でも公式ROM側は`conform: 8/8`相当と言える）。
`tools/conform_l4.sh`自体による公式ROM側8腕の`conform`表示の再確認は、
自作main ROM一式の組み立てが復旧してから改めて行うことが望ましい
（自作main ROMのビルド失敗は`tools/conform_l4.sh`が公式ROM側の照合へ
進む前の共通ステップで起きるため、`src/l4_basic/`の並行編集が収まり
次第、同コマンドを再実行するだけで良い）。

## 故障注入（検出力の自己検査。公式環境不要、`tools/conform_l4.sh`が
常に実行する）

事前登録どおり、PROGRAM場面用にPRINT/FLOAT場面と同型の自己検査
a・b1・c・dを追加し、いずれの実行でも全項目OKだった。

- 自己検査a(PROGRAM): 記録（出力セルの文字コード相当の1バイト）を
  変えるとSHA-256が変わる（検出力あり）
- 自己検査b1(PROGRAM): 正しい記録は期待値と`conform`、壊した記録は
  `not_conform`
- 自己検査c(PROGRAM): 期待値の1行の`cell_count`を壊すと、正しい記録
  でも`not_conform`で検出される
- 自己検査d(PROGRAM): 期待値の1行のSHA-256を壊すと`not_conform`で
  検出される

さらに本場面で新設した自己検査e（群の印の切替）も全項目OKだった。
実データではなく、明らかに不一致になる合成の期待値行（`cell_count=999`・
架空のSHA-256）を使い、実際の自作ROM(`SELF_ROMDIR`)に対して走らせた。

- 自己検査e-1: 見出しコメントが`selfmade=not_implemented_yet`のとき、
  `program_group_status`が`not_implemented_yet`を正しく返す
- 自己検査e-2: 見出しコメントを`selfmade=implemented`に書き換えると、
  `program_group_status`が`implemented`を正しく返す
- 自己検査e-3: `implemented`にした状態で実際に自作ROMを走らせて合成の
  期待値と照合すると、`not_conform(件数不一致)`として**NG**になった。
  すなわち、`not_implemented_yet`による判定外の扱いは「本物の判定を
  隠していない」——実際に照合させれば、未実装ゆえの不一致がちゃんと
  検出できる状態であることを確認した

## 判定

- P1〜P8（1群"programs"、8腕）: 公式ROM側は8腕すべて2走の記録が完全
  一致し、`tests/conformance/expected_l4_programs.tsv`の8行とも一致
  （`conform`相当。上記「実行結果」節のとおり`tools/conform_l4.sh`
  本体での最終再確認は並行編集の影響で完走できず、別ドライバでの
  直接確認にとどまる）
- 自作ROM側: 全8腕`not_implemented_yet`（判定外、rc算入なし）。
  プログラムモードの実装が個々のプログラムを実行できる段階に達したら、
  見出しコメントを`implemented`に書き換えれば`conform`/`not_conform`
  の実判定に移る設計になっていることを自己検査eで確認済み
- 既存の場面（打鍵エコー・PRINT・FLOAT、計52腕）: 振る舞いを変えず、
  引き続き自作・公式とも全`conform`（器具コミット直後の実行で確認）
- 故障注入（PROGRAM場面の記録・期待値を壊す自己検査a〜d、群の印を
  切り替える自己検査e）: いずれもOK

## 判定後の行き先

事前登録どおり、公式側の期待値8腕は`tests/conformance/
expected_l4_programs.tsv`にコミット済みとして固定する。プログラム
モードの実装担当（`src/l4_basic/`）への申し送りとして、本ノートと
器具コミット（`b5c1b34`）を参照する。実装が個々のプログラムを実行
できる段階に達したら、見出しコメントを`implemented`に書き換えて
`conform`/`not_conform`の判定に移す。また、`src/l4_basic/`の並行編集
（本ノート作成時点で進行中だった`interp.asm`・`run.asm`の変更）が
収束した後、`PC88_REF_ROM_DIR`ありで`tools/conform_l4.sh`を再実行し、
公式ROM側8腕が同ツール上でも`conform: 8/8`と表示されることを確認する
ことを次の作業の入力とする（本ノートが直接確認した記録の一致自体は
上記のとおり別ドライバで済んでいるため、内容が変わる見込みは無い）。

## 生データ

期待値作成用の使い捨てドライバ・写し・記録・自作ROM一式・公式ROM一式の
複製はリポジトリ外の作業ディレクトリ（scratchpad配下）に置き、本ノートを
書いたあと削除した。
