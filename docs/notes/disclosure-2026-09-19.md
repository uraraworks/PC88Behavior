# 開示記録 2026-09-19

`CLAUDE.md`「汚染したとき」の書き方（[contamination-2026-08-07.md](contamination-2026-08-07.md)・
[disclosure-2026-08-10.md](disclosure-2026-08-10.md)・
[disclosure-2026-09-03.md](disclosure-2026-09-03.md)）を踏襲する。隠さない。
種類としては[m7hk](m7hk-screen-content-leak-path-closed.md)（画面本文が
ツール出力に出る経路）の4件目にあたる。

## 何が起きたか

キーリピート（自動繰り返し）測定（事前登録 l4-s1h、コミット`c9d5935`）の
担当が、動作確認のつもりで`tools/harness/frontend/q88measure`を、
既存のラッパー（`tools/measure.sh`・`tools/lib_l3_measure.sh`の
`run_q88measure_retry`等。いずれも標準出力を必ずファイルへリダイレクトする
設計）を通さず、`--out`を指定せずに直接実行した。

`main.c`の`write_report()`は`--out`の有無に関わらず標準出力へも常に
報告全体を書く実装になっており、その中の`write_screen()`
（当時1242行付近）が「[測定終了時のテキスト画面]」節を無条件に書き出す。
結果として、**公式ROMの起動画面の本文（起動時の問いの文言・
ファンクションキー行の項目名程度の種類）が、担当の作業端末の標準出力へ
一時的に表示された。**

禁止事項7が対象とする「画面本文」そのものであり、対象は公式ROM由来の
表示内容（公式ディスクのディレクトリ一覧等ではない）。

## 成果物への転記は無い

担当はこの表示に気づいた時点で作業を止めて報告した。ノート・コミット
メッセージ・コミット対象ファイルのいずれにも画面本文は転記されていない。
表示は担当セッションの作業端末（対話シェルの標準出力）に一度出ただけで、
親セッション（本記録の作成者を含む）の文脈には画面本文そのものは
一度も入っていない。

## 対処

1. 担当の会話記録と作業ディレクトリをゴミ箱へ移した（CLAUDE.md「汚染したとき」
   2番、担当を外す措置）。
2. 担当をキーリピート測定（l4-s1h関連）の実装から外した。事前登録
   （`c9d5935`）自体は書き換えていない。測定はやり直しの対象になりうる。
3. **経路を閉じた（本コミット）。** `tools/harness/frontend/main.c`を
   変更し、`write_report()`が作業端末（標準出力・標準エラー）へ書くときは
   `write_screen()`本体を呼ばず、`write_screen_redacted_notice()`
   （画面節の見出しも含めて一切出さず、1行の案内だけを出す）に置き換えた。
   `--out`で指定したファイルへ書く経路（既存の
   `tools/check_l3_screen_output.py`・`tools/check_l3_entry_screen.py`が
   読む前提の書式）は変えていない。`--dump-text`（標準エラーへの画面表示。
   既存の`tools/`配下のスクリプトはいずれも使っていないことを確認済み）も
   同じ理由で同様に閉じた。詳細は
   [m7hk](m7hk-screen-content-leak-path-closed.md)の4件目の節を参照。

## 自己検査

`tools/screen_content_leak_selftest.sh`に、自作ROM（`make_test_rom.py`が
生成する合成ROM。公式ROM不使用）でq88measureを`--out`無しで実際に走らせ、
標準出力・標準エラーのどちらにも画面節の見出し・行データが一切現れない
ことを確かめる項目（u1〜u4）を追加した。u4は`main.c`に既存の
`Q88MEASURE_FAULT_*`環境変数群と同じ作法で追加した
`Q88MEASURE_FAULT_SHOW_SCREEN_ON_STDOUT`により、修正前の挙動
（--out無しでも標準出力に画面節が出る）を再現し、u2相当の判定が
実際に落ちる（検出力を持つ）ことを確認した。全項目OK、終了コード0。

既存の`tools/conform_l4.sh`（自作ROM側の照合、公式環境不要）・
`tools/conform_l3_editor.sh`は、本変更の前後で結果が変わらないことを
確認した（`conform_l3_editor.sh`は本変更と無関係な既知の不一致
「B4」が変更前後とも同一に残るのみ）。`--out`ファイルの中身
（`write_screen()`本体の出力）は変更していないため、これらのスクリプトが
読む画面節の内容そのものに影響は無い。

## 情報境界

本記録の作成者は、`tools/harness/frontend/main.c`・
`tools/measure.sh`・`tools/lib_l3_measure.sh`・`tools/conform_l3.sh`・
`tools/conform_l4.sh`の**ソースコードだけ**を読んだ。自作ROM
（`make_test_rom.py`生成）だけでq88measureを実行し、画面出力の**有無**
（見出し文字列の存在・不在）だけを検査した。表示された可能性のある
公式ROMの画面本文そのものは、本記録の作成・検証のいずれにも読んでいない。
公式ROM・公式ディスクのバイト列・`private/`の内容は読んでいない。
