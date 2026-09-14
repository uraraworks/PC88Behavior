# M7 段階0（後半）— 自作アセンブラの外部オラクル突き合わせ

## 位置づけ

`docs/notes/l4-design.md` 段階0「アセンブラ」の後半。自作アセンブラ
`tools/asm/z80text.py`（コミット b8d9eee）の符号化が、Z80 の**文書化された
全命令**で正しいことを、外部アセンブラ2種と突き合わせて確かめる。

自作を自作の相手役（既存の `make_ipl_rom.py`/`make_subrom.py` の表）で検査
すると同じ誤解が両方に入りうる（`feedback_selftest_both_sides_selfmade.md`）
ので、正解は**リポジトリ外の外部アセンブラ**から取る。外部アセンブラは
**検査専用**で、自作 ROM のビルドには使わない。

## 正解役（オラクル）

| 名前 | 版 | コミット | ライセンス | 置き場 |
|---|---|---|---|---|
| sjasmplus | v1.24.0 | `d379eeac9ad3857fb48fd3a3929175d0a56038ce` | BSD-3-Clause | `/Users/haruurara/MyProject/_emulator/PC88/vendor/asm-oracles/sjasmplus-src/sjasmplus`（ビルド済みバイナリ） |
| z88dk-z80asm | v2.4 | `4d530b6eb779ad0f2a1d13c0bb670cf717477501` | Artistic License 2.0 | `/Users/haruurara/MyProject/_emulator/PC88/vendor/asm-oracles/z88dk-src/src/z80asm/z88dk-z80asm`（ビルド済みバイナリ） |

いずれも `PC88Behavior` リポジトリの**外**（`_emulator/PC88/vendor/`）に置く。
理由は2つ:

1. ビルドには使わない道具をリポジトリに混ぜない（`docs/PLAN.md` の主張＝
   「自作 ROM は自作の道具だけで作った」を薄めない）。
2. ライセンスの異なる第三者ソース／バイナリをコミット対象に持ち込まない。

パスは環境変数で受け取る（スクリプトに絶対パスを焼き込まない）:

```
Z80_ORACLE_SJASMPLUS=/Users/haruurara/MyProject/_emulator/PC88/vendor/asm-oracles/sjasmplus-src/sjasmplus
Z80_ORACLE_Z88DK=/Users/haruurara/MyProject/_emulator/PC88/vendor/asm-oracles/z88dk-src/src/z80asm/z88dk-z80asm
```

未設定（またはパスが存在しない）場合は `oracle_crosscheck.py` が
「SKIP: 正解役なし＝未検査」を目立つ形で表示し、終了コード **2**（0=合格
とは別の値）で終わる。CI やスクリプトが SKIP を合格と誤読しないための
区別。

## 作った道具

- `tools/asm/gen_z80_corpus.py`: Zilog 標準ニーモニックで、Z80 の文書化
  された命令形を1行1命令で列挙する。レジスタは全組み合わせ、即値・番地は
  境界値（`0, 1, 0x7F, 0x80, 0xFF, 0x7FFF, 0x8000, 0xFFFF, 0x1234` 等）、
  `(IX+d)`/`(IY+d)` は `d = -128, -1, 0, 1, 127`、`JR`/`DJNZ` は `$-126`
  （d=-128）〜`$+129`（d=127）の境界、`RST` は8種全部、`IM 0/1/2`、
  `IN`/`OUT` は `(C)` 形と `(n)` 形の両方を含む。未文書化命令（SLL、
  IXH/IXL 直接アクセス、DD/FD CB の「おまけ」書き込み先、IN F,(C) 等）は
  入れない。3者で表記が割れる箇所は無かった（`0x..` 表記・`ex af,af'`・
  `rst 0x08` 形はいずれも sjasmplus/z88dk-z80asm(`-m=z80_strict`)/z80text.py
  で共通に通ることを最初に3命令ほどの小さいファイルで確認してから全体を
  生成した）。
  - 出力: `.asm` 本体と、行ごとの命令テキスト・期待バイト長・分類タグを
    記録した manifest（TSV）。期待バイト長は Z80 ISA の一般知識（命令形が
    何バイトになるか）から決めており、ROM 由来ではない。正誤判定は
    manifest を使わず、外部2アセンブラの出力バイト列同士を突き合わせる
    ことで行う。
  - 生成時に見つけた自分のミスを1件修正した: ED 前置きの
    `LD (nn),HL`/`LD HL,(nn)` を BC/DE/SP と同列に列挙していたが、
    HL はこの文字列に対して main ページの3バイト形（同じニーモニック）が
    既にあり、どのアセンブラも短い方を選ぶため4バイトの ED 形には
    到達しない。コーパス生成器側のバグと判断し、ED 側のループは
    BC/DE/SP のみに直した（z80text.py 本体は無関係）。

- `tools/asm/oracle_crosscheck.py`: コーパス全体を1つの `.asm` として
  z80text.py・sjasmplus・z88dk-z80asm（`-m=z80_strict -no-synth -b`、
  素の生バイナリを出力）にそれぞれ**1回ずつ**通し（1行ずつ個別プロセスを
  立てるより桁違いに速い）、manifest の期待バイト長で3者の出力を同じ
  命令境界に切り分けてから1命令ずつ比較する。3者の合計バイト数が
  期待値と食い違う場合は「組めない」として NG 扱いにする。
  - 判定は「3者一致／自作だけ違う／外部同士が違う／組めない」の4値。
    自作だけ違う・外部同士が違うが1件でもあれば NG。
  - 網羅は**外部アセンブラの出力バイト列側**から数える（自作の表は使わない）:
    主命令ページ（先頭バイトが CB/DD/ED/FD 以外）の先頭バイト種類数、
    CB xx の2バイト目種類数、ED xx・DD xx（非CB）・FD xx（非CB）の
    2バイト目種類数、DD CB d xx / FD CB d xx の末尾バイト種類数。
    主命令ページ252・CB 248 に届かなければ NG（コーパスの抜けを意味する
    ため）。
  - 陽性対照（故障注入）: 環境変数 `Z80TEXT_FAULT_LINE=<index>` を渡すと、
    z80text.py の出力をこのスクリプトが読み込んだ**後**に該当命令の
    先頭バイトを1ビット反転させる（z80text.py 本体は変更しない）。
    NG として検出できることを確認済み（下記結果参照）。

## 実行方法

```
Z80_ORACLE_SJASMPLUS=.../sjasmplus \
Z80_ORACLE_Z88DK=.../z88dk-z80asm \
python3 tools/asm/oracle_crosscheck.py
```

1回の実行は 0.5 秒未満（コーパス生成・3アセンブラ起動・比較・網羅集計を
含む）。`run_all_selftests.sh`・`conform_l3.sh` には含めていない
（段階0専用の検査のため、既存のセルフテスト群とは別系統で回す）。

## 結果（2026-09-15 実施分）

- コーパス: **1293行**（主命令ページ・CB・ED・DD/FD・DD/FD CB を網羅）
- 3者一致: **1293 / 1293**（自作だけ違う 0件、外部同士が違う 0件、
  組めない 0件）
- 網羅（sjasmplus 側・z88dk 側の出力から独立に集計、両者一致）:
  - 主命令ページ 先頭バイト種類数: **252 / 252**（充足）
  - CB xx 種類数: **248 / 248**（充足。SLL 相当の8通りは除外どおり）
  - ED xx 種類数: 52
  - DD xx（非CB）種類数: 39
  - FD xx（非CB）種類数: 39
  - DD CB d xx 末尾バイト種類数: 31（回転7種＋BIT/RES/SET各8種）
  - FD CB d xx 末尾バイト種類数: 31（同上）
- 陽性対照: `Z80TEXT_FAULT_LINE=5`（`LD B,L` の符号化）を1ビット反転させたところ、
  「3者一致 1292/1293」「不一致1件・自作だけ違う」として正しく NG 判定
  （終了コード1）になることを確認した。

## 結論

z80text.py を修正する必要は無かった（コーパス生成器側のバグ1件のみで、
z80text.py 本体は無変更）。この節点でのコミットはコーパス生成器・突き合わせ
器具・本ノートの1本のみ。
