# m7iz: セクタ数の違う自作ディスクで、run長が追随するかを測る — 事前登録

## 位置づけ

[m7iy](m7iy-disk10-separation-retry-results.md)は判定X1で、**`disk#10`の
「連続READ」が1シリンダ上の全件失敗の読み出し**（READ DATA 108件が108件とも
`NO DATA`、9件×12回）であることを確定した。そして
**「読めない領域を持つディスクを作れば土俵になる」**という道を示した。

**その土俵は、すでに手元にあった。**

`tools/conform_l3.sh`の`unreadable_disk`シナリオは、**`tools/make_l3_testdisk.py`
が生成する自作D88をB:に入れ、`FILES 2`を打鍵し`--frames 3000`で測る**——
**本連が使ってきた水準Eと同じ打鍵**である。

さらに、**3つのディスクでトラックあたりセクタ数が全部違う。**

| ディスク | 1トラックあたりセクタ数 | 出どころ |
|---|---:|---|
| `make_l3_testdisk.py`の自作D88 | **8** | `SECTORS_PER_TRACK = 8` |
| `make_n88_blank_disk.py`の自作ブランク | **16** | `SECTORS_PER_TRACK = 16` |
| `disk#10`（公式） | （run長として**9**を観測） | `m7hb`・`m7iy` |

**`m7hb`が区別できないまま残したH1派生とH2を、これで切り分けられる。**

- **H1派生（1トラック分＝トラックあたりセクタ数）**が正なら、
  **run長はディスクのセクタ数に追随する**（自作8なら8、自作16なら16）。
- **H2（内部固定カウンタ）**が正なら、**どのディスクでもrun長は9のまま**である。

**どちらに転んでも、`m7hb`以来の未確定が動く。**

## 段階0（本稿）: 事前登録を測定前にコミットする

本稿は測定を1回も走らせる前に単独でコミットする。測定後の書き換え・amendは
行わない。

## 測定条件

- 条件Oのみ（公式ROM一式）。**A: は`disk#8`（`650cfac8`）に固定**。
- **B: を3種類で振る（測定前に固定。後から足さない・除かない）:**
  - **B1**: `python3 tools/make_l3_testdisk.py <出力先>`（**8セクタ/トラック**）
  - **B2**: `python3 tools/make_n88_blank_disk.py <出力先>`（**16セクタ/トラック**）
  - **B3**: `disk#10`（`0c6f7a53`。`tools/stage_disk_by_digest.sh`経由。**参照**）
- 打鍵は水準E（`--type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n'
  --frames 3000`）。**摂動は当てない**（観察）。
- **窓は`m7ix`と同じ`frame >= 700`**（正典は
  `tools/count_fdc_commands_after_frame.py`の絞り方）。**窓を自分で発明しない。**

## 記録する指標（`m7ix`と同じ。すべて値を出さない）

- FDCコマンド総数、READ DATA総数
- **READ DATAのrun長の並びとその多重集合**
- 結果相にエラーが立ったコマンドの件数（`is_error_status`が真の件数）と、
  **エラーの公開ビット復号名の内訳**
- SEEKの件数
- **相異なるSEEK目的シリンダの個数**（個数だけ。値は内部で比較して捨てる）

## 事前登録する判定（測定前に固定。後から動かさない）

**主判定は「run長がセクタ数に追随するか」である。**

- **Y1（追随する）**: **B1でrun長8のrunが1本以上現れ、かつB2でrun長16のrunが
  1本以上現れる。**
- **Y1a（部分的に追随）**: B1で8、B2で16のうち**片方だけ**が現れる。
- **Y2（9のまま）**: B1・B2の少なくとも一方で**run長9**のrunが現れ、
  **8も16も現れない**。
- **Y3（どれでもない）**: エラーは出るが、run長が8・16・9のいずれとも違う
  長さ2以上のrunになる。
- **Y4（土俵が成立しない）**: B1・B2ともエラーが0件、または長さ2以上のrunが
  1本も現れない。**このとき自作ディスクでは`disk#10`の状況を再現できて
  いないので、H1派生とH2の区別はつかない。**
- **O（測定不能）**: B3（`disk#10`）の再測定が`m7iy`の記録と食い違う、
  自作ディスクの生成が再現しない、決定論性が確認できない。

**どの判定になるかは予測しない。**

## 事前登録する合格条件（測定前に固定）

1. `tools/recv_run_field_leak_selftest.sh`が全項目OK・rc=0。
2. `tools/analyze_error_exchange_shape_selftest.sh`がrc=0。
3. **B3（`disk#10`）の再測定が`m7iy`と一致**: 窓`frame >= 700`で
   FDC総数144・READ DATA総数108・エラー真108・run長の並び`{9:12}`・
   相異なるシリンダ数1。食い違えば判定O。
   **これは「同じものを見ている」ことの確認である。**
4. **自作ディスクの生成が再現すること**: B1・B2をそれぞれ2回生成し、
   **生成物のSHA-256が一致すること**。一致しなければ判定O。
5. **`make_n88_blank_disk.py --check`が通ること**（B2について。道具が持つ
   自己検査）。
6. **決定論性**: B1・B2・B3のそれぞれで、生ログが独立2回でバイト一致。
7. **元ディスクを壊さない**: 測定前後で`disk#8`・`disk#10`の原本ダイジェストが
   不変であること。
8. **実行した条件数を出力に載せ、3であることを確認する**。
9. `tools/check_cleanroom.sh`が全項目OK。

## 言えないこととして先に書いておくこと

- **Y1が出ても「9はトラックあたりセクタ数である」と断定はしない。** 言えるのは
  「run長がディスクのセクタ数に追随する」までである。公式ディスクの
  セクタ数を測ったわけではない（**公式ディスクのイメージは読まない**）。
- **Y2が出ても「内部固定カウンタである」と断定はしない。** 言えるのは
  「自作ディスクのセクタ数を変えてもrun長が9のまま」までである。
- **B1は8シリンダしかない小さな自作ディスク**（`N_CYLINDERS = 8`）であり、
  公式ディスクと形が違う。**形の違いが結果に効く可能性を排除していない。**
- **Y4のときは何も切り分けられない。** 自作ディスクで`NO DATA`が出ない場合、
  土俵の作り方を改めて設計する必要がある。
- run長やセクタ数から公式ディスクの値を逆算しない（禁止事項5）。
- 条件O・水準E・A:=`disk#8`固定という1つの使い方しか見ていない。

## 結果ノート

結果は `docs/notes/m7ja-selfmade-disk-runlength-results.md` に書く。事前登録
（本稿）の候補・窓・指標・判定規則を後から動かさない。手順逸脱・事故は隠さず
開示節に書く。

## 禁止（本稿の測定中も例外なく適用）

- 公式ROMのバイト列を読まない・出力しない・保存しない。逆アセンブルしない。
- **公式ディスクのイメージを直接読まない**（D88のヘッダ・セクタ情報を含む）。
  **自作ディスクの構造は読んでよい**（`tools/`が公開規則から生成したもので、
  公式媒体を入力していない）。
- FDCデータポート値、シリンダ値、PCN値、受信run・応答runのバイト値を出力しない。
  **結果ステータスは公開ビットの復号名と真偽の集計のみ。**
- 画面本文の生の行を報告・ノート・コミットメッセージ・ツール出力へ書かない
  （禁止事項7）。
- **公式ディスクの実ファイル名を展開して表示しない。**
  `tools/stage_disk_by_digest.sh`を必ず経由する。
- **トレースバックを集計ファイルへ流さない**（`m7iw`の事故）。例外は型名だけ
  記録し、標準エラーを結果ファイルへ混ぜない。
- 値を掃引・推論で復元しない。件数や基数から元の値を逆算しない。
- 第三者の逆アセンブルリスト・解析記事のコード断片を参照しない。

## 根拠リンク（`ls`で存在確認済み）

[m7iy](m7iy-disk10-separation-retry-results.md)（本稿の出所。`disk#10`の連続READが
全件失敗であること、土俵の作り方が見えたこと。合格条件3の照合先）・
[m7ix](m7ix-disk10-separation-retry-preregistration.md)（窓の正典）・
[m7iw](m7iw-disk10-separation-results.md)（トレースバック混入の事故）・
[m7iv](m7iv-disk10-separation-preregistration.md)（仮説E）・
[m7hb](m7hb-consecutive-read-rule-results.md)（H1派生とH2を区別できなかった
記録。本稿が切り分けにいく相手）・
[m7gg](m7gg-data-disk-screening.md)・
[m7il](m7il-position5-preregistration.md)（ディスク側に土俵が無いとした記録。
本稿はその土俵が既存の`unreadable_disk`にあったことを使う）・
[m7iu](m7iu-response-position-results.md)（236armの格上げ）・
`docs/spec/l3-subrom.md` 1.47節・1.48節（`unreadable_disk`のエラー応答経路）・
1.57節・3節（第164版）・
`tools/make_l3_testdisk.py`（**8セクタ/トラック**。B1の出どころ）・
`tools/make_n88_blank_disk.py`（**16セクタ/トラック**。B2の出どころ。`--check`）・
`tools/conform_l3.sh`（`unreadable_disk`シナリオの組み立て方）・
`tools/count_fdc_commands_after_frame.py`（窓の正典）・
`tools/stage_disk_by_digest.sh`・
`tools/compare_l3_entry_fdc.py`（`command_names`・`status_fields`・
`describe_status`・`is_error_status`）・
`tools/analyze_write_path.py`（`parse_commands`・`Command.param_values`）・
`tools/recv_run_field_leak_selftest.sh`・
`tools/analyze_error_exchange_shape_selftest.sh`・`tools/check_cleanroom.sh`。
