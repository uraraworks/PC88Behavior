# m7gw: `disk#10`が示す3つの食い違いの切り分け — 事前登録

## 位置づけ

[m7gv](m7gv-three-sites-unit-conformance-results.md)は`FILES 2`・
`disk#10`条件で、段24・28・32（`exchange11_fallthrough`・
`exchange14_prepare_first_read`・`bulk_read_do`）が公式と一致することを
確認する過程で、**この条件だけ画面出力が公式と一致しない**ことを見つけた
（起点は段4付近、本稿ではこの3箇所とは対応づけていない）。

`disk#10`は他のB:候補と違う振る舞いを3つ示している:

1. [m7gg](m7gg-data-disk-screening.md)（訂正追記込み）: `FILES 2`で
   `READ DATA`が108件（他候補は5〜7件）
2. [m7gv](m7gv-three-sites-unit-conformance-results.md): `FILES 2`で
   画面出力が公式と一致しない（起点は段4付近）
3. [m7gm](m7gm-write-path-drive-axis-results.md): `SAVE"2:.."`が
   WRITE 0件で終わる（末端まで到達しない）

**これらが同じ原因かどうかは分かっていない。** 本稿はこの3症状の位置と
関係を、`src/`を修正せずに測定だけで切り分ける。

## 段階0（本稿）: 事前登録を測定前にコミットする

本稿は測定を1回も走らせる前にコミットする。測定後の書き換え・amendは
行わない。

## 測定条件（共通）

- ROM: `PC88_REF_ROM_DIR`（未設定時`private/rom`）の公式一式（条件O）と、
  `tools/lib_l3_measure.sh`の`build_mixed_rom`が作る混成（公式main一式＋
  自作サブROM＝条件M、探針引数なしの既定ビルド）。
- A: `disk#8`（`650cfac8`、`m7gd`で確認済みの起動可能ディスク）の使い
  捨て複製に固定。
- B: 主対象は`disk#10`（`0c6f7a53`）。対照条件として`disk#1`
  （`0cd0727b`、`m7gg`で「読める」・`m7gm`で「WRITE使えた」と分類済みの
  B:候補）を併用する。
- ディスクはすべて`tools/stage_disk_by_digest.sh`でダイジェストから
  中立パスを得てから使う。実ファイル名を扱う経路を作らない。

## 段階1: `FILES 2`×`disk#10`の食い違いの位置を特定する

条件O対条件M（既定ビルドどうし。探針は使わない）を、A:=`disk#8`・
B:=`disk#10`、打鍵`--type-at 300 --type '\n' --type-at 700 --type
'FILES 2\n' --frames 3000`（`m7gg`/`m7gu`と同一作法）で比較する。

- **段レベル**（シリンダ指定）: `tools/compare_l3_entry_fdc.py
  --after-frame 700 --list-all-stages`で、SEEK/SENSE INTERRUPT STATUS
  各段のシリンダ一致/不一致を段番号（**1起点、SEEKとSENSE INTERRUPT
  STATUSだけを数えた通番**であることをコード
  （`enumerate(commands, 1)`、`print_all_stage_details`）で確認済み）
  付きで見て、`m7gv`が「起点は段4付近」とした主張を追認するか、違うなら
  違うと書く。
- **FDCコマンド種別列レベル**: `tools/analyze_error_exchange_shape.py`
  （本来`no_disk`/`unreadable_disk`向けだが、生iologを一般的に解析する
  だけなので`disk#10`条件にもそのまま使える）で、FDCコマンド種別の一致
  prefix件数・分岐位置・main⇔sub交換run構造の先頭一致prefix件数を見る。
- **画面出力**: `tools/check_l3_screen_output.py --compare-report`で
  行数・文字数・SHA-256の一致/不一致を見る。

同じ比較を対照条件`disk#1`にも当てる（段階2の対照条件と共有する）。

## 段階2: 3つの症状が同じ原因かを切り分ける

**仮説を1つに決めず、区別できる観測を選ぶ。**

- **症状1（`READ DATA`108件）**: 段階1で得る条件O・`disk#10`・
  `FILES 2`のiologに`tools/count_fdc_commands_after_frame.py
  --after-frame 700`を当て、**公式側**の`READ DATA`件数を数える。
  `m7gg`は条件Oで`disk#10`=108件・他候補=5〜7件と既に記録している
  （本稿は同一条件で独立に再測定し、比較材料として`disk#1`のO条件も
  同じiologから数える）。**公式でも108件前後なら、これはディスクの
  内容の性質であって症状ではない。** 公式と混成で件数が大きく違うなら
  （＝混成だけ異常に多い/少ないなら）、症状として扱う。
- **症状2（画面不一致）と症状3（WRITE 0件）**: 段階1で特定した分岐点
  （段番号・FDCコマンド種別列上の位置）と、症状3のWRITE経路探針
  （`recv_dispatch_write_sector`、`SAVE"2:TQ"`条件）の到達地点を比較する。
  同じ分岐点由来なら、症状2・3は少なくとも上流を共有する。別の分岐点
  なら独立と扱う。
- **症状3のB:固有性**: `SAVE"1:TQ"`（A:へ保存、B:=`disk#10`を挿した
  まま）を測り、WRITE系コマンド件数を見る。0件でなければ、症状3は
  「`disk#10`が挿さっていること」ではなく「`disk#10`へ書き込もうと
  すること」に固有と言える。打鍵は`m7gm`と同一
  （`--type-at 300 --type '\n' --type-at 700 --type '10 PRINT
  "T"\nSAVE"1:TQ"\n' --frames 4200`、宛先番号だけ`1`に変える）。
  ROM条件は`m7gm`のベースラインと同じ条件M（探針なし）。

## 段階3: 既知のエラー経路と照合する

1.47節・1.48節（`no_disk`/`unreadable_disk`）の構造分類と、`disk#10`
条件の構造分類（段階1で`analyze_error_exchange_shape.py`が出す分岐直前
要求の長さ・分岐後応答runの長さ・交換run構造の先頭一致prefix）を比較する。

- `tools/measure_error_exchange_shape.sh`
  （`PC88_ERROR_SHAPE_OPT_IN=1`必須）で`no_disk`・`unreadable_disk`の
  参照シェイプを本セッションで新規に採取し、`disk#10`条件の分類と同じ
  観点（要求長・分岐位置・応答run長・prefix件数）で並べる。
- 同型なら、既知のエラー経路の話に帰着する（新しい欠陥ではない可能性）。
- 同型でないなら、新しい分岐として扱う。

## 事前登録する合格条件（測定前に固定。後から動かさない）

判定に数値比較を使わない（件数・一致prefix・段番号・真偽値の比較のみ）。

1. **陽性対照**: `build_mixed_rom ... --break-drive-selector`
   （1.46節のドライブ指定伝播を壊す既存の故障注入、`m7gv`と同じ考え方）
   を条件M・`FILES 2`・B:=`disk#10`で比較し、
   `compare_l3_entry_fdc.py --after-frame 700`のunit/head差件数が0件
   より大きいことを確認する。あわせて
   `tools/analyze_error_exchange_shape_selftest.sh`（既存の合成ログ
   selftest）を実行し、rc=0（全項目OK）であることを確認する。**どちらか
   が通らなければ、以降の段階1・段階3の解釈をしない。**
2. **判定規則を先にベースラインへ当てる**: 条件O2run同士・条件M2run同士
   （`disk#10`・`FILES 2`）で、`compare_l3_entry_fdc.py`・
   `check_l3_screen_output.py`・`analyze_error_exchange_shape.py`の
   いずれも「差なし」（画面`match`、FDC種別列完全一致、交換run構造
   prefixが全長一致）と出ることを確認してから、条件O対条件Mへ当てる。
3. **決定論性**: 差が出た条件は2run測って自己一致を確認する。1runに
   とどめた条件は明記する。
4. **対照条件**: `disk#10`の段階1・症状1の結果は、必ず`disk#1`と同条件
   で比較する。`disk#10`だけを測ると、それが`disk#10`固有なのか条件
   全体の性質なのか区別できない。
5. 元ディスク（`disk#8`・`disk#10`・`disk#1`の複製元）を壊さない
   （書き込みを伴う測定では使い捨て複製。全測定後にSHA-256不変を確認）。
6. 成果物に実ファイル名が含まれないこと（ダイジェスト・通し番号のみ）。

## 事前登録する予測（測定前に書く。どれになるかは予測しない）

- **D1**: 3症状が段階1で特定した単一の分岐点に帰着する ⇒ 1つの原因
- **D2**: 症状1は公式でも同じ（＝性質であって症状ではない）で、症状2・3
  だけが食い違い
- **D3**: 症状が互いに独立 ⇒ 複数の原因
- **D4**: 既知のエラー経路（1.47節・1.48節）と同型 ⇒ 新しい欠陥ではない
- **D5**: 陽性対照が通らない／位置が特定できない ⇒ 解釈しない

**複数のDが同時に成立してもよい**（例: D2とD4が両立する等）。無理に
1つへ寄せない。

## 禁止（本稿にも適用）

- 結果が予測と合わなくても、上記の合格条件・判定規則を動かさない。
  当てはまらない結果は「当てはまらない」と書く。
- `src/`を修正しない（原因が分かっても本稿では直さない）。
- 値（バイト値・データポート値・シリンダ値・画面本文）を書かない。
- リポジトリに存在しないファイル名を引かない。実ファイル名は書かない。

## 測定の実務

- 混成ROMは`build_mixed_rom`で作る。公式一式は`*.ROM`を`cp -p`で
  コピーするだけ。
- **フォアグラウンドで走らせる。`run_in_background`は使わない。**
- **測定中に`git stash`・ブランチ切替・ファイル編集を重ねない。**
- 無言でSKIPする分岐を作らない。SKIP・リトライ失敗は件数を数えて記録
  する。
- 生ログ・混成ROM・ディスク複製はリポジトリ外（scratchpad配下）に置き、
  **コミットしない。**
- 出力は`grep -c`等で件数・一致/不一致・rcに絞る。値の列を画面に出さ
  ない。
- **`src/`は変更しない。修正もしない。**
- **使い捨てのデバッグでもディスクの実ファイル名を展開して表示しない。**

## 情報境界 / 根拠リンク

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容（実ファイル名を含む）は、本稿の作業・成果物に含めない。

根拠（`ls`で存在確認済み）:
[m7gv](m7gv-three-sites-unit-conformance-results.md)・
[m7gu](m7gu-three-sites-unit-conformance-preregistration.md)・
[m7gm](m7gm-write-path-drive-axis-results.md)・
[m7gl](m7gl-write-path-drive-axis-preregistration.md)・
[m7gg](m7gg-data-disk-screening.md)・
[m7gp](m7gp-disk-name-leak-path-closed.md)・
`docs/spec/l3-subrom.md` 1.46節・1.47節・1.48節・1.56節・3節・
`src/l3_service/make_subrom.py`（本稿では変更しない）・
`tools/lib_l3_measure.sh`（`build_mixed_rom`・`run_q88measure_retry`）・
`tools/compare_l3_entry_fdc.py`・`tools/check_l3_screen_output.py`・
`tools/count_fdc_commands_after_frame.py`・
`tools/analyze_error_exchange_shape.py`・
`tools/analyze_error_exchange_shape_selftest.sh`・
`tools/measure_error_exchange_shape.sh`・`tools/stage_disk_by_digest.sh`・
`tools/verify_drive_byte2_attribution.sh`（陽性対照の作法の出所）・
`tools/hash_write_stream.py`。
