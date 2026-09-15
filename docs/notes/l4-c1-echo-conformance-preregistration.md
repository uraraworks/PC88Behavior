# l4-c1 — 打鍵エコーの公式・自作比較 — 事前登録

記録日: 2026-09-15
状態: 事前登録、測定前

## 位置づけ

段階2c（仕様書 `docs/spec/l3-main.md` 第3版 `fc14e8f` に合わせて自作 main ROM を
書く実装、本ノート作成時点で並行して作業中）の自作 main ROM の HEAD を使い、
公式ROM一式と打鍵エコーを比べる。比べる相手は常に公式ROM一式であり、自作側は
本測定を実施する時点の自作 main ROM の HEAD を使う。これはゴールA の完了条件
（公式と同じ出力）に向けた最初の場面であり、M8（第三者が回せる適合テスト）の
新しい種類のテストになる。

l4-s1a〜l4-s1e はいずれも公式ROM単体の観測（仕様書の記述の裏付け）だったが、
本測定は公式ROMと自作ROMの**2系統を同じ条件で走らせて比較する**、初めての
適合テストである。

## 比べるもの

- 打鍵の前と後の写しの差分（`tools/l4_vram_probe.py --diff-before/--diff-after
  --count-only-rows 19`）
- 「前が空白だったセル」の並び: 最初に変わったセルを原点とした相対の桁
  （と相対の行）と、文字コード
- エコーの行の属性域40バイト（既定の並びとの一致）
- バナーの行・ファンクションキーの行は比べない（バナーは禁止事項6で定義上
  一致しない。ファンクションキーの行は ROM のデータ）
- 位置の絶対値は比べない（バナーの行数が違うのでエコーの行が異なる）

## 腕

RETURN を含む腕は入れない（公式は BASIC として実行し、自作はまだ BASIC を
持たない）。起動settleは公式ROMの既存測定（l4-s1a〜l4-s1e）と同じ
`--type-at 300 --type '\n'` を両ROM側に共通で使う。実打鍵の開始は
`tools/conform_l3.sh` の全シナリオが採る `--type-at 700` を踏襲する
（l4-s1a・l4-s1c 事前登録の根拠と同じ）。1文字あたりの反映フレームは
`--key-hold`/`--key-gap` 既定値（各4フレーム）による `hold+gap=8` フレーム/文字
（l4-s1c 事前登録「打鍵と走行フレームの決め方」節と同じ根拠）。写し(前)は
`--type-at` の10フレーム前（l4-s1b Q2 の `写し(前)=690`〔frame700の10フレーム前〕
と同じ間隔）とする。

- **E1** `--type` で英数字（`ab12`、4文字、RETURN なし）
  - `--vram-dump-at 690`（前）、`--vram-dump-at 752`（後 = 700 + 8×4 + 20。
    +20は l4-s1c 事前登録が定めた「実行の余裕」をそのまま踏襲、根拠は同節）
  - 走行フレーム数: 952（後写し + 200、l4-s1a・l4-s1c の余裕の踏襲）
- **E2** `--type` で記号（`":(),.;`、7文字、打鍵注入で打てるもの。l4-s1a・
  l4-s1c が実際に使えたと確認した記号のみを使う）
  - `--vram-dump-at 690`（前）、`--vram-dump-at 776`（後 = 700 + 8×7 + 20）
  - 走行フレーム数: 976
- **E3** `--key-matrix` で修飾つき（SHIFT・CAPS・カナ・GRPH の4種、それぞれ
  Q（`04H`D1）・A（`02H`D1）の2キーずつ、計8組。port:bit の対応は
  l4-s1b Q1結果（`docs/notes/l4-s1b-key-matrix-results-q1q3.md`）による。
  修飾キーの port:bit は同ノートの表から、SHIFT・CAPS・カナ・GRPH それぞれ
  の欄を測定担当が実測前に確認する）
  - 押し方は l4-s1b Q2 の手順をそのまま流用: 修飾を frame700・HOLD30で
    押しっぱなしにし、文字キー（Q または A）を frame710・HOLD既定(4)で押す
  - `--vram-dump-at 690`（前）、`--vram-dump-at 724`（後 = 710 + 4 + D。
    D=10 は l4-s1b Q1〜Q2 が固定した値をそのまま流用、根拠は
    `docs/notes/l4-s1b-key-matrix-results-q1q3.md`「D=10に決定」節）
  - 走行フレーム数: 900（l4-s1b Q2 と同一）
- **E4** 80桁を超える打鍵（`a` を85回、RETURN なし。行の折り返しの位置と形
  を見る）
  - `--vram-dump-at 690`（前）、`--vram-dump-at 1400`（後 = 700 + 8×85 + 20）
  - 走行フレーム数: 1600

腕の総数: E1(1) + E2(1) + E3(8) + E4(1) = **11腕**。各腕を公式ROM・自作ROMの
両方で走らせ、それぞれ2走ずつ行う（G3 決定論性）。延べ走行数 = 11腕 × 2ROM ×
2走 = 44走。

## 記録する内容

今日（2026-09-15）の別測定で「件数だけ記録して値を残さなかった」
「どの行を見たか残さなかった」ことが後から確かめられなくなった経緯があるため、
結果ノートには腕ごと・両ROMごとに、次を機械可読な表として必ず載せる。

1. 差分モード（`--diff-before/--diff-after`、E3は`--count-only-rows 19`併用）
   で得た「前が空白だったセル」について、**原点に選んだセルの絶対位置
   (row0, col0)**。原点は「前が空白だったセル」一覧を row0 昇順・同じ row0
   内では col0 昇順に並べた先頭の1件とする
2. 上記1で選んだ原点を基準にした、「前が空白だったセル」全件の
   **(相対の行 = row0−原点row0, 相対の桁 = col0−原点col0, 文字コード16進)**
   の並びそのもの（出現順＝row0昇順・col0昇順）
3. エコーの行の **row0** と、その行の**属性域40バイト**（16進、前後とも）
4. 最下行（`--count-only-rows 19`）の変化件数（文字域・属性域それぞれ、
   件数のみ。位置・値は出さない）
5. 「前が空白でなかったセル」の件数（位置・値は出さない。差分モードの
   出力仕様どおり `(row0, col0, addr)` と「前が空白でない」印だけが対象。
   本ノートでは件数に集約する）

## 本文を出さない

- 公式側・自作側とも、エコーのセルは自分が打った文字の反映（自分で決めた
  打鍵文字列）なので、コードを出してよい（l4-s1b と同じ扱い）
- 「前が空白でなかったセル」・最下行は件数だけ（`tools/l4_vram_probe.py` の
  `--count-only-rows` がそのための機能）
- バナー行・ファンクションキー行の文字そのものは出さない（比べない対象な
  ので、そもそも走査の対象に含めない）
- 写し・記録・iolog は使い捨ての作業ディレクトリ（リポジトリ外）に置き、
  結果ノートを書いたら削除する

## 関門

- G1 器具の自己検査: 測定時 HEAD（公式ROM測定用・自作ROM測定用それぞれの
  q88measure ビルド）で `tools/harness/vram_dump_selftest.sh`・
  `tools/harness/vram_dump_dynamic_selftest.sh`・
  `tools/harness/mem_write_log_selftest.sh`・
  `tools/harness/key_matrix_selftest.sh`・`tools/screen_content_leak_selftest.sh`
  の全項目が OK
- G2 取りこぼし0・打てない文字の警告0（44走すべてのstderrで確認）
- G3 決定論性: 各腕・各ROM側で2走とも、写しはファイルの sha256 が一致、
  記録（本ノートに載せるデータ行）は sha256 が一致
- G4 陰性対照: 何も打たない走（起動settleのみ）で、両ROM側とも差分（文字域・
  属性域とも）が0件
- G5 自作ROM側の `tools/l3_main_selftest.sh` が、測定時 HEAD で rc=0

判定の前に G1〜G5 がすべて真であること。いずれかが偽の腕は、その腕を
`gate_failed` として判定に含めず、理由を記述する。

## 判定

- 腕ごとに `echo_matches` または `echo_differs` の2つの判定名だけを使う。
  - `echo_matches`: 記録する内容の1〜5すべてで、公式ROM側と自作ROM側が
    完全に一致する（相対座標の並び・文字コード・属性域40バイト・最下行の
    変化件数・前が空白でなかったセルの件数のすべて）
  - `echo_differs`: 上記のいずれかが一致しない。**この判定名以外は作らない**。
    一致しない具体的な形（最初に違う相対セルの位置と両側のコード、属性域の
    どのバイトが違うか等）を判定名の後に文章で記述する
- 全腕の集計: 11腕中 `echo_matches` の数／`echo_differs` の数を表にする

## 判定後の行き先

- 全腕 `echo_matches` なら、この場面を conform の場面として、期待値
  （公式2走の相対座標・文字コード・属性域の並びと SHA-256）を固定する
  （M6 の `expected.tsv` と同じ作法。値はリポジトリに持たない。ハッシュと
  形だけを結果ノートに書く）
- `echo_differs` を含む場合は、違いの形を仕様書 `docs/spec/l3-main.md` の
  観測節と突き合わせ、自作 main ROM 側の実装差か仕様の未解釈かを切り分ける
  次の作業（別セッション）の入力にする

## 結果ノート

`docs/notes/l4-c1-echo-conformance-results.md` に書く。関門・指標・判定と
数え方を後から動かさない。

## 根拠リンク

[l4-s1a-text-vram-preregistration](l4-s1a-text-vram-preregistration.md)・
[l4-s1a-text-vram-results](l4-s1a-text-vram-results.md)（`--type-at 700` の
由来）・
[l4-s1b-key-matrix-preregistration](l4-s1b-key-matrix-preregistration.md)・
[l4-s1b-key-matrix-results-q1q3](l4-s1b-key-matrix-results-q1q3.md)（port:bit
対応表、D=10の決定）・
[l4-s1b-key-matrix-results-q2](l4-s1b-key-matrix-results-q2.md)（修飾つき打鍵の
押し方: 修飾HOLD30・文字キー既定HOLD、写し(前)=690の間隔）・
[l4-s1c-attribute-values-preregistration](l4-s1c-attribute-values-preregistration.md)
（1文字8フレーム、実行の余裕+20フレームの根拠）・
[l4-s1d-a3m-reproduction-preregistration](l4-s1d-a3m-reproduction-preregistration.md)・
[l4-s1e-default-attr-and-scroll-range-preregistration](l4-s1e-default-attr-and-scroll-range-preregistration.md)
（既定の属性域の並び、事前登録の書式）・
`docs/spec/l3-main.md` 第3版（`fc14e8f`、比較の基準にする仕様）・
`tools/l4_vram_probe.py`（差分モード・`--count-only-rows` の出力範囲）・
`tools/conform_l3.sh`（`--type-at 700` を採る既存シナリオ）・
`tools/l3_main_selftest.sh`（自作ROM側の関門G5）・
`tools/harness/vram_dump_selftest.sh`・`tools/harness/vram_dump_dynamic_selftest.sh`・
`tools/harness/mem_write_log_selftest.sh`・`tools/harness/key_matrix_selftest.sh`・
`tools/screen_content_leak_selftest.sh`（関門G1の器具自己検査）。
