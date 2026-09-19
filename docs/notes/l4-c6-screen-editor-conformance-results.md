# l4-c6 — スクリーンエディタ適合の場面固定 — 結果

記録日: 2026-09-19

## 位置づけ

別担当が`docs/spec/l3-main.md`第4.1版 第16・17節だけを見て自作main
ROM（コミット`4e373c9`、自己検査`c4c9d53`）にスクリーンエディタ
（カーソル移動・INS/DEL・HOME/CLR・RETURN再読込）を実装した。自作
どうしの自己検査は両側に同じ誤解が入りうるため、公式ROM（環境変数
`PC88_REF_ROM_DIR`経由。`private/`への`ls`・`cat`・`find`等は一切
実施していない）と実際に打鍵を流して突き合わせる。**測定・照合のみを
行う。不一致が見つかっても自作ROMは直さない**（実装の修正は別担当）。

器具: `tools/l4_editor_conform_record.py`（打鍵計画の実行・座標記録、
`fe197e4`の前段`e359376`）・`tools/l4_editor_conform_normalize.py`
（件数・SHA-256への正規化、`fe197e4`）・`tools/conform_l3_editor.sh`
（実行スクリプト、`fe197e4`）。期待値
`tests/conformance/expected_l4_editor.tsv`は公式ROMで採取した
（`c424577`）。画面本文は一切記録していない（座標・件数・SHA-256のみ）。

## 対象・除外

`docs/spec/l3-main.md`第16節（矢印・INS/DEL・HOME/CLR、行の途中8腕＋
真の境界6腕〈B1・B2・B2'・B3・B3'・B4〉）・第17節（RETURN再読込、
R1a・R1b・R1c・U1・E1・T1・T2＋陽性対照PC1）の計22腕を対象とした。

以下は`docs/spec/l3-main.md`第18節「未確定」に当たるため、照合対象から
**除外した**（別担当が実装時に仮決めした部分と対応する）:

- **挿入モードで列79まで実文字が詰まった行への挿入**（未測定のまま。
  実装側の「RETURNで解除」は挿入モードを抜ける条件の仮決めであり、
  そもそも「抜ける条件」自体が未確定〈第16節「未実施・未確定」〉）。
- **挿入モードを抜ける条件**（同上）。
- **→単発での列79越え**（測定は長押し〈自動繰り返し〉でのみ行っており、
  単発押下での境界越えは未測定。実装側の「長押しと同じ」は仮決め）。
- **行0・最終行の境界の組み合わせ**（例: 最上行で↑、最終行で↓）
  （第16節はB1〜B4・B2'・B3'〈列0/列79の境界〉のみを対象とし、行方向
  〈行0・最終行〉の境界は測定していない。実装側の「無反応」は仮決め）。
- 80文字を越える論理行・CTRL系編集キー・G7（CRTC/iolog）は元々の
  第16・17節でも対象外。

## 結果

**22腕中21腕が一致、1腕（B4）が不一致。**

| 腕 | 一致 |
|---|---|
| arrow_left_mid・arrow_right_mid・arrow_up_mid・arrow_down_mid | 一致 |
| insdel_noshift_mid・insdel_shift_mid | 一致 |
| homeclr_noshift_mid・homeclr_shift_mid | 一致 |
| B1・B2・B2'（`B2p`）・B3・B3'（`B3p`） | 一致 |
| B4 | **不一致** |
| R1a・R1b・R1c・U1・T1・T2・E1・PC1 | 一致 |

### 不一致: B4（→を列79を越えるまで長押し）

最初に違うセルの位置（目印文字を打った差分。内容は書かない）:

- 公式ROM: 行1・列64
- 自作ROM: 行0・列1

自作ROMは、公式ROMと同じ長さ（600フレーム）の押しっぱなしに対して、
目印がほぼ動いていない（列1のみ）。公式ROMは自動繰り返し（キーリピート）
により継続的に列79を越えて次の行へ進むが、自作ROMではこの自動繰り返し
が働いていない、という座標の違いとして観測された（件数・座標のみで
判定。内容には触れていない）。

`docs/spec/l3-main.md`第18節項5「キーリピート（...リピート開始までの
遅延・リピート間隔そのものは測定していない）」のとおり、公式ROMの
キーリピートの正確な挙動（開始遅延・間隔）はこの適合テストの対象外
の測定に依存する部分であり、本テストは「同じ打鍵計画に対する結果が
一致するか」だけを見ている。

## 判定名との対応

一致した21腕は、いずれも判定名（`no_change`・`row_move`・`del_left`・
`ins_mode_only`・`clear`・`home`・`wrap_prev_line_end`・
`boundary_no_op`・`whole_line`・`reexec_overwrites_below`・
`line_registration_updated`・`reads_whole_row`）に対応する座標・出力
署名が公式・自作間で完全一致した。B4（`wrap_to_next_line`）のみ、
着地位置が一致しなかった。

## 再現方法

```
tools/conform_l3_editor.sh                                    # 自作ROM側の照合のみ
PC88_REF_ROM_DIR=/path/to/rom tools/conform_l3_editor.sh       # 公式の再現性確認+自作照合
```

## 行き先

B4の不一致（自動繰り返しの実装）への対応は、実装担当が判断する。本
ノートは測定・照合の記録のみで、自作ROM側のソースは変更していない。

## 根拠リンク

`docs/spec/l3-main.md`第16・17節・`tools/l4_editor_conform_record.py`・
`tools/l4_editor_conform_normalize.py`・`tools/conform_l3_editor.sh`・
`tests/conformance/expected_l4_editor.tsv`・`tools/conform_l4.sh`
（二層方針の踏襲元）。
