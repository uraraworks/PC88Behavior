# UTF-8ロケールでの変数展開バグと、それを見落としていた理由 2026-08-11

## 何が起きたか

複数のシェルスクリプト（`tools/conform_l3.sh`、`tools/cmp_io_selftest.sh`、
`tools/check_cleanroom.sh`、`tools/verify_l2.sh`、`tools/verify_l3.sh`、
`tools/harness/intlog_selftest.sh`、`tools/harness/fontsrc_selftest.sh`、
`tools/analyzer_redaction_selftest.sh`）に、`"...（$port）"` のように
**`$var` の直後に全角括弧・読点などの非ASCII文字が続く**書き方が残っていた。

UTF-8ロケールのbashは識別子をマルチバイト単位で解釈できてしまうため、
`$port）` は `port）` という1つの識別子として読まれ、`$port` 単独では
展開されない。

- `set -u` があるスクリプト（`tools/conform_l3.sh` 等）→ `unbound
  variable` で**シェルごと即終了**。`conform_l3.sh` は実際に自己検査
  d の途中で死んでおり、それより後段の「適合テスト本体」が一度も
  実行されていなかった。
- `set -u` が無いスクリプト → 空文字列に展開されて**黙って誤った
  出力**を出す。こちらの方が発見しにくく、より悪質。

再現:
```
LC_ALL=ja_JP.UTF-8 tools/conform_l3.sh   # 途中で異常終了
LC_ALL=C           tools/conform_l3.sh   # 正常終了
```

Cロケールでは0x80以上のバイトが識別子に入らないため `$port` で正しく
切れる。

## なぜ長期間気づかなかったか

**これまでの回帰確認をすべてCロケールで行っていた。** シェルの起動時
ロケールを明示的に切り替えて動作確認したことが一度も無かったため、
「検査を回したら通った」を「常に正しく動く」と取り違えていた。

この種の見落としの構造は過去の記録（`feedback_measure_the_end_not_the_signal.md`
「不自然に揃った数字は観測系の故障を疑う」、
`feedback_two_logs_need_one_clock.md`「2回改善して数字が動かないのは
観測系を疑う合図」）と同じ形をしている——**「検査が通った」は
「検査を回した環境で通った」でしかなく、環境そのものを疑う視点が
無いと再現しない。** 今回は環境変数（ロケール）1つの違いで結果が
反転する脆さだった。

## どう直したか

1. 該当箇所を`${var}`の形に修正した（変数展開文脈にあるものだけ。
   Pythonのコメント・docstring内や、シェルのコメント行・シングル
   クオート内にある `$FB` 等の「ポート名としての文章」は変数展開
   されないため対象外とし、触っていない）。
2. `tools/check_cleanroom.sh` に検査項目9を追加した。追跡中の
   `*.sh` を走査し、変数展開文脈で `$var` の直後が非ASCII文字に
   なっている行があれば落ちるようにした。判定はヒューリスティック
   （シングルクオート内かどうかを未エスケープ`'`の個数の偶奇で
   推定するのみ）であり、誤検出時は対象行末に
   `# cleanroom-lint:ignore` を付けて除外理由をコメントで書く運用に
   した（握りつぶさない）。わざと壊した一時ファイルで検出できること、
   検査を無効化すると検出できなくなることを確認済み。
3. `tools/run_all_selftests.sh` を追加した。selftest群を
   `LC_ALL=C` と `LC_ALL=ja_JP.UTF-8` の両方で実行し、終了コードが
   一致するかを一覧で出す。今後はこれを両ロケールでの回帰確認の
   標準手順にする。

## 再検証結果（両ロケールで実行、`tools/run_all_selftests.sh`）

以下すべてで `LC_ALL=C` と `LC_ALL=ja_JP.UTF-8` の終了コードが一致した
（差は残っていない）。

| script | C | UTF-8 |
|---|---|---|
| tools/check_cleanroom.sh | 0 | 0 |
| tools/cmp_io_selftest.sh | 0 | 0 |
| tools/redact_iolog_selftest.sh | 0 | 0 |
| tools/analyzer_redaction_selftest.sh | 0 | 0 |
| tools/conform_l3.sh | 0 | 0 |
| tools/verify_l1.sh | 0 | 0 |
| tools/verify_l2.sh | 0 | 0 |
| tools/verify_l3.sh | 1 | 1 |
| tools/harness/clock_selftest.sh | 0 | 0 |
| tools/harness/fontsrc_selftest.sh | 0 | 0 |
| tools/harness/intlog_selftest.sh | 0 | 0 |
| tools/harness/iolog_selftest.sh | 0 | 0 |
| tools/harness/selftest.sh | 0 | 0 |
| tools/harness/trap_selftest.sh | 0 | 0 |

`tools/verify_l3.sh` の rc=1 は既知のL3不適合（仕様書5.2条件4：
ディスク無し時にsubが1命令も実行しない、を現状の自作サブROMが
満たしていない）であり、スクリプト自身の出力にも明記されている。
今回の修正とは無関係で、両ロケールで同じ結果なので**ロケール依存の
問題ではない**ことが確認できた。

`tools/conform_l3.sh` は `PC88_REF_ROM_DIR` / `PC88_REF_DISK_DIR`
未設定のため、両ロケールとも「私物ROM/ディスクが無い」旨のusageを
出して即終了する経路のみを確認した（実際のROM/ディスクを使った適合
テスト本体は私物が無いこの環境では実行できていない。私物を持つ環境
で改めて両ロケール確認が必要）。
