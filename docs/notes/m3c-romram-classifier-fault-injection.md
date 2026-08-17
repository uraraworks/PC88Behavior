# M3c: ROM/RAM 判定器の故障注入による検出力確認

測定日: 2026-08-17
対象: 計測ハーネスの ROM/RAM 判定器（`tools/harness/core/q88h_trace.h`、
`tools/patches/0002-bus-trace.patch` の `q88h_addr_is_rom()`）。
コミット `56c19d4` で導入したが、その時点では **RAM 側に分類される実測イベントが
一度も出ていなかった**（`docs/notes/m3b-alphados-demand.md`「残す宿題」2）。

---

## 情報境界

この作業で見たのは以下だけ。公式 ROM・公式ディスクは一切使っていない。

- `tools/harness/core/q88h_trace.h`（自分たちが書いたハーネスのヘッダ）
- `tools/patches/0002-bus-trace.patch`（同、パッチ差分）
- `vendor/quasi88-libretro/src/pc88main.c` の `q88h_addr_is_rom` /
  `q88h_ptr_in_rom`（上流エミュレータのメモリマップ実装。ROM の中身ではなく
  エミュレータ自身のソースコードなので禁止事項1・2に抵触しない）
- `tools/harness/make_test_rom.py`（自作の合成 ROM 生成スクリプト）

RAM 実行を発生させるのに port $31 のバンク切替（ハードウェア仕様）を使うことも
検討したが、使わずに済んだ。**window/main_ram 固定帯（0x8400-0xBFFF）は
バンク切替に関係なく常に RAM 判定される**ことがコードから読み取れたので、
そこへ直接コードを書いて JP するだけで足りた。

## 手順

1. `q88h_addr_is_rom()` の実装箇所を確認（`56c19d4` の差分どおり、
   `vendor/quasi88-libretro/src/pc88main.c` 内、`pc88main_bus_setup` の直前）。
2. `tools/harness/make_test_rom.py` に `--enable-ram-exec` を追加。
   ENTRY (0x1234) 到達後、RAM (0x9000) に自作の4バイト
   （`3E 07 18 FE` = `LD A,07h` に続けて `JR $`）を `LD (HL),n` の連続で
   書き込み、`JP 9000h` する。書き込む値も含めすべて自作の値であり、
   ROM・ディスクいずれのバイト列とも無関係。
3. `tools/harness/romram_selftest.sh` を新設。以下を1本のスクリプトで行う:
   - 実際のビルド済みコアに対して上記 ROM を実行し、
     `[メインCPU 実行された番地 (fetch, ROM)]` /
     `(fetch, RAM)` の両方が非ゼロであることを確認する（陽性対照）。
   - `q88h_addr_is_rom()` を意図的に壊した3種の故障注入版を、
     `$VENDOR`（共有のビルド済みコア一式）を丸ごと一時ディレクトリへ
     `cp -a` した上でその場でビルドし、同じ ROM で実行して結果を比較する。
     共有の `vendor/quasi88-libretro` 本体は一切書き換えない
     （並行作業中の別セッションへの影響を避けるため）。
   - 故障注入版の結果が正常版と一致してしまったら、その時点で NG にする
     （「判定器か観測系が死んでいる」を検出条件として組み込んである）。

## 故障注入3版と結果

正常版（実際のビルド済みコア）: **main ROM側=14件 RAM側=2件**
（RAM側の2件が 0x9000/0x9002 — 自作コードを書き込んだ番地とその中の
分岐先。これが m3b の宿題そのものの解消: RAM 側の枝が実測で踏まれている）。

| 故障注入版 | 変更内容 | 期待 | 実測結果 | 判定 |
|---|---|---|---|---|
| always_rom | `q88h_addr_is_rom()` の先頭で常に `return 1` | RAM側=0件 | ROM=16件 RAM=0件 | 検出できた |
| always_ram | 同じ箇所で常に `return 0` | ROM側=0件 | ROM=0件 RAM=16件 | 検出できた |
| shifted | window/main_ram固定帯(0x8400-0xBFFF)の分岐を `return 0`→`return 1` に変更（境界の意図的な誤適用） | 正常版と異なる内訳になる | ROM=16件 RAM=0件（always_romと同じ値になったが、正常版とは明確に異なる） | 検出できた |

3版とも「正常版とは異なる結果」という検出条件を満たした。
判定器は「全部ROM」「全部RAM」に張り付いた壊れた実装ではなく、
実際に番地ごとの実体を見て振り分けていることが、故障注入によって
（コードを読んだ確認とは別に）実測で裏付けられた。

shifted 版が always_rom 版と数値上たまたま一致したのは、今回のテスト用
RAM実行番地(0x9000)が両方の故障箇所（`q88h_addr_is_rom`全体を上書きする
always_rom と、window帯だけを誤らせるshifted）の影響範囲に共通して
含まれていたため。検出条件は「正常版との差」であって「他の故障注入版との
差」ではないので、これは問題にならない。

## RAM側の枝を実測で踏めたか

踏めた。正常版で **RAM側2件**（0x9000, 0x9002）を観測。
`romram_selftest.sh` の陽性対照として組み込み済みなので、以後
毎回のselftest実行で「RAM側が0件に戻っていないか」を継続的に検査する。

## selftestへの組み込み

`tools/harness/romram_selftest.sh` を新設し、`tools/run_all_selftests.sh` の
`SCRIPTS_EXPECTED` に追加した（期待rc=0）。`LC_ALL=C` / `LC_ALL=ja_JP.UTF-8`
両ロケールで実行し、rc一致・期待rc一致を確認済み。`tools/run_all_selftests.sh`
全体（22件）も通ることを確認した。

Makefileのヘッダ依存漏れ（別件で対処中の事故）を踏まないよう、故障注入版は
毎回 `pc88main.o` を消してから確実に再コンパイルさせている
（`rm -f "$dst/src/pc88main.o"` の後にビルド）。

## 結論

- m3b の宿題2（RAM側の枝が実測で一度も踏まれていない）は解消した。
  正常版の実測で RAM側2件を観測し、故障注入3版すべてで判定器の検出力を
  確認した。
- 「判定ロジックが全部ROM・全部RAMに張り付いていないか」という懸念は、
  コードを読んだ確認（`56c19d4` のコミットメッセージ）に加えて、
  故障注入による実測でも否定された（＝判定器は正しく機能している）。
- 今後この判定器のロジックを変更する場合は、`romram_selftest.sh` が
  検出力の回帰試験として機能する。
