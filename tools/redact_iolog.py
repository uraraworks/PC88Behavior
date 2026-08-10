#!/usr/bin/env python3
"""tools/redact_iolog.py — iolog に写り込んだ公式ディスクの実データを伏せる。

## なぜ・いつ・何を伏せるか

`measurements/*.iolog.txt` には OUT/IN の発生順・ポート・値・PC・フレーム
番号を記録している（形式は各ファイル冒頭のコメント参照）。この「値」の列は
ほとんどが CPU⇔デバイスの制御・ステータスのやり取りだが、一部のポートは
**公式ディスク（diskA 等、private/ 配下の私物）から読み出した実データが
そのまま出力される**。CLAUDE.md 禁止事項4「ROM由来のバイト列を含む
ファイルをコミットしない」の趣旨はディスク由来のデータにも及ぶため、
公開前に手当てする（2026-08-10、tools/redact.py に続く伏せ字ツールの追加）。

**伏せるのはデータ経路の3ポートの value 列だけ。** 対象は
`docs/spec/l3-subrom.md` で「データそのものをやり取りする」と確定した
ポートに限る：

  - `$FC` / `$FD` — main⇔sub 間の PIO データ経路（同ノート 1.2節・1.6節。
    双方向一致率100%・256値中255〜256種を使う分布から、制御/ストローブ
    ではなくデータレジスタと確定）
  - `$FB` — sub が自分の FDC（実ディスク）を叩くデータポート
    （同ノート 1.9節。`sub OUT $FB` は毎バイト `$FA` ポーリングを
    伴う厳格なハンドシェイクで、ディスクの実データ/コマンドバイトが載る）

`$FA`（ステータス）・`$FE`（待ち状態）・`$FF`（フェーズコード）・`$F7`/`$F8`
（ほぼ定数の制御ポート）・`IN 40`（VRTC）・CRTC ポート等は、ハードウェアの
事実そのものであり伏せる理由が無いので**残す**（同ノート 1.4〜1.5節・
1.12〜1.13節）。行・seq・clock・frame・port・kind・pc も残す。これらは
`tools/cmp_io.py` の分岐点検出（適合条件の判定）に必要で、消すと解析能力が
落ちる。

## 何をするか

- 対象ポート（既定 `$FB`/`$FC`/`$FD`。`--ports` で上書き可）への
  IN/OUT（main/sub 両CPU）の value 列だけを固定文字列 `--` に置換する。
  桁数は元の値に依存しない固定長なので、値の長さから元の値を推測する
  手掛かりにならない。
- 置換前に、伏せる (cpu, port, kind) の組ごとに元の値列の件数と SHA-256 を
  計算する。ハッシュ計算は `tools/hash_io_stream.py` の `hash_values()` を
  import して使う（二重実装しない。同じ値列に対して両ツールが同じ
  ハッシュを出すことが tests/conformance/expected.tsv との比較で効く）。
- ファイル末尾に「伏せた記録」の節として、その (cpu, port, kind, count,
  sha256) を追記する。**値そのものはここにも書かない。**
- 既に伏せてある（「伏せた記録」の節を持つ）ファイルに再実行すると、
  何もせずそのまま返す（冪等性）。

## 使い方

    tools/redact_iolog.py <ファイル>              # 標準出力に書く（既定）
    tools/redact_iolog.py --in-place <ファイル>... # その場で書き換える
    tools/redact_iolog.py --ports 00FB,00FC,00FD <ファイル>

終了コード: 正常 0 / 入力エラー 2
"""

import argparse
import gzip
import pathlib
import sys
from pathlib import Path

# hash_io_stream.py（さらにその先の cmp_io.py）と同じディレクトリから import。
# ハッシュ計算を二重実装しないための唯一の依存。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hash_io_stream  # noqa: E402
from cmp_io import normalize_port, FormatError  # noqa: E402

# 対象ポート（docs/spec/l3-subrom.md 1.2節・1.6節・1.9節。根拠はモジュール
# docstring 参照）。4桁16進・大文字に正規化した表記で持つ（ログの表記と
# 揃える。cmp_io.normalize_port と同じ規則）。
DEFAULT_TARGET_PORTS = ["00FB", "00FC", "00FD"]

MASK = "--"

FOOTER_MARKER = "# ---- tools/redact_iolog.py: 伏せた記録 ----"


def _open_maybe_gz(path, mode="rt"):
    """iolog を透過的に開く。拡張子が .gz なら gzip 展開する。

    tools/cmp_io.py の _open_iolog と同じ方針（読み込み側）。書き込み側
    (--in-place の出力) にも同じ判定を使う。
    """
    p = str(path)
    if p.endswith(".gz"):
        return gzip.open(path, mode, encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def _parse_ports_arg(spec: str) -> list[str]:
    return [normalize_port(p) for p in spec.split(",") if p.strip()]


def redact_text(text: str, target_ports: list[str]) -> tuple[str, dict]:
    """text を1行ずつ見て、対象ポートの value 列を伏せる。

    戻り値: (伏せ字後のテキスト, {(cpu, port, kind): [伏せる前の値, ...]})

    既に「伏せた記録」の節（FOOTER_MARKER）を持つテキストは、そのまま
    (変更無し, {}) を返す（冪等性）。
    """
    if FOOTER_MARKER in text:
        return text, {}

    target_set = set(target_ports)
    collected: dict[tuple[str, str, str], list[str]] = {}
    out_lines = []
    had_trailing_newline = text.endswith("\n")

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out_lines.append(line)
            continue

        fields = stripped.split()
        # cmp_io.parse_iolog と同じ2形式。
        #   旧形式(7列): seq frame cpu kind port value pc
        #   新形式(8列): seq clock frame cpu kind port value pc
        if len(fields) == 7:
            seq_s, frame_s, cpu, kind, port, value, pc = fields
            value_idx = 5
        elif len(fields) == 8:
            seq_s, clock_s, frame_s, cpu, kind, port, value, pc = fields
            value_idx = 6
        else:
            # イベント行の形をしていない行（本文コメント等）はそのまま残す。
            out_lines.append(line)
            continue

        if kind not in ("IN", "OUT") or cpu not in ("main", "sub"):
            out_lines.append(line)
            continue
        try:
            int(seq_s)
        except ValueError:
            out_lines.append(line)
            continue

        try:
            port_norm = normalize_port(port)
        except FormatError:
            out_lines.append(line)
            continue

        if port_norm not in target_set:
            out_lines.append(line)
            continue

        key = (cpu, port_norm, kind)
        collected.setdefault(key, []).append(value)

        fields[value_idx] = MASK
        out_lines.append(" ".join(fields))

    new_text = "\n".join(out_lines) + ("\n" if had_trailing_newline else "")
    return new_text, collected


def append_footer(text: str, collected: dict, target_ports: list[str]) -> str:
    """「伏せた記録」の節を末尾に追記する。値そのものは書かない。"""
    if not text.endswith("\n"):
        text += "\n"

    lines = [
        FOOTER_MARKER,
        "#",
        "# 対象ポート（値のみ伏せた。他の列は残す）: "
        + ", ".join(sorted(target_ports))
        + "（docs/spec/l3-subrom.md 1.2節・1.6節・1.9節。根拠は"
        + " tools/redact_iolog.py 冒頭のコメント参照）",
        "# 書式: cpu  port  kind  count  sha256",
        "# sha256 は tools/hash_io_stream.py の hash_values() と同一計算",
        "# （tools/cmp_io.py --cpu <cpu> --port <port> --kind <kind> の抽出結果と一致する）。",
    ]
    for (cpu, port, kind), values in sorted(collected.items()):
        digest = hash_io_stream.hash_values(values)
        lines.append(f"# {cpu}\t{port}\t{kind}\t{len(values)}\t{digest}")

    return text + "\n".join(lines) + "\n"


def redact_iolog(text: str, target_ports: list[str]) -> tuple[str, dict]:
    """redact_text + append_footer をまとめる。既に伏せてあれば無変更。"""
    new_text, collected = redact_text(text, target_ports)
    if not collected:
        # FOOTER_MARKER が既にあった（冪等）か、対象ポートが1件も無かった。
        return new_text, collected
    return append_footer(new_text, collected, target_ports), collected


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="iolog のデータポート(既定 $FB/$FC/$FD)の value 列だけを伏せる"
    )
    parser.add_argument("files", nargs="+", help="対象の .iolog.txt（.gz可）")
    parser.add_argument(
        "--ports",
        default=None,
        metavar="PORT,PORT,...",
        help="伏せるポートをカンマ区切りで上書き（既定: "
        + ",".join(DEFAULT_TARGET_PORTS)
        + "）",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="その場で書き換える（既定は標準出力に書く）",
    )
    args = parser.parse_args(argv)

    try:
        target_ports = (
            _parse_ports_arg(args.ports)
            if args.ports is not None
            else list(DEFAULT_TARGET_PORTS)
        )
    except FormatError as e:
        print(f"エラー: --ports の指定が不正: {e}", file=sys.stderr)
        return 2

    for f in args.files:
        p = pathlib.Path(f)
        try:
            with _open_maybe_gz(p, "rt") as fh:
                text = fh.read()
        except OSError as e:
            print(f"エラー: {p} を読めない: {e}", file=sys.stderr)
            return 2

        new_text, collected = redact_iolog(text, target_ports)

        if args.in_place:
            with _open_maybe_gz(p, "wt") as fh:
                fh.write(new_text)
            if collected:
                n = sum(len(v) for v in collected.values())
                print(f"{p.name}: {len(collected)} 組・{n} 件の value を伏せた")
            else:
                print(f"{p.name}: 変更無し（既に伏せてある、または対象ポートが0件）")
        else:
            sys.stdout.write(new_text)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
