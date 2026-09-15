# l4-c1b — 打鍵エコー適合の場面固定 — 事前登録

記録日: 2026-09-15
状態: 事前登録、期待値の再導出前

## 位置づけ

`l4-c1`（事前登録 `13ceb2e`、結果 `1817efb`、追記 `e975d49`）で、公式ROM一式と
自作main ROM（段階2c、仕様書 `docs/spec/l3-main.md` 第3版 `fc14e8f` 準拠）の
打鍵エコーを11腕で比べ、9腕 `echo_matches`・2腕（E3のSHIFT×Q・SHIFT×A）
`echo_differs` だった。`echo_differs` の中身は、記録項目1・2・3・5
（相対座標と文字コードの並び・原点のセル以外の形・エコー行の属性域40バイト・
前が空白でなかったセルの件数）はすべて一致し、違うのは記録項目4（最下行＝
ファンクションキー表示行の変化件数）だけだった。開発者判断（2026-09-15、
`e975d49` の追記）により、最下行は当面バナー行と同じ扱いで比較対象から外す
と決まっている。

本ノートは、この「最下行を除いた打鍵エコー」を M6 の適合テスト
（`tools/conform_l3.sh`、期待値 `tests/conformance/expected*.tsv`）と同じ
作法——**期待値は件数とSHA-256だけをコミットし、値そのものは持たない**——
で、以後いつでも回せる適合の場面として固定するための事前登録である
（M7・M8）。腕・打鍵・フレームは `l4-c1` の11腕をそのまま使い、比べる内容と
判定基準だけを「最下行を除く」形に確定し直す。

## 比べるもの（最下行は比較しない）

- 打鍵の前と後の写しの差分（`tools/l4_vram_probe.py --diff-before/--diff-after
  --count-only-rows 19`。**必ずこのオプションを付ける**）
- 記録項目1: 「前が空白だったセル」一覧を row0昇順・同row0内col0昇順に
  並べた先頭の1件を原点(row0,col0)とする
- 記録項目2: 原点を基準にした「前が空白だったセル」全件の
  (相対の行, 相対の桁, 文字コード16進)の並び（出現順＝row0昇順・col0昇順）
- 記録項目3: エコーの行（文字域に変化があった行。row19は含まない）ごとの、
  原点基準の相対行と、その行の属性域40バイト（16進、前後とも）
- 記録項目5: 「前が空白でなかったセル」の件数（位置・値は出さない）
- **最下行（row19、`--count-only-rows 19` で件数だけ集計される行）は
  比較の対象に含めない**（`l4-c1` 追記の開発者判断どおり、バナー行と
  同じ扱い）。位置の絶対値（row0そのもの）も比べない（バナー行数の違いで
  両ROM間の比較には使えないため、`l4-c1` と同じ理由）

## 腕

`l4-c1` の11腕をそのまま使う。腕の定義・打鍵内容・フレーム指定は
`docs/notes/l4-c1-echo-conformance-preregistration.md`「腕」節と同一
（変更しない）。

- E1 英数字 `ab12`（写し690/752、走行952F）
- E2 記号 `":(),.;`（写し690/776、走行976F）
- E3 修飾つき8組（SHIFT・CAPS・カナ・GRPHそれぞれQ・A。修飾を frame700・
  HOLD30、文字キーを frame710・HOLD既定(4)、写し690/724、走行900F。
  port:bit は `l4-c1` 結果ノートの表: SHIFT=08H:6、CAPS=0AH:7、
  カナ=08H:5、GRPH=08H:4、Q=04H:1、A=02H:1）
- E4 80桁超 `a`×85（写し690/1400、走行1600F）

腕の総数: E1(1) + E2(1) + E3(8) + E4(1) = **11腕**。

## 期待値の作り方

- 公式ROM一式（`PC88_REF_ROM_DIR`）で、11腕それぞれを**2走**実施する
  （G3 決定論性の確認を兼ねる）
- 2走が完全一致した腕について、「比べるもの」節の記録項目1・2・3・5を
  正規化した記録（原点基準の相対座標、原点セル以外の並び、属性域40バイト、
  非空白セル件数）を機械可読な形にまとめ、その**SHA-256**と件数
  （相対セル件数・非空白セル件数・属性行数）を
  `tests/conformance/expected_l4_echo.tsv` に書く
- **文字コードの並びそのもの・属性域の値そのものは期待値ファイルに書かない。
  SHA-256と件数だけ**（CLAUDE.md 禁止事項4・M6 `expected.tsv` と同じ作法）
- 正規化とハッシュ化は `tools/l4_echo_conform_record.py`（新設予定）が行う。
  `tools/l4_vram_probe.py` の差分モードの出力（`diff_vram_dumps`）と
  `attr_rows`/`load_vram_dump` をそのまま import して使い、二重実装しない
  （`tools/hash_io_stream.py` が `tools/cmp_io.py` の抽出ロジックを import
  する既存の作法を踏襲する）

## 自作ROM側の照合のしかた

- 自作main ROMは測定時HEADで `python3 src/build_main_rom.py <新規dir>` により
  都度組み立てる（`tools/l3_main_selftest.sh` と同じ作法）。**公式ROMは
  自作ROM側の測定には一切使わない**
- 自作ROM側でも同じ11腕を走らせ、`tools/l4_echo_conform_record.py` で
  同じ正規化・ハッシュ化を行い、`expected_l4_echo.tsv` のSHA-256と件数を
  照合する
- 公式環境（`PC88_REF_ROM_DIR`）が無い環境でも、コミット済みの
  `expected_l4_echo.tsv` さえあれば自作ROM側の照合は独立に回せる
  （公式環境の有無は自作ROM側の照合を妨げない）

## 判定名（本事前登録で定める。この3つ以外は作らない）

- `conform`: 記録する内容（記録項目1・2・3・5、最下行を除く）のSHA-256と
  件数が、期待値と完全に一致する
- `not_conform`: 上記のいずれかが一致しない。一致しない具体的な形
  （件数不一致かSHA-256不一致か）を判定名の後に文章で記述する。
  **値そのもの（文字コード・属性の並び）は出さない**（期待値ファイル自体が
  値を持たないため、原理的に「どこが違うか」は件数とハッシュ不一致以上には
  特定できない。`tools/conform_l3.sh` の分岐点報告と同じ制約）
- `gate_failed`: 関門（下記G1〜G5）のいずれかが偽だった腕。判定に含めず、
  理由を記述する

## 関門

- G1 器具の自己検査: 測定時HEADで `tools/harness/vram_dump_selftest.sh`・
  `tools/harness/vram_dump_dynamic_selftest.sh`・
  `tools/harness/mem_write_log_selftest.sh`・`tools/harness/key_matrix_selftest.sh`・
  `tools/screen_content_leak_selftest.sh` の全項目がOK
- G2 取りこぼし0・打てない文字の警告0（全走のstderrで確認）
- G3 決定論性: 期待値を作る公式側2走で、写し・記録のsha256が一致
- G4 陰性対照: 何も打たない走（起動settleのみ）で、差分（文字域・属性域とも）
  が0件
- G5 自作ROM側の `tools/l3_main_selftest.sh` が測定時HEADでrc=0

## 判定後の行き先

- 全11腕 `conform` なら、`tools/conform_l4.sh` を M7以降の恒常的な適合
  テストとして `tools/run_all_selftests.sh` に登録する（公式環境が無い
  場合は自作ROM側の照合だけが回る形にする）
- `not_conform` を含む場合は、`docs/spec/l3-main.md` と突き合わせ、実装差か
  仕様の未解釈かを切り分ける次の作業の入力にする

## 故障注入（器具の検出力の確認。関門G1〜G5とは別に必須）

- 自作ROM側の記録の1バイト（正規化した記録のJSON表現のどこか1文字）を
  変えると、SHA-256が変わり `not_conform` になること
- 期待値ファイル `expected_l4_echo.tsv` の1行（件数またはSHA-256）を壊すと、
  正しい自作ROM記録との照合で検出できること（件数不一致はSHA-256比較の前に
  検出する。`tools/lib_l3_conformance.sh` の `run_conformance` と同じ順序）

## 結果ノート

`docs/notes/l4-c1b-echo-conformance-scene-results.md` に書く。関門・判定名・
数え方は本ノートから動かさない。

## 根拠リンク

[l4-c1-echo-conformance-preregistration](l4-c1-echo-conformance-preregistration.md)
（`13ceb2e`、腕の定義・記録する内容の原型）・
[l4-c1-echo-conformance-results](l4-c1-echo-conformance-results.md)
（`1817efb`、9腕一致・E3の2腕は最下行のみ不一致という実測結果、追記
`e975d49` の開発者判断）・
`tools/conform_l3.sh`・`tools/lib_l3_conformance.sh`（期待値の作法・
`run_conformance` の判定順序）・`tests/conformance/expected.tsv`（件数と
SHA-256だけを持つ期待値の書式）・`tools/l4_vram_probe.py`
（差分モード・`--count-only-rows`）・`tools/l3_main_selftest.sh`
（自作ROM側の組み立てと関門G5）。
