#!/usr/bin/env python3
"""m6i-k 事前登録・凍結表・実装定数を照合する G8。"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO))
import analyze_m6ik as analyzer  # noqa: E402
import judge_m6ik as judge  # noqa: E402
import src.build_main_rom as builder  # noqa: E402

EXPECTED = {
    "frozen": ["yes"], "repetitions": ["2"], "measurement_frames": ["2010"],
    "disk_a_sha256": ["060613aec5092ce8b750b8233cec3ef88011efa6626f7e9fa6bce7a428ea5bb6"],
    "disk_b_sha256": ["0006dd541d4743592d9534824c03c81b23ebfe9486a9cf89202f4783dbfcfdd3"],
    "plain_subrom_sha256": ["d8b2e64bc27465f955fd308719228f21b06aa07fd780081a88124a52e6d76070"],
    "arm": ["K-00:none:0x00", "K-01:none:0x01", "K-F0:0x17,0x0F:0x00",
            "K-F1:0x17,0x0F:0x01", "K-M1:0x17,0x01:0x01",
            "K-FR:0x17,0x0F:0x01:R+1"],
    "row": ["1:1:0:1", "2:1:37:13", "3:2:37:13", "4:2:1:1",
            "5:1:1:1", "6:2:0:1"],
    "classification": ["agree", "logical", "cylinder", "other", "no_read"],
    "arm_result": ["logical", "cylinder", "split_by_drive", "mixed",
                   "control_failed", "unreached"],
    "judgment": list(judge.JUDGMENTS),
}


def parse(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("\t")
        if not sep or not value:
            raise ValueError("TSV")
        result.setdefault(key, []).append(value)
    return result


def check(config: Path, prereg: Path) -> None:
    if parse(config) != EXPECTED:
        raise ValueError("凍結表")
    text = prereg.read_text()
    for token in [*(f"| {arm} |" for arm in analyzer.ARMS),
                  *(f"| {n} | {d + 1} | {t} | {r} |" for n, d, t, r in analyzer.ROWS),
                  *(f"`{name}`" for name in judge.JUDGMENTS)]:
        if token not in text:
            raise ValueError("事前登録")
    if tuple(builder.M6IK_ARMS) != analyzer.ARMS or \
            tuple((i, *row) for i, row in enumerate(builder.M6IK_ROWS, 1)) != analyzer.ROWS:
        raise ValueError("ROM座標または腕")
    if (analyzer.MARKER, analyzer.PRE_MARKER) != (0xE039, 0xE03A):
        raise ValueError("RAM刻印")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=HERE / "m6ik_frozen.tsv")
    ap.add_argument("--prereg", type=Path, default=REPO / "docs/notes/m6i-k-read-request-geometry-preregistration.md")
    args = ap.parse_args()
    try:
        check(args.config, args.prereg)
    except (OSError, ValueError) as exc:
        print(f"gate_failed: {exc}", file=sys.stderr)
        return 1
    print("m6i-k preregistration gate: OK sha256=" + hashlib.sha256(args.config.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
