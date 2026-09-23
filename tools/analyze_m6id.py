#!/usr/bin/env python3
"""m6i-d の実ログを、ゲート観測の件数・真偽・SHAだけへ縮約する。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_main_to_sub as m2s  # noqa: E402
import build_m6ib_measure_rom as m6ib  # noqa: E402
sys.path.insert(0, str(HERE.parent / "src" / "l3_service"))
import make_subrom as subrom  # noqa: E402

ARMS = ("D-B0", "D-B1", "D-B2", "D-B3", "D-B4", "D-B5", "D-B6-A0")
GATE_LABELS = {
    "D-B0": None,
    "D-B1": "M6IB_B1_RESET_GATE",
    "D-B2": "M6IB_B2_BEFORE_FDC_GATE",
    "D-B3": "M6IB_B3_AFTER_INIT_GATE",
    "D-B4": "M6IB_B4_BEFORE_ROUND0_GATE",
    "D-B5": "M6IB_B5_AFTER_ROUND0_GATE",
    "D-B6-A0": None,
}
ALL_GATE_LABELS = {label for label in GATE_LABELS.values() if label is not None}


def frozen_gate_labels(path: Path) -> dict[str, str | None]:
    values: dict[str, str | None] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        fields = raw.split("\t")
        if len(fields) != 2 or fields[0] != "gate_label":
            continue
        arm, sep, label = fields[1].partition("=")
        if sep != "=" or arm not in ARMS or arm in values or not label:
            raise ValueError("frozen gate labels")
        values[arm] = None if label == "-" else label
    if tuple(values) != ARMS or values != GATE_LABELS:
        raise ValueError("frozen gate labels")
    return values


def gate_address_for_arm(arm: str, config: Path) -> int | None:
    """自作sub ROMのラベル表から腕固有のゲート番地を得る。"""
    expected = frozen_gate_labels(config)[arm]
    kwargs: dict[str, bool] = {}
    if expected is not None:
        kwargs[f"inject_m6ib_{arm[2:].lower()}"] = True
    metadata: dict[str, object] = {}
    subrom.build(metadata=metadata, **kwargs)
    labels = metadata.get("labels")
    if not isinstance(labels, dict):
        raise ValueError("sub ROM labels")
    present = ALL_GATE_LABELS.intersection(labels)
    expected_set = set() if expected is None else {expected}
    if present != expected_set:
        raise ValueError("sub ROM gate label mismatch")
    if expected is None:
        return None
    address = labels.get(expected)
    if type(address) is not int or not 0 <= address <= 0xFFFF:
        raise ValueError("sub ROM gate address")
    return address


def gate_observation(rows: list[m2s.Ev], gate_address: int | None) \
        -> tuple[bool, bool, int, int]:
    """ゲートPCのI/O件数と、最後のゲートI/O後に進んだ件数を返す。"""
    if gate_address is None:
        return False, False, 0, 0
    gate_pc = f"{gate_address:04X}"
    gate_indexes = [index for index, row in enumerate(rows)
                    if row.cpu == "sub" and row.pc == gate_pc]
    if not gate_indexes:
        return False, False, 0, 0
    post_count = sum(
        row.cpu == "sub" and row.pc != gate_pc
        for row in rows[gate_indexes[-1] + 1:]
    )
    return True, post_count > 0, len(gate_indexes), post_count


def summarize(arm: str, rows: list[m2s.Ev], masked_count: int,
              rom_dir: Path, expected_rom_sha256: str,
              gate_address: int | None) -> dict[str, object]:
    entered, released, gate_count, post_count = gate_observation(
        rows, gate_address)
    digest = m6ib.rom_set_sha256(rom_dir)
    return {
        "arm": arm,
        "reached": masked_count == 0
        and any(row.cpu == "sub" for row in rows)
        and digest == expected_rom_sha256,
        "gate_entered": entered,
        "gate_released": released,
        "gate_io_count": gate_count,
        "post_gate_io_count": post_count,
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
        "gate_io_count": 0, "post_gate_io_count": 0,
        "rom_set_sha256": "",
    }
    try:
        rows, masked = m2s.parse_iolog(args.iolog)
        gate_address = gate_address_for_arm(args.arm, args.config)
        if len(args.expected_rom_set_sha256) != 64:
            raise ValueError("expected ROM SHA-256")
        int(args.expected_rom_set_sha256, 16)
        base = summarize(args.arm, rows, sum(masked.values()), args.rom_dir,
                         args.expected_rom_set_sha256, gate_address)
        print(json.dumps(base, sort_keys=True, separators=(",", ":")))
        return 0 if base["reached"] else 1
    except (OSError, UnicodeError, ValueError):
        print(json.dumps(base, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
