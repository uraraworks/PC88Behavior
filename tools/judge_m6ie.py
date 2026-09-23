#!/usr/bin/env python3
"""m6i-e の4腕各2走を、事前登録済み判定へ写像する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ARMS = ("E0", "E1", "E2", "E3")
ARM_RESULTS = {
    "E0": ("e0_reproduced", "e0_not_reproduced"),
    "E1": ("e1_reproduced", "e1_not_reproduced"),
    "E2": ("e2_success", "e2_failure"),
    "E3": ("e3_success", "e3_failure"),
}
OVERALL = (
    "m6i_e_single_read_is_the_cause", "m6i_e_layout_is_the_cause",
    "m6i_e_any_insertion_breaks", "m6i_e_single_read_insufficient",
    "m6i_e_inconclusive",
)
REGISTERED = ("success", "failure", "gate_failed", "unreached",
              *(name for pair in ARM_RESULTS.values() for name in pair), *OVERALL)


class InputError(Exception):
    pass


def parse_gates(entries: list[str]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for entry in entries:
        name, sep, value = entry.partition("=")
        if sep != "=" or name not in {f"G{i}" for i in range(1, 10)} \
                or name in result or value not in ("true", "false"):
            raise InputError
        result[name] = value == "true"
    if set(result) != {f"G{i}" for i in range(1, 10)}:
        raise InputError
    return result


def validate_run(arm: str, row: dict[str, object]) -> str:
    if row.get("arm") != arm or row.get("fault_injection") is not None:
        raise InputError
    if type(row.get("reached")) is not bool:
        raise InputError
    if not row["reached"]:
        return "unreached"
    result = row.get("result")
    if result not in ("success", "failure"):
        raise InputError
    digest = row.get("rom_set_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise InputError
    try:
        int(digest, 16)
    except ValueError as exc:
        raise InputError from exc
    wanted_success = arm != "E0"
    reproduced = (result == "success") == wanted_success
    return ARM_RESULTS[arm][0 if reproduced else 1]


def judge(values: dict[str, list[dict[str, object]]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    arm_results: dict[str, str] = {}
    for arm in ARMS:
        rows = values.get(arm, [])
        if len(rows) != 2:
            raise InputError
        pair = [validate_run(arm, row) for row in rows]
        value = pair[0] if pair[0] == pair[1] else "unreached"
        if value != "unreached" and rows[0].get("rom_set_sha256") != rows[1].get("rom_set_sha256"):
            raise InputError
        arm_results[arm] = value
        counts[value] += 1
    if (any(value == "unreached" for value in arm_results.values())
            or arm_results["E0"] != "e0_reproduced"
            or arm_results["E1"] != "e1_reproduced"):
        counts["m6i_e_inconclusive"] = 1
    else:
        e2_ok = arm_results["E2"] == "e2_success"
        e3_ok = arm_results["E3"] == "e3_success"
        counts[{
            (False, True): "m6i_e_single_read_is_the_cause",
            (True, False): "m6i_e_layout_is_the_cause",
            (False, False): "m6i_e_any_insertion_breaks",
            (True, True): "m6i_e_single_read_insufficient",
        }[(e2_ok, e3_ok)]] = 1
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
    args = ap.parse_args()
    hasher = hashlib.sha256()
    grouped: dict[str, list[dict[str, object]]] = {}
    try:
        gates = parse_gates(args.gate)
        for name in sorted(gates):
            hasher.update(f"{name}={str(gates[name]).lower()}\n".encode("ascii"))
        if not all(gates.values()):
            emit(Counter({"gate_failed": 1}), hasher.hexdigest())
            return 1
        if len(args.result) != len(ARMS) * 2:
            raise InputError
        for index, path in enumerate(args.result):
            raw = path.read_bytes()
            hasher.update(index.to_bytes(4, "big") + len(raw).to_bytes(8, "big") + raw)
            row = json.loads(raw)
            if not isinstance(row, dict) or row.get("arm") not in ARMS:
                raise InputError
            grouped.setdefault(str(row["arm"]), []).append(row)
        emit(judge(grouped), hasher.hexdigest())
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, OverflowError):
        emit(Counter({"gate_failed": 1}), hasher.hexdigest())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
