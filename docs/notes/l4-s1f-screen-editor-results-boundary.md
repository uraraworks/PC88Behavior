# l4-s1f — 境界（真の列0・列79）— 結果

記録日: 2026-09-19
根拠:
[l4-s1f-screen-editor-preregistration-addendum2](l4-s1f-screen-editor-preregistration-addendum2.md)
（`aaf7240`）。実ROM（`PC88_REF_ROM_DIR`経由、`private/`への直接アクセス
は無し）で6腕、各2走を実施。画面本文は記録していない（座標・件数・
自分で打った文字のコードのみ）。

## 関門

- G3（決定論性）: **真**。6腕とも2走で目印座標が完全一致。
- G1・G2・G4-G9: 本体・追補1の枠組みを流用（HOME/CLR無修飾による画面
  初期化＝新規の陽性対照を兼ねる。全腕でrc=0、打鍵系の警告0）。

## 判定

| 腕 | 設定 | 目印の着地点 | 判定 |
|---|---|---|---|
| B1 | ←を真の(行0,列0)で単発押下 | (行0,列0)（不変） | `unique_survivor(clamp_no_change)` |
| B2 | ←を(行1,列0)で単発押下、行0は空白 | (行0,列79) | `unique_survivor(wrap_prev_line_end)` |
| B2' | ←を(行1,列0)で単発押下、行0に1文字だけ内容あり | (行1,列0)（不変） | `unique_survivor(clamp_no_change)` |
| B3 | DEL無修飾を真の(行0,列0)で単発押下 | (行0,列0)（不変） | `unique_survivor(boundary_no_op)` |
| B3' | DEL無修飾を(行1,列0)で単発押下、行0に1文字だけ内容あり | (行1,列0)（不変、行0の内容も無変化） | `unique_survivor(boundary_no_op)` |
| B4 | →を列79に達するまで（さらに越えるまで）長押し | 次の行（行+1）の列へ継続的に進んだ | `unique_survivor(wrap_to_next_line)` |

いずれも候補は1つだけが生き残り、`no_survivor`・`multiple_survivors`は
無かった。

## 結論

- **DEL（無修飾）は真の境界（行頭・列0）では常に無反応**
  （`boundary_no_op`）。直前の行に内容があっても、それを消して詰める
  （`merge_prev_line`）ことは起きなかった（B3・B3'とも不変）。本体の
  訂正で取り下げた「DELは行頭でも縮退しない」は、**真の境界では逆に
  「常に縮退する（無反応になる）」が正しい**、と本ラウンドで確定した。
- **→は列79を越えて長押しすると次の行へ回り込む**（`wrap_to_next_line`）。
  クランプ（止まる）は観測されなかった。
- **←の境界での挙動は、直前の行の内容の有無に依存する。** 直前の行が
  空白なら列79へ回り込む（`wrap_prev_line_end`）。直前の行に既に文字が
  あると、単発の押下では回り込まず、その場（行1・列0）に留まる
  （`clamp_no_change`）。この条件分岐そのものが今回の主な新規知見であり、
  「←は境界で常に○○する」という単一の結論には縮約できない。

## 未実施

- 「挿入モードで列79まで実文字が詰まった行に1文字挿入」は、実文字での
  行充填手順が新規に要るため本ラウンドでは実施していない（追補2に
  明記、次回持ち越し）。
- G7（Q2/CRTC経路との突き合わせ）は本ラウンドでも未実施（本体の訂正と
  同じ理由・同じ位置づけ）。判定はQ3（目印の直接確認）のみで行った。

## 行き先

`docs/spec/l3-main.md`への反映は別担当が行う。本ノートは測定・判定のみ。

## 根拠リンク

[l4-s1f-screen-editor-preregistration-addendum2](l4-s1f-screen-editor-preregistration-addendum2.md)・
[l4-s1f-screen-editor-results](l4-s1f-screen-editor-results.md)（訂正節・
HOME/CLR無修飾=`clear`の根拠）。

## 訂正（レビューによる）

記録日: 2026-09-19。本節はコーディネータによるレビューを受けての訂正で
あり、上記本文は書き換えず追記のみ行う。

### B2'・B3'の準備手順に位置ずれがあった

B2'・B3'の準備手順「HOME/CLR→文字1つ→↓」は、文字を1つ打った時点で
カーソルが(行0,列1)（打鍵は必ずカーソルを1つ右へ進める）になっており、
続く↓は列不変（本体で確定済みの`row_move`）なので、実際に対象キーを
押した位置は**(行1,列0)ではなく(行1,列1)** だった。

この結果、B2'（←、旧記録「(1,0)のまま＝`clamp_no_change`」）は
(1,1)→(1,0)という**行の途中での通常の左移動**と区別できず、B3'（DEL、
旧記録「(1,0)のまま＝`boundary_no_op`」）も(1,1)での`del_left`（左の
空白1つを詰めて(1,0)へ）と区別できない。**したがって「←は前の行の
内容の有無に依存して分岐する」「DELは前の行に内容があっても行頭で
無反応」という結論は成り立たず、取り下げる。**

有効な（境界を正しく捉えている）結論は**B1・B2・B3・B4のみ**。
B2'・B3'は下記の追補3による取り直しに置き換わる。

### 位置確認の対照

指摘を受け、B1〜B4の準備手順についても、対象キーを押す直前の位置を
「対象キー無しで直接目印を打つ対照走」で確認し直した（各2走、目印の
座標のみ記録。以下いずれも2走完全一致）。

- B1・B3・B4の準備（HOME/CLR単独）→ (行0,列0)。本体で`clear`候補の
  Q3として既に複数腕で確認済みの値と一致。
- B2の準備（HOME/CLR→↓）→ (行1,列0)。本体で`row_move`（列不変）が
  確定済みのため妥当。
- 訂正後のB2'・B3'の準備（HOME/CLR→文字1つ→↓→←、←はもう1回分の
  位置決めとして追加）→ (行1,列0)を確認。

詳細（新しい候補・取り直した測定）は
[l4-s1f-screen-editor-results-boundary2](l4-s1f-screen-editor-results-boundary2.md)
（追補3
[l4-s1f-screen-editor-preregistration-addendum3](l4-s1f-screen-editor-preregistration-addendum3.md)
に基づく）を参照。

## 直接モードでの取り直し（B1・B4）

記録日: 2026-09-19。
[l4-s1f-screen-editor-results](l4-s1f-screen-editor-results.md)
「前提についての注記」・
[l4-s1g-screen-editor-return-preregistration-addendum](l4-s1g-screen-editor-return-preregistration-addendum.md)
（settle手順、G11）のとおり、境界ラウンド（本ノート・追補2・追補3の
B1〜B4・B2'・B3'）は**すべてframe700の起動時入力待ちの中で測定していた**
ことが判明した。B2・B3は既に
[l4-s1f-screen-editor-results-boundary2](l4-s1f-screen-editor-results-boundary2.md)
の前提注記で扱い済みのため、残るB1・B4を、settle手順（RETURN×2、G11で
無反応を確認）の後の真の直接モードで取り直した。

- **関門P（位置確認、対象操作無しの対照走、各2走）**: settle→HOME/CLR
  →目印、で(行0,列0)を確認（2走一致）。B1・B4とも起点は同じ(0,0)のため
  この1本で両腕分を兼ねる。
- **B1（←を真の(行0,列0)で単発押下）**: 目印の着地点は(行0,列0)（不変）、
  2走完全一致。`unique_survivor(clamp_no_change)`。**入力待ち中の結果
  （`clamp_no_change`）と一致。**
- **B4（→を列79に達するまで長押し）**: 目印の着地点は(行1,列64)、
  2走完全一致。`unique_survivor(wrap_to_next_line)`。**入力待ち中の結果
  （`wrap_to_next_line`、着地列も同じ列64）と一致。**

**結論: B1・B4とも、入力待ち中の判定名（`clamp_no_change`・
`wrap_to_next_line`）と完全に一致した。撤回する結論は無い。** これで
本ノート・追補2・追補3が扱った境界腕（B1・B2・B2'(改)・B3・B3'(改)・B4）
すべてについて、真の直接モードでの再現確認が完了した。
