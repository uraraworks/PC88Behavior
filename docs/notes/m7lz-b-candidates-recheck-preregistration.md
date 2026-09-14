# m7lz — B:候補の実物で FILES 2 と SAVE"2:.." を公式・混成で比べ直す（3章の残る3項を閉じる） — 事前登録

## 位置づけ

[m7ly](m7ly-chapter3-inventory.md)（仕様第218版）の3章棚卸しで、本当に残る項は3つだった。

- **5448（第141版）**: B:へ書く `SAVE"2:.."` の WRITE 経路が公式と一致することを、`m7gr` は `disk#8` 1本でしか確かめていない。
- **5485（第143版）・5508（第144版）**: 公式ディスク `disk#10` を B:に入れた `FILES 2`・`SAVE"2:.."` で、FDCコマンド種別列が
  56件目で分岐し画面も一致しなかった。その後の追跡（1.57〜1.58節）は自作媒体で進み、第202〜206版で自作媒体では外形が公式と
  一致したが、**disk#10 の実物では照合し直していない**。

本稿はこの3項を、現行（自作サブROMの生成器 sha `4f0b85c0344b`、`src/` は変えない）で測って閉じるための事前登録である。
**実装は変えない。**

## 媒体と場面

- ROM: 公式一式（official）／公式main＋自作sub（mixed、`build_mixed_rom`）。
- 媒体は `tools/stage_disk_by_digest.sh <先頭8桁>` で使い捨て複製を作る（名前は出さない）。対応は [m7gg](m7gg-data-disk-screening.md) の表:
  disk#1 `0cd0727b`・disk#2 `3c218749`・disk#4 `f314f59f`・disk#5 `9054ca7b`・disk#7 `39c2fbeb`・disk#8 `650cfac8`・
  disk#9 `6acfca05`・disk#10 `0c6f7a53`（disk#3 は disk#8 と同一内容、disk#6 は測定失敗のため除く）。
- **A: は全腕で disk#8 の複製**（`m7gg`・`m7gr` と同じ。起動確認済み）。B: は候補ごとの別の複製。A:・B: は m3u で渡す。
- 打鍵は `--type-at 300 --type '\n'` のあと、
  - 読み腕 R-N: `--type-at 700 --type 'FILES 2\n'`、`--frames 4000`
  - 書き腕 W-N: `--type-at 700 --type '10 PRINT"T"\nSAVE"2:TQ"\n'`、`--frames 4200`（`m7gr` と同じ）
- 腕は 8候補 × {R, W} = 16腕。各腕を official 2回・mixed 2回走らせる。

## 関門（1つでも偽なら `gate_failed`。判定しない）

- G1 媒体: 8つの先頭8桁がそれぞれちょうど1本の複製を作る（道具が0件・複数件でエラー終了しない）。
- G2 取りこぼし: 全走で I/Oログの取りこぼし0件。
- G3 決定論性: 各腕の official 2回どうし・mixed 2回どうしで、I/Oログのデータ行（見出し行を除く）と画面署名が一致する。
- G4 陽性対照: W-8（disk#8 の書き腕）を `build_mixed_rom ... --break-drive-selector` の混成で1回走らせ、official 1回目と比べて
  「WRITEストリーム（件数・バイト数・SHA-256）が異なる」または「`compare_l3_entry_fdc.py --after-frame 700` の入口区間
  unit/head差件数が1以上」のどちらかが成り立つ（比べ方が差を検出できること）。
- G5 実装不変: 測定に使う混成の生成器 sha が `4f0b85c0344b`（HEAD と同じ）。

## 腕ごとの指標（official 1回目と mixed 1回目を比べる）

- E（mainの末端）: main `IN $FD` 列と main `IN $FC` 列の件数・SHA-256 が一致する。
- S（画面）: 終了時の画面署名（`tools/check_l3_screen_output.py --compare-report`）が一致する。
- W（書き腕だけ）: `tools/hash_write_stream.py` の結果（件数・総バイト数・SHA-256）が一致する。**両側とも書き込み0件（rc=2）なら
  W は「一致（未到達）」とし、その腕は「WRITE未到達」と数える。** 片側だけ0件なら W は偽。

## 判定（関門がすべて真のとき）

- **J1（5485・5508）**: R-10 の E と S、W-10 の E・S・W がすべて真 → `disk10_matches`。1つでも偽 → `disk10_differs`。
- **J2（5448）**: 8つの書き腕すべてで E・S・W が真で、かつ disk#8・disk#10 以外の候補のうち **official の WRITE が1件以上の腕が3つ以上**
  → `write_matches`。すべて真だが WRITE に届いた腕が3つ未満 → `write_coverage_short`。1つでも偽 → `write_differs`。
- **J3（読みの広がり、追加）**: 8つの読み腕すべてで E と S が真 → `read_matches`。1つでも偽 → `read_differs`。

判定の行き先:
- `disk10_matches` → 仕様3章の 5485・5508 を「解消」とする。`disk10_differs` → 最初の食い違いの位置を記述し、M6の宿題として残す（診断は別の事前登録）。
- `write_matches` → 5448 を「解消」とする。`write_coverage_short` → 届いた候補の範囲を書いて 5448 を残す。`write_differs` → M6の宿題。
- `read_differs` → 食い違った候補を M6の宿題として3章に新しく登録する。

## 記述として載せるもの（合否に使わない）

- 腕ごとの `compare_l3_entry_fdc.py --after-frame 700` の結果（種別列の一致prefix・最初の差の分類・unit/head差件数・結果ステータス差の有無）。
- 腕ごとの official の READ DATA 件数・WRITE 件数（700フレーム以降）。
- disk#10 について、第143版の「56件目で分岐」が現行でどうなったか。
- 画面の行数・文字数（本文は書かない）。

## 言えないこととして先に書いておくこと

- **エミュレータ（QUASI88 libretro版）上の振る舞いである。**
- 候補は手元の公式ディスク8本だけで、B:媒体一般には一般化しない。A: は disk#8 に固定した。
- 打鍵は `FILES 2` と `SAVE"2:TQ"` の2つだけである。
- 媒体の中身（ファイル一覧・データ）は書かない。

## 結果ノート

`docs/notes/m7lz-b-candidates-recheck-results.md` に書く。関門・指標・判定と数え方を後から動かさない。

## 根拠リンク

[m7ly](m7ly-chapter3-inventory.md)・[m7gg](m7gg-data-disk-screening.md)・`m7gr`（第141版、WRITE経路の判定）・
`m7gx`／`m7gy`（第143・144版、disk#10 の分岐）・仕様1.57〜1.58節。
