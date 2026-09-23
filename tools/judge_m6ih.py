#!/usr/bin/env python3
"""m6i-hの4腕各2走を、固定済みの総合判定3種・副問2種へ写像する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ARMS = ("H-N", "H-W", "H-A", "H-B")
ARM_RESULTS = {
    "H-N": ("h_n_reproduced", "h_n_not_reproduced"),
    "H-W": ("h_w_reproduced", "h_w_not_reproduced"),
    "H-A": ("h_a_success", "h_a_failure"),
    "H-B": ("h_b_success", "h_b_failure"),
}
OVERALL = ("m6i_h_no_wait_sufficient", "m6i_h_wait_required", "m6i_h_inconclusive")
SECONDARY = ("m6i_h_retry_without_send_sufficient",
             "m6i_h_retry_without_send_insufficient")
REGISTERED = ("success", "failure", "gate_failed", "unreached",
              *(name for pair in ARM_RESULTS.values() for name in pair), *OVERALL, *SECONDARY)


class InputError(Exception):
    pass


def parse_gates(entries: list[str]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for entry in entries:
        name, sep, value = entry.partition("=")
        if sep != "=" or name not in {f"G{i}" for i in range(1, 11)} \
                or name in result or value not in ("true", "false"):
            raise InputError
        result[name] = value == "true"
    if set(result) != {f"G{i}" for i in range(1, 11)}:
        raise InputError
    return result


def validate_run(arm: str, row: dict[str, object]) -> str:
    if row.get("arm") != arm or row.get("fault_injection") is not None \
            or type(row.get("reached")) is not bool:
        raise InputError
    if not row["reached"]:
        return "unreached"
    result = row.get("result")
    if result not in ("success", "failure"):
        raise InputError
    digest = row.get("rom_set_sha256")
    try:
        if not isinstance(digest, str) or len(digest) != 64:
            raise InputError
        int(digest, 16)
    except ValueError as exc:
        raise InputError from exc
    wanted_success = arm != "H-N"
    return ARM_RESULTS[arm][0 if (result == "success") == wanted_success else 1]


def judge(values: dict[str, list[dict[str, object]]]) -> Counter[str]:
    counts: Counter[str] = Counter(); arm_results: dict[str, str] = {}
    for arm in ARMS:
        rows = values.get(arm, [])
        if len(rows) != 2:
            raise InputError
        pair = [validate_run(arm, row) for row in rows]
        value = pair[0] if pair[0] == pair[1] else "unreached"
        if value != "unreached" and rows[0].get("rom_set_sha256") != rows[1].get("rom_set_sha256"):
            raise InputError
        arm_results[arm] = value; counts[value] += 1
    controls_ok = (arm_results["H-N"] == "h_n_reproduced"
                   and arm_results["H-W"] == "h_w_reproduced")
    if any(value == "unreached" for value in arm_results.values()) or not controls_ok:
        counts["m6i_h_inconclusive"] = 1
    elif arm_results["H-A"] == "h_a_success":
        counts["m6i_h_no_wait_sufficient"] = 1
    else:
        counts["m6i_h_wait_required"] = 1
    if arm_results["H-B"] == "h_b_success":
        counts["m6i_h_retry_without_send_sufficient"] = 1
    elif arm_results["H-B"] == "h_b_failure":
        counts["m6i_h_retry_without_send_insufficient"] = 1
    return counts


def emit(counts: Counter[str], digest: str) -> None:
    rows = [{"judgment": name, "count": counts[name], "present": counts[name] > 0}
            for name in REGISTERED]
    print(json.dumps({"judgments": rows, "sha256": digest},
                     sort_keys=True, separators=(",", ":")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", action="append", default=[])
    ap.add_argument("--result", action="append", default=[], type=Path)
    args = ap.parse_args(); hasher = hashlib.sha256(); grouped = {}
    try:
        gates = parse_gates(args.gate)
        for name in sorted(gates):
            hasher.update(f"{name}={str(gates[name]).lower()}\n".encode("ascii"))
        if not all(gates.values()):
            emit(Counter({"gate_failed": 1}), hasher.hexdigest()); return 1
        if len(args.result) != len(ARMS) * 2:
            raise InputError
        for index, path in enumerate(args.result):
            raw = path.read_bytes(); hasher.update(index.to_bytes(4, "big") + raw)
            row = json.loads(raw)
            if not isinstance(row, dict) or row.get("arm") not in ARMS:
                raise InputError
            grouped.setdefault(str(row["arm"]), []).append(row)
        emit(judge(grouped), hasher.hexdigest()); return 0
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, OverflowError):
        emit(Counter({"gate_failed": 1}), hasher.hexdigest()); return 2


if __name__ == "__main__":
    raise SystemExit(main())
