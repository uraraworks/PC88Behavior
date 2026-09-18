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
