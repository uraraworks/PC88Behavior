#!/usr/bin/env python3
"""m6i-d の7腕各2走を、事前登録済みの判定名へ写像する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ARMS = ("D-B0", "D-B1", "D-B2", "D-B3", "D-B4", "D-B5", "D-B6-A0")
AUDIT_ARMS = ("D-B1", "D-B2", "D-B3", "D-B4", "D-B5")
CONTROL_ARMS = ("D-B0", "D-B6-A0")
ARM_RESULTS = ("arm_gate_released", "arm_gate_never_released",
               "arm_gate_not_entered")
CONTROL_RESULTS = ("control_no_gate_run", "control_gate_run_observed")
OVERALL = (
    "m6i_d_observation_unusable", "m6i_d_inconclusive",
    "m6i_d_only_b5_unverified", "m6i_d_b1_control_void",
    "m6i_d_multiple_arms_unverified", "m6i_d_no_arm_unverified",
)
SURVIVAL = ("m6i_b_b2_b4_survive", "m6i_b_b2_b4_do_not_survive")
REGISTERED = ("gate_failed", "unreached", *ARM_RESULTS, *CONTROL_RESULTS,
              *OVERALL, *SURVIVAL)
GATES = ("G1", "G2", "G3", "G4", "G5", "G7", "G8")


class InputError(Exception):
    pass


def _bool(value: object) -> bool:
    if type(value) is not bool:
        raise InputError
    return value


def _count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise InputError
    return value


def parse_gates(entries: list[str]) -> dict[str, bool]:
    gates: dict[str, bool] = {}
    for entry in entries:
        name, sep, raw = entry.partition("=")
        if sep != "=" or name not in GATES or name in gates \
                or raw not in ("true", "false"):
            raise InputError
        gates[name] = raw == "true"
    if tuple(sorted(gates)) != tuple(sorted(GATES)):
        raise InputError
    return gates


def validate_run(arm: str, row: dict[str, object]) -> tuple[str, str]:
    if row.get("arm") != arm:
        raise InputError
    digest = row.get("rom_set_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise InputError
    try:
        int(digest, 16)
    except ValueError as exc:
        raise InputError from exc
    if not _bool(row.get("reached")):
        return "unreached", digest
    entered = _bool(row.get("gate_entered"))
    released = _bool(row.get("gate_released"))
    gate_count = _count(row.get("gate_io_count"))
    post_count = _count(row.get("post_gate_io_count"))
    if entered != (gate_count > 0) or released != (post_count > 0):
        raise InputError
    if post_count > 0 and gate_count == 0:
        raise InputError
    if arm in CONTROL_ARMS:
        return ("control_gate_run_observed" if entered else "control_no_gate_run",
                digest)
    if not entered:
        return "arm_gate_not_entered", digest
    return ("arm_gate_released" if released else "arm_gate_never_released",
            digest)


def judge(values: dict[str, list[dict[str, object]]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    per_arm: dict[str, str] = {}
    for arm in ARMS:
        runs = values.get(arm, [])
        if len(runs) != 2:
            raise InputError
        pair = [validate_run(arm, row) for row in runs]
        judgment = pair[0][0] if pair[0] == pair[1] else "unreached"
        per_arm[arm] = judgment
        counts[judgment] += 1

    if any(per_arm[arm] == "control_gate_run_observed" for arm in CONTROL_ARMS):
        counts["m6i_d_observation_unusable"] = 1
    elif any(value == "unreached" for value in per_arm.values()):
        counts["m6i_d_inconclusive"] = 1
    else:
        unverified = {arm for arm in AUDIT_ARMS
                      if per_arm[arm] != "arm_gate_released"}
        if unverified == {"D-B5"}:
            counts["m6i_d_only_b5_unverified"] = 1
        if "D-B1" in unverified:
            counts["m6i_d_b1_control_void"] = 1
        if len(unverified) >= 2:
            counts["m6i_d_multiple_arms_unverified"] = 1
        if not unverified:
            counts["m6i_d_no_arm_unverified"] = 1

    # 副問は総合判定と独立。ただし陰性対照が崩れた観測には帰属しない。
    controls_usable = all(per_arm[arm] == "control_no_gate_run"
                          for arm in CONTROL_ARMS)
    b2_b4 = (per_arm["D-B2"], per_arm["D-B4"])
    if controls_usable and b2_b4 == ("arm_gate_released", "arm_gate_released"):
        counts["m6i_b_b2_b4_survive"] = 1
    elif controls_usable and any(value != "arm_gate_released"
                                 for value in b2_b4):
        counts["m6i_b_b2_b4_do_not_survive"] = 1
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
            hasher.update(index.to_bytes(4, "big"))
            hasher.update(len(raw).to_bytes(8, "big"))
            hasher.update(raw)
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
