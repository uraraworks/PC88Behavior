#!/usr/bin/env python3
"""m6i-iの5腕各2走を腕別・故障別・総合判定へ写像する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ARMS = ("I-S", "I-F-H", "I-F-D", "I-F-R", "I-F-RETRY")
FAULT_ROWS = {
    "I-F-H": (2, 5, 7, 9, 10),
    "I-F-D": (8, 9, 10),
    "I-F-R": tuple(range(1, 12)),
}
ROW_RESULTS = ("row_match", "row_mismatch", "row_no_data")
REGISTERED = (
    "gate_failed", "unreached", *ROW_RESULTS, "sweep_all_match", "sweep_mismatch",
    "fault_detected", "fault_missed", "fault_not_exercised",
    "m6i_i_general_read_verified", "m6i_i_general_read_wrong",
    "m6i_i_measurement_blind", "m6i_i_inconclusive",
)


class InputError(ValueError):
    pass


def parse_gates(entries: list[str]) -> dict[str, bool]:
    gates: dict[str, bool] = {}
    for entry in entries:
        name, sep, value = entry.partition("=")
        if sep != "=" or name not in {f"G{i}" for i in range(1, 11)} \
                or name in gates or value not in ("true", "false"):
            raise InputError
        gates[name] = value == "true"
    if set(gates) != {f"G{i}" for i in range(1, 11)}:
        raise InputError
    return gates


def validate_run(arm: str, run: dict[str, object]) -> list[dict[str, object]] | None:
    if run.get("arm") != arm or type(run.get("reached")) is not bool:
        raise InputError
    if not run["reached"]:
        return None
    rows = run.get("rows")
    if not isinstance(rows, list) or len(rows) != 11:
        raise InputError
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or row.get("row") != number \
                or row.get("result") not in ROW_RESULTS \
                or type(row.get("entry_count")) is not int or row["entry_count"] < 1:
            raise InputError
    return rows


def classify_arm(arm: str, rows: list[dict[str, object]]) -> str:
    if arm == "I-S":
        return ("sweep_all_match" if all(row["result"] == "row_match" for row in rows)
                else "sweep_mismatch")
    if arm == "I-F-RETRY":
        exercised = [rows[number - 1] for number in (8, 9, 10)
                     if rows[number - 1]["entry_count"] >= 2]
        if not exercised:
            return "fault_not_exercised"
        return ("fault_missed" if any(row["result"] == "row_match" for row in exercised)
                else "fault_detected")
    targets = [rows[number - 1] for number in FAULT_ROWS[arm]]
    return ("fault_missed" if any(row["result"] == "row_match" for row in targets)
            else "fault_detected")


def _signature(rows: list[dict[str, object]]) -> tuple[object, ...]:
    return tuple((row["result"], tuple(row.get("actual_coordinate", ()))) for row in rows)


def judge(values: dict[str, list[dict[str, object]]]) -> tuple[Counter[str], dict[str, str]]:
    counts: Counter[str] = Counter()
    arm_results: dict[str, str] = {}
    for arm in ARMS:
        runs = values.get(arm, [])
        if len(runs) != 2:
            raise InputError
        parsed = [validate_run(arm, run) for run in runs]
        for rows in parsed:
            if rows is not None:
                counts.update(str(row["result"]) for row in rows)
        if parsed[0] is None or parsed[1] is None:
            result = "unreached"
        else:
            first = classify_arm(arm, parsed[0])
            second = classify_arm(arm, parsed[1])
            result = first if first == second and _signature(parsed[0]) == _signature(parsed[1]) \
                else "unreached"
        arm_results[arm] = result
        counts[result] += 1
    if any(value == "unreached" for value in arm_results.values()):
        overall = "m6i_i_inconclusive"
    elif arm_results["I-S"] == "sweep_mismatch":
        overall = "m6i_i_general_read_wrong"
    elif any(arm_results[arm] == "fault_missed" for arm in ("I-F-H", "I-F-D", "I-F-R")):
        overall = "m6i_i_measurement_blind"
    else:
        overall = "m6i_i_general_read_verified"
    counts[overall] += 1
    return counts, arm_results


def emit(counts: Counter[str], arms: dict[str, str], digest: str) -> None:
    judgments = [{"judgment": name, "count": counts[name], "present": counts[name] > 0}
                 for name in REGISTERED]
    print(json.dumps({"arm_results": arms, "judgments": judgments, "sha256": digest},
                     sort_keys=True, separators=(",", ":")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", action="append", default=[])
    ap.add_argument("--result", action="append", default=[], type=Path)
    args = ap.parse_args()
    digest = hashlib.sha256()
    try:
        gates = parse_gates(args.gate)
        for name in sorted(gates):
            digest.update(f"{name}={str(gates[name]).lower()}\n".encode("ascii"))
        if not all(gates.values()):
            emit(Counter({"gate_failed": 1}), {}, digest.hexdigest())
            return 1
        if len(args.result) != len(ARMS) * 2:
            raise InputError
        grouped: dict[str, list[dict[str, object]]] = {}
        for index, path in enumerate(args.result):
            raw = path.read_bytes()
            digest.update(index.to_bytes(4, "big") + raw)
            row = json.loads(raw)
            if not isinstance(row, dict) or row.get("arm") not in ARMS:
                raise InputError
            grouped.setdefault(str(row["arm"]), []).append(row)
        counts, arms = judge(grouped)
        emit(counts, arms, digest.hexdigest())
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, OverflowError):
        emit(Counter({"gate_failed": 1}), {}, digest.hexdigest())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
