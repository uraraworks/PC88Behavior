# m7ls: no_diskの打鍵フレームを動かしても+0の要求長が変わらないか（空き時間＝main受理件数の除外）— 事前登録

## 位置づけ

[m7lr](m7lr-no-disk-main-interrupt-attribution-results.md)は、7つ目の容疑者（窓内main側割り込み受理の差、
公式683件／混成679件）を介入で除外できなかった（公式側`suppress_near`腕が保存済みの+0交換軸へ届かず
`SearchError`で停止）。ただし診断（事前登録外）で、683／679の差は**「起動時交換が混成で5フレーム遅く
終わる」ことと「+0の要求が両側とも同じフレーム759に始まる」ことの差として、数の上で説明がついた**
（run35の終わりが公式77・混成82、run36=+0の開始は両側ともframe 759）。測定の打鍵はframe 700に
`FILES 2`＋改行で固定されている（道具のシナリオ）。

本稿はこの説明を**介入による除外へ格上げする**。固定打鍵のフレームを動かして「+0までの空き時間」
（＝窓内main受理件数）を変え、それでも+0の要求長（公式5・混成6）が動かないかを測る。

**言えるのは「打鍵フレーム500〜780の範囲で動かない」まで**であり、「起動時交換が混成で遅いこと」自体は
本介入の対象ではない（次の候補として残る。m7lrの「次の候補」1.）。

## 器具（本稿で足した。測定前にコミットする）

- **打鍵フレームの引数化**（`tools/search_error_response_candidate.py`）: `measure_once`と
  `calibration_measure`に固定で入っていた`--type-at 700 --type "FILES 2\n"`を、キーワード引数
  `files_type_at`（既定700）で差し替えられるようにした。共通部分は`keystroke_command_suffix(files_type_at)`
  へ切り出し、既定値のときのargvは変更前の固定argvとバイト単位で同一（自己検査で確認）。frame 300の
  改行は変更していない。
- **新モード`keystroke-shift`**（`--scenario no_disk`専用。既存の`main-interrupt-attribute`を型にした）:
  下記の腕を走らせ、判定を`keystroke-shift.json`へ出す。判定に使う純関数
  `keystroke_shift_arm_valid`（腕の有効性、条件a〜d）と`classify_keystroke_shift`（4判定）を切り出し、
  合成データだけで自己検査できるようにした。
- **自己検査**（`tools/search_error_response_candidate_selftest.sh`に追加）:
  - 既定`files_type_at=700`のargvが変更前の固定argvと完全一致すること。
  - `classify_keystroke_shift`に合成行を通し、4判定（`nondeterministic`・`keystroke_timing_affects_branch`・
    `wait_length_excluded`・`inconclusive_ineffective_arms`）がそれぞれ出ること。`unreached`（`valid=False`）
    な腕が1つでもあると`wait_length_excluded`にならないこと。
  - **陽性対照1**: 打鍵フレームの引数をargvへ渡し忘れる故障（腕が常に700で走る）を模し、`files_at=780`
    （期待ずれ+80）なのに実測ずれが0の合成データを`keystroke_shift_arm_valid`へ与えると、有効性条件(c)
    （+0開始フレームのずれが打鍵フレーム移動量と対応するか）が無効と判定することを確認した。
  - **陽性対照2**: 条件(c)の許容幅(tolerance)を無限にする故障を注入すると、陽性対照1と同じ合成データが
    「有効」に化けて検出できなくなることを確認した。これにより(c)が検出を担っていることを裏付けた。
  - いずれも**故障を注入した版で実際に赤くなることを見てから**、既定の実装（tolerance=2の`keystroke_shift_arm_valid`）
    に戻して緑になることを確認した。

## 測定前の関門（すべて真でなければ測定しない）

- **P1** 器具の自己検査と陽性対照2つ（済み）。
- **P2** `tools/run_all_selftests.sh`がrc=0（済み）。
- **P3** `calibrate --scenario no_disk --frames 900`で対照の要求長が公式5・混成6を再現し、
  校正軸（axis）が公式・混成とも36である（測定時に確認）。
- **P4** 既定打鍵（files_type_at=700）での`control`腕の要求長・+0開始フレーム・窓内main受理件数が、
  m7lrの診断値（公式: 要求長5・+0開始フレーム759・窓内受理682／混成: 要求長6・+0開始フレーム759・
  窓内受理677）と一致する（測定時に確認。一致しなければ測定しない）。

## 腕（公式側・混成側の両方で走らせる。axisはcalibrateが保存した+0の交換run番号）

| 腕 | files_type_at | 役割 |
|---|---|---|
| control | 700 | 対照（既定の打鍵フレーム） |
| control_repeat | 700 | 決定論性（対照と成果物指紋・指標が一致すること） |
| files_at_500 | 500 | 打鍵を200フレーム早める |
| files_at_600 | 600 | 打鍵を100フレーム早める |
| files_at_780 | 780 | 打鍵を80フレーム遅らせる |

`--frames`は校正と同じ900。

## 有効な腕の条件（測定前に固定する。すべて真）

`control`・`control_repeat`を除く3腕（`files_at_500`・`files_at_600`・`files_at_780`）× 2側 = **6腕**に適用する。

- (a) run 0〜axis-1の(方向, 長さ)列が、同じ側の対照（`control`腕）と同一（打鍵は起動時交換の後なので、
  手前は変わらないはず）。
- (b) `runs[axis]`が存在しmain→sub（＝+0交換軸へ到達している）。
- (c) **+0の開始フレームの対照からのずれが、(files_type_at − 700)に対し±2フレーム以内**
  （到達指標は介入と同じ次元＝打鍵フレームの移動量→+0開始フレームの移動量）。
- (d) 窓[axis-1, axis]内のmain受理件数（`no_disk_timing`の`interrupt_counts['main']['axis_near']`、
  m7lrと同じ取り方）が、同じ側の対照と異なる。

**腕が軸に届かない場合は例外で止めず、その腕を`reached=False`（無効）として記録して続行する**
（m7lrの教訓: 止めると判定が消える）。

## 判定規則（測定前に固定する。この順）

1. どちらかの側で**対照と対照の繰り返し（`control`と`control_repeat`）が（成果物指紋・指標とも）
   一致しない** → `nondeterministic`（結論を出さない）。
2. **公式側のどれかの有効な腕で要求長が5以外、または混成側のどれかの有効な腕で6以外になった**
   → `keystroke_timing_affects_branch`: **打鍵タイミング（＝空き時間・main受理件数）を動かすと、
   +0の要求長が動く。**
3. どれも動かず、**6腕すべてが有効** → `wait_length_excluded`: **打鍵フレーム500〜780・許容±2フレームの
   範囲で、main側受理差（空き時間）は+0分岐の原因ではない**（7つ目の容疑者の、この範囲での除外）。
4. どれも動かず、有効でない腕が1つでもある → `inconclusive_ineffective_arms`（除外もしない）。

## 記述として載せるもの（合否に使わない）

- 腕ごとの窓内main受理件数（対照・各腕）、+0開始フレームの対照からのずれと期待値との差、
  交換prefix・FDC prefix・画面3指標の一致。
- 公式・混成の対照で、窓内main受理件数がm7lrの682／677を再現するか。

## 言えないこと

- **エミュレータの上での振る舞いである。**
- 除外できても、**打鍵フレーム500〜780・許容±2フレームの範囲に限る**。
- **起動時交換が混成で数フレーム遅いこと自体は、本介入では動かしていない**（m7lrの「次の候補」2.として残る）。
- 動いても「打鍵タイミングが分岐に効く」までで、**公式mainが要求長を何で決めているかは言わない。**

## 禁止（本稿の測定中も例外なく適用）

公式ROM・公式ディスクのバイト列を読まない・出力しない・逆アセンブルしない。`private/`の中身を見ない。
道具は交換値・FDC生値・画面本文・PC・割り込みlevel・絶対clockを保存しない（件数・長さ・一致・指紋・
フレーム番号だけ）。私物のパスは環境変数でだけ渡す。本稿の測定（公式環境での実走）はまだ実施しない。

## 結果ノート

`docs/notes/m7ls-no-disk-keystroke-shift-results.md` に書く。腕・窓・判定規則を後から動かさない。

## 根拠リンク

[m7lr 事前登録](m7lr-no-disk-main-interrupt-attribution-preregistration.md)・
[m7lr 結果](m7lr-no-disk-main-interrupt-attribution-results.md)（本稿の動機、683/679の説明、
「次の候補」1.）・仕様1.50〜1.52節・3章（no_diskの残差）・
[m7co](m7co-no-disk-request-branch-hypothesis.md)（683／679の観測とsub側割り込みの帰属・陽性対照の作法）。
