# l4-c5 事前登録 追補3 — 代表プログラムは17行以内、腕の入力は測定直前のtests/programs

記録日: 2026-09-16
状態: 事前登録の追補、測定前
対象: [l4-c5-representative-programs-conformance-scene-preregistration.md](l4-c5-representative-programs-conformance-scene-preregistration.md)
（`2837926`）・[追補1](l4-c5-representative-programs-conformance-scene-preregistration-addendum.md)
（`ebe29dc`）・[追補2](l4-c5-representative-programs-conformance-scene-preregistration-addendum2.md)
（`89b503e`）を上書きする形で追補する。本体・追補1・追補2は書き換え
ない。

## 経緯

器具（`tools/l4_program_conform_record.py`、追補2の手順を反映した版
`54a4cdc`）の試走で、追補2の手順（`new`→`cls`→各行→G9確認→`cls`→
前の写し→`run`→…）でも、**P3（`p03_bubble_sort.bas`、19行）は依然
としてG9が合わなかった**。

原因は、`new`直後の`cls`の実行によって現れる`Ok`行（1行）と、その後に
打つプログラムの各行（P3は19行）と、最後の行を打った後のEnterで
カーソルが進む先の行（1行）を合わせると、画面で使える行数（20行から
ファンクションキー行1行を引いた19行）を超えるためである。

```
1（最初のclsのOk） + 19（P3のプログラム行） + 1（最後のEnterで
  カーソルが進む先の行） = 21 > 19（使える行数）
```

P3は19行ちょうどでも、`Ok`行と最後のEnterの分を合わせると2行分足り
ない。開発者判断により、**P3を`:`で文をまとめて17行以内に書き直す**
ことにした（プログラムの働きと出力は変えない。1行に複数の文を`:`で
つなぐ書式は`l4-s5g`で観測済みであり、新しい未観測の機能を使うことに
はならない）。書き直しは器具の担当が`tests/programs`を直して別に
コミットする（本ノートの担当範囲外）。

## 1. 代表プログラム集の決まり: 1本は17行以内

```
1（最初のclsのOk） + N（プログラムの行数） + 1（最後のEnterで
  カーソルが進む先の行） ≤ 19（画面で使える行数、最下行を除く）
  ⟺ N ≤ 17
```

**代表プログラム集の各プログラムは、以後17行以内でなければならない**
（`Ok`行＋プログラム＋最後のEnterが、使える19行に収まるため）。8本の
うち17行を超えるもの（本追補の時点ではP3のみ）は、`:`で文をまとめる
等、観測済みの機能の範囲で17行以内に収めた版に差し替える。

## 2. 腕の入力は測定直前のtests/programs、コミットハッシュの記録

代表プログラム集（`tests/programs`）は、器具の担当による書き直し
（第1節、別コミット）を経て変わりうる。腕の打鍵内容がどのコミットの
`tests/programs`に基づくかが不明確だと、期待値と自作側の照合が別の
版のプログラムを比べることになりかねない。これを避けるため、次を
定める。

- **腕の入力（各プログラムの打鍵文字列）は、公式側の期待値の測定を
  始める直前のコミットの`tests/programs`とする。**
- 測定の結果ノート（`docs/notes/l4-c5-representative-programs-
  conformance-scene-results.md`）に、**そのコミットハッシュを明記
  する**。
- **測定の後に`tests/programs`を変えたら、その期待値は使えなくなる**
  （プログラムの内容が変わればエコー・出力のセル並びも変わるため）。
  `tests/programs`を変えた場合は、変更後のコミットで期待値を測り
  直す。

**関門として追加する（本体・追補1・追補2のG1〜G10に加える）**:

- **G11（新設）: 測定開始時に参照した`tests/programs`のコミットと、
  期待値ファイル（`tests/conformance/expected_l4_programs.tsv`）を
  コミットした時点の`tests/programs`が、同一のコミット（内容が同一）
  であること。** `git log`・`git diff`で、期待値コミット前後で
  `tests/programs`配下に変更が無いことを確認する。一致しなければ、
  期待値ファイルはコミットしない（測定をやり直す）。

## 変更しないもの

本体・追補1・追補2の腕（P1〜P8。ただし第1節によりP3の中身は将来
差し替わりうる）・「比べるもの・正規化」節の定義・期待値ファイルの
書式・判定名・関門G1〜G10の定義・`cls`を挟む手順・G9の確認方法・
検出力の自己検査は変更しない。本追補が変えるのは、代表プログラム集の
行数の上限（17行、第1節）と、腕の入力の版を固定しコミットハッシュを
記録する運用・関門G11の新設（第2節）だけである。

## 結果ノートへの反映

`docs/notes/l4-c5-representative-programs-conformance-scene-results.md`
に、測定時に参照した`tests/programs`のコミットハッシュを明記し、G11
の確認結果（期待値コミット時点との一致）を記載する。P3が17行以内に
収まったバージョンで測定したことも明記する。

## 根拠リンク

[l4-c5-representative-programs-conformance-scene-preregistration.md](l4-c5-representative-programs-conformance-scene-preregistration.md)
（`2837926`）・
[l4-c5-representative-programs-conformance-scene-preregistration-addendum.md](l4-c5-representative-programs-conformance-scene-preregistration-addendum.md)
（`ebe29dc`、追補1）・
[l4-c5-representative-programs-conformance-scene-preregistration-addendum2.md](l4-c5-representative-programs-conformance-scene-preregistration-addendum2.md)
（`89b503e`、追補2。G9の確認方法・`cls`を挟む手順の直接の原型）・
`54a4cdc`（器具、追補2反映版。試走でP3のみG9不一致〔行数超過〕が
判明した根拠）・`324acb7`（`tests/programs`下書き、P3の元の19行版の
出所）・[l4-s5g-read-data-rem-multi-statement-preregistration.md](l4-s5g-read-data-rem-multi-statement-preregistration.md)
（1行に複数の文〔`:`〕が観測済みであることの根拠。P3書き直しの手段）。
