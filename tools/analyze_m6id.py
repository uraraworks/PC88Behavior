#!/usr/bin/env python3
"""m6i-d の実ログを、ゲート観測の件数・真偽・SHAだけへ縮約する。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_m6ic as m6ic  # noqa: E402
import analyze_main_to_sub as m2s  # noqa: E402
import build_m6ib_measure_rom as m6ib  # noqa: E402

ARMS = ("D-B0", "D-B1", "D-B2", "D-B3", "D-B4", "D-B5", "D-B6-A0")


def cfg_one(path: Path, key: str) -> str:
    values = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        fields = raw.split("\t")
        if len(fields) == 2 and fields[0] == key:
            values.append(fields[1])
    if len(values) != 1:
        raise ValueError("frozen config")
    return values[0]


def gate_observation(rows: list[m2s.Ev], minimum: int) \
        -> tuple[list[m6ic.GateRun], bool]:
    """走の全区間にある sub IN $FE run と、最後のrunの解除を返す。"""
    runs = m6ic.sub_fe_runs(rows, -1, minimum)
    released = bool(runs) and any(
        row.cpu == "sub" and not (row.kind == "IN" and row.port == "00FE")
        and row.clock > runs[-1].end_clock
        for row in rows
    )
    return runs, released


def summarize(arm: str, rows: list[m2s.Ev], masked_count: int,
              rom_dir: Path, expected_rom_sha256: str,
              minimum: int) -> dict[str, object]:
    runs, released = gate_observation(rows, minimum)
    digest = m6ib.rom_set_sha256(rom_dir)
    return {
        "arm": arm,
        "reached": masked_count == 0
        and any(row.cpu == "sub" for row in rows)
        and m6ib.sizes_valid(rom_dir)
        and digest == expected_rom_sha256,
        "gate_entered": bool(runs),
        "gate_released": released,
        "gate_run_count": len(runs),
        "gate_run_max_length": max((run.length for run in runs), default=0),
        "rom_set_sha256": digest,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--iolog", required=True, type=Path)
    ap.add_argument("--rom-dir", required=True, type=Path)
    ap.add_argument("--expected-rom-set-sha256", required=True)
    ap.add_argument("--config", type=Path, default=HERE / "m6id_frozen.tsv")
    args = ap.parse_args()
    base: dict[str, object] = {
        "arm": args.arm, "reached": False,
        "gate_entered": False, "gate_released": False,
        "gate_run_count": 0, "gate_run_max_length": 0,
        "rom_set_sha256": "",
    }
    try:
        rows, masked = m2s.parse_iolog(args.iolog)
        minimum = int(cfg_one(args.config, "gate_run_min_length"))
        if len(args.expected_rom_set_sha256) != 64:
            raise ValueError("expected ROM SHA-256")
        int(args.expected_rom_set_sha256, 16)
        base = summarize(args.arm, rows, sum(masked.values()), args.rom_dir,
                         args.expected_rom_set_sha256, minimum)
        print(json.dumps(base, sort_keys=True, separators=(",", ":")))
        return 0 if base["reached"] else 1
    except (OSError, UnicodeError, ValueError):
        print(json.dumps(base, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
