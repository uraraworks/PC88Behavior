#!/usr/bin/env python3
"""自作main要求byte2のドライブ指定がREAD単位の公開FDC unitへ届くか検査する。"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_main_to_sub as m2s  # noqa: E402
import analyze_write_path as awp  # noqa: E402


READ_UNIT = (0x0F, 0x08, 0x04, 0x06)
UNIT_COMMAND_INDEXES = (0, 2, 3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("iolog", type=Path)
    ap.add_argument("--expected-unit", type=int, choices=(0, 1), required=True)
    args = ap.parse_args()

    rows, masked = m2s.parse_iolog(args.iolog)
    if sum(masked.values()):
        raise SystemExit("伏せ字ログではFDC unitを判定できない")
    commands = awp.parse_commands(rows)
    groups = [
        commands[i:i + 4]
        for i in range(len(commands) - 3)
        if tuple(c.opcode for c in commands[i:i + 4]) == READ_UNIT
    ]
    if not groups:
        print("NG: SEEK/SENSE INTERRUPT/SENSE DRIVE STATUS/READ DATA単位が無い")
        return 1

    bad = 0
    for group in groups:
        for index in UNIT_COMMAND_INDEXES:
            params = group[index].param_values or []
            if not params or (params[0] & 0x03) != args.expected_unit:
                bad += 1
    if bad:
        print(f"NG: READ単位{len(groups)}件中、期待unitと異なる対象が{bad}件")
        return 1
    print(f"OK: READ単位{len(groups)}件のSEEK/SENSE/READがすべてunit{args.expected_unit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
