# l4-s5g — READ/DATA・REM・1行に複数の文 — 事前登録

記録日: 2026-09-15
状態: 事前登録、測定前

## 位置づけ

ゴールAの代表プログラム集（`tests/programs`、`324acb7`）を書いた担当
が、仕様書に無いため避けた機能のうち、典型的なプログラムでよく使う
ものを本ノートで測る。`RND`は生成する数列を公式と合わせるのが大仕事
になるため、今回の対象から外す。

## 問い

- Q1 `READ`/`DATA`（G1〜G4）: 値が正しく読み込まれるか
- Q2 `RESTORE`（G3）: `DATA`の読み取り位置が先頭に戻るか
- Q3 `THEN`の後の代入（G5）: `IF`〜`THEN`の`THEN`に代入文を書けるか
- Q4 添字0（G6）: 配列の添字`0`が使えるか
- Q5 1行に複数の文（G7）: `:`区切りの文がすべて実行されるか
- Q6 `DATA`切れ（G8）: `DATA`が無い状態で`READ`したときの挙動
- Q7 `REM`と`'`（G9・G10）: コメントの扱い
- Q8 `IF`と同じ行の残り（G11・G12）: `THEN`の後に`:`で複数の文を並べた
  とき、真のとき全部実行されるか、偽のとき同じ行の残りが飛ばされるか

## 腕（12腕＋陽性対照1腕）

打鍵はこのまま使う（英字は小文字）。1腕＝`new`のあと行を打ち`run`を
打つ、という一連の打鍵を1つの`--type`文字列として与える（`l4-s5a`〜
`l4-s5f`と同じ作法）。

| 腕 | 打鍵文字列（`\n`は改行） | 目的 |
|---|---|---|
| G1 | `new`/`10 read a,b`/`20 print a+b`/`30 data 3,4`/`run` | Q1 基本のREAD/DATA |
| G2 | `new`/`10 for i=1 to 3`/`20 read a`/`30 print a;`/`40 next`/`50 data 5,6,7`/`run` | Q1 ループ内のREAD |
| G3 | `new`/`10 read a`/`20 restore`/`30 read b`/`40 print a;b`/`50 data 8,9`/`run` | Q2 RESTORE |
| G4 | `new`/`10 read a$`/`20 print a$`/`30 data 12`/`run` | Q1 文字列変数へのREAD |
| G5 | `new`/`10 if 1 then a=5`/`20 print a`/`run` | Q3 THENの代入 |
| G6 | `new`/`10 dim a(3)`/`20 a(0)=7`/`30 print a(0)`/`run` | Q4 添字0 |
| G7 | `new`/`10 a=1:b=2:print a+b`/`run` | Q5 複数の文 |
| G8 | `new`/`10 read a`/`20 print a`/`run` | Q6 DATA切れ |
| G9 | `new`/`10 print 1:rem 9`/`20 print 2`/`run` | Q7 REM |
| G10 | `new`/`10 ' 9`/`20 print 3`/`run` | Q7 `'`コメント |
| G11 | `new`/`10 a=2:if a=2 then print 1:print 2`/`run` | Q8 真のとき残りの文 |
| G12 | `new`/`10 if 0 then print 1:print 2`/`20 print 3`/`run` | Q8 偽のとき残りの文 |

### 陽性対照（1腕、腕数には含めない）

直接モードの`print 7717`（`l4-s4a`以来使ってきた陽性対照と同一）。

- 打鍵文字列: `print 7717\n`（文字数11）
- フレーム計算式は下記「条件・関門」節の全腕共通の式をそのまま使う:
  `line_end = 700 + 8*11 = 788`、`dump = line_end + 300 = 1088`、
  `run = dump + 200 = 1288`（`l4-s5c`〜`l4-s5f`の作法を踏襲し、陽性
  対照のフレーム式も本文に明記する）。

腕の総数: **12腕**（G1〜G12）。各腕2走（決定論性の関門G3）。

## 条件・関門

`l4-s5f`（`5bf9ef5`）・`l4-s5e`（`0627571`）の「条件・関門」節をそのまま
踏襲する。

- 起動settle`--type-at 300 --type '\n'`、実打鍵開始`--type-at 700`
- 1文字あたり`hold+gap=8`フレーム/文字（`\n`も1文字として数える）
- フレーム計算式（全腕共通。陽性対照にも同じ式を適用する）:
  ```
  line_end(k) = 700 + 8 * (その腕で打った文字数の累計。\n も1文字)
  dump(k)     = line_end(k) + 300
  run(k)      = dump(k) + 200
  ```
- 写しは打鍵前（`--type-at`の10フレーム前=690）と`dump(k)`後の2枚を
  `--diff-before`/`--diff-after`に渡す。

## 記録する内容

`l4-s5c`（`09c933a`）〜`l4-s5f`と同一の手順を踏襲する。

- **`Ok`行の位置（打った行からの相対行）と、`RUN`の後に出た行の数を、
  すべての腕で必ず記録する。**
- 出力行は、**行ごとに**`l4-s4a`の数値分類器（`tools/l4_s4a_float_
  classify.py`、`5735eb3`）を適用する。`numeric_output`と分類された
  行は、(相対行, 相対桁, 文字コード)の並びをそのまま記録する。それ
  以外の行（エラー・`Ok`自身の文字列等）は、件数と位置の範囲だけを
  記録する。コード・文言は一切出さない。
- **G8（`DATA`切れ）**: `20 print a`で誤りが起きる想定の腕であり、
  Q6の該当項目は**出力行数と`Ok`の位置だけを記述する**（依頼文の
  とおり。誤りの行そのものは、上記の分類規則により`non_numeric_
  output`として件数と範囲だけの記録になる）。

## 本文を出さない取り扱い

`l4-s4a`〜`l4-s5f`と同一。「記録する内容」節の分類規則に従い、
`numeric_output`の行だけコードを記録し、それ以外は件数と範囲だけに
する。分類器（`tools/l4_s4a_float_classify.py`）は集合外のコードを
標準出力・標準エラーへ出さない設計であることが`5735eb3`の時点で確認
済み。

## 関門

`l4-s5f`のG1〜G5・G8と同一（G6は対になる予測表が無いため本測定にも
適用しない）。

- G1 器具の自己検査: 測定時HEADで`tools/harness/vram_dump_selftest.sh`・
  `tools/harness/vram_dump_dynamic_selftest.sh`・
  `tools/harness/key_matrix_selftest.sh`・
  `tools/harness/type_untypable_selftest.sh`・
  `tools/screen_content_leak_selftest.sh`の全項目がOK
- G2 取りこぼし0・打てない文字の警告0（全走のstderrで確認）
- G3 決定論性: 各腕2走とも、写しはファイルのsha256が一致、記録は
  sha256が一致
- G4 陰性対照: 何も打たない走で差分0件
- G5 陽性対照: 直接モードの`print 7717`腕で`7717`の並びを確認
- G8 出力完了の確認: 「後」の写しで、出力行の後に`Ok`行が現れている
  こと。現れない腕は`gate_failed`とし、「写しが早すぎた」とだけ記述
  する

判定の前にG1〜G5・G8がすべて真であること。いずれかが偽の腕は、その
腕を`gate_failed`として判定に含めず、理由を記述する。

## 判定

判定名はこの事前登録に書いたものだけを使う。「記録する内容」節を
参照する。当てはまらない形はすべて`other`とし、記述で補う。

- Q1（G1〜G4）: `read_ok`（`READ`が`DATA`の値を順に正しく読み込む）／
  `other`。腕ごとに値を記述する。
- Q2（G3）: `restore_ok`（`RESTORE`の後、`DATA`の読み取り位置が先頭に
  戻り、2回目の`READ`が最初の値を再び読む）／`other`
- Q3（G5）: `then_assign_ok`（`THEN`の後の代入文が実行される）／
  `other`
- Q4（G6）: `index0_ok`（添字`0`への代入・参照が期待どおりに機能する）
  ／`other`
- Q5（G7）: `multi_ok`（`:`で区切った文がすべて実行される）／`other`
- Q6（G8）: 記述のみ（判定名は付けない）。出力行数と`Ok`の位置をその
  まま書く。
- Q7（G9・G10）: `rem_ok`（`REM`・`'`の後の文字列がプログラムの実行に
  影響しない）／`other`
- Q8（G11・G12）: G11は`rest_runs_when_true`（`THEN`が真のとき、`:`で
  続く後続の文もすべて実行される）／`other`。G12は
  `rest_skipped_when_false`（`THEN`が偽のとき、同じ行の`:`以降を含め
  てすべて飛ばされる）／`rest_runs_when_false`（`THEN`は飛ばされるが
  同じ行の`:`以降の文は実行される）／`other`
- `gate_failed`: 関門のいずれかが偽だった腕。判定に含めず、理由を
  記述する。

## 器具の確認（公式ROMは使わない）

測定開始前に、自作main ROM（測定時HEAD`324acb7`から`src/build_main_
rom.py`で組み立て）に対し、12腕＋陽性対照の計13腕すべてを打鍵し、
各行のエコーが打鍵どおりに届くかを`tools/l4_vram_probe.py --marker`
（各腕の打鍵文字列を`\n`で分割し、各行をそれぞれmarkerとして指定）で
確認した。**自作ROMはまだプログラムモードを持たないため、実際の
`READ`/`DATA`・`RESTORE`・`REM`等の挙動は見ておらず、エコーだけを
確認した。**

作業ツリーには別担当（src/・tools/）が並行してビルドを崩す変更を進行
中だったため、`git worktree add --detach`でHEAD（`324acb7`）の別作業
ツリーを立て、そこから自作ROMを組み立てて確認した（作業ツリーの状態
に左右されず、測定時HEADから独立に確認するため）。フロントエンド
（`q88measure`）はソース変更が及んでいないため、本リポジトリの既存
ビルド済みバイナリをそのまま流用した。

結果: **13腕すべてで、全行のエコーが打鍵どおりに出現した**（腕ごとの
全行でmarker一致、打鍵前の走行失敗〔型チェックによる事前拒否〕も
無し）。`'`（G10）、`:`（G7・G9・G11・G12）、`,`（G1・G3）、`$`（G4）
を含め、届かなかった記号は無かった。

作業に使ったROM・写し・スクリプト・別作業ツリーはリポジトリ外の使い
捨てディレクトリ（scratchpad配下）に置き、確認後に削除・撤去した。

## 判定後の行き先

Q1〜Q8の判定結果を仕様書`docs/spec/l4-program.md`（または新設する
仕様書節）に反映し、段階5の実装（`READ`/`DATA`/`RESTORE`・`THEN`の
代入・添字0・複数文・`REM`/`'`・`IF`の同一行の残り）の入力とする。

## 結果ノート

`docs/notes/l4-s5g-read-data-rem-multi-statement-results.md`に書く。
関門・判定名と数え方は本ノートから動かさない。

## 根拠リンク

[l4-s5f-screen-commands-preregistration.md](l4-s5f-screen-commands-preregistration.md)
（`5bf9ef5`）・
[l4-s5e-input-string-numeric-functions-preregistration.md](l4-s5e-input-string-numeric-functions-preregistration.md)
（`0627571`、条件・関門G1〜G5・G8・記録する内容・本文を出さない取り
扱い・陽性対照のフレーム式明記の直接の原型）・`324acb7`（代表プログラム
集の下書き。仕様書に無いため避けた機能の洗い出しの出所）・`5735eb3`
（`tools/l4_s4a_float_classify.py`、数値分類器）・`tools/
l4_vram_probe.py`（差分モード・`--marker`）。
