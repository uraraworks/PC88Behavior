#!/usr/bin/env python3
"""m6i-c の4腕各2走を、事前登録済みの主判定と副問判定へ写像する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ARMS = ("C0", "C1", "C2", "C3")
ARM_RESULTS = {
    "C0": ("c0_reproduced", "c0_not_reproduced"),
    "C1": ("c1_reproduced", "c1_not_reproduced"),
    "C2": ("c2_success", "c2_failure"),
    "C3": ("c3_success", "c3_failure"),
}
OVERALL = (
    "m6i_c_sub_gate_only", "m6i_c_branch_tag_only",
    "m6i_c_interaction_required", "m6i_c_no_single_factor",
    "m6i_c_inconclusive",
)
GATE_RESULTS = (
    "gate_not_entered", "gate_never_released",
    "gate_released_but_request_lost", "gate_released_and_request_ran",
    "gate_observation_unusable",
)
REGISTERED = (
    "success", "failure", "gate_failed", "unreached",
    *(name for pair in ARM_RESULTS.values() for name in pair),
    *OVERALL, *GATE_RESULTS,
)


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
        if sep != "=" or name not in {f"G{i}" for i in range(1, 10)}:
            raise InputError
        if name in gates or raw not in ("true", "false"):
            raise InputError
        gates[name] = raw == "true"
    if set(gates) != {f"G{i}" for i in range(1, 10)}:
        raise InputError
    return gates


def validate_run(arm: str, row: dict[str, object]) -> str:
    if row.get("arm") != arm or row.get("fault_injection") is not None:
        raise InputError
    if not _bool(row.get("reached")):
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
    if arm == "C0":
        return ARM_RESULTS[arm][0 if result == "failure" else 1]
    if arm == "C1":
        return ARM_RESULTS[arm][0 if result == "success" else 1]
    return ARM_RESULTS[arm][0 if result == "success" else 1]


def gate_result(row: dict[str, object]) -> str:
    entered = _bool(row.get("gate_entered"))
    released = _bool(row.get("gate_released"))
    runs = _count(row.get("gate_run_count"))
    maximum = _count(row.get("gate_run_max_length"))
    requests = _count(row.get("request_runs"))
    if entered != (runs > 0) or released and not entered:
        raise InputError
    if (runs == 0 and maximum != 0) or (runs > 0 and maximum == 0):
        raise InputError
    if not entered:
        return "gate_not_entered"
    if not released:
        return "gate_never_released"
    if requests == 0:
        return "gate_released_but_request_lost"
    return "gate_released_and_request_ran"


def judge(values: dict[str, list[dict[str, object]]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    arm_judgments: dict[str, str] = {}
    for arm in ARMS:
        runs = values.get(arm, [])
        if len(runs) != 2:
            raise InputError
        pair = [validate_run(arm, row) for row in runs]
        judgment = pair[0] if pair[0] == pair[1] else "unreached"
        if (judgment != "unreached"
                and runs[0].get("rom_set_sha256") != runs[1].get("rom_set_sha256")):
            raise InputError
        arm_judgments[arm] = judgment
        counts[judgment] += 1

    if (any(value == "unreached" for value in arm_judgments.values())
            or arm_judgments["C0"] != "c0_reproduced"
            or arm_judgments["C1"] != "c1_reproduced"):
        counts["m6i_c_inconclusive"] = 1
    else:
        c2_ok = arm_judgments["C2"] == "c2_success"
        c3_ok = arm_judgments["C3"] == "c3_success"
        overall = {
            (True, False): "m6i_c_sub_gate_only",
            (False, True): "m6i_c_branch_tag_only",
            (False, False): "m6i_c_interaction_required",
            (True, True): "m6i_c_no_single_factor",
        }[(c2_ok, c3_ok)]
        counts[overall] = 1

    # G8-2 は主判定を変えず、副問だけを使用不能にする。
    if any(_count(row.get("gate_run_count")) > 0
           for arm in ("C1", "C2") for row in values[arm]):
        counts["gate_observation_unusable"] = 1
    else:
        for arm in ("C0", "C3"):
            if arm_judgments[arm] == "unreached":
                continue
            pair = [gate_result(row) for row in values[arm]]
            # 副問の2走が不一致なら帰属名を付けない。主問には影響させない。
            if pair[0] == pair[1]:
                counts[pair[0]] += 1
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
