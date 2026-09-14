# m7lz — B:候補の実物再測（2回目）— 事前登録（追補）

## 位置づけ

[m7lz](m7lz-b-candidates-recheck-preregistration.md)（1回目の事前登録、HEAD `db822b8`）は
関門G3（決定論性）が偽になり `gate_failed` で終わった
（[m7lz-...-results](m7lz-b-candidates-recheck-results.md)）。3章の3項（5448・5485・5508）は
まだ判定できていない。本稿は同じ測定を、**測定器具だけを直して**もう一度走らせるための
事前登録の追補である。関門・指標・判定・数え方は1回目から一切変えない。

## 1回目がgate_failedになった原因（主セッションが確認した事実）

- q88measure は `--rom-dir` に渡したディレクトリを、libretro コアの SYSTEM・
  CORE_ASSETS・**SAVE** ディレクトリとして返す
  （`tools/harness/frontend/main.c` 276〜280行、`RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY`）。
  コアは既定で書き込みの差分をこの保存先に `<媒体名>.srm` として置く（同160〜163行のコメント）。
- 1回目の駆動 `tmp/m7lz-work/drive.sh` は、official・mixed・mixed_break それぞれについて
  ROM ディレクトリ（`rom_official`・`rom_mixed`・`rom_mixed_break`）を**全走で使い回した**
  （`romdir_for()` が固定パスを返す実装だった）。`tools/stage_disk_by_digest.sh` が作る
  媒体複製の中立名はダイジェスト由来で走をまたいで同じなので、2回目以降の走は、同じ
  ROM ディレクトリに残っていた前の走の `SAVE"2:TQ"` の結果を `.srm` 経由で重ねて読んだ。
- 証拠: 使い回した ROM ディレクトリに `<先頭8桁>.srm` が残っており、中身があるのは
  D1・D2・D7（WRITE に届いた3本）だけだった。1回目でG3が偽になったのもこの3候補の
  書き腕（official・mixedとも）で、内訳（診断節）と一致する。差は WRITE より前の
  正常終了 READ DATA 4件のデータ部32バイトに出ていた。媒体複製の SHA・mtime は
  4本とも同一で、パス（作業ディレクトリ名の振り方）は無関係であることも確認済み
  （パス説は否定済み）。QUASI88 の fdc.c に乱数は無い。

## 変えるのは器具だけ

実装（`src/`）・自作subROMの生成器・腕の定義・打鍵・フレーム数・媒体・比べ方は
1回目からまったく変えない。変えるのは次の3点だけである。

- **(a) 走ごとに ROM ディレクトリを新しく作る。** official は公式ROM一式の複製、
  mixed は `build_mixed_rom`、G4陽性対照の `--break-drive-selector` 版も、
  それぞれの走専用のディレクトリに毎回組み立て直す（1回目のような使い回しをやめる）。
- **(b) 各走の直前に、その ROM ディレクトリに `.srm` が1つも無いことを確かめる。**
  あれば測らずに止まる（器具の漏れが塞がっていないことの検出）。
- **(c) 各走の後に生じた `.srm` の有無と大きさを記録する。** 記述としてのみ載せ、
  合否判定には使わない。

## 変えないもの

- **関門 G1〜G5・腕ごとの指標 E/S/W・判定 J1〜J3・数え方は1回目のまま。**
  文言・しきい値・母集団の定義を一切動かさない。
- 候補8本（D1〜D8）・A:固定（disk#8）・打鍵（`FILES 2`／`10 PRINT"T"\nSAVE"2:TQ"\n`）・
  フレーム数（R:4000、W:4200）・走数（official 2回・mixed 2回・G4陽性対照1回）は
  1回目と同一。
- 1回目の結果ノート（`m7lz-b-candidates-recheck-results.md`）は消さず、そのまま残す。
  2回目の結果は別のノート `m7lz-b-candidates-recheck-results-run2.md` に書く。

## 器具が直ったことの確認（本測定の判定を見る前に行う）

1回目に揺れた D1-W の official 2回で、sub 側 `IN $FB` 列の SHA-256 が一致し、
かつその値が1回目の official run1（ROM ディレクトリがまだ使い回されていない
「まっさら側」）の値 `7e16390c2aa3` と同じであることを確認する
（`tools/hash_io_stream.py --cpu sub --port FB --kind IN` の SHA-256 先頭12桁）。
違えば止まって報告する。この確認は本測定の合否には使わない（器具が意図どおり
機能しているかの事前確認である）。

## 言えないこと

- 1回目の run1 どうし（official 1回目と mixed 1回目の比較。G3とは別の指標
  E/S/W の計算に使った値）が一致していたのは、各 ROM ディレクトリの「その候補・
  その側で最初に走った回」がまっさらだったためと読めるが、**この読み方は今回の
  判定には使わない**。改めて2回目で測り直す。
- 本追補は器具の修正であり、1回目のE/S/W・FDCコマンド種別列などの記述値を
  上書き・訂正するものではない。1回目のノートはそのまま残る。

## 結果ノート

`docs/notes/m7lz-b-candidates-recheck-results-run2.md` に書く。関門・指標・判定と
数え方を後から動かさない。

## 根拠リンク

[m7lz-...-preregistration](m7lz-b-candidates-recheck-preregistration.md)・
[m7lz-...-results](m7lz-b-candidates-recheck-results.md)・
`tools/harness/frontend/main.c`（SAVE ディレクトリの割当・`.srm` の既定挙動）・
`tools/lib_l3_measure.sh`（`build_mixed_rom`）。
