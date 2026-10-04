# l4-s9g 1回目結果 — E_GW の採用（行の編集・NEW・CLEAR のあとの状態）

2026-10-05。記録担当。公式ROMは測定済みで、本作業は既存TSVの集計と仕様・期待値の
編集のみ。ROMのバイト列や画面本文を読まず、自作プログラムのPRINT整数組と、
ERR番号・包含／完全一致の2値だけを使った。src/ と tools/ は変更していない。

## 集計

事前登録は [行編集後の状態の事前登録](l4-s9g-edit-invalidation-preregistration.md)、
追補は [追補1（exactを比較から外す再判定）](l4-s9g-addendum1-rejudge.md)。
器具は `tools/l4_editinv_measure.py`（`af0e396`、再判定の追加は `d3770e2`）。
元TSVはリポジトリ外の `../tmp/l4s9g-work/official_round1.tsv`、
再判定TSVは同 `official_round1_rejudged.tsv`。150腕×2走＝300行。

| 判定 | gate | E_GW | 行数 |
|---|---|---|---:|
| 元の判定（exactを含む） | gate_failed | gate_failed | 300 |
| 再判定（exactを除く） | pass | agree | 294 |
| 再判定 | pass | unpredicted | 6 |
| 再判定 | pass | differ / gate_failed | 0 |

元の全300行が gate_failed だった理由は追補1のとおり、対照3腕の予測が誤りの行の
完全一致（exact=true）まで要求したため。公式は誤りの全腕で exact=false だった。
再判定は観測を再構成して同じ関門を再検査したもので、対照10腕は全て既知値一致、
採取失敗0、2走の観測は全腕で完全一致（exactを含む）。

| 群 | 腕数 | agree | unpredicted | differ |
|---|---:|---:|---:|---:|
| 本体・予測あり | 137 | 137 | 0 | 0 |
| 本体・予測なし（missing × onerror／resume／resume-goto） | 3 | 0 | 3 | 0 |
| 対照 | 10 | 10 | 0 | 0 |
| 合計 | 150 | 147 | 3 | 0 |

**E_GW の判定: 予測のあった137腕（と対照10腕）が全て一致し、不一致は0。
登録候補 E_GW を、測定した14操作×10検査の範囲で採る。**
ただし再判定は事前登録の後に比較規則を変えた結果であり、exactを除いた範囲の
一致である（下記「決めなかったこと」）。事前登録の腕集合・各2走・打鍵列・固定予測は
変更していない。

## 操作14種×調べもの10種の表

各セルは「操作のあとの診断で観測した値または誤り番号」。誤り番号は ERR 番号だけで、
文言は記録していない（括弧内の名は l4-basic 第7.1節のマニュアルの記載）。
腕は操作ごとに別の起動、診断は準備の同じ停止状態から1操作だけ行った後に実行した。

操作は3つの組に分かれ、同じ組の中の全腕・全検査が同じ結果だった。

- **保持**: none・list・assign・missing（missing は ON ERROR／RESUME 設定中の3腕を除く）
- **初期化A**: insert-before・insert-after・delete-before・delete-after・
  replace-stop・replace-before・replace-after・replace-identical・clear（9操作）
- **初期化B**: new

| 検査（診断） | 保持 | 初期化A（編集成功・CLEAR） | 初期化B（NEW） |
|---|---|---|---|
| vars（変数・配列・文字列の値） | 17, 23, 3 のまま（assign は a=29、他は同じ） | 0, 0, 0（数値変数・配列要素・文字列の長さが空） | 同左 |
| cont（CONT） | 再開する（`s9hc 1 1`） | ERR 17（Can't continue） | ERR 17 |
| gosub（CONT） | 戻って続く（`s9hr 1 71`） | ERR 17 | ERR 17 |
| for（CONT） | 続く（`s9hf 1 3 4`） | ERR 17 | ERR 17 |
| data（READの位置、GOTO 110） | 次の値22（読み位置が保持される） | 先頭の値11（先頭へ戻る） | ERR 8（行110が無い） |
| onerror（GOTO 110） | 捕捉して続く（`s9he 1 5`、`s9hn 1 1`） | 捕捉されず ERR 5 | ERR 8（行110が無い） |
| return-goto（GOTO 110） | RETURN が戻る（`s9hr 1 71`） | ERR 3（RETURN without GOSUB） | ERR 8 |
| next-goto（GOTO 110） | NEXT が続く（`s9hf 1 3 4`） | ERR 1（NEXT without FOR） | ERR 8 |
| resume（CONT） | 続く（`s9hu 1 83`） | ERR 17 | ERR 17 |
| resume-goto（GOTO 110） | RESUME NEXT が戻る（`s9hu 1 83`） | ERR 20（RESUME without error） | ERR 8 |

読み取れること。

- 「停止位置より前／後」「行の挿入／削除／置換」「本文が長くなるか」「同一番号・
  同一本文の打ち直し」の差は、全検査で現れなかった。編集が成功すれば、
  これらは全部同じ結果だった。
- 初期化されるのは、変数・配列・文字列、CONT の再開位置、GOSUB の戻り先、FOR の
  続き、ON ERROR の設定、RESUME の保存（RESUME が使えなくなる）、READ の位置（先頭へ）。
  FOR／GOSUB の無効化は CONT 経由でも GOTO 経由（return-goto・next-goto）でも
  同じ誤り番号が観測され、CONT の可否とは独立に観測できた。
- DATA の読み位置は「消える」ではなく**先頭へ戻る**。NEW だけは本文が空になるため
  GOTO の行先が無く ERR 8 になり、DATA の位置・ON ERROR・RESUME・GOSUB／FOR の無効化
  そのものは NEW では GOTO 診断で観測できない（CONT 診断では ERR 17）。
- 直接モードの代入（assign）と LIST は何も初期化しない。assign は代入した変数だけが
  変わる。
- 存在しない行番号だけの入力（missing）は ERR 8 を出すが、状態は保持される（7検査）。

## 予測なしだった3腕の観測（記述のみ）

事前登録は誤り処理そのものが状態を変えうるため、missing × onerror／resume／
resume-goto を予測なしにした。観測は以下で、どれも2走一致。

| 腕 | 操作の段階 | 診断の段階 |
|---|---|---|
| missing-onerror | 誤り処理に入り、ERR 8 を示す印（`s9he 1 8`）、続けて `s9hn 1 1`（RESUME 120 で終了側へ）、その後 `s9ho 1 1`。直接の誤りの行は出ない | GOTO 110 で ERR 5 を捕捉して `s9he 1 5`、`s9hn 1 1`。ON ERROR は設定されたまま |
| missing-resume | 直接の ERR 8（捕捉されない）、`s9ho 1 1` | CONT で `s9hp 1 1` の印だけが出て、`s9hu` の印は出ず、誤りは出ない |
| missing-resume-goto | 同上（ERR 8、捕捉されない） | GOTO 110 で `s9hp 1 1` の印だけが出て、`s9hu` の印は出ず、誤りは出ない |

読み取れること: ON ERROR が設定されていると、直接モードの存在しない行番号の入力が
その設定どおりに誤り処理へ飛ぶ（missing-onerror）。誤り処理の中（RESUME 前）の
状態で同じ入力をすると誤りは捕捉されず ERR 8 が出て、そのあとの診断は CONT でも
GOTO 110 でも、RESUME の完了（`s9hu`）には至らず、行100の印が再び出た
（missing-resume・missing-resume-goto。2腕は同じ観測）。この3腕を
E_GW への適合には数えず、規則も立てない。なぜ行100の印が再び出るかは未確定。

## exact（誤りの行の形）の観測

再判定は比較から exact を外したが、観測の値は変えていない。公式は誤りが出た全腕
（ERR 番号を持つ96腕）で、番号の包含は true、完全一致 exact は false だった
（腕数は追補1の数え上げと一致。うち result 段階87、operation 段階9）。
自作は直接モードの対照で exact=true になる（追補1）。**差の中身（公式の行が
自作の行と何が違うか）は推定せず、記録もしない。** 行の文言は転記していない。

## 期待値の固定と照合

根拠の鎖は、自作PRINT整数組の測定TSV → 本ノート → [l4-program 第4.17節](../spec/l4-program.md)。
期待値 [expected_l4_editinv.tsv](../../tests/conformance/expected_l4_editinv.tsv)
は再判定TSVの全150腕で、列は `arm`・`observation`（1走目の観測JSON、公式のまま。
errors の第3要素 exact も公式の観測値 false を含める。check は比較からその要素を外す）。
予測なしの3腕は E_GW ではなく観測値そのものを保存している（記述の固定であり、
E_GW の予測ではない）。

```
python3 tools/l4_editinv_measure.py check --expected tests/conformance/expected_l4_editinv.tsv --measured ../tmp/l4s9g-work/official_round1_rejudged.tsv
```

照合一致、終了値0。公式ROMの再測定、git add、コミットは実行していない。

## 決めなかったこと

- LOAD・MERGE（ディスクを使う別段）、CHAIN、スクリーンエディタによる行の編集中の挙動。
- exact の差の中身。公式と自作で、直接モードの誤りの行の形が違う（96腕）。
  表示形の仕様確定と自作の修正は別段。
- 本文ポインタ・内部領域の消去方法、CLEAR の引数（容量）、乱数・イベント・
  ファイル・描画状態の初期化。
- ON ERROR／RESUME 設定中の存在しない行の入力の仕組み（上の3腕）。
- 自作実装の状況: 自作ROMは編集後の初期化を測っていない（事前登録どおり、
  17腕×2走の自己検査のみ）。実装は段D以降。
