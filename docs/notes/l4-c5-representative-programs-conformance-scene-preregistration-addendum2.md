# l4-c5 事前登録 追補2 — newの直後にもcls、G9は画面全体で打った行を数える

記録日: 2026-09-16
状態: 事前登録の追補、測定前
対象: [l4-c5-representative-programs-conformance-scene-preregistration.md](l4-c5-representative-programs-conformance-scene-preregistration.md)
（`2837926`）・[追補](l4-c5-representative-programs-conformance-scene-preregistration-addendum.md)
（`ebe29dc`）を上書きする形で追補する。本体・追補1は書き換えない。

## 経緯

器具（`tools/l4_program_conform_record.py`、追補1の手順を反映した版
`63d96d9`）の試走で、8本すべて`Ok`行が見つかり画面（20行）にも収まっ
たが、**関門G9（打鍵が全部届いたこと）だけP3（`p03_bubble_sort.bas`、
19行）で合わなかった**。

G9はこれまで「起動時のバナーがある0〜5行程度を数えない」定め方だった
（本体・追補1のいずれも、`new`直後は画面上部にバナーが残っている前提
で、プログラムの行が現れる範囲をその下に限定して数えていた）。P3は
19行と長く、打ち込んでいる間に画面がスクロールし、プログラムの行が
バナーのあった範囲へ押し上げられたため、この「バナーを除いた範囲」
という決め方では行数が合わなくなった。

本追補は、公式側の期待値の測定を始める前に、この不整合を解消する。

## 1. 腕の手順の変更

腕の打鍵手順を、次のとおり変更する（追補1からの差分は下線部相当の
「`new`の直後の`cls`」の追加のみ）。

```
new → cls → プログラムの各行 → 【関門G9の確認】 → cls → 【前の写し】
    → run →（INPUTのある腕は値）→ 【後の写し】
```

最初の`cls`で起動時のバナーを消してから、プログラムの行を打ち始める。
これにより、プログラムの行を打っている間、画面には**プログラムの行
だけ**が現れる状態になり、バナーの有無で数える範囲を場合分けする必要
が無くなる。

フレームの決め方（追補1の式を、`new`直後の`cls`を挟む形に拡張する）:

```
head        = "new\ncls\n"
n_head      = len(head)                     （= 8）
line_end_head = 700 + 8 * n_head            （最初のclsまで、継続した
                                               1つの--type文字列として
                                               打つ）

body        = プログラムの各行（それぞれ末尾に\n）を連結した文字列
              （cls・runは含まない）
n_body      = len(body)
line_end_body = line_end_head + 8 * n_body   （bodyもheadに続けて同じ
                                               --type文字列で打つ）

【G9の確認】: line_end_body の直後（+20フレーム。追補1・l4-s1c・
l4-s3aと同じ「実行の余裕」の既定値）に単独の写しを取る。

cls2_str    = "cls\n"
line_end_cls2 = line_end_body + 8 * len(cls2_str)
dump_precls2 = line_end_cls2 + 300           （2つ目のclsのOkが出る
                                               までの余裕。追補1と同じ
                                               +300フレーム）
```

`dump_precls2`が「前の写し」になる。以降（`run`・入力値・「後の写し」
のフレーム式）は追補1の該当箇所をそのまま使う（`type_at_run =
dump_precls2`から数える）。

## 2. G9の定め方（画面全体で打った行を数える）

最初の`cls`の後は画面にバナーが無いため、G9の確認範囲を次のとおり
定め直す。

**ファンクションキーの行（最下行）を除く画面全体で、打った行（行番号
で始まる行）が、プログラムの行数だけ見えていることを確かめる。**

- 数え方は既存の道具だけを使う。`tools/l4_vram_probe.py
  --nonblank-summary-rows`で、最下行を除く各行の非空白セルの有無
  （件数）を見て、非空白の行数を数える。あるいは、`tools/
  l4_list_classify.py`（`l4-s5a`、`d330dd2`）の「行番号で始まる行だけ
  を数える」考え方を件数の確認にだけ流用してもよい（**いずれも文字
  コード・文言は一切出さない**。件数だけを見る）。
- **打った行の数と、非空白（または行番号で始まると判定できる）行の
  数が一致すること**をG9の判定基準とする（本体のG9の「打った行数と
  一致すること」という基準そのものは変えない。数える対象範囲を
  「バナーを除いた範囲」から「最下行を除く画面全体」に変えるだけ）。
- **最後の行を打った後のEnter（改行）で画面が1行スクロールしても、
  行数は保たれる。** 画面がちょうど埋まった状態で最後の`\n`を打つと、
  最上行（プログラムの1行目）が画面外へ押し出され、代わりに最下行の
  1つ上に空行が現れる形でスクロールが起きうるが、これは「1行減って
  1行増える」動きであり、**非空白行の総数は変わらない**。したがって
  G9の判定基準（打った行数と一致すること）は、このスクロールが起きた
  かどうかによらず成立する。

## 3. 画面の行数を超えるプログラムの扱い

代表プログラム集（`tests/programs`）の8本のうち最長はP3（19行）で
あり、**画面の行数（20行、既定表示。ファンクションキー行を含む）より
多い行のプログラムは代表プログラム集に無い**。19行はファンクション
キー行を除く19行（＝画面のプログラム表示に使える最大行数、20行から
最下行1行を引いた数）にちょうど収まる。

もし将来、画面の行数を超える行数のプログラムが代表プログラム集に加わ
った場合、**G9の確認方法（「最後の行を打っても行数が保たれる」という
前提）が成り立たなくなる**（打っている間に本体プログラムの一部が
画面外へ完全に押し出され、`--nonblank-summary-rows`等で数えられる範囲
に収まらなくなるため）。その場合はG9を`gate_failed`扱いとし、その
腕を判定から外す（本体・追補1の「関門のいずれかが偽の腕は
`gate_failed`として判定に含めない」という扱いをそのまま適用する。
新しい判定名は作らない）。

## 変更しないもの

本体・追補1の腕（P1〜P8）・「比べるもの・正規化」節の定義・期待値
ファイルの書式・判定名・関門G1〜G5・G8・G10の定義・検出力の自己検査
は変更しない。追補1で定めた「`run`の前に`cls`を挟む」「前の写しは
`cls`のOk後に取る」という設計思想もそのまま引き継ぐ。本追補が変える
のは、`new`の直後にもう1つ`cls`を挟むこと（第1節）、G9の確認範囲を
「バナーを除いた範囲」から「最下行を除く画面全体」に変えること
（第2節）、画面の行数を超えるプログラムが将来加わった場合の扱い
（第3節）の3点だけである。

## 結果ノートへの反映

`docs/notes/l4-c5-representative-programs-conformance-scene-results.md`
に、本追補の手順（`new`直後にも`cls`を挟む）で測定したことを明記し、
P3で実際にG9が成立したか（追補2適用後の確認結果）を記述する。

## 根拠リンク

[l4-c5-representative-programs-conformance-scene-preregistration.md](l4-c5-representative-programs-conformance-scene-preregistration.md)
（`2837926`、本体の腕・関門G9の原型）・
[l4-c5-representative-programs-conformance-scene-preregistration-addendum.md](l4-c5-representative-programs-conformance-scene-preregistration-addendum.md)
（`ebe29dc`、追補1。`run`前の`cls`・前の写しの時刻の直接の原型）・
`63d96d9`（器具、追補1反映版。試走でP3のみG9不一致が判明した根拠）・
`tools/l4_program_conform_record.py`・`tools/l4_vram_probe.py`
（`--nonblank-summary-rows`）・[l4-s5a-program-line-input-list-format-preregistration.md](l4-s5a-program-line-input-list-format-preregistration.md)
（`tools/l4_list_classify.py`、`d330dd2`。行番号で始まる行を数える
考え方の原型）。
