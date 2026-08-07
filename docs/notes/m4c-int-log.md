# M4c 割り込み受理ログ

測定日: 2026-08-07
対象: 公式 N88-BASIC ROM（32KB, メイン CPU）と DISK.ROM（2KB, サブ CPU）。
測定結果の実体: `measurements/l1-boot-int.txt` / `measurements/l1-boot-int.intlog.txt`
（割り込みモード・intr_ack()のレベル・受理直前PC・分岐後PC・フレーム番号のみ。
ROM の内容は含まない）

---

## 何を作ったか

`docs/spec/l1-ipl.md` 第8節の最後の未解決点「定常状態が1フレームに1回で
ある理由。割り込み駆動か、そうでないか」を、PC が RAM(E7Fx) にあるという
状況証拠ではなく、Z80 が実際に割り込みを受理した事実そのもので確定させる。

作ったもの:

- `tools/harness/core/q88h_intlog.c` / `.h` — 割り込み受理ログのコア側実装。
  q88h_iolog と同じ構造（main/sub別バッファ、既定off、取りこぼしは
  n_dropped で必ず報告、上書きしない）。1CPUあたり最大 2^16 件
  （割り込み受理は OUT/IN ほど頻発しないので q88h_iolog より小さい）。
- `tools/patches/0006-int-log.patch` — `src/z80.c` の `z80_interrupt()` に
  記録呼び出しを追加。`Makefile.common` にソース追加。
- フロントエンド (`tools/harness/frontend/main.c`) に `--int-log <file>` を追加。
  作法は `--io-log` と同じ。
- `tools/harness/make_test_rom.py` に `--enable-int` を追加。合成ROMの末尾に
  「割り込みマスク設定→レベル設定→IM1+EI+HALTループ」を仕込む。
- `tools/harness/intlog_selftest.sh` — 公式ROM不要の自己検証。
- `tools/setup_harness.sh` の疎通試験に `intlog_selftest.sh` と
  `retro_q88h_intlog` の nm 検査を追加。
- `tools/measure.sh` に `--int-log` 用の redact/sed 経路を追加
  （`--io-log` で一度事故った教訓を最初から踏襲）。

## main/sub の判別方法

`z80.c` は `z80arch*` を受け取るだけの汎用コアで、PC88 固有の
`z80main_cpu`/`z80sub_cpu` を宣言するヘッダを元々 include していない。
`pc88cpu.h` の中身を確認したところ `z80.h` だけを要求する薄い extern
宣言ヘッダ（2行のみ）だと分かったため、`z80.c` 側で直接 `#include
"pc88cpu.h"` して `z80 == &z80main_cpu` で比較する方式にした。
`z80arch` 構造体自体への識別子追加は行っていない。

（呼び手側からポインタを登録してもらう方式も検討したが、上記の理由で
不要と判断した。パッチのコメントにも同じ判断を書いてある。）

## ret_pc は HALT の番地そのものではなく +1 になる

`z80_interrupt()` は HALT 中の受理で `z80->HALT=FALSE; z80->PC.W++;` を
先に行ってから割り込み分岐に入る。これは HALT オペコードのフェッチ時に
一度 `PC.W++` された後、HALT 処理自体で `PC.W--` して同じ番地に留まる
実装になっているため（`z80-code.h` の `case HALT` を確認）。したがって
「受理直前のPC＝スタックに積まれる戻り番地」を HALT 中に受理する形で
控えると、値は **HALT の番地そのものではなく、その次の番地（+1）** になる。
これは実機の Z80 も同じ挙動——HALT の再実行を戻り先にする意味が無いため。

`intlog_selftest.sh` はこれを実測で確認している
（HALT_ADDR=0x1249 に対し ret_pc=0x124A）。

## わざと壊して確認した結果

`intlog_selftest.sh` の検査ロジックを採用する前に、以下を実際に壊し、
落ちることを確認した（確認後は元に戻した）。

1. **ret_pc の期待値を1つずらす**——スクリプト中の
   `RET_PC_EXPECT="$(printf '%04X' "$((HALT_ADDR + 1))")"` を
   `$((HALT_ADDR + 2))` に変えて実行 →
   `ret_pc が 124A 。期待値は 124B` で **NG（終了コード1）**になることを確認。
   元に戻して再実行し、合格に戻ることも確認。
2. **`--int-log` を付けない**——既定 off のまま走らせると記録ファイルが
   作られないことを確認済み（スクリプト内の検査そのものがこの経路）。

## 測定結果は測定コミットの docs/notes 側ではなく measurements/ を参照

`l1-boot-int` の実測数値（定常状態の受理回数・IM/level・handler_pc・
初期化中の有無）は `measurements/l1-boot-int.txt` /
`measurements/l1-boot-int.intlog.txt` に残す。このノートはハーネス実装の
設計判断の記録に専念する。
