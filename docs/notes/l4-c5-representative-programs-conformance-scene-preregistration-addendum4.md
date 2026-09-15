# l4-c5 事前登録 追補4 — runの後の待ちを全腕+3000フレームへ、速さは比べない

記録日: 2026-09-16
状態: 事前登録の追補、測定前
対象: [l4-c5-representative-programs-conformance-scene-preregistration.md](l4-c5-representative-programs-conformance-scene-preregistration.md)
（`2837926`）・[追補1](l4-c5-representative-programs-conformance-scene-preregistration-addendum.md)
（`ebe29dc`）・[追補2](l4-c5-representative-programs-conformance-scene-preregistration-addendum2.md)
（`89b503e`）・[追補3](l4-c5-representative-programs-conformance-scene-preregistration-addendum3.md)
（`f0172d0`）を上書きする形で追補する。本体・追補1〜3は書き換えない。

## 経緯

自作ROM側の照合で、P2（`p02_primes.bas`）が`ok_row_not_found`になった。
原因を切り分けた結果、実装の誤りではなく、**自作のインタプリタが公式
より実行が遅く、`run`の後の待ち（本体・追補1〜3の既定`+300`フレーム）
の間に実行が終わらなかった**ことによるものと分かった（修正担当の
報告）。待ちを広げて測り直したところ、自作の出力は件数・`Ok`の相対
位置・SHA-256のいずれも公式側の期待値（`67aa02b`）と完全に一致した。

本追補は、公式側の期待値の測定を始める前に、この待ちの扱いを見直して
定める。

## 1. 適合で比べるのは「実行が終わった後の画面」であり、速さは比べない

ゴールA（代表プログラムが動く）の定義は、プログラムを実行した結果の
画面が公式と一致することであり、**実行にかかる時間（速さ）は比較の
対象に含めない**。本体「比べるもの・正規化」節が定める比較対象
（`run`の打鍵のエコー行の次の行から、最後の`Ok`行の前の行までのセル
の並び、`Ok`行の相対位置）は、この節でも変更しない。速さの違いは、
実行結果が同じである限り不適合の理由にしない。

## 2. runの後の待ちを全腕一律+3000フレームへ延ばす

`run`（および`INPUT`のある腕は、入力値を打った後）から「後の写し」
までの待ちを、**全腕一律に**`+300`フレームから**`+3000`フレーム**へ
延ばす。**自作ROM側だけを延ばすのではなく、公式ROM側を含む全腕・
全走に一律で適用する**（自作の遅さに合わせて自作だけ特別扱いすると、
「同じ条件で比べる」という適合テストの前提が崩れるため）。

- 本体の`dump_final = line_end_run + 300`という式を、以後**`dump_final
  = line_end_run + 3000`**に置き換える（`run_frames = dump_final +
  200`は変えない）。
- `cls`前後の待ち（追補1・追補2の`+300`フレーム、G9確認の`+20`フレー
  ム）は変更しない（`cls`の実行はプログラムの`RUN`と異なり、公式・
  自作の速度差が問題になった箇所ではないため）。
- **関門G8（`Ok`行が現れていること）は、完了の関門としてそのまま
  使う。** 待ちを延ばしても`Ok`行が現れない腕は、引き続き
  `gate_failed`とし「写しが早すぎた」と記述する（延ばした`+3000`
  フレームでもなお終わらない実装があれば、それはG8がそのまま検出
  する）。

## 3. 公式側の期待値の測り直しと、既存期待値との一致確認

公式側の期待値（`tests/conformance/expected_l4_programs.tsv`）は、
延ばした待ち（`+3000`フレーム）で**測り直す**。

- 各腕2走で記録（cell_count・ok_relative_row・sha256）が一致すること
  （本体の関門G3のとおり）。
- **加えて、測り直した記録が、既存の期待値（測定`67aa02b`、`+300`
  フレームで測ったもの）とcell_count・ok_relative_row・sha256のすべて
  で完全一致することを関門に加える**（実行が終わった後の画面は待ちの
  長さによらず変わらないはずだが、それは確かめて初めて言えることで
  あり、前提として押し通さない）。
- **一致しない腕があれば、期待値ファイルを差し替えない。** その事実
  （どの腕で、cell_count・ok_relative_row・SHA-256のどれが不一致
  だったか。値そのものは出さない）を報告し、測定を止める（原因を
  切り分けてから再度事前登録の手順を見直す）。

## 4. 速さの記録（判定とは別の観察）

`run`の打鍵（またはINPUTの値の打鍵）から`Ok`行が現れるまでのフレーム
数は、**判定とは別の観察として**、公式ROM側・自作ROM側の両方で記録
してよい。記録できる範囲は、写しの間隔（何フレーム後の写しで`Ok`行
が現れたか）から分かる程度の粗い値にとどめる（`+3000`フレームの窓の
中のどの時点かを2分探索的に絞り込む、といった追加の測定は本ノートの
範囲外とする）。この観察は「比べるもの」（第1節）には含めず、判定
（`conform`/`not_conform`等）にも影響させない。

## 変更しないもの

本体・追補1〜3の腕（P1〜P8）・「比べるもの・正規化」節の対象定義・
期待値ファイルの書式・判定名・関門G1〜G7・G9〜G11の定義・`cls`を挟む
手順・G9の確認方法・代表プログラムの17行以内という決まり・腕の入力を
測定直前の`tests/programs`に固定する運用・検出力の自己検査は変更
しない。本追補が変えるのは、`run`後の待ちを全腕一律`+3000`フレームへ
延ばすこと（第2節）、公式側の期待値を測り直し既存期待値との一致を
関門に加えること（第3節）、速さを判定に含めない観察として記録できる
ようにすること（第1節・第4節）だけである。

## 結果ノートへの反映

`docs/notes/l4-c5-representative-programs-conformance-scene-results.md`
に、`+3000`フレームで測り直したことと、既存期待値（`67aa02b`）との
一致確認の結果を明記する。速さの観察（フレーム数、公式・自作それぞれ）
を、判定とは別の節として記載する。

## 根拠リンク

[l4-c5-representative-programs-conformance-scene-preregistration.md](l4-c5-representative-programs-conformance-scene-preregistration.md)
（`2837926`）・
[l4-c5-representative-programs-conformance-scene-preregistration-addendum.md](l4-c5-representative-programs-conformance-scene-preregistration-addendum.md)
（`ebe29dc`、追補1）・
[l4-c5-representative-programs-conformance-scene-preregistration-addendum2.md](l4-c5-representative-programs-conformance-scene-preregistration-addendum2.md)
（`89b503e`、追補2）・
[l4-c5-representative-programs-conformance-scene-preregistration-addendum3.md](l4-c5-representative-programs-conformance-scene-preregistration-addendum3.md)
（`f0172d0`、追補3。フレーム式・関門の直接の原型）・`67aa02b`（公式側
既存期待値の測定。本追補で一致確認の対象とする既存記録の出所）・
自作ROM側の修正担当の報告（P2が`run`後の待ち不足で`ok_row_not_found`
になっていた原因の切り分け、本追補の直接の理由）。
