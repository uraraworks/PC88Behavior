# l4-s1f — 事前登録への追補（マーカー開始位置・CAPS切り分け）

記録日: 2026-09-19
状態: 本番24腕の**前**にコミット。事前登録本体
（[l4-s1f-screen-editor-preregistration](l4-s1f-screen-editor-preregistration.md)、
改訂1`39620ac`）の判定名・関門の意味は変えない。前提の具体化のみ。

## 経緯

事前登録どおりに器具（`tools/l4_s1f_arms.py`・`tools/l4_s1f_candidates.py`・
`tools/l4_s1f_run.sh`）をコミット（`2bbde68`）した後、実ROM（環境変数
`PC88_REF_ROM_DIR`経由。`private/`への`ls`・`cat`・`find`等は一切実施
していない）で「連続打鍵チェーンの自己検査」を試走したところ、以下2点が
事前登録の前提と食い違った。いずれも**本番の腕数には数えない**予備走
（切り分け専用）で確認した。

## 切り分け1: CAPS保持

**結論: CAPSは事前登録どおりに機能している。誤りは無かった。**

`tools/l4_s1f_arms.py`と同じタイミング（CAPS(`0A:7`)をframe700から
HOLD136で押しっぱなし、文字キー`Q`(`04:1`)をframe708からHOLD4）で
走らせ、キー入力の無い基準走との差分（`--diff-before`/`--diff-after`、
出したのは変化したセルの座標と自分で打った文字のコードのみ）を取った
ところ、書かれた文字コードは`51`（大文字`Q`、CAPS込みコード）だった。
`l4-s1b-key-matrix-results-q2.md`のCAPS腕（修飾frame700・HOLD30、文字
frame710・HOLD既定）とほぼ同じ組（開始オフセット8対10フレーム）でも
同様に大文字が得られることを確認した。

前回（このコミットの前段）観測した「小文字コード（`71`/`78`/`7A`/`6A`/
`6B`）」は、**`tools/l4_s1f_chain_selftest.sh`の自己検査が意図的にCAPSを
含めずに走らせていた**（`--type`がCAPSを合成しないため、比較対象を
CAPS無しに揃えた設計。スクリプトのコメントに明記済み）ことによるもので、
`tools/l4_s1f_arms.py`側の欠陥ではない。**`tools/l4_s1f_arms.py`の
タイミング定数は変更しない。**

## 切り分け2: マーカーの開始列

**結論: 事前登録が前提としていた「マーカー行は無編集時、列0〜4が
QXZJK・それ以外は空白」というモデルが実機と食い違う。**

- 起動直後・キー入力前の写し（frame690、基準走）の時点で、**row0=1に
  既に非空白セルが列0〜20の範囲にある**（`--nonblank-summary-rows`、
  件数19。内容には一切触れていない）。row0=19（ファンクションキー表示行、
  既知）にも件数21。他の行は0件。
- さらに700フレーム待って比較しても（frame1290まで、キー入力なし）
  この内容は変化しなかった。**起動シーケンスはframe700までに完了して
  おり、これは「まだ起動中」ではなく安定した最終状態**（`l4-s1a`・
  `l4-s1b`が使ってきたframe700の前提と矛盾しない）。
- CAPS+マーカー`QXZJK`（`tools/l4_s1f_arms.py`と同じタイミング）を打った
  ところ、変化したのは**row0=1・col0=22〜26**の5セルで、コードは
  `51/58/5A/4A/4B`（大文字QXZJK、期待どおり）。**col0=21は変化せず
  空白のまま**（列21と22の間に1桁の間があることになる）。2回の独立した
  走行（単独`Q`のみの走・`QXZJK`5文字の走）で同じrow0=1・col0=22が
  再現した。
- 「行末の入力行に既存の文字があるなら、RETURNで空白行へ進めばよい」
  という代案を試した。row0=1でRETURN(`01:7`)を1回押すと、row0=2〜5に
  わたって多数のセルが変化した（複数行にまたがる書き換え、件数のみ
  確認）。これは`docs/spec/l3-main.md`が`01:7`を「未判定・複数セル変化」
  としている既存の記述と整合する。**挙動が予測できず、押す回数を
  安全に決め打ちできないため、この代案は採用しない。**

## 採用する方針（コーディネータ指示の代案2）

マーカー行の署名を「行全体(列0-79)」ではなく、**マーカー開始列
(`col_start`)を基準にした列範囲(window)限定の署名**に変更する。

- `col_start`・`row0`は事前に決め打ちしない。実測担当は、本番24腕の
  直前に「連続打鍵チェーンの自己検査」（`tools/l4_s1f_chain_selftest.sh`、
  本追補を受けて改修する）を通し、`--diff-before`/`--diff-after`で
  実際の`row0`・`col_start`を確認してから腕を組む。今回の切り分けで
  `row0=1`・`col_start=22`が2回再現しているが、これは**参考値**であり、
  本番直前の自己検査でも同じ値になることを確認したうえで使う
  （変わっていたらその時点の実測値を使う。既存事実の書き換えではなく
  確認の追加）。
- 行頭・行中・行末の列は、絶対列0/2/5ではなく**`col_start`からの相対
  位置**（マーカー内の0/2/5文字目相当）にする。事前登録の「候補の
  作り方」自体（del_left/del_at/ins_mode_only/ins_space等の操作の定義）
  は変えない。列の基準点を動かすだけ。
- Q1の判定は、行全体ではなく**window（`col_start-1`〜`col_start+6`の
  8バイト）限定の署名**で行う。window外（既存の起動画面の内容がある
  列0〜`col_start-2`側）には一切触れない。この署名の作り方・正規化規則
  （末尾空白を除いてSHA-256）は事前登録本体と同じ、範囲だけがwindowに
  縮小される。
- HOME/CLR（`clear`/`home`の2候補）は、windowではなく**画面全体の
  非空白セル総件数**で判定する（`clear`は起動画面の内容も含め全体が
  消えるため、windowより広い範囲で見るほうが自然に区別できる）。
  事前登録の候補名・判定基準（`clear`＝全消去、`home`＝内容不変）は
  変えない。
- 器具:
  - `tools/l4_s1f_candidates_v2.py` → `docs/notes/l4-s1f-candidate-table-v2.json`
    （window限定のQ1候補8種×矢印/INS-DEL条件、18条件×位置。元の
    `tools/l4_s1f_candidates.py`・`l4-s1f-candidate-table.json`は
    そのまま残す。版を分ける）。
  - `tools/l4_s1f_window_probe.py`: 実測の写しからwindow限定の署名を
    作る（`row0`・`col_start`・件数・正規化後長・SHA-256のみ出力）。
  - 検証: `fullmarker.bin`（本追補の切り分け走、CAPS+QXZJK、
    row0=1・col_start=22）に対し`l4_s1f_window_probe.py`を実行した
    結果のSHA-256が、v2候補表の`arrow_left_noshift/mid`の`no_change`
    候補（マーカーのみ・未編集）のSHA-256と**完全一致**した。
    window限定モデルが実測と整合することを確認済み。

## 判定名・関門への影響

- 判定名（`no_change`/`wrap_prev_line`/`wrap_next_line`/`row_move`/
  `del_left`/`del_at`/`ins_mode_only`/`ins_space`/`clear`/`home`/
  `boundary_reflow`/`unique_survivor`等）は一切変更しない。
- G1〜G9の意味・数え方も変更しない。G1「連続打鍵チェーンの自己検査」は
  windowモデルで判定するよう`tools/l4_s1f_chain_selftest.sh`を改修する
  （row0・col_startを`--diff-before`/`--diff-after`で実測してから
  windowを切る）。
- 本追補は「マーカー行の内容」「列の基準点」という前提の具体化であり、
  事前登録が定めた問い（Q1〜Q3）・候補・腕数（24）・走数（52）は変えない。

## 根拠リンク

[l4-s1f-screen-editor-preregistration](l4-s1f-screen-editor-preregistration.md)・
[l4-s1b-key-matrix-results-q2](l4-s1b-key-matrix-results-q2.md)（CAPS腕の
タイミング）・`docs/spec/l3-main.md` 第9節（`01:7`未判定の既存記述）・
`tools/l4_s1f_arms.py`・`tools/l4_s1f_candidates.py`・
`tools/l4_s1f_candidates_v2.py`・`tools/l4_s1f_window_probe.py`。
