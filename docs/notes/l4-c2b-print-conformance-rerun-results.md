# l4-c2b — 直接モードPRINT適合テスト再測定 — 結果

事前登録: [l4-c2b-print-conformance-rerun-preregistration](l4-c2b-print-conformance-rerun-preregistration.md)
（`43071f2`）。判定名・記録項目・関門・数え方は事前登録から動かしていない。

## 器具

- 測定時HEAD: `37b5fea2bb1a09deb34de1f3520d213aece46f83`
  （`fc69064`のSPACE修正を含む。以降、測定終了まで自身の作業は
  docs/notes追加のみで`src/`・`tools/`は変更していない）
- 自作ROM一式: 測定時HEADで `python3 src/build_main_rom.py <新規dir>`
  （`--enable-l4-selftest`は付けない、通常ビルド）により1回だけ組み立て、
  以後の全走で複製して使い回した
- 公式ROM一式: `PC88_REF_ROM_DIR`（`private/rom`）から`*.ROM`を走ごとに
  新しいROMディレクトリへ`cp -p`するだけ（中身は読まない）。ディスク無し
- 作業ディレクトリ: リポジトリ外`_emulator/PC88/tmp/l4-c2b-work/`
  （本ノート作成後に削除）
- 解析器具: `tools/l4_vram_probe.py`の差分モード(`--count-only-rows 19`)と
  `--row-signature`のみを使う使い捨てドライバ（リポジトリには置いていない、
  セッションのスクラッチパッドに置いた）。生のVRAM写しを自分ではパースせず、
  常に`tools/l4_vram_probe.py`が返す安全な形の値（位置・自分の打鍵に由来する
  文字コード・件数・SHA-256）だけを扱った

### 自作ROM一式の sha256（先頭12桁）

| ファイル | sha256(先頭12桁) |
|---|---|
| N88.ROM | `4585f3dbe7b6` |
| DISK.ROM | `d8b2e64bc274` |
| FONT.ROM | `53d8cc941814` |

（DISK.ROM・FONT.ROMは`l4-c2`測定時と同じ。N88.ROMはSPACE修正により変化した）

## 関門

| 関門 | 判定 | 根拠 |
|---|---|---|
| G1 器具の自己検査 | **真** | 測定時HEADで`vram_dump_selftest.sh`・`vram_dump_dynamic_selftest.sh`・`mem_write_log_selftest.sh`・`key_matrix_selftest.sh`・`screen_content_leak_selftest.sh`の全項目OK |
| G2 取りこぼし0・打てない文字の警告0 | **真** | 全72走（18腕×2ROM×2走）のstderrで「untypable」「打てない」該当0件。q88measureの起動時再試行(既知欠陥`m7az`)も0回 |
| G3 決定論性 | **真** | 全18腕×2ROM(=36組)で、run1/run2の正規化構造（P1〜P5は出力行セル列とOk相対行、P6はエラー行row_sha256）が完全一致 |
| G4 陰性対照 | **真** | 何も打たない走(起動settleのみ)で、公式・自作とも文字域・属性域とも変化0件 |
| G5 自作ROM側の自己検査 | **真** | `tools/l4_basic_selftest.sh`が測定時HEADでrc=0（内部で`tools/l3_main_selftest.sh`・`tools/conform_l4.sh`も実行されOK） |

gate_failedとして除外した腕は無い（全18腕、両ROMともG1〜G5すべて真）。

## 原点（両ROMとも全18腕で一定、`l4-c2`と同値）

| ROM | origin (row0, col0) |
|---|---|
| 公式ROM | (6, 0) |
| 自作ROM | (4, 0) |

## P1〜P5（16腕）の判定

**全16腕で`print_matches`。** 両ROMとも、出力行の相対行(+1)・`Ok`の相対行(+2)
が一致し、出力行の(相対桁, 文字コード)の並びが完全に一致した
（`l4-c2`で不一致の原因だったSPACEキーのエコー前進を`fc69064`が修正済み）。

| 腕 | 打鍵文字列 | 出力セル数(公式=自作) | Ok相対行 | 判定 |
|---|---|---|---|---|
| P1-1 | `print 1` | 1 | 2 | print_matches |
| P1-0 | `print 0` | 1 | 2 | print_matches |
| P1-m5 | `print -5` | 2 | 2 | print_matches |
| P1-32767 | `print 32767` | 5 | 2 | print_matches |
| P1-m32768 | `print -32768` | 6 | 2 | print_matches |
| P2-expr1 | `print 2*(3+4)` | 2 | 2 | print_matches |
| P2-expr2 | `print 1+2*3` | 1 | 2 | print_matches |
| P2-neg | `print -(4)` | 2 | 2 | print_matches |
| P3-str | `print "q7z"` | 3 | 2 | print_matches |
| P3-semi-num | `print 1;2` | 2 | 2 | print_matches |
| P3-semi-str | `print "a";"b"` | 2 | 2 | print_matches |
| P3-comma-str | `print "a","b"` | 2 | 2 | print_matches |
| P3-comma-num | `print 1,2` | 2 | 2 | print_matches |
| P4-semi | `print "a";:print "b"` | 2 | 2 | print_matches |
| P4-comma | `print "a",:print "b"` | 2 | 2 | print_matches |
| P5-q | `? 7` | 1 | 2 | print_matches |

（「出力セル数」は事前登録「比べるもの」節が定義する、出力行(相対+1)の
「前が空白だったセル」の件数。両ROMで全腕とも同数・同位置・同文字コード
だった。値は自分で打った数値・文字列の直接の出力であるため出してよい
——事前登録「本文を出さない取り扱い」節）

## P6（構文の誤り、2腕）— 記録のみ、判定は付けない

事前登録どおり、開発者判断（`734b490`）によりこの2腕は適合の比較対象から
外している。件数とSHA-256だけを記録する。

| 腕 | 打鍵文字列 | 公式:非空白件数 | 自作:非空白件数 | 決定論性(run1=run2) |
|---|---|---|---|---|
| P6-syntax | `print 1+` | 15 | 11 | 真（両ROMとも） |
| P6-unknown | `printx 1` | 12 | 11 | 真（両ROMとも） |

- 非空白件数は`l4-c2`・`l4-c2-error-signature-diagnosis.md`が既に記録した
  値と一致し、公式ROM・自作ROMともHEAD間で挙動が変わっていないことを確認した
- row_sha256は公式・自作の全4通り(2腕×2ROM)いずれも相互に不一致だった。
  ただし**自作ROM側は`P6-syntax`と`P6-unknown`で同一のrow_sha256**
  だった（`l4-c2`診断で既に観測済みの構造——自作は同じ文言を出している
  らしいという推測——が今回のHEADでも変わっていないことを確認した）。
  文字コードの並びそのもの・文言は一切出していない

## 全18腕の集計

| 判定 | 件数 |
|---|---|
| print_matches | 16 |
| print_differs | 0 |
| 記録のみ（判定なし、P6） | 2 |
| gate_failed | 0 |

## 判定後の行き先

P1〜P5の16腕すべてが`print_matches`になった。事前登録どおり、
`tools/conform_l4.sh`へのl4-c2場面の追加登録自体は本ノートの担当範囲外
（親が別途決める）。P6は記録のみで完結し、行き先を分岐させない。

## 禁止事項7について

画面本文（文字コードの並びそのもの・文言）は、報告・本ノート・ツール
出力のいずれにも一切書いていない。出しているのは (a) 自分で打った数・
式・文字列とその直接の出力の文字コードと相対位置（事前登録「本文を
出さない取り扱い」節で明示的に許可された範囲）、(b) `Ok`行の相対行番号
（内容そのものは比較にも記録にも使っていない）、(c) P6エラー行の非空白
件数とSHA-256署名のみ。解析には`tools/l4_vram_probe.py`の差分モード
(`--count-only-rows 19`)と`--row-signature`のみを使い、P6のエラー行は
測定の最初の段階から常に署名モードでしか扱っていない（生の差分として
一度も出力していない、事前登録どおり）。

## 生データ

写し・記録・自作ROM一式・使い捨てドライバスクリプトは使い捨ての作業
ディレクトリ（`_emulator/PC88/tmp/l4-c2b-work/`、ドライバ本体はセッションの
スクラッチパッド）に置き、本ノートを書いたあと削除した。
