# SAVE の書き込み先 D の照合（2026-10-01）

公式ROM・公式ディスクのバイト列・画面本文は載せない。件数・一致/不一致・位置だけ。

## 項目1: conform_save hybrid の D 照合の陰性対照

器具: `tools/conform_save.sh` が各腕に `runs/<arm>/stage.txt`（frontend_rc / other_drive / compare）を
残す。hybrid の J-D1 はドライブ2に別媒体(B1)を挿し、その不変も見る（J-1 はドライブ1=公式 N88_FE の不変を
元から見ていた）。故障注入は `tools/save_drive_fault_selftest.sh`（`src/` 不変、ビルド後の N88_2.ROM の
`s2_write_stream` 先頭 `AND 1` を書き換える）。

| 注入 | J-1（"2:" 宛, D=1） | J-D1（"1:" 宛, D=0） |
|---|---|---|
| なし（陽性対照） | OK | OK |
| `AND 0`（D 常に0） | NG: frontend_rc=0, other_drive=ok, compare=ng | OK |
| `OR 1`（D 常に1） | OK | NG: frontend_rc=0, other_drive=changed, compare=ng |

- どちらも手前（ビルド・タイムアウト・別検査）で落ちたのではなく、frontend は rc=0 で完走し、
  読み戻し照合（宛先イメージに期待どおりのファイルが無い）の段で落ちる。D=1 固定ではさらに
  「もう一方のドライブ不変」の段も落ちる（B1 が書き換わる）。
- 限界: D=0 を誤って送った J-1 では、公式 N88_FE のドライブ1は書き換わらなかった（other_drive=ok）。
  このときこの検査は鈍く、読み戻し照合だけが検出する。理由（公式subが書かない等）は測っていない。
- 画面署名は両注入で変わらなかった（SAVE の画面出力は空）ので、画面は D の検出に寄与しない。

## 項目2: 混成腕（公式main＋自作sub）のもう一方のドライブ

確認: 既存の SAVE 場面（条件5・write_protect・seqfile 等）の宛先はすべてドライブ1。B:宛の SAVE は
conform_l3 に無かった（B: は FILES 2 の読みのみ）。そこで `save_drive1`（`SAVE"1:Q8D"`）と
`save_drive2`（`SAVE"2:Q8E"`）を2ドライブ構成（A/B同内容の使い捨て複製・保護解除・4200F）で追加。

結果（公式一式と混成、各2回）: 両場面とも
- main IN $FD/$FC の件数・SHA-256 が公式と一致（FD 5635、FC 7976）。A宛とB宛でFCのハッシュは別なので、
  場面は D を区別している。
- FDC コマンド種別列 124件が全長一致、WRITE DATA 8件・READ DATA 19件、unit/head 分類差 0、
  SENSE DRIVE STATUS 19件はそれぞれ A / B の unit で一致。
- 画面署名（10行・211文字）が公式と混成で完全一致。
- 自作subの 0x14,D 後の SENSE DRIVE STATUS は D によらず仕様 1.35a節の範囲で適合。実装変更なし。

期待値は公式を2回実測して固定（`tests/conformance/expected_save_drive{1,2}.tsv`、
`expected_screen.tsv`）。

## 器具の注意

q88measure は稀に起動時に SIGABRT（rc=134）する既知欠陥（m7az）。path 系の測定に限り、
ROM・媒体を作り直して最大5回再試行する（`run_path_measurement`）。最初の版は ROM ディレクトリを
作り直さず、クラッシュ後の run がコアの実行状態を継承して2回の全イベント列が一致しなくなった
（作り直しで解消）。
