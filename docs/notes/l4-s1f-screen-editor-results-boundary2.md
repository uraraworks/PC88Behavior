# l4-s1f — 境界（B2'・B3'取り直し、位置確認つき）— 結果

記録日: 2026-09-19
根拠:
[l4-s1f-screen-editor-preregistration-addendum3](l4-s1f-screen-editor-preregistration-addendum3.md)
（`08d344f`）。実ROM（`PC88_REF_ROM_DIR`経由、`private/`への直接アクセス
は無し）。画面本文は記録していない（座標・自分で打った文字のコード
のみ）。

## 関門P（位置確認、対象キー無しの対照走）

| 対照 | 準備手順 | 目印の着地点（2走とも） |
|---|---|---|
| P-A | HOME/CLR単独 | (行0,列0) |
| P-B | HOME/CLR→↓ | (行1,列0) |
| P-C | HOME/CLR→文字1つ→↓→←（B2'/B3'用の修正手順） | (行1,列0) |

いずれも2走完全一致。P-Cにより、B2'(改)・B3'(改)が意図どおり
(行1,列0)（行0に1文字だけ内容がある状態）で対象キーを押していることを
確認した。P-A・P-Bは訂正節（`l4-s1f-screen-editor-results-boundary.md`
末尾）に記録済みの再掲。

## B2'(改)・B3'(改)

| 腕 | 対象キー | 目印の着地点（2走とも一致） | 判定 |
|---|---|---|---|
| B2'(改) | ←(`0A:2`)単発 | (行0,列79) | `unique_survivor(wrap_prev_line_end)` |
| B3'(改) | DEL無修飾(`08:3`)単発 | (行1,列0)（不変） | `unique_survivor(boundary_no_op)` |

候補は1つだけが生き残り、`no_survivor`・`multiple_survivors`は無かった。

## 結論（更新）

位置ずれを修正した結果、B2'(改)・B3'(改)は**B2・B3（行0が空白の場合）
と同じ結論になった**。すなわち:

- **←は真の境界（列0）では、前の行の内容の有無によらず常に
  `wrap_prev_line_end`（前の行の列79へ回り込む）。**
  （B2＝行0空白→(0,79)、B2'(改)＝行0に1文字→(0,79)。両者一致）
- **DEL（無修飾）は真の境界（列0）では、前の行の内容の有無によらず
  常に`boundary_no_op`（無反応）。**
  （B3＝行0空白→無変化、B3'(改)＝行0に1文字→無変化。両者一致）

`l4-s1f-screen-editor-results-boundary.md`が記録した「←は前の行の内容に
依存して分岐する」は、位置ずれによる誤りだったことが確定した
（訂正節のとおり撤回）。**正しい結論は「分岐しない・常に同じ」である。**

## 未実施（変更なし）

- 「挿入モードで列79まで実文字が詰まった行に1文字挿入」は未実施のまま。
- G7（Q2/CRTC経路との突き合わせ）は本ラウンドでも未実施。

## 行き先

`docs/spec/l3-main.md`への反映は別担当が行う。本ノートは測定・判定のみ。

## 根拠リンク

[l4-s1f-screen-editor-preregistration-addendum3](l4-s1f-screen-editor-preregistration-addendum3.md)・
[l4-s1f-screen-editor-results-boundary](l4-s1f-screen-editor-results-boundary.md)
（訂正節、B1〜B4の結果）。
