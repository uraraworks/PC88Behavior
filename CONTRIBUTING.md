# Contributing

> **In English**
>
> This project is written without ever reading the official ROM's code — that
> is the whole premise (see [CLAUDE.md](CLAUDE.md)). The same constraint has to
> apply to what we *receive*: if a disassembly listing, a code fragment, or an
> internal ROM address lands in an Issue, a PR, or a discussion thread, reading
> it contaminates the project the moment it is read. Intent doesn't matter —
> the read is the damage.
>
> **Please do not send us:**
> - Disassembly listings or code fragments of the official ROM, or quotes of
>   the form "it says X here" from articles that reproduce them
> - Internal ROM structure: entry addresses, jump tables, work-area addresses,
>   the contents of in-ROM data tables
> - Official ROM byte dumps, or commercial software disk images
>
> **Welcome contributions:**
> - Hardware facts (port numbers, bit meanings, CRTC command formats, circuit
>   behaviour, timing) — the kind of information that gives the *same value*
>   whether you measure it on real hardware or on an emulator
> - Language-spec facts from the official N88-BASIC manual (what a statement
>   means, not how the interpreter is built)
> - Measurement results with reproduction steps (how you measured it)
> - Discrepancies between `docs/spec/` and your own measurements
> - Typos, unclear wording, broken build steps
>
> **Rule of thumb:** *can it be verified by measurement?* If yes, it's
> welcome. If the only source for it is someone's analysis or a disassembly,
> it isn't.
>
> **If something in the list above shows up anyway:** we will close it
> without reading the body. That is not a judgment about the sender's intent
> — the read itself is what causes the damage, and by the time we've read
> enough to judge intent, it's already too late. We are posting this policy
> up front precisely so that this response is not a surprise. We're sorry if
> that feels blunt; it's a condition of the project working at all, not a
> comment on you.

---

## このプロジェクトが受け取れる情報

このプロジェクトは公式 ROM のコードを**一切読まずに**書く
（[CLAUDE.md](CLAUDE.md) のクリーンルーム規律）。

これは自分たちの手だけの話ではない。**外部から送られてくる情報にも同じ制約がかかる。**
Issue・PR・議論のどれであっても、逆アセンブルの断片や ROM 内部の番地が書き込まれた
時点で、それを読めば汚染になる。読んだ担当は該当箇所の実装から外れ、測定からやり直しに
なる（実例: [docs/notes/contamination-2026-08-07.md](docs/notes/contamination-2026-08-07.md)）。
善意か悪意かは関係ない。読んだという事実だけが効く。

背景・設計思想は [docs/PLAN.md](docs/PLAN.md) と [CLAUDE.md](CLAUDE.md) を参照。

## 送らないでほしいもの

Issue・PR・議論のどの形であっても、以下は送らないでください。

- 公式 ROM の逆アセンブルリスト、コード断片
- それらを含む書籍・記事への「ここにこう書いてある」という形の引用
- ROM 内部の構造: エントリアドレス、ジャンプテーブル、ワークエリアの番地、
  ROM 内のデータテーブルの中身
- 公式 ROM のバイト列・ダンプ、市販ソフトのディスクイメージ

## 歓迎するもの

- **ハードウェアの事実**: ポート番号、ビットの意味、CRTC のコマンド書式、回路、
  タイミングなど、実機でもエミュレータでも**測れば同じ値が出る**種類の情報
- N88-BASIC の**マニュアル**に記載された言語仕様・命令の意味
- 実測結果と再現手順（どう測ったかが書いてあるもの）
- `docs/spec/` の記述と実測が食い違っている、という指摘
- 誤字、文書の分かりにくさ、ビルド手順の不備の指摘

## 判定の目安

**「測定で裏が取れる種類の情報か」** の一点で判定してください。

測れば同じ値が出る情報（ポート番号、ビットの意味、タイミングなど）は歓迎します。
その情報の出所が特定の資料（解析記事・逆アセンブルリストなど）にしかないなら、
送らないでください。

## 送られてきた場合の扱い

上記に該当する内容が Issue・PR・議論に含まれていた場合、**本文を読まずに閉じます**。

理由は単純で、読んだ時点で手遅れだからです。悪意の有無は問いません。
不快に思われたら申し訳ありませんが、この扱いをあらかじめ掲示しておくこと自体が、
このプロジェクトが成立するための前提条件です。

## 参考

- [docs/PLAN.md](docs/PLAN.md) — 設計と進め方
- [CLAUDE.md](CLAUDE.md) — クリーンルーム規律
- [docs/notes/contamination-2026-08-07.md](docs/notes/contamination-2026-08-07.md) —
  過去の汚染事例と対応
