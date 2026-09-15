# l4-c2 — 直接モードPRINT適合テスト — 結果

事前登録: [l4-c2-print-conformance-preregistration](l4-c2-print-conformance-preregistration.md)
（`39eeb53`）。判定名・記録項目・関門・数え方は事前登録から動かしていない。

## 器具

- 測定時HEAD: `adddda84dacea906629b4978e45e655382e28837`
- 自作ROM一式: 測定時HEADで `python3 src/build_main_rom.py <新規dir>` により
  1回だけ組み立て、以後の全走で複製して使い回した（並行担当の途中変更の
  影響を受けないようにするため。事前登録どおり公式ROMは自作ROM側の測定
  には一切使わない）
- 公式ROM一式: `PC88_REF_ROM_DIR`（`private/rom`）から `*.ROM` を走ごとに
  新しいROMディレクトリへ `cp -p` するだけ（中身は読まない）。ディスク無し
- 作業ディレクトリ: リポジトリ外 `_emulator/PC88/tmp/l4-c2-work/`
  （本ノート作成後に削除）

### 自作ROM一式の sha256（先頭12桁）

| ファイル | sha256(先頭12桁) |
|---|---|
| N88.ROM | `6c54029815f6` |
| DISK.ROM | `d8b2e64bc274` |
| FONT.ROM | `53d8cc941814` |

## 関門

| 関門 | 判定 | 根拠 |
|---|---|---|
| G1 器具の自己検査 | **真** | 測定時HEADで `vram_dump_selftest.sh`・`vram_dump_dynamic_selftest.sh`・`mem_write_log_selftest.sh`・`key_matrix_selftest.sh`・`screen_content_leak_selftest.sh` の全項目OK |
| G2 取りこぼし0・打てない文字の警告0 | **真** | 全74走（18腕×2ROM×2走＋陰性対照2走）のstderrで「untypable」「打てない」「取りこぼし」該当0件 |
| G3 決定論性 | **真** | 全18腕×2ROM(=36組)で、run1/run2の差分記録(char_changes・attr_changes・件数)のSHA-256が完全一致。P6のエラー行署名(row_sha256)もrun1=run2で一致 |
| G4 陰性対照 | **真** | 何も打たない走(起動settleのみ)で、公式・自作とも文字域・属性域の変化が0件 |
| G5 自作ROM側の自己検査 | **真** | `tools/l4_basic_selftest.sh` が測定時HEADでrc=0（内部で`tools/l3_main_selftest.sh`・`tools/conform_l4.sh`も実行されOK）。確認時点の`git status`は空（他人の未コミット変更なし）だった |

gate_failedとして除外した腕は無い（全18腕、両ROMともG1〜G5すべて真）。

**測定完了後に判明した並行変更**: 全走を終えた後の`git status`確認で、
`src/l4_basic/make_print_dispatch.py`・`src/l4_basic/print_dispatch.asm`・
`tools/l4_basic_selftest.sh`に他人（並行担当）の未コミット変更が新たに
現れていた。G5確認時点（走を始める前）では空だったこと、および自作ROM
一式は測定時HEADで走開始前に1回だけ組み立てて固定し全走で複製を使い
回したことから、本測定の結果はこの並行変更の影響を受けていない。

## 原点（両ROMとも全18腕で一定）

| ROM | origin (row0, col0) |
|---|---|
| 公式ROM | (6, 0) |
| 自作ROM | (4, 0) |

## P1〜P5（16腕）の判定

全16腕で、両ROMとも `Ok` の相対行は2（原点行=0、出力行=+1、Ok行=+2）で
一致し、出力セルの件数も両ROM間で一致した。**しかし出力セルの相対桁位置が
両ROMで1桁ずつずれており（自作ROM側が1桁前に詰まる）、全16腕が
`print_differs` になった。**

| 腕 | 打鍵文字列 | 公式:出力セル数 | 自作:出力セル数 | 判定 |
|---|---|---|---|---|
| P1-1 | `print 1` | 7 | 7 | print_differs |
| P1-0 | `print 0` | 7 | 7 | print_differs |
| P1-m5 | `print -5` | 9 | 9 | print_differs |
| P1-32767 | `print 32767` | 15 | 15 | print_differs |
| P1-m32768 | `print -32768` | 17 | 17 | print_differs |
| P2-expr1 | `print 2*(3+4)` | 14 | 14 | print_differs |
| P2-expr2 | `print 1+2*3` | 11 | 11 | print_differs |
| P2-neg | `print -(4)` | 11 | 11 | print_differs |
| P3-str | `print "q7z"` | 13 | 13 | print_differs |
| P3-semi-num | `print 1;2` | 10 | 10 | print_differs |
| P3-semi-str | `print "a";"b"` | 14 | 14 | print_differs |
| P3-comma-str | `print "a","b"` | 14 | 14 | print_differs |
| P3-comma-num | `print 1,2` | 10 | 10 | print_differs |
| P4-semi | `print "a";:print "b"` | 20 | 20 | print_differs |
| P4-comma | `print "a",:print "b"` | 20 | 20 | print_differs |
| P5-q | `? 7` | 3 | 3 | print_differs |

### 最初に違うセル（P1-1、代表例。値は自分で打った文字なので出してよい）

- 公式ROM: 相対行0・相対列6・文字コード`31`（打った`1`）
- 自作ROM: 相対行0・相対列5・文字コード`31`（同じ`1`）

両ROMとも打鍵エコー`print`（5文字）の直後に打った値が続くが、**自作ROM側
では`print`と値の間の空白1文字が書き込まれていない**（他の15腕も同型の
1桁ずれで、原因はこの空白脱落と考えられる。既知の制約——自作main ROMの
キー処理はスペースキーを書き込まない設計——が`--type`によるキー注入
でも同様に効いている可能性がある。仕様の解釈違いか実装差かの切り分けは
本ノートの範囲外、事前登録どおり次の作業に送る）。

## P6（構文の誤り、2腕）の判定

| 腕 | 打鍵文字列 | 公式:エラー行相対行 / 非空白件数 | 自作:エラー行相対行 / 非空白件数 | 署名一致 | 判定 |
|---|---|---|---|---|---|
| P6-syntax | `print 1+` | +1 / 15 | +1 / 11 | 不一致 | error_signature_differs |
| P6-unknown | `printx 1` | +1 / 12 | +1 / 11 | 不一致 | error_signature_differs |

エラー行の文字コードの並びそのもの・文言は一切出していない（件数と
SHA-256のみ、`tools/l4_vram_probe.py --row-signature` による）。

**自作ROM側の特記事項**: `P6-syntax`と`P6-unknown`の自作ROM側row_sha256が
**同一**だった（両腕とも自作ROMの出力は同じ内容らしいと推測される。値は
出さない）。公式ROM側はP6-syntax(非空白15)とP6-unknown(非空白12)で件数・
署名とも異なり、両者を区別する文言を出しているとみられる。これは
`docs/notes/refs-manual-error-messages.md`由来の文言をそのまま採用した
自作実装と、公式ROMの実際の画面表示が一致しなかった具体的な観測であり、
事前登録の想定（「値は出さず、署名だけで一致／不一致を見る」）どおりの
帰結。

## 全18腕の集計

| 判定 | 件数 |
|---|---|
| print_matches | 0 |
| print_differs | 16 |
| error_signature_matches | 0 |
| error_signature_differs | 2 |
| gate_failed | 0 |

## 判定後の行き先

全18腕が一致しなかったため、事前登録の「全18腕が一致」の分岐
（`tools/conform_l4.sh`への追加登録）は適用しない。事前登録どおり、
`print_differs`・`error_signature_differs`の内訳（P1〜P5は自作ROMの空白
キー処理の疑い、P6は自作ROMのエラー文言が公式ROMの画面表示と未確認だった
こと）を`docs/spec/l4-basic.md`と突き合わせ、実装差か仕様の未解釈かを
切り分ける次の作業への入力とする（本ノートでは切り分け作業自体は行わない）。

## 禁止事項7について

画面本文（文字コードの並びそのもの・文言）は、報告・本ノート・ツール
出力のいずれにも一切書いていない。出しているのは (a) 自分で打った数・
式・文字列とその直接の出力（事前登録「本文を出さない取り扱い」節で
明示的に許可された範囲）の文字コードと相対位置、(b) `Ok`行・エラー行の
相対行番号、(c) P6エラー行の非空白件数とSHA-256署名のみ。解析には
`tools/l4_vram_probe.py`の差分モード(`--count-only-rows 19`)と
`--row-signature`のみを使い、P6のエラー行は測定の最初の段階から常に
署名モードでしか扱っていない（生の差分として一度も出力していない）。

## 生データ

写し・記録・自作ROM一式は使い捨ての作業ディレクトリ
（`_emulator/PC88/tmp/l4-c2-work/`）に置き、本ノートを書いたあと削除した。
