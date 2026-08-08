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
> which is excluded from git and has never appeared in the commit history. Everything
> published here — documents, source, build scripts, conformance tests — is independently
> re-derivable by a third party.
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
公開しているのは**文書・ソース・ビルドスクリプト・適合性テスト**だけで、
すべて第三者が独立に再導出できるものに限っている。

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
| M6 | L3 サービスルーチン | 進行中。サブ ROM（`DISK.ROM`）の仕様第4版、自作サブ ROM が自己検証を通過 |
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

公式 ROM は各自で用意すること（`private/rom/` に置く。このリポジトリには含まない）。

```
tools/setup_harness.sh    # 上流をピン留めコミットで取得・改変・ビルド・疎通試験
tools/check_cleanroom.sh  # 防御が効いているかの検査
tools/measure_suite.sh    # 測定一式（28条件）
tools/profile.py --growth measurements/*.txt
```

## ライセンス

MIT License（[LICENSE](LICENSE)）。文書・測定結果・ツールを含め全体に適用する。

土台に使っている QUASI88 / QUASI88-libretro は BSD 3-Clause で、
本リポジトリには第三者のコードを含まない（ピン留めコミットへのパッチのみ）。
詳細は [docs/notes/m1-quasi88-survey.md](docs/notes/m1-quasi88-survey.md)。

## 測定結果について

`measurements/` に入っているのは、公式 ROM を動かしたときに
**どの番地にどの種類のアクセスがあったか**の記録である。
ROM の内容（バイト列）は含まない。

条件が意図どおりだったかを結果自身で検証できるよう、終了時のテキスト画面も
残している。ただしディスクのファイル一覧だけは私物の内容なので伏せている
（`tools/redact.py`）。
