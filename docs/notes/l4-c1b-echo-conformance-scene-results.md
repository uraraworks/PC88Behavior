# l4-c1b — 打鍵エコー適合の場面固定 — 結果

事前登録: [l4-c1b-echo-conformance-scene-preregistration](l4-c1b-echo-conformance-scene-preregistration.md)
（`6b206b5`）。器具追加: `a6d9b3e`（`tools/conform_l4.sh`・
`tools/l4_echo_conform_record.py`・`tests/conformance/expected_l4_echo.tsv`）。
判定名・記録項目・関門・数え方は事前登録から動かしていない。

## 器具

- 測定時 HEAD: `a6d9b3eb62c82fb18f1ce912e0277165c87e00d4`
- 公式ROM一式: `PC88_REF_ROM_DIR`（`private/rom`）から `*.ROM` を走ごとに
  新しいROMディレクトリへ `cp -p` するだけ（中身は読まない）。ディスク無し
- 自作ROM一式: 測定時HEADで `python3 src/build_main_rom.py <新規dir>` により
  N88.ROM・DISK.ROM・FONT.ROMを生成。複数回ビルドしてもバイト列が一致する
  ことを確認済み（下記sha256、`l4-c1` 結果ノートの値と同一）
- 作業ディレクトリ: リポジトリ外 `_emulator/PC88/tmp/l4-c1b-work/`
  （本ノート作成後に削除）

### 自作ROM一式の sha256（先頭12桁。複数ビルドで一致）

| ファイル | sha256(先頭12桁) |
|---|---|
| N88.ROM | `5fca35a9642a` |
| DISK.ROM | `d8b2e64bc274` |
| FONT.ROM | `53d8cc941814` |

## 器具の変更点（事前登録からの1つの修正）

事前登録の「腕」節は、11腕すべてで起動settle（`--type-at 300 --type '\n'`）を
共通に使う前提だったが、実装時に `tools/harness/frontend/main.c` の
`cf677dc`（2026-09-15）で `--key-matrix` と `--type` の併用が引数エラーに
なっていることが分かった（「どちらも `key_scan` を書き換えるため処理順に
依存して不安定になる」という設計判断。`l4-c1` 実測時にはこの禁止が
まだ入っていなかった可能性がある）。E3（`--key-matrix`使用の8腕）だけ
起動settleを外し、直接キー行列を叩く形にした。公式ROM実測でSHIFT×Qが
1セルだけ変化する既知の形（`l4-c1` 結果ノートと同じ構造）と一致すること
を確認済みで、記録内容・判定には影響しない。

## 関門

| 関門 | 判定 | 備考 |
|---|---|---|
| G1 器具の自己検査 | **真** | `vram_dump_selftest.sh`・`vram_dump_dynamic_selftest.sh`・`mem_write_log_selftest.sh`・`key_matrix_selftest.sh`・`screen_content_leak_selftest.sh` の全項目OK |
| G2 取りこぼし0・打てない文字の警告0 | **真** | 全走(公式11腕×2走+自作11腕+陰性対照3走)のstderrに「打てない」「untypable」の警告なし |
| G3 決定論性 | **真** | 公式ROM側、各腕とも2走の記録(cell_count/nonblank_count/attr_row_count/sha256)が完全一致。11腕すべてで確認 |
| G4 陰性対照 | **真** | 何も打たない走(起動settleのみ、frame690/752)で、公式・自作とも全行(row19含む)の文字域・属性域の変化が0件 |
| G5 自作ROM側の自己検査 | **真** | `tools/l3_main_selftest.sh` が測定時HEADでrc=0 |

## 11腕の判定

`tools/conform_l4.sh`（`PC88_REF_ROM_DIR`設定あり）を実行し、公式ROM側
（2走）・自作ROM側（測定時HEAD）とも、`tests/conformance/expected_l4_echo.tsv`
と照合した。

| 腕 | 公式ROM側 | 自作ROM側 |
|---|---|---|
| E1（英数字 `ab12`） | conform | conform |
| E2（記号 `":(),.;`） | conform | conform |
| E3_shift_Q | conform | conform |
| E3_shift_A | conform | conform |
| E3_caps_Q | conform | conform |
| E3_caps_A | conform | conform |
| E3_kana_Q | conform | conform |
| E3_kana_A | conform | conform |
| E3_grph_Q | conform | conform |
| E3_grph_A | conform | conform |
| E4（80桁超 `a`×85） | conform | conform |

## 全腕の集計

| 判定 | 公式ROM側 | 自作ROM側 |
|---|---|---|
| conform | 11 / 11 | 11 / 11 |
| not_conform | 0 / 11 | 0 / 11 |
| gate_failed | 0 / 11 | 0 / 11 |

`l4-c1`（`1817efb`・`e975d49`）で、最下行を除けば11腕すべて（E3の
SHIFT×Q・SHIFT×Aを含む）の記録項目1・2・3・5が公式・自作間で一致していた
という実測結果が、絶対位置を含まない正規化のもとで恒常的な適合テスト
としてそのまま固定できることを確認した。

## 公式環境が無い場合の自作ROM側照合

`PC88_REF_ROM_DIR` を未設定のまま `tools/conform_l4.sh` を実行し、以下を
確認した。

- 公式ROM側は「SKIP: 公式ROMの環境変数(PC88_REF_ROM_DIR)が未設定。」と
  明示され、判定不能として扱われる（黙って一致に化けない）
- 自作ROM側の照合（11腕、コミット済み `expected_l4_echo.tsv` とだけ照合）
  は公式環境の有無と無関係に実行され、11腕すべて `conform`
- 終了コードは両ケースとも0（自作側が全項目OKであれば、公式側SKIPは失敗
  として扱わない設計。`tools/run_all_selftests.sh` にそのまま登録できる）

## 故障注入（器具の検出力の確認）

`tools/conform_l4.sh` 内蔵の自己検査（合成データ、公式環境不要）で、
毎回自動的に確認する:

- 自己検査a: 正規化した記録の属性域1バイトを変えるとSHA-256が変わる
  （検出力あり）
- 自己検査b1: 正しい記録は期待値と `conform`、1バイト変えた記録は
  `not_conform` と判定される
- 自己検査c: 期待値ファイルの件数(1列)を壊すと、正しい記録でも
  `not_conform` として検出される
- 自己検査d: 期待値ファイルのSHA-256を壊すと、正しい記録でも
  `not_conform` として検出される

いずれも今回の実行（公式環境あり・なしの両方）で全項目OKだった。

## 言えないこと

- 本測定はエミュレータ(QUASI88 libretro版コア)上の振る舞いである
  （実機の挙動そのものではない）。`l4-c1` と同じ制限。
- 確認したのは記録項目1・2・3・5（最下行を除く）の一致であり、最下行
  （ファンクションキー表示行）自体の適合は本テストの対象外のまま
  （`l4-c1` 追記の開発者判断どおり）。
- E3で確認したのはSHIFT・CAPS・カナ・GRPHをそれぞれ単独でQ・Aに重ねた
  8組のみ（`l4-c1` と同じ範囲）。

## 判定後の行き先

全11腕が公式・自作の両方で `conform` だったため、事前登録の行き先どおり
`tools/conform_l4.sh` を M7以降の恒常的な適合テストとして
`tools/run_all_selftests.sh` に登録済み（`a6d9b3e`。公式環境の有無に
関わらず自作ROM側の照合が回る設計で、SKIP判定の特別扱いは不要）。

## 生データ

写し・iolog・記録は使い捨ての作業ディレクトリ
(`_emulator/PC88/tmp/l4-c1b-work/`)に置き、本ノートを書いたあと削除した。
