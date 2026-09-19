# l4-s1g — スクリーンエディタ「RETURNで画面上の行を読み直す」— 結果

記録日: 2026-09-19
根拠: 事前登録
[l4-s1g-screen-editor-return-preregistration](l4-s1g-screen-editor-return-preregistration.md)
（改訂1`3b3be75`）＋追補
[l4-s1g-screen-editor-return-preregistration-addendum](l4-s1g-screen-editor-return-preregistration-addendum.md)
（`da3cc2d`、settle手順の訂正）。実ROM（`PC88_REF_ROM_DIR`経由、
`private/`への直接アクセスは一切無し）。画面本文は記録していない
（座標・件数・SHA-256・自分で打ったBASIC文字列・候補表既載の数値のみ）。

## 関門

| 関門 | 結果 | 備考 |
|---|---|---|
| G1 器具 | **真** | 既存自己検査（ROM不要）は流用元(l4-s1f)でOK済み。PC1(陽性対照)自体がBASIC文字列＋特殊キー混在チェーンの自己検査を兼ねる（下記G4）。`tools/l4_s1g_candidates.py --check`もOK（前セッションで確認済み）。 |
| G2 取りこぼし・警告0 | **真** | 全走rc=0。打鍵系の警告0。 |
| G3 決定論性 | **真** | 関門P(9箇所)・本走(9腕)とも各2走で座標・署名・生存候補が完全一致。 |
| G4 陽性対照 | **真** | PC1の出力行が`print_12`候補と一致（2走とも）。 |
| G5 陰性対照 | **真** | NC1（settle後HOME/CLRのみ、以後無打鍵）で2走ともvram差分0件。 |
| G6 反映の遅れ | **真** | 既存値(D=10)を流用、全腕で変化を確認。 |
| G7 | **対象外** | 事前登録が測定前に対象外と明記済み（Q2/CRTC解析器具が無いため）。 |
| G8 故障注入 | **真** | 本走で実測した署名（R1a/U1/E1/T1/PC1の出力行）を候補表の`_fault_dummy_of_*`全件と直接照合し、一致0件を確認。 |
| G9/関門P | **真** | 下記「関門P」節のとおり、対象操作を押す直前の位置を対象操作無しの対照走で確認済み（9箇所、各2走一致）。 |
| G10 | **真** | 出力行と想定した行は、対象操作前の写しで非空白0件だった（`nb_before`に出力行が含まれない）ことを確認。 |
| G11（追補で新設、settle確認） | **真** | settleの2回目のRETURN前後で画面全体の非空白件数が変化しないことを確認済み（追補の切り分けで確認、本走はこの手順を踏襲）。 |

## 関門P（位置確認）

R1a/R1b/R1c・E1・T1/T2・U1-a/U1-b/U1-cの9箇所、いずれも対象操作無しの
対照走（各2走）で、目印の着地点が事前登録の設計どおり（R1a=列7、
R1b=列8、R1c=列0、U1-a=(行1,列0)、U1-b=(行1,列1)、U1-c=(行0,列0)、
E1=列9〈行は打鍵計画上の自然な位置〉、T1=列7、T2=列8）であることを
確認した（2走とも完全一致）。1つもずれは無かった。

## 判定

### 群R（Q1・Q2、どちらの行が実行されるか）

R1a・R1b・R1c、3位置すべてで出力行が候補`print_42`（画面上の内容
`print 42`が示す値）と一致し、`unique_survivor(whole_line)`（縮退込み、
事前登録の想定どおり）。**候補`buffer_wins`（値12）は3位置とも生存せず。**

**群Rの結論: `whole_line`（画面に表示されている内容がそのまま実行される。
打鍵バッファではない）。** R1a（上書き直後）・R1c（列0まで戻した場合）
も含め、一貫して画面の内容（`42`）が実行された。

### 群U（Q3、別の行へ移ってからのRETURN）

U1: RETUENを押す直前は出力行(row1)が候補`print_99`（99への上書き）と
一致していたが、RETURN後は候補`print_12`に変化した（`docs/notes/
l4-s1g-candidate-table.json`と直接照合）。`unique_survivor
(reexec_overwrites_below)`。

**群Uの結論: `reexec_overwrites_below`。** 画面上の別の（既に実行済みの）
行へカーソルを戻してRETURNを押すと再実行され、その出力が下の行（99へ
上書きされていた行）を上書きする。

### 群E（Q4、プログラム行の編集）

E1: `LIST`出力行の値`1`を`4`へ上書きしてRETURN、続けて`run`+RETURNを
打った結果、出力行が候補`print_42`と一致した。`unique_survivor
(line_registration_updated)`。

**群Eの結論: `line_registration_updated`。** `LIST`で表示された行番号
つきの行をカーソルで書き換えてRETURNを押すと、登録されているプログラム
の内容が実際に書き換わる。

### 群T（Q5、行末の古い文字の扱い）

T1（上書き直後、列7）・T2（列8、旧`2`の直後）、いずれも出力行が候補
`print_423`と一致した。`unique_survivor(reads_whole_row)`（両位置とも）。

**群Tの結論: `reads_whole_row`。** 元の行より短い内容で上書きしても、
上書きされずに残った行末の古い文字（`2``3`）は読み直しの対象に**含まれる**
（`4`で上書きした行は`print 423`として実行された）。

## 未実施

- 論理行（80文字を越える行）の読み直し、挿入モードでの列79詰まった行への
  挿入は、事前登録の「対象外」節のとおり本ノートの対象外。
- G7（Q2/CRTC）は事前登録の時点で対象外と明記済み。

## 前提についての注記

本走は、事前登録改訂1が想定していた「HOME/CLR初期化」の前に、追補の
settle手順（RETURN×2、G11で無反応を確認）を挟んで実施した。これにより
[l4-s1f-screen-editor-results](l4-s1f-screen-editor-results.md)「前提に
ついての注記」が記録した「frame700は起動時の入力待ち中だった」問題を
回避している。関門P・本走とも、settle後の座標は事前登録本体が設計した
相対位置（例: R1a=列7、U1-c=(行0,列0)）とそのまま一致した。

## 行き先

`docs/spec/l3-main.md`の`01:7`（RETURN）の記述、`docs/spec/l4-basic.md`・
`l4-program.md`のRETURN再読込に関する節の追記は、別担当（判定後の実装
担当）が行う。本ノートは測定・判定のみ。

## 根拠リンク

[l4-s1g-screen-editor-return-preregistration](l4-s1g-screen-editor-return-preregistration.md)・
[l4-s1g-screen-editor-return-preregistration-addendum](l4-s1g-screen-editor-return-preregistration-addendum.md)・
[l4-s1f-screen-editor-results](l4-s1f-screen-editor-results.md)（前提に
ついての注記）・`tools/l4_s1g_arms.py`・`tools/l4_s1g_candidates.py`・
`docs/notes/l4-s1g-candidate-table.json`。
