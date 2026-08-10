#!/usr/bin/env python3
"""tools/hash_io_stream.py — iolog の特定ポート/方向の値列を、値そのものではなく
「件数」と「SHA-256」だけに要約する。

docs/PLAN.md「次にやること（M6の続き）」1項の**適合テスト層**のために作った。
自己検証層（`tools/verify_l3.sh`）は公式ROM無しで回せるが、diskA 起動時の
バースト転送（5635件、`docs/spec/l3-subrom.md` 5.2節条件1）の値そのものは
公式ディスクの実データであり、リポジトリに持てば禁止事項4（ROM由来のバイト列を
コミットしない）に触れる。ハッシュだけなら値を復元できないので、
`tests/conformance/` に期待値として置ける。

抽出ロジックは `tools/cmp_io.py` の `parse_iolog` / `filter_port_kind` を
そのまま import して使う（コピペで二重実装しない。`cmp_io.py --cpu main
--port FD --kind IN` と完全に同じ抽出結果になる）。

**このスクリプトは値そのものを一度も標準出力に出さない。** 出すのは
件数とハッシュだけ。

使い方:
    tools/hash_io_stream.py <iolog> --cpu main --port FD --kind IN
    tools/hash_io_stream.py <iolog> --cpu main --port FD --kind IN --name m6g-d0-boot

--name を指定すると、tests/conformance/ の期待値ファイル1行分の書式
（name<TAB>cpu<TAB>port<TAB>kind<TAB>count<TAB>sha256）でそのまま出す。

終了コード: 正常 0 / iolog の書式エラー・抽出0件 2
"""

import argparse
import hashlib
import sys
from pathlib import Path

# cmp_io.py と同じディレクトリにあるので、そこから抽出ロジックを import する。
# 二重実装を避けるための唯一の依存。cmp_io.py 側の既存 CLI 挙動は変えない。
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmp_io  # noqa: E402


def extract_values(path: str, cpu: str, port: str, kind: str) -> list[str]:
    """cmp_io.py --cpu <cpu> --port <port> --kind <kind> と同一の抽出結果を返す。

    返り値は値(value)の列のみ（port/kind は絞り込み条件として既に固定されている）。
    """
    events = cmp_io.parse_iolog(path, cpu)
    filtered = cmp_io.filter_port_kind(events, kind, port)
    return [e.value for e in filtered]


def hash_values(values: list[str]) -> str:
    """値の列から SHA-256 を計算する。

    区切りを明示するため、各値の後ろに改行を1つ挟んで結合する
    （"AB" + "CD" と "A" + "BCD" のような桁ずれ衝突を避ける）。
    """
    h = hashlib.sha256()
    for v in values:
        h.update(v.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="iolog の特定ポート/方向の値列を件数+SHA-256だけに要約する"
                     "（値そのものは出力しない）"
    )
    parser.add_argument("iolog", help="対象の .iolog.txt")
    parser.add_argument("--cpu", choices=["main", "sub"], default="main",
                        help="対象CPU（既定: main）")
    parser.add_argument("--port", required=True, metavar="PORT",
                        help="対象ポート（例 FD, 00FD）")
    parser.add_argument("--kind", choices=["IN", "OUT"], required=True,
                        help="対象方向")
    parser.add_argument("--name", default=None, metavar="NAME",
                        help="指定すると tests/conformance/ の期待値1行"
                             "（name<TAB>cpu<TAB>port<TAB>kind<TAB>count<TAB>sha256）"
                             "の書式で出力する")
    args = parser.parse_args()

    try:
        values = extract_values(args.iolog, args.cpu, args.port, args.kind)
    except cmp_io.FormatError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"エラー: ファイルを読めない: {e}", file=sys.stderr)
        return 2

    if not values:
        print(f"エラー: {args.cpu}/{args.kind}/{args.port} に該当するイベントが0件"
              "（抽出失敗が黙って通らないよう、0件はエラーにする）", file=sys.stderr)
        return 2

    count = len(values)
    digest = hash_values(values)

    if args.name:
        port_norm = cmp_io.normalize_port(args.port)
        print(f"{args.name}\t{args.cpu}\t{port_norm}\t{args.kind}\t{count}\t{digest}")
    else:
        print(f"count\t{count}")
        print(f"sha256\t{digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
