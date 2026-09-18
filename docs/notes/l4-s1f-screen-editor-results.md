# l4-s1f — スクリーンエディタ — 結果

記録日: 2026-09-19
根拠: 事前登録
[l4-s1f-screen-editor-preregistration](l4-s1f-screen-editor-preregistration.md)
（改訂1`39620ac`）＋追補
[l4-s1f-screen-editor-preregistration-addendum](l4-s1f-screen-editor-preregistration-addendum.md)
（`e585b8d`）。実ROM（環境変数`PC88_REF_ROM_DIR`経由。`private/`への
`ls`・`cat`・`find`等は一切実施していない）で24腕×2走＋対照4走の実測。
画面本文（マーカー・目印以外の文字内容）は一切記録していない
（座標・件数・SHA-256・自分で打った文字のコードのみ）。

## 関門

| 関門 | 結果 | 備考 |
|---|---|---|
| G1 器具 | **真** | ROM不要の既存自己検査5件は全てOK（前段コミット`2bbde68`）。「連続打鍵チェーンの自己検査」は、追補で採用したwindow署名モデルの陽性・陰性対照（下記G4・G5）が実ROMで期待どおりの結果（陽性=`no_change`候補と完全一致、陰性=空列のSHA-256）になったことをもって、より強い形で代替確認した（`tools/l4_s1f_chain_selftest.sh`単体の`--type`比較は、CAPSを意図的に外した設計のため実施していない。追補に経緯記載）。 |
| G2 取りこぼし・警告0 | **真** | 52走全てrc=0。stderrに「警告」「打てない」の一致0件（ROM任意拡張ファイルの`Couldn't find`は起動可否と無関係の定型ログで、全走で同数・同内容のため打鍵系の警告ではない）。 |
| G3 決定論性 | **真** | 24腕×2走、対照4走とも、window署名(SHA-256)・Q3差分件数・差分座標が2走間で完全一致。 |
| G4 陽性対照 | **真** | マーカーのみの走のwindow署名が、v2候補表`no_change`（未編集マーカー）候補と完全一致（2走とも）。 |
| G5 陰性対照 | **真** | 無打鍵走のwindow署名が空列のSHA-256（`e3b0c442...`）、非空白0件（2走とも）。 |
| G6 反映の遅れ | **真** | D=10で全腕とも変化を確認（既存値を流用、本ノートでは再決定しない）。 |
| G7 経路一致 | **未実施** | Q2（CRTC、iolog）の解析は本セッションでは行っていない（iolog内の`frame`列がvram-dumpの`--vram-dump-at`と単位が一致せず、対応付けの器具が無かった）。判定はQ3（目印挿入、差分で直接確認）のみで行った。Q2との突き合わせは次回への持ち越し。 |
| G8 故障注入 | **真** | v2候補表の`_fault_dummy_of_*`（1バイトずらし）は設計上、実測と一致しない値（生成時に検証済み、`tools/l4_s1f_candidates_v2.py`）。 |
| G9 隣接行空白 | **真** | 全腕の打鍵前write写しで、マーカー行(row0=1)前後の非空白件数の内訳（row1=19+row19=21+マーカー5=45、または+SHIFT分48）が一致し、他行（row0・row2）からの寄与が0であることを確認。 |

## 前提（追補による具体化、参考値）

マーカー行row0=1、マーカー開始列col_start=22（本番24腕で再現、2走×24腕
=48走全てで同一）。この値はハードウェア設定値相当の位置情報であり、
画面本文ではない。

## Q1・Q3 判定

各キー条件について、3位置（行頭・行中・行末）の`unique_survivor`が
一貫しているため、以下のとおり確定した（未決定は無し）。

| # | キー条件 | Q1判定（3位置一貫） | Q3（カーソル、3位置とも一貫） |
|---|---|---|---|
| 1 | ← 無 | `no_change` | 列−1（境界＝行頭でも同一行内に留まり前の行へは回り込まない。`wrap_prev_line`は不採用） |
| 2 | → 無 | `no_change` | 列+1（境界＝行末でも同一行内に留まり次の行へは回り込まない。`wrap_next_line`は不採用） |
| 3 | ↑ 無 | `row_move`（`no_change`とは別候補として確定） | 行−1・列不変 |
| 4 | ↓ 無 | `row_move` | 行+1・列不変 |
| 5 | INS/DEL 無 | `del_left` | 列−1（行頭でも同様に左詰めが起こり、`no_change`への縮退は観測されなかった） |
| 6 | INS/DEL SHIFT | `ins_mode_only` | 目印直後の打鍵で後続文字が右へ押し出される（挿入モード成立を確認、行頭・行中で複数セル変化） |
| 7 | HOME/CLR 無 | `clear` | (0,0)（画面消去＋ホームポジション） |
| 8 | HOME/CLR SHIFT | `home` | (0,0)（内容不変、カーソルのみホームへ） |

### INS/DELの機能名（事前登録の判定規則どおり）

**無修飾=`del_left`、SHIFT=`ins_mode_only`。** 無修飾はカーソル位置を含む
以降を1つ左へ詰める動作（行頭でも縮退せず、実際に左シフトが起きた）。
SHIFTは押した時点では行内容が変化せず、直後に打った目印文字がその位置に
挿入され、後続の文字が右へ押し出された（行中で4セル、行頭で6セル変化。
これはSHIFT保持中に押した目印1文字の挿入で説明できる件数で、`del_at`
（列不変・押し出し無し）や`ins_space`（キー単独で空白挿入）とは一致しない）。

### HOME/CLRの機能名

**無修飾=`clear`、SHIFT=`home`。** 無修飾を押すと画面全体の非空白セルが
ファンクションキー表示行（row0=19、既存仕様`fkey_row_reserved`）のぶんの
21件のみまで減り（起動画面の内容・マーカーとも消える）、カーソルは
(0,0)へ移る。SHIFTを押すと画面内容はほぼ不変（マーカー・起動画面とも
残る）で、カーソルのみ(0,0)へ移る。

## 判定名との対応（`unique_survivor`/`no_survivor`/`multiple_survivors`）

矢印キーの境界腕（←行頭・→行末・↑↓全位置）は、window署名だけでは
`no_change`と対抗候補（`wrap_prev_line`/`wrap_next_line`/`row_move`）の
両方が生き残る`multiple_survivors`状態だったが、Q3（目印の実座標）で
一意に決着した（事前登録の「Q1候補だけでは区別できない場合はQ2・Q3で
区別する」規定どおり）。INS/DEL・HOME/CLRはwindow署名（またはHOME/CLRは
画面全体件数）のみで`unique_survivor`が得られた。

## 未決定・持ち越し

- **G7（Q2/CRTC経路との突き合わせ）は未実施。** iolog解析器具
  （`--vram-dump-at`のフレーム番号とiolog内`frame`列の単位対応付け）が
  無く、本セッションでは作らなかった。Q3（目印挿入による直接確認）で
  全腕とも一意に決着しているため判定自体への影響は無いと考えるが、
  正式にはG7「真」ではなく「未実施」として記録する。
- RETURN再読込（事前登録が明示的に対象外とした第2弾分）は本ノートの
  対象外のまま。

## 行き先

`docs/spec/l3-main.md` 第9節の`no_write`・未判定の記述の更新は、
別担当（判定後の実装担当）が行う。本ノートは測定・判定のみ。

## 根拠リンク

[l4-s1f-screen-editor-preregistration](l4-s1f-screen-editor-preregistration.md)・
[l4-s1f-screen-editor-preregistration-addendum](l4-s1f-screen-editor-preregistration-addendum.md)・
`tools/l4_s1f_arms.py`・`tools/l4_s1f_candidates_v2.py`・
`docs/notes/l4-s1f-candidate-table-v2.json`・`tools/l4_s1f_window_probe.py`。
