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

M6（L3 サービスルーチン）進行中。L1 IPL と L2 フォントは完了しており、
どちらも**公式 ROM が無くても検証できる**（`tools/verify_l1.sh` / `tools/verify_l2.sh`）。

| | 層・内容 | 状態 |
|---|---|---|
| M1–M3 | 計測ハーネス、トラップ ROM、需要プロファイル | 完了 |
| M4 | L1 IPL | 完了（2026-08-07） |
| M5 | L2 フォント | 完了（2026-08-07） |
| M6 | L3 サービスルーチン | 進行中。サブ ROM（`DISK.ROM`）の仕様第4版、自作サブ ROM が自己検証を通過。二層検証（自己検証 `tools/verify_l3.sh` / 適合テスト `tools/conform_l3.sh`、期待値は件数と SHA-256 のみ）を追加 |
| M7 | L4 BASIC 互換処理系 | 未着手 |
| M8 | 適合性テストスイート公開 | M6 と並行して形が決まりつつある |
| M9 | ゴール B（番地互換） | 未着手 |

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

公式 ROM が必要なのは**測定を再現する場合だけ**である（`private/rom/` に各自で置く。このリポジトリには含まない）。完成した互換 ROM を利用するのに公式 ROM の複製は不要で、それがこのプロジェクトの目的そのものである。

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

終了時のテキスト画面も、条件が意図どおりだったかを結果自身で検証できるよう
残している。ディスクのファイル一覧だけは私物の内容なので伏せている
（`tools/redact.py`）。

**2026-08-10 より前は、この伏せ字化を行っていなかった。** 2026-08-07 から
2026-08-10 まで、データポートの値列は伏せ字のないまま public リポジトリに
push されていた。この事実は隠さず、過去のコミットもそのまま残す（履歴は
書き換えない——`CLAUDE.md` の「行き止まりを `git reset` で消さない」に従う）。
何が公開されていたか、いつからいつまでか、どう直したかは
[docs/notes/disclosure-2026-08-10.md](docs/notes/disclosure-2026-08-10.md) に
すべて書いてある。
