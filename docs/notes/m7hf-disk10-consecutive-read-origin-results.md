# m7hf: disk#10で連続READ件数の起源を大きさと位置で切り分ける — 結果

実施日: 2026-09-04

## 位置づけ

[m7he](m7he-disk10-consecutive-read-origin-preregistration.md)が事前登録した
測定の結果である。事前登録は測定開始前に単独コミット（`655066b`）してあり、
本稿では事前登録の条件・水準・判定規則を後から動かしていない。`src/`・
`tools/`は本稿では変更していない。

**結論を先に書く: 段階1の3項目のうち1項目（書き込み可否）が通らず、
段階2・段階3は実施していない。主判定はO4である。** ただし、通らなかった
理由自体が新しい情報を残した（後述）。

## 陽性対照（最初に書く）

1. `build_mixed_rom ... --break-drive-selector`（1.46節の既存故障注入）を
   条件M・`FILES 2`・B:=`disk#10`で比較した。
   `tools/compare_l3_entry_fdc.py --after-frame 700`のunit/head差件数は
   **15件**（0件より大きい）。
2. `tools/analyze_error_exchange_shape_selftest.sh`は全4項目OK・rc=0。

**両方通ったため、以降の解釈を行う。**

## 判定規則をベースラインへ当てる（合格条件2）

条件M（探針なし）を`disk#10`・`FILES 2`で独立2回測り、
`--list-all-stages`（`--after-frame`無し、`m7gz`が確認した数え方）で比較
した。

| 比較 | 結果 |
|---|---|
| M run1 vs M run2（全段） | 完全一致（不一致0件） |

**判定規則は偽陽性を作らないことを確認した。**

## 段階1: 前提の確認

### 項目1: ライトプロテクト解除で`disk#10`に書き込めるか — 通らなかった

`disk#10`の使い捨て複製に、`m7gt`と同じ手当て（D88ヘッダのオフセット26
バイト目を0へ）を適用し、A:=`disk#8`（起動）・B:=`disk#10`（複製）の
2枚挿し構成で、事前登録した`OPEN "2:<ファイル名>" FOR OUTPUT AS #1` /
`FOR`〜`NEXT` / `PRINT#1` / `CLOSE`のループ書式（[構文の妥当性は本稿の
段階1項目2で別途確認]）を打鍵し`RUN`した。

結果、**`RUN`直後に`bad allocation table`というBASICのエラー表示が出て、
`Ok`に戻った。** 独立に以下の3通りで確認した。

| 試行 | 手段 | ライトプロテクト解除 | 結果 |
|---|---|---|---|
| 1回目 | `OPEN`/`PRINT#`ループ | 解除あり | `bad allocation table` |
| 2回目 | 1行`SAVE"2:.."` | 解除なし | `bad allocation table` |
| 3回目（決定論性確認） | `OPEN`/`PRINT#`ループ | 解除あり | `bad allocation table`（1回目と一致） |

**ライトプロテクトの解除の有無にかかわらず同じエラーが出た。** これは、
`m7gx`（症状3、`SAVE"2:.."`のWRITE 0件）が「原因は調べていない」として
保留していた点に、部分的な説明を与える——**BASICが`bad allocation table`
という自己のディレクトリ整合性チェックで書き込みを打ち切っており、FDCへ
WRITE DATAが1件も発行されない（`m7gx`の観測と整合する）。** 書き込み
そのものがハードウェアのライトプロテクト機構で止まっているのではない。

### 手法自体の陽性対照（本稿で追加実施）

上記の失敗が「本稿の`OPEN`/`PRINT#`ループの書き方自体が誤り」ではなく
「`disk#10`固有の状態」であることを切り分けるため、同じループを
`disk#8`自身の複製（A:のみ、ドライブ1）へ適用した。

| 対象 | ライトプロテクト解除 | 結果 |
|---|---|---|
| `disk#8`複製・ドライブ1 | 解除なし | `file write protected in 10`（`disk#10`とは異なる、期待どおりのエラー） |
| `disk#8`複製・ドライブ1 | 解除あり | `Ok`（**正常に書き込み完了**） |

**この対照により、本稿の`OPEN`/`PRINT#`/`FOR`ループの書式自体は正しく
機能しており（ライトプロテクトがあれば正しくそれを検出し、解除すれば
正常に書き込める）、`disk#10`が示した`bad allocation table`は
`disk#10`固有の状態であって、本稿の手法の誤りではないと言える。**

### 項目2: ループ打鍵が打鍵数上限内で成立するか — 通った

事前登録したサイズ制御プログラム（`OPEN`+`FOR`+`PRINT#`+`NEXT`+`CLOSE`+
`RUN`、6行）の打鍵列は、投入前の機械的カウントで**120打鍵**だった
（`MAX_KEYSTROKES 512`の1/4以下）。実測でも`q88measure`標準エラーに
「打鍵列が長すぎる」は一度も出なかった（本稿の全試行で0件）。上記の
`disk#8`対照が実際に`Ok`まで到達したことも、打鍵列が構文・打鍵数の両面
で機能したことの追加証拠になる。**通った。**

### 項目3: 読み出しが`general_read_request`を通るか — 通った

条件M・B:=`disk#10`・`FILES 2`打鍵で、`--probe-site general_read_request
--probe-mode cyl`版と探針なし基準を`--list-all-stages`で比較した。

**段48・52・56・60・64・68の6段（いずれもSEEK）でシリンダ指定が不一致に
なった。** `m7gz`が同一手法・同一対象（`disk#10`・`FILES 2`）で確認した
結果（段48・52・56・60・64・68の6段）と一致する。**この打鍵での読み出し
区間は`general_read_request`を通る。通った。**

### 段階1の総合判定: 通らなかった

3項目中、項目2・項目3は通ったが、**項目1（書き込み可否）が通らなかった**
ため、事前登録の「3項目とも確認できてから段階2へ進む」を満たさない。
**段階2・段階3は実施しなかった。**

## 段階2・段階3

**未実施。** 段階1項目1が通らなかったため。

## O1〜O5の判定

- **O1**（件数が大きさに追随） / **O2**（変わらない） / **O3**（位置で
  変わる）: 判定対象外（測定していない）。
- **O4**（段階1のいずれかが通らない）: **成立。採用。** 項目1
  （`disk#10`への書き込み可否）が通らなかった。
- **O5**（陽性対照不通過）: 不成立。陽性対照は2件とも通った。

**主判定はO4。**

## 元ディスクを壊さない

全測定で使ったのは`tools/stage_disk_by_digest.sh`が作る使い捨て複製の
みである。`disk#10`・`disk#8`の元ファイルへの書込みコマンドは一度も
実行していない（`--save-to-disk-image`はすべて複製先に対してのみ指定
した）。測定開始前と全測定終了後に両元ファイルのSHA-256を計算し、
完全に一致することを確認した（`ORIG_UNCHANGED=yes`。値そのものは
記録しない）。

## 言えること・言えないこと

**言えること:**

- `disk#10`の使い捨て複製へ、ライトプロテクトフラグを解除しても
  `OPEN...FOR OUTPUT AS #1`（またはそれに相当する`SAVE`）で新規に
  ファイルを書き込むことができず、`bad allocation table`という
  BASICのエラーで打ち切られる。この結果は3回の独立試行（書式2種、
  ライトプロテクト解除の有無2通り）すべてで一致し、決定論的である。
- この`bad allocation table`は、ライトプロテクトが有効な`disk#8`
  複製に同じ手法を適用したときに出る`file write protected`とは
  異なるエラーであり、`disk#10`側は原因がライトプロテクトそのもの
  ではないことを示す。
- 本稿の`OPEN`/`PRINT#`/`FOR`ループという打鍵技術は、`disk#8`複製
  （ライトプロテクト解除後）に対しては正常に書き込みを完了できる
  ことを確認した。手法自体の欠陥ではない。
- `m7gx`が保留していた「`SAVE"2:.."`のWRITE 0件（原因未特定）」に、
  本稿は部分的な説明を加えた——BASIC自身のディレクトリ整合性チェック
  （`bad allocation table`）が書き込みをFDCへ到達する前に打ち切って
  いる可能性が高い（本稿はこの機構の内部動作までは調べていない。
  観測されたのは画面表示のエラーメッセージと、それがWRITE 0件という
  既知の観測と整合するという事実だけである）。
- `disk#10`・`FILES 2`の読み出しが`general_read_request`を通ることを、
  本稿でも独立に再確認した（`m7gz`と同じ6段で不一致）。

**言えないこと:**

- 連続READ DATAの件数が「大きさ」で決まるのか「位置」で決まるのかは、
  **本稿でも決定できなかった。** `disk#10`へ新規ファイルを書けないため、
  大きさ・位置を変える梃子（本稿が計画したループ書込み）自体を
  `disk#10`上で使えなかった。
- `bad allocation table`の**根本原因**（`disk#10`のディレクトリ構造の
  どの部分がBASICのチェックに引っかかっているか）は不明。本稿はバイト
  値・ディスク内容を見ていないため、これ以上の切り分けはできない。
- `disk#10`が既存ファイルを多数持つ状態（ディレクトリがほぼ埋まって
  いる等）と`bad allocation table`が関係するかどうかも、本稿では
  確認していない（ディレクトリの空き状況を見る手段を使っていない）。

## 次に何を測れば絞れるか

1. **`disk#10`以外で連続READ構造を示す候補を新たに探す。** 現状「連続
   READ構造を見せるのは`disk#10`だけ」「`disk#10`は書き込めない」という
   組み合わせが、この実験系統そのものを行き止まりにしている。
   `m7gg`のデータディスク一覧（`disk#10`のREAD DATA=108件が突出して
   いた表）を再確認し、108件ほどではなくても連続READ区間が現れる別候補
   がないか、`disk#1`・`disk#2`以外の候補もスクリーニングする価値がある。
2. **書き込み可能な候補で、大量の既存ファイルを持つディスクを新たに作る。**
   `disk#8`（書き込み可能と確認済み）に、本稿で検証済みの`OPEN`/
   `PRINT#`ループ技術を使って多数のファイル・大きなファイルを作り、
   「連続READ構造が現れるだけのファイル数・サイズ」に到達できるか
   確かめる（`m7hd`が参考測定で見た「小さいファイルでは現れない」を
   踏まえ、もっと大きい規模を作る）。
3. **`bad allocation table`の意味をBASIC言語仕様の範囲で確認する。**
   `refs-nec-manuals-2026-09-04.md`が可としている資料のエラーメッセージ
   一覧（あれば）を見て、このエラーが具体的に何を検査して出るものかを
   確認する（(a)言語仕様の範囲であり、本稿では未実施）。これが分かれば、
   `disk#10`のどんな状態がこの検査に引っかかるかの手がかりになる
   （ただし引っかかる具体的な内容そのものはROM内部構造(b)に踏み込む
   可能性があるため、確認できる範囲は限定的と見込む）。

## 開示

手順逸脱・汚染は無かった。測定はすべてフォアグラウンドで実行し、
測定中に`git stash`・ブランチ切替・ファイル編集は行っていない。無言で
SKIPした分岐は無い（`bad allocation table`という結果は、記録すべき
結果として扱い、SKIPとして数えていない——事前登録の「`Ok`でなければ
その回はSKIP」という規則は水準ごとの完了確認に対するものであり、
段階1項目1自体の「書き込める/書き込めない」の判定はSKIPの対象では
ないため）。

## 情報境界

公式ROM・公式ディスクのバイト列、公式ROMの逆アセンブル、`private/`の
内容は読んでいない・出力していない。記録したのは公開FDCコマンド種別名、
段番号・一致/不一致の真偽、BASICの画面エラーメッセージ文字列
（`bad allocation table`・`file write protected`——これらはBASIC言語
仕様の一部として公開されている診断メッセージであり、ROM内部構造や
逆アセンブル結果ではない）、rc、自作ファイル名（`QL01`・`QL02`。公式
ディスクの実ファイル名ではない）、ディスクの通し番号・ダイジェストだけ
である。FDCデータポート値列・シリンダ値・PCN値は表示も転記もしていない。
資料は参照していない（言語仕様の範囲に確信があったため、`refs-nec-
manuals-2026-09-04.md`の判定係手順は本稿では追加で使っていない）。
生ログ・ディスク複製はリポジトリ外
（`/private/tmp/claude-501/.../scratchpad/m7he/`）に置き、コミットしない。

## 検証

`tools/check_cleanroom.sh`は全項目OK、rc=0。`git status`で`private/`由来
の混入・生ログ・ROM像・ディスク複製が無いことを確認した。`src/`・
`tools/`は本稿では変更していない。

## 根拠リンク（`ls`で存在確認済み）

[m7he](m7he-disk10-consecutive-read-origin-preregistration.md)・
[m7hb](m7hb-consecutive-read-rule-results.md)・
[m7hc](m7hc-consecutive-read-count-origin-preregistration.md)・
[m7hd](m7hd-consecutive-read-count-origin-results.md)・
[m7gy](m7gy-command56-divergence-preregistration.md)・
[m7gz](m7gz-command56-divergence-results.md)・
[m7gx](m7gx-disk10-divergence-results.md)（症状3・WRITE 0件の出所）・
[m7gt](m7gt-odd-cylinder-by-layout-change-results.md)（ライトプロテクト
解除の手当ての出所）・[m7gk](m7gk-save-drive-syntax.md)・
[m7gp](m7gp-disk-name-leak-path-closed.md)・
[m7gg](m7gg-data-disk-screening.md)（`disk#10`のREAD DATA件数突出の出所）・
[m7gd](m7gd-boot-disk-screening.md)（`disk#10`が起動不可であることの出所）・
`docs/spec/l3-subrom.md` 1.57節（第144版）・1.36節・1.37節・3節・
`tools/compare_l3_entry_fdc.py`（`command_names`・`--list-all-stages`）・
`tools/check_l3_screen_output.py`・`tools/check_l3_entry_screen.py`
（`reached`・`screen_rows`）・`tools/stage_disk_by_digest.sh`・
`tools/analyze_error_exchange_shape_selftest.sh`・
`tools/lib_l3_measure.sh`（`build_mixed_rom`）・
`tools/harness/frontend/main.c`（`MAX_KEYSTROKES`・`--save-to-disk-image`・
`schedule_typing`・`--disk2`）・`tools/check_cleanroom.sh`。
