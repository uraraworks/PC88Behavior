# PC88Behavior

> **In English**
>
> A clean-room reimplementation of the NEC PC-8801 ROM, written **without ever reading
> the original ROM's code**. The name refers to the method: the only permitted source of
> information is externally observed *behaviour*.
>
> The PC-88 cannot boot without its ROM — even the code that reads a floppy lives there —
> so running one without the original means writing a replacement.
>
> **What this repository does not contain:** no original ROM bytes, no disassembly of the
> original ROM, no dumped disk images, no commercial software. Those stay in `private/`,
> which is excluded from git and has never appeared in the commit history.
>
> `measurements/` *is* published, and it does contain measurement logs taken while running
> the official ROM — I/O port accesses with address, value, direction and timing. The value
> stream on the data ports (`$FB`/`$FC`/`$FD`) is raw data read off the official disks, so
> those values are redacted before commit (count and SHA-256 of the pre-redaction stream are
> kept for conformance checks) and the logs are gzip'd. **This was not the case from
> 2026-08-07 to 2026-08-10: unredacted data-port values were committed and pushed to the
> public repo for about three days before this was caught and fixed.** See
> [docs/notes/disclosure-2026-08-10.md](docs/notes/disclosure-2026-08-10.md) for the full
> account — what was exposed, how it was fixed, and why the history is not rewritten.
> Everything published here — documents, source, build scripts, conformance tests — is
> independently re-derivable by a third party from the (redacted) measurements.
>
> **Method:** instead of reading a disassembly, measurement hooks are added to an emulator
> and the ROM's entry points are exercised to record what goes in and what comes out.
> What that yields is *facts* (given this input, this output follows), not expression.
> A side effect is that no copy of the original code exists on the machine at all, so
> there is nothing to copy from. The discipline is structural, not a promise.
>
> **Language:** the documentation, notes and commit messages are in Japanese. The subject
> matter, the hardware references and the contemporaneous working notes are all Japanese,
> and maintaining two live copies of a document that is still changing would invite drift.
> **An English translation of the design documents is planned once the project reaches a
> usable state.** If you need something specific before then, please open an issue.
>
> Start with [docs/PLAN.md](docs/PLAN.md) (design and method) and
> [CLAUDE.md](CLAUDE.md) (the clean-room rules, enforced by the permission settings in
> `.claude/settings.json` and checked by `tools/check_cleanroom.sh`).
>
> **Before opening an Issue or PR, please read [CONTRIBUTING.md](CONTRIBUTING.md)** —
> it explains what information we can and cannot accept.

---

PC-8801 の ROM の**代替**を、公式 ROM のコードを**一切読まずに**、外部から観測した振る舞いだけを
根拠に書き起こすプロジェクト。名前の "Behavior" はその手法そのものを指す。

PC-88 は ROM が機械の本体で、抜くとディスクを読むコードすら無くなる。
だから ROM 無しでこの機械を動かすには、ROM を作るしかない。

## このリポジトリに入っていないもの

- 公式 ROM のバイナリ、およびその一部バイト列
- 公式 ROM の逆アセンブル結果
- 吸い出したディスクイメージ、市販ソフト

これらは `private/`（git 管理外）に隔離されており、コミット履歴に一度も現れない。

`measurements/` は公開している。公式 ROM を動かして採った I/O ログ（番地・値・
方向・タイミング）が入っている。このうちデータポート（`$FB`/`$FC`/`$FD`）の
値列は公式ディスクの実データそのものなので、コミット前に伏せ字化・gzip 化する
（伏せる前の件数と SHA-256 は残し、適合判定に使う）。**2026-08-07〜2026-08-10 は
これができておらず、伏せ字前の値列を約3日間 public に push していた。**
経緯は [docs/notes/disclosure-2026-08-10.md](docs/notes/disclosure-2026-08-10.md)。

公開しているのは**文書・ソース・ビルドスクリプト・（伏せ字化した）測定ログ・
適合性テスト**で、すべて第三者が独立に再導出できるものに限っている。

## 手法

逆アセンブルを読む代わりに、エミュレータに計測フックを入れ、ROM の入口に入力を振って
出力を採取する。採れるのは「こう与えたらこう返る」という**事実**であり、表現ではない。

副次的に、手元に原典コードが存在しない状態になる。写経しようにも写経元が無い。
規律を守るのではなく、破れない構造にしてある。

## 状態

2026-10-02時点。M6（L3 サービスルーチン）は測定した需要入口の範囲でいったん完了し、
M7（L4 BASIC 互換処理系）は**ゴール A（代表的な BASIC プログラムが動く）の達成判定を
得た（`tools/conform_l4.sh`、`l4-c5` の8本中8本一致、2026-09-16）**。
その後、スクリーンエディタ・キーリピート・単精度の数値関数を実装し、自作mainから
`FILES`・`LOAD`（ASCII）・`SAVE ,A`・`KILL`・`NAME`まで接続した
（各適合検査の範囲は下記）。全機能の互換や番地互換を達成したわけではない。
L1 IPL と L2 フォントも完了しており、どちらも**公式 ROM が無くても検証できる**
（`tools/verify_l1.sh` / `tools/verify_l2.sh`）。

| | 層・内容 | 状態 |
|---|---|---|
| M1–M3 | 計測ハーネス、トラップ ROM、需要プロファイル | 完了 |
| M4 | L1 IPL | 完了（2026-08-07） |
| M5 | L2 フォント | 完了（2026-08-07） |
| M6 | L3 サービスルーチン | 測定した需要入口の範囲でいったん完了（2026-09-14）。公式main＋自作subの適合検査 `tools/conform_l3.sh` は参照媒体2種・2ドライブのSAVE場面を含め OK 510件・SKIP 0件（2026-10-02）。期待値は件数と SHA-256 のみ。例外と再開条件は [docs/PLAN.md](docs/PLAN.md) 8節。サブROM仕様は [第223版](docs/spec/l3-subrom.md) |
| M7 | L4 BASIC 互換処理系 | ゴールAの達成判定済み（`l4-c5`、代表プログラム8本中8本一致、2026-09-16）。以後の実装・適合範囲は下記。仕様は [l4-basic.md](docs/spec/l4-basic.md) 第3.17版・[l4-program.md](docs/spec/l4-program.md) 第13版 |
| M8 | 適合性テストスイート公開 | L3・L4・ディスク命令別の適合検査と `tests/conformance/` の期待値を公開。`tools/run_all_selftests.sh` は約207本、全OK（2026-10-02、公式環境なしの定型SKIPあり）。公式ROM保有者向けの手順書は未整備 |
| M9 | ゴール B（番地互換） | 未着手 |

### M7 の実装・適合範囲

- **直接モード・プログラムモード:** 打鍵エコー11腕・`PRINT`16腕・浮動小数点25腕・
  代表プログラム8本が公式の期待値と一致（`tools/conform_l4.sh`、`l4-c1b`・`l4-c2c`・
  `l4-c3`・`l4-c5`）。行の入力・保存・`LIST`・`NEW`・`RUN`と流れの制御を実装済み。
- **編集・数値計算（2026-09-19〜2026-09-20）:** スクリーンエディタの編集キー・RETURN行読み直し・
  キーリピートを実装（`tools/conform_l3_editor.sh`、`l4-c6` の32腕が検査対象）。
  単精度の四則演算の丸め・`CDBL`、`SQR`・`SIN`・`COS`・`TAN`・`ATN`・`EXP`・`LOG`を実装し、
  `l4-c7` 40腕・`l4-c8` 59腕が公式の期待値と一致（`tools/conform_l4.sh`）。
  単精度FINは`REP01`採用を撤回して`GW`へ変更した。倍精度FINの`DREP10A`は推定のまま。
- **ディスク命令（2026-09-27〜2026-10-02）:** 自作mainから`FILES`・`LOAD`（ASCII）・
  `SAVE ,A`・`KILL`・`NAME`を実装。`tools/conform_files.sh` はlocal 29腕・hybrid 4腕、
  `conform_load.sh` は8腕・4腕、`conform_save.sh` は6腕・2腕、`conform_killname.sh` は10腕・10腕で
  公式の判定と一致（2026-10-02）。localは自作一式、hybridは自作main＋公式sub。
  ディスク形式の根拠は [l3-disk-format.md](docs/spec/l3-disk-format.md) 第7版。
- **LIST（2026-10-01〜2026-10-02）:** 語・空白などを公式の規則で整形し、
  `l4-s5h` 723腕中722腕が一致（`tools/l4_listkw_selftest.sh`、`go sub10` は未確定）。
  数値定数は行の入力時に値として読み直し、LIST用に書き直す
  （`tools/l4_listnum_measure.py check`、`l4-s5i` 193腕が一致。入力時エラー行末尾の
  非ASCII 1文字は再現しない既知差として扱う）。

拡張ROMバンク `N88_0.ROM`〜`N88_3.ROM`も使用する。バンク0に単精度の数値関数、
バンク1に`FILES`・`LOAD`、バンク2に`SAVE ,A`・`KILL`・`NAME`、バンク3に
`READ`・`RESTORE`・`CONT`やLISTの数値書き換えを置く
（[ext-rom-bank.md](docs/spec/ext-rom-bank.md)、`src/ext_bank/`）。

### できないこと（正直に）

ゴールAは「代表的なテキスト画面のBASICプログラムが動く」の範囲であって、
N88-BASICの全機能ではない。2026-10-02時点で以下は未対応・未検証のまま：

- グラフィック・音、`RND`、`PRINT USING`は未実装。
- 通常の`SAVE`（中間コード形式）・`SAVE ,P`・`BSAVE`の本体形式は未測定で、
  自作mainでは未実装。`,A`無しの`SAVE`と種別`0x80`等の`LOAD`は`ERR 51`で断る。
  M6で公式main＋自作subが通った命令すべてを、自作mainで使えるわけではない。
- 数値関数の倍精度専用経路は未実装・未確定。単精度でも`SIN`の一部の残差、
  `ATN`の`|x|=1`の1ULP差の原因、`SQR`の反復手順・近似精度は未確定。
  固定した`l4-c8`の適合は、すべての引数での一致を意味しない。
- LISTの`go sub10`の規則、数値入力時のエラー行末尾の非ASCII 1文字は未再現。
  FINの24文字バッファに収まらない数値字句の書き換えも未実装。
- 浮動小数点の定数読み取り（FIN）は未検証の部分が残る。単精度は`GW`へ変更済みだが、
  全入力での一致は未確認。倍精度`DREP10A`は事後の当てはめを含む推定で、
  前向き測定の全腕一致を得ていない（[l4-basic.md](docs/spec/l4-basic.md) 第5.1節）。
- `WIDTH 40`の画面は未対応（`WIDTH 80,25`は測定・実装済み）。
- 実行の速さ（自作ROMは公式ROMより遅い場合があり、比較対象にしていない）。
- 番地互換（ゴールB）は未着手。

各仕様書の「未確定」節（[l4-basic.md](docs/spec/l4-basic.md) 第10節・
[l4-program.md](docs/spec/l4-program.md) 第8節）に、測定できていない項目の一覧がある。

需要プロファイル: 公式 ROM を 28 条件で測ったところ、メイン ROM 32KB のうち
実行されるのは 32.5%、サブ ROM（`DISK.ROM`）2KB のうち 648 バイト。

**行き止まりや誤りもそのまま残している。** 観測系に共通の時間軸が無くて経路同定が
頭打ちになった経緯、一致率 100% を「エミュレータの実装由来で必然」と判断して
証拠に採用しなかった判断、判定スクリプトが8列ログを一度も正しく読めていなかった
バグ——いずれも `docs/notes/` にある。測定が実装に先行した順序も履歴に残っている。

- 設計と進め方: [docs/PLAN.md](docs/PLAN.md)
- 仕様書（ここだけを見て実装する）: [docs/spec/](docs/spec/)
- 土台にした QUASI88-libretro の調査: [docs/notes/m1-quasi88-survey.md](docs/notes/m1-quasi88-survey.md)
- 需要プロファイル: [docs/notes/m3-demand-profile.md](docs/notes/m3-demand-profile.md)
- Issue・PR を送る前に: [CONTRIBUTING.md](CONTRIBUTING.md)（送ってよい情報・いけない情報の判定基準）

### 手元で再現する

公式 ROM が必要なのは**測定を再現する場合と、適合テストの公式ROM側を自分の目で
確かめる場合だけ**である（`private/rom/` に各自で置く。このリポジトリには含まない）。
**完成した互換 ROM を組み立てて動かすだけなら公式 ROM の複製は不要**で、
それがこのプロジェクトの目的そのものである。

自作 ROM の組み立ては `python3` だけで、外部依存（アセンブラ等の別ツール）は
不要である（内蔵の自作 Z80 テキストアセンブラ `tools/asm/z80text.py` で組む）。

```
python3 src/build_main_rom.py <出力先ディレクトリ>   # N88.ROM/DISK.ROM/FONT.ROMと拡張ROMバンク4本を組み立てる
tools/verify_l1.sh        # L1 IPLの自己検証（公式ROM不要）
tools/verify_l2.sh        # L2 フォントの自己検証（公式ROM不要）
tools/verify_l3.sh        # L3 サービスルーチンの自己検証（公式ROM不要）
tools/conform_l4.sh       # L4 適合テスト（自作ROM側だけでも回る。公式ROMがあれば公式側も判定）
```

組み立てた ROM は QUASI88-libretro 系のエミュレータへ載せて動かす。公式 ROM を
使った測定の再現や、適合テストの公式ROM側の再導出には、以下を使う。

```
tools/setup_harness.sh    # 上流をピン留めコミットで取得・改変・ビルド・疎通試験
tools/check_cleanroom.sh  # 防御が効いているかの検査
tools/measure_suite.sh    # 測定一式（28条件）
tools/profile.py --growth measurements/*.txt
tools/conform_l3.sh       # L3 適合テスト（期待値は件数+SHA-256のみ）
```

## ライセンス

MIT License（[LICENSE](LICENSE)）。文書・測定結果・ツールを含め全体に適用する。
「測定結果」は現在 `measurements/` にある伏せ字化・gzip 化後のログを指す
（伏せ字化前は第三者の著作物であるディスクの実データを含んでいたため、
MIT の対象ではなかった。経緯は前節）。

土台に使っている QUASI88 / QUASI88-libretro は BSD 3-Clause で、
本リポジトリには第三者のコードを含まない（ピン留めコミットへのパッチのみ）。
詳細は [docs/notes/m1-quasi88-survey.md](docs/notes/m1-quasi88-survey.md)。

## 測定結果について

`measurements/` の各 `*.iolog.txt.gz` には、公式 ROM を動かしたときの
I/O アクセスが1件ずつ記録されている。フィールドの扱いは値の種類で分ける：

- **データ経路の値**（`$FB` FDC データ、`$FC`/`$FD` PIO データ）→ **伏せ字**。
  公式ディスクから読み出した実データそのものだから。伏せる前の件数と SHA-256
  は各ログ末尾に記録してあり、適合判定（`tools/cmp_io.py` 等）は継続できる
- **ステータス・フェーズコード**（`$FA`/`$FE`/`$FF`/`IN 40`/CRTC 等の値）→ 残す。
  ハードウェアの事実であり、伏せる理由が無い
- **pc（発行元アドレス）** → 残す。ROM 内部の番地だが自分で測って得たもの
- **frame / clock / seq** → 測定系が付けた番号

伏せ字化は `tools/redact_iolog.py`、ログは全件 gzip 済み。`tools/cmp_io.py` や
`tools/hash_io_stream.py` などは `.gz` を透過的に読む。検査は
`tools/check_cleanroom.sh` が自動で行い、伏せ字漏れ・未 gzip・50MB 超のファイルを
検出する。

終了時のテキスト画面は、画面本文を出さず、行数・文字数・SHA-256の署名と
真偽判定で検証する（`CLAUDE.md` 禁止事項7、`tools/check_l3_screen_output.py`・
`tools/check_l3_entry_screen.py`）。

**2026-08-10 より前は、この伏せ字化を行っていなかった。** 2026-08-07 から
2026-08-10 まで、データポートの値列は伏せ字のないまま public リポジトリに
push されていた。この事実は隠さず、過去のコミットもそのまま残す（履歴は
書き換えない——`CLAUDE.md` の「行き止まりを `git reset` で消さない」に従う）。
何が公開されていたか、いつからいつまでか、どう直したかは
[docs/notes/disclosure-2026-08-10.md](docs/notes/disclosure-2026-08-10.md) に
すべて書いてある。
