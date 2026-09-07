# m7ix: 窓を`m7gg`と揃えて、何が`disk#10`を特別にしているかを測り直す — 事前登録

## 位置づけ

[m7iw](m7iw-disk10-separation-results.md)は主判定O（測定不能）に終わった。
合格条件3（`m7gg`との一致）が通らず、READ DATA総数が**全9本で一様に`+9`**
食い違ったためである。

原因は切り分け済みで、**窓の定義の食い違い**である——`m7gg`は打鍵後
（`frame >= 700`）に絞って数え、`m7iw`は全区間を数えた。差の`+9`は`m7ho`が
「frame 35〜76」と確定した**起動段階の単発READ 9本**である。

**本稿は窓を`m7gg`と揃えて測り直す。** 指標・候補・仮説は`m7iv`のまま動かさない。

## 窓の定義を正典から取る（今回はここを外さない）

`m7gg`が使った窓は **`frame >= 700`** であり、その正典は
**`tools/count_fdc_commands_after_frame.py`**（`--after-frame`）である。
このスクリプトは`compare_l3_entry_fdc.py`が2本を比較するのに対し**1本**を
対象にするもので、パースは`analyze_write_path.parse_commands`と
`analyze_main_to_sub.parse_iolog`をそのまま呼ぶ。

**本稿はこのスクリプトが使うのと同じ絞り込み（`c.frame >= 700`）を用いる。**
`m7iw`のように自前で窓を決めない。**窓を自分で発明しないことが本稿の要点で
ある。**

## 段階0（本稿）: 事前登録を測定前にコミットする

本稿は測定を1回も走らせる前に単独でコミットする。測定後の書き換え・amendは
行わない。

## 測定条件（`m7iv`と同一。窓の定義だけを直す）

- 条件Oのみ（公式ROM一式）。**A: は`disk#8`（`650cfac8`）に固定**。
- **B: を`m7gg`の候補10本で振る**（`#1`=`0cd0727b`、`#2`=`3c218749`、
  `#3`=`c29e67d4`、`#4`=`f314f59f`、`#5`=`9054ca7b`、`#6`=`93694fad`、
  `#7`=`39c2fbeb`、`#8`=`650cfac8`、`#9`=`6acfca05`、`#10`=`0c6f7a53`）。
  **10条件。後から候補を足さない・除かない。**
  `disk#6`は`m7gg`・`m7iw`とも測定失敗だったが、**規則どおり含める**。
- ディスクはすべて`tools/stage_disk_by_digest.sh`でステージングする。
- 打鍵は水準E（`--type-at 300 --type '\n' --type-at 700 --type 'FILES 2\n'
  --frames 3000`）。**摂動は当てない**（本稿は介入ではなく観察）。

## 記録する指標（`m7iv`と同じ。すべて`frame >= 700`で絞る）

- **(a)** FDCコマンド総数、READ DATA総数
- **(b)** READ DATAのrun長の並びとその多重集合、run長9のrunの本数
- **(c)** **結果相にエラーが立ったコマンドの件数**（`is_error_status`が真の件数）
- **(d)** SEEKの件数
- **(e)** **相異なるSEEK目的シリンダの個数**（**個数だけ**。値は内部で比較して捨てる）
- **(f)** 画面の到達判定（`tools/check_l3_entry_screen.py`。**本文は出さない**）

**(b)については、窓で絞ると起動段階の単発9本が落ちるため、`disk#10`の並びは
`9`が12本だけになるはずである。** そうならなければ窓の当て方を間違えている
ので判定Oとする。

## 事前登録する判定（測定前に固定。後から動かさない）

**主判定は指標(c)についてのみ行う**（仮説Eの検定であるため。`m7iv`と同じ）。

- **X1（エラーが分離軸である）**: `disk#10`のエラー件数が、**測定できた他の
  ディスクすべてより大きい**。
- **X2（分離しない）**: `disk#10`のエラー件数以上のディスクが1本以上ある、
  または`disk#10`のエラー件数が0である。
- **O（測定不能）**: 合格条件のいずれかが通らない。

**どの判定になるかは予測しない。**

**併せて記録する（判定ではない）**: (a)(b)(d)(e)(f)を10本すべてについて表に
する。**(e)が`disk#10`を分離するかどうかも記述するが、主判定には使わない。**

## 事前登録する合格条件（測定前に固定）

1. `tools/recv_run_field_leak_selftest.sh`が全項目OK・rc=0。
2. `tools/analyze_error_exchange_shape_selftest.sh`がrc=0。
3. **`m7gg`との一致（今回の本丸）**: 窓`frame >= 700`で数えたREAD DATA総数が
   `m7gg`の記録（`#1`=5／`#2`=7／`#3`=7／`#4`=5／`#5`=5／`#6`=測定失敗／
   `#7`=7／`#8`=7／`#9`=7／`#10`=108）と**測定できた9本すべてで一致すること**。
   食い違えば判定O。
   **さらに、同じ窓で数えた本稿の値が`m7iw`の値ちょうど`-9`になることも
   確認する**（`m7iw`の食い違いが窓だけに由来したことの裏づけ）。
   `-9`でなければ、原因の切り分けが誤っていたことになるので判定Oとする。
4. **`is_error_status`の両方向確認**: 窓内でエラー真・エラー偽のコマンドが
   **どちらも1件以上存在すること**（`m7ho`と同じ手当て）。
5. **決定論性**: `disk#10`と`disk#8`（自己複製）で生ログが独立2回でバイト一致。
6. **元ディスクを壊さない**: 測定前後で10本の原本ダイジェストが不変。
7. **実行した条件数を出力に載せ、10であることを確認する**。
8. `tools/check_cleanroom.sh`が全項目OK。

## 集計スクリプトの作り方（`m7iw`の事故を繰り返さない）

`m7iw`では集計スクリプトが`Command`の属性名を誤り（`params`。正しくは
`param_values`）、`2>&1`でトレースバックを集計ファイルへ書き込んだ。
**本稿では次を守る。**

- 例外は**捕まえて型名だけ**を記録する（トレースバックを集計へ流さない）。
- 集計の取り込みは`2>/dev/null`とし、**標準エラーを結果ファイルへ混ぜない**。
- 属性名は`tools/analyze_write_path.py`の`Command`定義を**先に読んで**使う
  （`param_values`・`data_values`・`input_values`は**内部専用**で、
  `__repr__`にも出さない設計であることを踏まえる）。

## 言えないこととして先に書いておくこと

- **X1が出ても「エラーが連続READの原因である」とは言えない。** 言えるのは
  「エラー件数が`disk#10`を他から分離する」までである。因果には介入が要る。
- **X2が出ても仮説Eが否定されるわけではない**（件数で分離しないだけ）。
- **(e)の個数は基数であって値ではない。** 個数からシリンダの値を推し量らない。
- `disk#6`が測定できなければ、**「測定できたディスクすべてより大きい」**と
  範囲を明示して書く（**10本すべて**とは書かない）。
- 条件O・水準E・A:=`disk#8`固定という1つの使い方しか見ていない。
- 10本という母集団は`m7gg`が選んだものであり、一般性は主張しない。

## 結果ノート

結果は `docs/notes/m7iy-disk10-separation-retry-results.md` に書く。事前登録
（本稿）の候補・窓・指標・判定規則を後から動かさない。手順逸脱・事故は隠さず
開示節に書く。

## 禁止（本稿の測定中も例外なく適用）

- 公式ROMのバイト列を読まない・出力しない・保存しない。逆アセンブルしない。
- **公式ディスクのイメージを直接読まない**（D88のヘッダ・セクタ情報を含む）。
- FDCデータポート値、シリンダ値、PCN値、受信run・応答runのバイト値を出力しない。
  **結果ステータスは公開ビットの復号名と真偽の集計のみ。**
- 画面本文の生の行を報告・ノート・コミットメッセージ・ツール出力へ書かない
  （禁止事項7）。到達判定は`tools/check_l3_entry_screen.py`で行う。
- **公式ディスクの実ファイル名を展開して表示しない。**
  `tools/stage_disk_by_digest.sh`を必ず経由する。
- **トレースバックを集計ファイルへ流さない**（`m7iw`の事故）。
- 値を掃引・推論で復元しない。件数や基数から元の値を逆算しない。
- 第三者の逆アセンブルリスト・解析記事のコード断片を参照しない。

## 根拠リンク（`ls`で存在確認済み）

[m7iw](m7iw-disk10-separation-results.md)（本稿の出所。判定Oと`+9`の切り分け、
判定に採らなかった観測、トレースバック混入の事故）・
[m7iv](m7iv-disk10-separation-preregistration.md)（仮説Eと指標の定義。本稿は
これを窓だけ直して踏襲する）・
[m7gg](m7gg-data-disk-screening.md)（候補10本、READ DATA件数、窓`frame>=700`。
合格条件3の照合先）・
[m7ho](m7ho-seek-without-recv-run-results.md)（起動段階の単発READ 9本が
frame 35〜76にあることの出所。`+9`の説明。`is_error_status`両方向の先例）・
[m7hb](m7hb-consecutive-read-rule-results.md)（「9件×12周期」の構造）・
[m7hf](m7hf-disk10-consecutive-read-origin-results.md)（`bad allocation table`）・
[m7il](m7il-position5-preregistration.md)（ディスク側に土俵が無いことの記録）・
[m7iu](m7iu-response-position-results.md)（236armの格上げ。本連の動機）・
`docs/spec/l3-subrom.md` 1.57節・3節（第163版）・
`tools/count_fdc_commands_after_frame.py`（**窓の正典**。`--after-frame`）・
`tools/stage_disk_by_digest.sh`・
`tools/compare_l3_entry_fdc.py`（`command_names`・`status_fields`・
`is_error_status`）・
`tools/analyze_write_path.py`（`parse_commands`・`Command.param_values`）・
`tools/analyze_main_to_sub.py`（`parse_iolog`）・
`tools/check_l3_entry_screen.py`・
`tools/recv_run_field_leak_selftest.sh`・
`tools/analyze_error_exchange_shape_selftest.sh`・`tools/check_cleanroom.sh`。
