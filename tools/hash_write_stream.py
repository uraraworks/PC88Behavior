#!/usr/bin/env python3
"""tools/hash_write_stream.py — 書き込み経路（仕様書1.35節）の適合判定に使う
「subがFDCへ流した書き込みの中身」を、**値を出さずに**件数とSHA-256で表す。

なぜこの形か: 適合条件は「値そのものを期待値ファイルに置かない」ことを前提に
している（CLAUDE.md禁止事項4、tests/conformance/expected.tsv はハッシュのみ）。
書き込みも同じ形にする——WRITE系コマンドの**パラメータ8バイトとデータ部**を
発生順に連結した列のSHA-256と、コマンド件数・総バイト数だけを出す。

出力例（値は含まない）:
    commands\t8
    bytes\t2112
    sha256\t<64桁>

終了コード: 書き込みが1件も無ければ2（判定不能）、あれば0。
"""
import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s                      # noqa: E402
from analyze_write_path import parse_commands, WRITE_OPCODES  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("iolog", type=Path)
    args = ap.parse_args()

    rows, masked = m2s.parse_iolog(args.iolog)
    if sum(masked.values()):
        print("判定不能: 伏せ字ログでは書き込みの中身を復元できない", file=sys.stderr)
        return 2
    writes = [c for c in parse_commands(rows) if c.opcode in WRITE_OPCODES]
    if not writes:
        print("commands\t0")
        print("bytes\t0")
        return 2

    h = hashlib.sha256()
    total = 0
    for c in writes:
        payload = bytes(c.param_values or []) + bytes(c.data_values or [])
        h.update(payload)
        total += len(payload)
    print(f"commands\t{len(writes)}")
    print(f"bytes\t{total}")
    print(f"sha256\t{h.hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
