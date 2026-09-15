# 事前登録: l4-c5 — 代表プログラム集の適合場面

記録日: 2026-09-16
状態: 事前登録、測定・器具作成前

## 位置づけ

開発者判断（2026-09-15）により、ゴールA（代表プログラムが動く）の
達成判定に使う代表プログラム群は`tests/programs`（`324acb7`、こちらで
書いた8本、テキスト画面のみ）に決まった。`l4-c2c`（打鍵エコー・
`PRINT`）・`l4-c3`（浮動小数点`PRINT`）と同じ作法で、プログラムを打ち
込んで`RUN`した結果の画面を、適合テスト`tools/conform_l4.sh`の場面
にする。

**公式側の期待値を実装より先に固定し、自作側はプログラムごとに後から
照合する**（`l4-c3`と同じ順序。CLAUDE.md「コミット規律」の「測定コミッ
トが実装コミットに先行する」の順序をそのまま踏襲する）。実装が済むまで
は、`l4-c3`で定義済みの判定名`not_implemented_yet`をそのまま使う（本
ノートでは新設しない）。

## 腕（8腕、プログラムごとに1腕）

`tests/programs`の8本、ファイル名の順にP1〜P8とする。

| 腕 | ファイル | 内容 | INPUT |
|---|---|---|---|
| P1 | `p01_kuku.bas` | 九九の表（9×9） | なし |
| P2 | `p02_primes.bas` | 30までの素数の列挙 | なし |
| P3 | `p03_bubble_sort.bas` | 配列のバブルソート | なし |
| P4 | `p04_fibonacci.bas` | フィボナッチ数列（単精度32項、桁あふれ含む） | なし |
| P5 | `p05_factorial.bas` | 階乗（単精度・倍精度並記） | なし |
| P6 | `p06_strings.bas` | 文字列関数一式 | なし |
| P7 | `p07_gosub_subroutine.bas` | `GOSUB`サブルーチン | なし |
| P8 | `p08_input_calc.bas` | `INPUT`で受け取った2値の和・積 | `5,3`（`tests/programs/README.md`記載の固定値） |

各腕の打鍵文字列は、`new`のあと該当ファイルの各行をそのままの順で
打ち、最後に`run`を打つ（`l4-s5a`以来の段階5の作法と同一）。ファイル
の内容は英字がすべて小文字で書かれている（`tests/programs/README.md`
に明記のとおり、打鍵注入が小文字で届く仕様に合わせてある）ため、
打鍵文字列を組み立てる際に大小文字の変換は不要である。行番号・記号
（`README.md`「各プログラムの一覧」列「打鍵に要る記号」参照: `*`・
`;`・`-`・`(`・`)`・`>`・`#`・`$`・`"`・`+`・`,`）は、ファイルに書かれ
ている文字列をそのまま使う。

**「画面の命令を使う版」として印の付いたプログラムは、`tests/
programs/README.md`の時点では存在しない**（8本のいずれも`CLS`・
`LOCATE`・`COLOR`・`WIDTH`を使っていないことが明記されている）。その
ため、本ノートでは**P1〜P8を1つの群として扱う**。将来、画面の命令を
使う版（`tests/programs/screen/`等、ファイル名に印の付いたもの）が
追加された場合は、それらを**別の群**として本ノートの枠組みをそのまま
拡張する（新しい事前登録を立てるか、本ノートの追補で群を追加する）。

## P8（INPUT）の打鍵タイミング

P8は`l4-s5e`のE1・E2と同じ考え方でフレームを決める。

```
prog        = "new" + プログラムの各行 + "run" を連結した打鍵文字列
n1          = len(prog)
line_end1   = 700 + 8 * n1
dump1       = line_end1 + 300   （プロンプトが出るまでの余裕。l4-s5e
                                   E1・E2と同じ+300フレームを流用する）
type_at2    = dump1              （プロンプト出現を、l4-s5eと同じ
                                   `--nonblank-summary-rows`による件数
                                   確認〔文字コードは見ない〕で確かめた
                                   後、続けて入力値を打つ）
val         = "5,3\n"
n2          = len(val)
line_end2   = type_at2 + 8 * n2
dump2       = line_end2 + 300
run2        = dump2 + 200
```

P8のみ、写しは3枚（打鍵前・プロンプト確認用・最終）を取る。他の7腕は
`l4-c2c`・`l4-c3`と同じ2枚（打鍵前・`dump`後）。

## 比べるもの・正規化

`run`の打鍵のエコー行の次の行から、最後の`Ok`行の前の行までの「前が
空白だったセル」を、`l4-c2c`の`tools/l4_print_conform_record.py`の
正規化と同じ考え方で(相対行, 列, 文字コード)に正規化してJSON化し、
SHA-256を取る。

- `origin_row` = 変化した行のうち最小のrow0（=`run`を打った行）
- `ok_row` = 変化した行のうち最大のrow0（=`Ok`の行）
- `cells`: `origin_row`より大きく`ok_row`より小さい行(=出力行)の「前が
  空白だったセル」を(row0-origin_row, col0, 文字コード)に正規化した
  並び
- `ok_relative_row` = `ok_row - origin_row`
- 出力(TSV、1行): `cell_count<TAB>ok_relative_row<TAB>sha256`
  （`l4-c2c`・`l4-c3`と同一の書式）
- **比較しない**: バナーの行、最下行（ファンクションキー表示行）、
  位置の絶対値（row0そのもの）（`l4-c2c`・`l4-c3`と同じ）

記録器は器具の担当が新しく作る予定（`tools/l4_program_conform_
record.py`。本ノートの担当範囲外）。`tools/l4_print_conform_record.py`
と同じく`tools/l4_vram_probe.py`の`diff_vram_dumps`をimportして使う
設計とし、二重実装しない。

## 期待値ファイル

`tests/conformance/expected_l4_programs.tsv`（**器具の担当が作る**。
本ノートの担当範囲外）。値そのもの（文字コード・セル位置の並び）は
一切コミットしない。件数（`cell_count`）と`ok_relative_row`とSHA-256
のみ（`expected_l4_print.tsv`・`expected_l4_float.tsv`と同じ作法、
CLAUDE.md禁止事項4）。

書式（TSV、1行1腕）:
```
arm<TAB>cell_count<TAB>ok_relative_row<TAB>sha256
```

生成: 公式ROM一式(`PC88_REF_ROM_DIR`)で8腕それぞれ**2走**実施し（G3
決定論性の確認を兼ねる）、2走の記録が完全一致した腕を採用する。

## 自作ROM側の照合のしかた

`tools/conform_l4.sh`の既存の二層方針（`l4-c1b`・`l4-c2c`・`l4-c3`分）
と同じ。

- 公式側の期待値（`expected_l4_programs.tsv`）は、実装の進行状況に
  関わらず本ノートの手順で先に固定する。
- 自作ROM側は、**プログラムごとに後から照合する**。プログラムモードの
  実装がまだそのプログラムを実行できる段階に達していない場合、その
  腕は`l4-c3`で定義済みの`not_implemented_yet`として記録でき、判定
  から外してよい（新しい判定名は本ノートでは作らない）。
- 群ごとの自作側の印（`selfmade=not_implemented_yet`/`implemented`）
  は`l4-c3`と同じ作法で付ける。将来、画面の命令を使う版の群が追加
  された場合も、群ごとに別々に印を管理する。
- 公式環境（`PC88_REF_ROM_DIR`）が無い環境では、公式側の再導出は目立つ
  SKIP（既存の場面のSKIP注記と同じ形）にする。
- 既存の場面（打鍵エコー・整数/文字列PRINT・浮動小数点PRINT）はそのまま
  残し、振る舞いを変えない。代表プログラムの場面は別配列・別関数
  （例: `PROGRAM_ARM_NAMES`・`program_arm_params`）として並置する。

## 関門

`l4-c3`のG1〜G5・G8を土台にし、本ノート固有の2点を追加する。

- G1 器具の自己検査: 測定時HEADで`tools/harness/vram_dump_selftest.sh`・
  `tools/harness/vram_dump_dynamic_selftest.sh`・
  `tools/harness/mem_write_log_selftest.sh`・
  `tools/harness/key_matrix_selftest.sh`・
  `tools/screen_content_leak_selftest.sh`の全項目がOK
- G2 取りこぼし0・打てない文字の警告0（全走のstderrで確認）
- G3 決定論性: 公式ROM側、各腕2走とも記録(cell_count/ok_relative_row/
  sha256)が完全一致（P8はプロンプト確認用の写しと最終写しの両方で
  確認する）
- G4 陰性対照: 何も打たない走で差分0件
- G5 自作ROM側の`tools/l4_basic_selftest.sh`と`tools/l3_main_
  selftest.sh`が、測定時HEADでともにrc=0（自作側の照合を行う腕に
  ついてのみ。`not_implemented_yet`の腕はG5の対象から外れる）
- G8 出力完了の確認: 「後」の写しで、出力行の後に`Ok`行が現れている
  こと。現れない腕は`gate_failed`とし、「写しが早すぎた」とだけ記述
  する
- **G9（新設）打鍵の到達確認**: プログラムを打ち終えた（`run`を打つ
  前の）時点で、打鍵が全部届いていることを確認する。確認方法は
  `tools/l4_vram_probe.py --nonblank-summary-rows`で、打ったプログラム
  の行数ぶんの非空白セルを含む行数が、実際に打った行数と一致すること
  を件数だけで見る（文字コードは見ない。値ではなく「行が抜けていない
  か」という構造の確認）。加えて、`l4-s5a`で新設した`tools/
  l4_list_classify.py`（LISTの出力行を数字始まりのASCIIだけコードごと
  記録する分類器）が使えるなら、`list`を打った結果の行数が元の
  プログラムの行数と一致することでも二重に確認する（自作ROM側の
  プログラムモードがまだ`LIST`を実装していない段階では、この二重
  確認は省略し、`--nonblank-summary-rows`による件数確認だけで足りると
  する）。一致しない腕は`gate_failed`とし、「打鍵が抜けていた」とだけ
  記述する（抜けた行の内容は出さない）。
- **G10（新設）出力が画面に収まっていること**: 出力がスクロールして
  いないことを確認する。`tests/programs/README.md`「出力の収まり方」
  節に、8本いずれも出力が画面1枚（20行）に収まり無限ループも無いと
  記載されているが、本ノートでは**その記載を前提として押し通さず、
  実測で確かめる**。確認方法は、`origin_row`（`run`を打った行）から
  `ok_row`（`Ok`の行）までの行数が、画面の行数（20行、既定表示。
  `docs/spec/l3-main.md`第5節参照）を超えていないことを見る。超えて
  いた腕（＝スクロールが起きた可能性がある腕）は`gate_failed`とし、
  「出力が画面に収まらなかった」とだけ記述する。

判定の前にG1〜G5・G8〜G10がすべて真であること（G6・G7は対になる
予測表が無いため本測定には適用しない）。いずれかが偽の腕は、その腕を
`gate_failed`として判定に含めず、理由を記述する。

## 判定

- `conform`: 記録する内容（cell_count・ok_relative_row・SHA-256）が
  期待値と完全に一致する
- `not_conform`: 上記のいずれかが一致しない。一致しない具体的な形
  （件数不一致かSHA-256不一致か）を判定名の後に文章で記述する。値
  そのものは出さない
- `not_implemented_yet`: 自作ROM側で、その腕のプログラムモード実装が
  まだ完了していないために照合自体を行っていない腕。判定外として
  扱う（`l4-c3`で定義済みの判定名をそのまま使う）
- `gate_failed`: 関門（G1〜G5・G8〜G10）のいずれかが偽だった腕。判定に
  含めず、理由を記述する

腕ごとに公式ROM側・自作ROM側それぞれの判定を出し、**群（現時点では
P1〜P8の1群のみ）ごとのまとめ**として、`conform`/`not_conform`/
`not_implemented_yet`/`gate_failed`の腕数を記述する。

## 検出力の自己検査（`tools/conform_l4.sh`が常に実行する。公式環境不要）

`l4-c2c`・`l4-c3`分の自己検査a〜dと同じ構造を、代表プログラム用の記録
に対しても行う（器具の担当が実装する。本ノートは要件のみ定める）。

- a. 自作ROM側の記録を模した対照データの1バイトを変えるとSHA-256が
  変わる（検出力の確認）
- b. 正しい記録は期待値と`conform`、壊した記録は`not_conform`
- c. 期待値の1行の`cell_count`または`ok_relative_row`を壊すと、正しい
  記録との照合でも`not_conform`になる（件数不一致の検出）
- d. 期待値の1行のSHA-256を壊すと`not_conform`になる（ハッシュ不一致
  の検出）

## 判定後の行き先

- 公式側の期待値8腕すべてが固定できたら（G1〜G4・G8〜G10を満たし、各
  腕2走の記録が一致）、`tests/conformance/expected_l4_programs.tsv`を
  コミットする。この時点では自作ROM側は`not_implemented_yet`のままで
  よい。
- 自作ROM側のプログラムモード実装が個々のプログラムを実行できる段階
  に達した腕から、順に照合し`conform`/`not_conform`の判定に移す。
- いずれかが`not_conform`なら、原因を結果ノートに記述し次の作業の
  入力にする。
- 画面の命令を使う版のプログラムが将来追加された場合は、別の群として
  本ノートの枠組みを拡張する（新しい事前登録、または本ノートの追補）。

## 結果ノート

`docs/notes/l4-c5-representative-programs-conformance-scene-results.md`
に書く。関門・判定名・数え方は本ノートから動かさない。

## 根拠リンク

[l4-c2c-print-conformance-scene-preregistration.md](l4-c2c-print-conformance-scene-preregistration.md)
（`0a2117f`、比べるもの・記録する内容・期待値ファイルの作法・関門
G1〜G5・自作ROM側二層方針の直接の原型）・
[l4-c3-float-print-conformance-scene-preregistration.md](l4-c3-float-print-conformance-scene-preregistration.md)
（`71d81a8`、判定名`not_implemented_yet`・「測定が実装に先行する」
順序・関門G8の直接の原型）・`324acb7`（`tests/programs`下書き、8本の
出所）・`tests/programs/README.md`（プログラムごとの内容・使用機能・
INPUT値・画面命令の不使用・出力の収まり方の記載）・
[l4-s5e-input-string-numeric-functions-preregistration.md](l4-s5e-input-string-numeric-functions-preregistration.md)
（`0627571`、INPUTのプロンプト待ちのフレーム決定・件数のみでの出現
確認の直接の原型）・`docs/spec/l3-main.md`（第5節、画面の行数〔20行
既定表示〕。関門G10の根拠）・`tools/l4_print_conform_record.py`
（正規化・ハッシュ化の既存実装、流用の根拠）・`tools/l4_vram_probe.py`
（差分モード・`--nonblank-summary-rows`）。
