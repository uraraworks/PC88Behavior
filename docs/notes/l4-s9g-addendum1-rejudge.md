# l4-s9g 追補1 — exactを比較から外した保存観測の再判定

状態: **再判定前**（2026-10-05）。この追補は器具の修正と一緒に
コミットされ、親が再判定する前に規則を固定する。本作業では公式ROMを実行せず、
保存済み公式観測の再判定も実行しない。

## 経緯と対照の仮定の誤り

[事前登録](l4-s9g-edit-invalidation-preregistration.md)と
[器具](../../tools/l4_editinv_measure.py)（af0e396）による公式の第1回測定は、
`../tmp/l4s9g-work/official_round1.tsv` に150腕×2走を保存した。
全300行が `gate_failed` になった。

原因は `control-direct-5/8/17` の予測が、誤り番号の包含だけでなく、
誤りの行と文言の完全一致（errorsの第3要素 `exact=true`）も要求したことだった。
公式観測はこれらで `exact=false`、番号の包含（第2要素）は全対照で正しく取れていた。
自作ROMは直接モードのこれらの対照で `exact=true` となり、自己検査は通過していた。

exactは公式の挙動として事前に測定していない性質だった。
番号の判別を確かめる対照の目的には不要な仮定を合格条件に含めていた。
自作ROMでの一致は、その仮定を公式の性質として裏付けるものではない。
親の事前試算ではexactを除けば対照10/10、本体の予測あり137腕がE_GWと一致し、
2走も一致、残る3腕は予測なしだった。これは再判定の正式結果として扱わない。

## 再判定の規則

- 全腕・全段階で、予測および期待値との比較からerrorsの第3要素exactだけを外す。
  誤り番号と包含、PRINTの印・値・順序は引き続き比較する。
- exactは観測のJSONにそのまま残し、真偽値としての形式検査も維持する。
  2走の一致はexactを含む観測全体の完全一致を要求する。
- 上記以外の比較・関門は事前登録のまま。対照10腕の一式と既知値一致、
  採取成功、印の妥当性、準備値・終端印を維持し、予測なし3腕も変更しない。
  `check` も同じ比較規則を用い、予測なしを合格にしない。

器具に `rejudge --measured IN --out OUT` を追加する。
保存TSVの腕・走番号・打鍵計画・採取失敗フラグを検査し、observationと
other_line_countsを2走分再構成して、measureと共通のemitで判定する。
旧gateと旧E_GWは再判定の入力条件にしない。旧全体関門失敗を
新しい関門の失敗として持ち越さず、観測から再検査する。
入力と出力は別ファイルにし、元の観測を保持する。

```sh
python3 tools/l4_editinv_measure.py rejudge --measured <保存済みTSV> --out <再判定TSV>
bash tools/l4_editinv_selftest.sh < /dev/null
```

再測定しない理由は、判定の仮定に誤りがあった一方、必要な観測の記録は完全で、
番号・包含・exact、PRINTの印と値、2走の採取失敗フラグが保存されているため。
2走の一致と形式の関門は再判定でも同じく効く。
修正済み器具の自己検査には、exactだけが異なる観測のagreeと、
番号が異なる観測のdiffer、保存TSVからの再構成と破損拒否を追加する。

`bash tools/l4_editinv_selftest.sh < /dev/null` は **rc=0**。
上記の合成検査と自作ROMの定数・既存機能17腕×2走、期待値改変拒否が通過した。
保存済み公式TSVへのrejudgeは未実行で、親がこの追補と器具の修正を
コミットした後に実行する。

## 副次的な発見の数え上げ（本文は記録しない）

直接モードの誤りの行の形に、公式と自作の差があった。
これは事前には未測定だった差であり、末尾の内容・文字や内部経路は推定しない。
保存済みTSVのerrorsだけを数えたexact=falseの腕は以下の96腕（各2走、計192行）。
この数え上げはE_GWの再判定ではない。
腕IDは操作IDと検査IDをハイフンで連結したもの。

| 操作または対照ID | exact=falseだった検査ID | 段階 | 腕数 |
|---|---|---|---:|
| control-direct-5/8/17、control-program-1/3/5 | 対照自身 | result | 6 |
| insert-before、insert-after、delete-before、delete-after、replace-stop、replace-before、replace-after、replace-identical、clear | cont、gosub、for、onerror、return-goto、next-goto、resume、resume-goto | result | 72 |
| new | cont、gosub、for、data、onerror、return-goto、next-goto、resume、resume-goto | result | 9 |
| missing | vars、cont、gosub、for、data、return-goto、next-goto、resume、resume-goto | operation | 9 |

公式側の文言は保存・転記しない。表示形の仕様確定や自作ROMの修正は本追補の範囲外。
