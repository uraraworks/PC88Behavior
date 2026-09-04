#!/usr/bin/env python3
"""tools/count_fdc_commands_after_frame.py — 単一iologのFDCコマンド種別を
値を出さずに件数だけ数える（打鍵後の窓を --after-frame で切る）。

`tools/compare_l3_entry_fdc.py` が公式・混成の2本を比較するのに対し、
本スクリプトは**1本**を対象にする点だけが違う。パース処理そのものは
`tools/analyze_write_path.py`（parse_commands）と
`tools/analyze_main_to_sub.py`（parse_iolog）をそのまま呼ぶ
（二重実装しない。CLAUDE.md「繰り返しパターンの一括処理」と同じ理由）。

出力するのは件数だけ（コマンド総数、READ DATA件数、WRITE DATA件数）。
FDCパラメータ・結果・データ値・シリンダ番号・PCNは一切出さない。
終了コードは、解析できれば0、伏せ字ログ等で解析不能なら2。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_write_path as awp  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--after-frame", type=int,
                     help="このframe以降だけを数える（省略時は全区間）")
    args = ap.parse_args()

    try:
        rows, masked = m2s.parse_iolog(args.iolog)
        if sum(masked.values()):
            raise awp.SafeError("伏せ字ログではFDCコマンド語を判定できない")
        cmds = awp.parse_commands(rows)
    except (ValueError, OSError, awp.SafeError) as ex:
        print(f"解析不能: {ex}", file=sys.stderr)
        return 2

    if args.after_frame is not None:
        cmds = [c for c in cmds if c.frame >= args.after_frame]

    names = [awp.NAMES[c.opcode] for c in cmds]
    print(f"command_count={len(names)}")
    print(f"read_data_count={names.count('READ DATA')}")
    print(f"write_data_count={names.count('WRITE DATA')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
