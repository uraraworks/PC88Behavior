# M6c 共通クロック（main/sub 横断の単調増加通し番号）

測定日: 2026-08-08
対象: 公式 N88-BASIC ROM 一式（メイン CPU）と DISK.ROM（サブ CPU）。
測定結果の実体: `measurements/m6c-sub-{nodisk,d0-boot,d1-files,d2-save,d5-seqfile}.iolog.txt`
/ `.intlog.txt`（OUT/IN・割り込み受理の発生順・ポート番号・値・発行元PC・
フレーム番号・共通クロック値のみ。ROM の内容は含まない）。

---

## なぜ作ったか（20%止まりの原因診断）

`docs/notes/m6-sub-proto.md`（第1版・第2版）で、メイン⇔サブCPU間のポート
（$F0〜$FF）の対応付けを試みたが、値の一致率が最大でも20%程度で頭打ちに
なった。第2版では対応付けアルゴリズム自体を2度改善した（OUT基点→IN基点
への反転、8255仮説の検証）が、数字はほとんど動かなかった。

これは「解析の粗さ」ではなく「観測系の分解能不足」だと判断した。理由:

- `q88h_iolog` / `q88h_intlog` は main/sub を別バッファに持ち、時刻情報は
  フレーム番号（`frame`）しか無かった。
- 1フレームあたりのイベント数は d5-seqfile で main 138,275件・
  sub 122,289件（`m6-sub-proto.md` の表）。frame が同じイベントが
  数百〜数千件単位で存在し、その中での main/sub の真の前後関係を
  frame からは一切復元できない。
- 対応付けアルゴリズムがどれだけ賢くなっても、入力（frame単位でしか
  順序付けられていないログ）に無い情報は作り出せない。改善するたびに
  数字が動かなかったのは、天井が解析側ではなく観測側にあったことの
  裏付けと見てよい。

## 何を足したか

**両CPU・両ログ種別（iolog/intlog）に共通の、呼び出し順に単調増加する
通し番号を1本追加した。**

- `tools/harness/core/q88h_clock.h` / `.c`（新規） — グローバルな
  `uint32_t` カウンタ。`q88h_clock_tick()` を呼ぶたびに増分して返す。
  0 は「まだ打刻していない」の番兵として予約し、1 から始まる。
- `q88h_iolog_ev_t` / `q88h_intlog_ev_t` に `clock` フィールドを追加
  （既存の `seq`/`frame`/... は変更せず、カラムを増やす形。
  `Q88H_IOLOG_VERSION` / `Q88H_INTLOG_VERSION` を 1→2 に上げた）。
- `q88h_iolog_record()` / `q88h_intlog_record()` の内部で
  `q88h_clock_tick()` を呼び、記録の都度打刻する。呼び出し元
  （`pc88main.c` の `q88h_io_in`/`q88h_io_out`、`z80.c` の
  `z80_interrupt`）は変更していない——record 関数の中に閉じ込めたので、
  既存パッチ 0005/0006 は無改造で済む。
- `retro_q88h_iolog_reset()` / `retro_q88h_intlog_reset()` の両方から
  `retro_q88h_clock_reset()` を呼ぶ。どちらが先でも、まだイベントが
  記録されていないタイミングで呼ばれる限り安全。
- フロントエンド（`tools/harness/frontend/main.c`）の出力に `clock` 列を
  追加した（`--io-log`/`--int-log` の出力フォーマット）。
- 変更は `tools/patches/0010-shared-clock.patch` に追加した。
  q88h_clock.c/h 自体は他の q88h_*.c/h と同じく `tools/setup_harness.sh`
  のコピー手順で配置されるファイルなのでパッチには載らない。パッチの
  中身は `Makefile.common` に `q88h_clock.c` を1行追加するだけ
  （既存の `q88h_iolog.c` などと同じ扱い）。

### なぜ「呼び出し順カウンタ」で足りるのか

QUASI88 は main/sub の2つの Z80 を、`src/emu.c` の `emu_main()` が
**時分割**で実行する（1回の `z80_exec()` 呼び出しは常にどちらか一方の
CPU だけを連続実行してから次に切り替える。同時並行実行はしていない）。
そのためフックの発火順序＝実際の実行順序そのものであり、発火順に
ただ番号を振るだけで、frame よりずっと細かい粒度（時分割の1バーストの
単位）で main/sub 間の前後関係を復元できる。

Z80 の実行サイクル数（T-state 累積）を直接刻めればより物理的だが、
`emu.c` の `main_state`/`sub_state` はスケジューラ内部の按分値であり
CPU 側から素直には見えない。今回は「真の発生順を保証する」という
必要条件を満たす通し番号に留め、サイクル数ベース化は次のスコープとする
（この判断は `q88h_clock.h` のコメントにも書いた）。

## 自己検証（わざと壊して検出できることを確認済み）

`tools/harness/clock_selftest.sh`（新規）+ `tools/harness/clock_order_check.py`
（新規）で以下を検証する。公式 ROM は使わず、`make_test_rom.py --enable-int`
が作る合成ROM（main CPU 上で OUT/IN と HALT+IM1 割り込みを交互に起こす）
だけで完結する。

1. **一意性** — main/sub・iolog/intlog を合わせた clock 値に重複が無い。
2. **単調性** — 同一バッファ（main iolog 節・main intlog 節）内では、
   ファイル出現順（=記録された順そのもの）と clock の大小関係が一致する。
3. **既知の真の前後関係との一致（本命）** — 合成ROMの構造上、
   「k番目の `OUT(E4)` ＜ k番目の割り込み受理 ＜ (k+1)番目の `OUT(E4)`」
   という前後関係が確定している（`OUT(E4)` は初回はレベルの初期アーム、
   以降は割り込みハンドラ内での再アーム）。これは main CPU 内で
   iolog（I/O記録）と intlog（割り込み受理記録）という**別バッファに
   またがる**前後関係であり、frame だけでは検証できない（1フレームに
   複数の `OUT(E4)` が起きうるため）。共通クロックが正しく機能していれば、
   この確定した前後関係が clock の大小として観測されるはずであることを
   実際に確認した。

**わざと壊して検出できることの確認**: `q88h_clock_tick()` を
「常に同じ値（1）を返す」ように書き換えた版でビルドし直し、
`clock_selftest.sh` を再実行した。結果は **NG**（検査1の一意性検査が
「clock 値に重複が121件ある」で落ちた）。正しい版に戻して再ビルドし、
全selftest（`selftest.sh` / `iolog_selftest.sh` / `intlog_selftest.sh` /
`clock_selftest.sh` / `trap_selftest.sh` / `fontsrc_selftest.sh`）が
揃って合格することを確認してから測定に進んだ。

既存の `iolog_selftest.sh` / `intlog_selftest.sh` は、出力に列が1本
（clock）増えたことで awk の列位置参照（`$6`/`$7` など）がずれたため、
新しい列位置に合わせて修正した（動作の検査内容自体は変えていない）。

## 再測定

既存の `measurements/m6-sub-*` と同じ5条件（`tools/measure_suite.sh` の
d0-boot/d1-files/d2-save/d5-seqfile と同じ引数、nodisk はネガティブ
コントロール）を、`--io-log`/`--int-log` に加えて共通クロック入りの状態で
再採取した。出力は `measurements/m6c-sub-<条件名>.iolog.txt` /
`.intlog.txt`（`.txt` は q88measure の通常トレース、既存の命名慣習と同じ）。

原本ディスクイメージには一切書かせていない（`tools/measure.sh` の
使い捨て複製の仕組みをそのまま使った。`d5-seqfile` のみ `--disk-writable`
で複製側のライトプロテクトを解除している。原本は変更していない）。

| 条件 | main IO | sub IO | main 割込 | sub 割込 |
|---|---:|---:|---:|---:|
| nodisk | 18,923 | 0 | 575 | 0 |
| d0-boot | 95,046 | 78,798 | 1,761 | 13,593 |
| d1-files | 119,029 | 89,861 | 2,360 | 15,399 |
| d2-save | 150,460 | 100,962 | 3,543 | 17,205 |
| d5-seqfile | 205,051 | 122,289 | 5,908 | 20,301 |

件数は `m6-sub-proto.md` の第1版時点の値（同条件、共通クロック無し版）と
近いが完全一致ではない（例: d1-files の main IO が105,435→119,029、
main 割込が1,996→2,360）。打鍵タイミングに依存する測定であり、
差分の主因はエミュレータの非決定性というより「その回の実行での
タイミングの揺れ」だと考えられる。取りこぼし（`n_dropped`）は
全条件・全ログで0件だった（5条件×iolog/intlog×main/subの全20系列）。

## スコープ外（次のスコープ）

- 解析器 `tools/analyze_sub_proto.py` を共通クロック対応に更新し、
  main/sub のイベントを clock でマージソートして真の1:1隣接対応を
  取り直すこと。
- それによる Q1（データ経路）の再判定。
- Z80 実行サイクル数ベースのクロックへの高精度化（このノート
  「なぜ『呼び出し順カウンタ』で足りるのか」参照）。

---

**追記（2026-08-10）**: このノートが参照する `measurements/*.iolog.txt` は、その後 `.iolog.txt.gz` に伏せ字＋圧縮した（データポート `$FB`/`$FC`/`$FD` の値列のみ。他の列はそのまま）。上記の記述自体は当時の事実として変更していない。詳細は [docs/notes/disclosure-2026-08-10.md](disclosure-2026-08-10.md) を参照。
