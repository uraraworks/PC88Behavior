# l4-c5 事前登録 追補 — RUNの前にCLSを入れて画面のスクロールを避ける

記録日: 2026-09-16
状態: 事前登録の追補、測定前
対象: [l4-c5-representative-programs-conformance-scene-preregistration.md](l4-c5-representative-programs-conformance-scene-preregistration.md)
（`2837926`）を上書きする形で追補する。本体は書き換えない。

## 経緯

器具（`tools/l4_program_conform_record.py`、`e5a6f1f`）の試走で、
10〜19行のプログラム（P2`p02_primes.bas`・P3`p03_bubble_sort.bas`・
P6`p06_strings.bas`）は、打ち込んでいる間にプログラムのエコー行だけで
画面が埋まり、途中でスクロールが起きることが分かった。本体の「比べる
もの・正規化」節が前提とする「前後の写しの差分で"前が空白だったセル"
を拾う」という方法は、スクロールが起きるとその基準（原点＝`run`を
打った行、という相対位置の取り方）が崩れる。実際、試走では`Ok`行が
写しの範囲内に見つからず、器具は正しくこれを検出してSHA-256を出さな
かった（器具自体は正常に動作しており、これは公式側の期待値を測定する
前に、腕の打鍵手順そのものを見直す必要があることを示す結果である）。

本追補は、公式側の期待値の測定を始める前に、腕の手順を見直して定める。

## 1. 腕の手順の変更

腕の打鍵手順を、次のとおり変更する。

```
new → プログラムの各行 → 【関門G9の確認】 → cls → 【前の写し】
    → run →（INPUTのある腕は値）→ 【後の写し】
```

**`cls`を`run`の直前に挟む**ことで、プログラムの打ち込みで埋まった
画面を一度消してから`run`する。これにより、`run`の出力は消去済みの
画面に対して現れるため、出力行数が20行を超えない限り（関門G10で確認
する）スクロールが起きない。

`cls`の振る舞いは`l4-s5f`（測定`7fbc47c`）・仕様書`docs/spec/
l4-program.md`第6版で観測済みである。`CLS`は画面を消し、消去後には
`Ok`相当の応答とファンクションキー表示行（最下行）が残る（`l4-s5f`
のQ1「消去」の判定結果）。この既知の振る舞いを根拠に、`cls`を挟んでも
`run`の出力そのものの比較（「比べるもの」節）には影響しないと判断
する。

**関門G9（打鍵が全部届いたこと）の確認は、`cls`の前に行う**（本体の
G9の定め方のまま変更しない。プログラムの各行を打ち終えた時点、`cls`
を打つ前の状態で、`--nonblank-summary-rows`により打った行数ぶんの
非空白セルを含む行数が実際に打った行数と一致することを確認する）。

## 2. 前の写し（フレームの決め方）

「前の写し」は、**`cls`の後、`Ok`が出た後**に取る。フレームの決め方は
次のとおり（`l4-s5d`のD12・`l4-s5e`のE1・E2で使った「前段の応答を
確認してから次の打鍵へ進む」考え方をそのまま踏襲する）。

```
prog        = "new\n" + プログラムの各行（それぞれ末尾に\n） を連結
              した文字列（cls・runは含まない）
n_prog      = len(prog)
line_end_prog = 700 + 8 * n_prog

【G9の確認】: line_end_prog の直後（+20フレーム。l4-s1c・l4-s3aで
使ってきた「実行の余裕」の既定値と同じ）に単独の写しを取り、
--nonblank-summary-rowsで行数を確認する。

cls_str     = "cls\n"
line_end_cls = line_end_prog + 8 * len(cls_str)   （clsはprogに続けて
              同じ--type文字列で打つ。line_end_progの直後から数える）
dump_precls = line_end_cls + 300   （clsのOkが出るまでの余裕。l4-s4d
              追補以来の全腕一律+300フレームと同じ値を使う）
```

`dump_precls`が「前の写し」（本体「条件・器具」節で言う`--diff-before`
に相当する写し）になる。この時点で`Ok`相当の応答が出ていること（関門
G8相当）を確認したうえで、`run`の打鍵をこの時刻から続けて打つ。

```
run_str     = "run\n"（＋P8のみ入力値。後述）
type_at_run = dump_precls
line_end_run = type_at_run + 8 * len(run_str)
dump_final  = line_end_run + 300      （「後の写し」＝本体の
              --diff-afterに相当）
run_frames  = dump_final + 200
```

P8（`INPUT`）は、`l4-s5e`のE1・E2と同じ考え方で、`run`の後にプロンプト
が出るまでの余裕（+300フレーム）を挟んでから入力値`5,3\n`を打つ（本体
「P8（INPUT）の打鍵タイミング」節の式の`type_at2`を、本追補の
`dump_final`に読み替える）。

## 3. 関門G10の対象

関門G10（出力が画面に収まっていること）は、**`run`の後の出力**につい
て確かめる（`origin_row`＝`run`を打った行から`ok_row`＝`Ok`の行までの
行数が、画面の行数を超えていないこと）。`cls`前のプログラム打ち込み
そのもののスクロール（本追補が対処する対象）は、G10の対象にしない
（G10は「比べるもの」の対象である`run`後の出力にのみ適用する、という
本体の定義を変えない）。

## 4. 自作ROM側の扱い

自作ROM側は、**`CLS`を実装するまで本場面の照合ができない**（腕の手順
自体が`cls`を含むため）。実装が済むまでは、本体で定めたとおり
`not_implemented_yet`として記録し、判定から外す（新しい判定名は本
追補でも作らない）。

## 変更しないもの

本体の腕（P1〜P8）・「比べるもの・正規化」節の定義・期待値ファイルの
書式・判定名（`conform`/`not_conform`/`not_implemented_yet`/
`gate_failed`）・関門G1〜G5・G8〜G10の定義そのもの（適用する時刻・
対象が変わる点を除く）・検出力の自己検査は変更しない。本追補が変える
のは、腕の手順に`cls`を挟むこと（第1節）、「前の写し」を取る時刻
（第2節）、G9・G10の適用時点の確認（第3節・本体のG9定義は不変）、
自作側が`CLS`実装まで照合できないという明記（第4節）だけである。

## 結果ノートへの反映

`docs/notes/l4-c5-representative-programs-conformance-scene-results.md`
に、本追補の手順（`cls`を挟む）で測定したことを明記し、P2・P3・P6で
実際にスクロールが起きていたかどうか（`cls`を挟む前の試走での事実と
して）を記述する。

## 根拠リンク

[l4-c5-representative-programs-conformance-scene-preregistration.md](l4-c5-representative-programs-conformance-scene-preregistration.md)
（`2837926`、本体の腕・関門・判定名の原型）・`e5a6f1f`（器具
`tools/l4_program_conform_record.py`、試走でスクロールを検出した根拠）
・[l4-s5f-screen-commands-preregistration.md](l4-s5f-screen-commands-preregistration.md)
の測定`7fbc47c`（`CLS`の振る舞い、消去後に`Ok`相当・最下行が残るという
既知の観測）・`docs/spec/l4-program.md`第6版（`CLS`の観測済み記載）・
[l4-s5d-conditional-comparison-logic-array-cont-preregistration.md](l4-s5d-conditional-comparison-logic-array-cont-preregistration.md)
（D12、前段の応答を確認してから続けて打つ考え方の原型）・
[l4-s5e-input-string-numeric-functions-preregistration.md](l4-s5e-input-string-numeric-functions-preregistration.md)
（E1・E2、INPUTのプロンプト待ちの原型）。
