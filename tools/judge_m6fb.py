#!/usr/bin/env python3
"""m6f-b の G1〜G8/G5b、到達、固定済み E1〜E8 から判定を出す。"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from derive_m6fb import ARMS, CASE_JUDGMENTS, DERIVATIONS, STATUSES

GATES = tuple([f"G{i}" for i in range(1, 9)] + ["G5b"])
OVERALL = (
    "m6f_b_entry_fields_derived", "m6f_b_entry_fields_incomplete",
    "m6f_b_inconclusive",
)
REGISTERED = (
    "gate_failed", "unreached", *STATUSES, *CASE_JUDGMENTS, *OVERALL,
)


class InputError(ValueError):
    pass


def parse_gates(entries: list[str]) -> dict[str, bool]:
    gates: dict[str, bool] = {}
    for entry in entries:
        name, sep, value = entry.partition("=")
        if not sep or name not in GATES or name in gates or value not in ("true", "false"):
            raise InputError("関門指定")
        gates[name] = value == "true"
    if set(gates) != set(GATES):
        raise InputError("関門の不足")
    return gates


def validate_measurement(doc: object) -> bool:
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        raise InputError("測定結果の形式")
    rows = doc["runs"]
    if len(rows) != 18:
        raise InputError("測定走数")
    seen = set()
    reached = True
    for row in rows:
        if not isinstance(row, dict) or row.get("arm") not in ARMS \
                or row.get("repetition") not in (1, 2) \
                or type(row.get("reached")) is not bool:
            raise InputError("測定走の形式")
        key = (row["arm"], row["repetition"])
        if key in seen:
            raise InputError("測定走の重複")
        seen.add(key)
        reached = reached and row["reached"]
    if seen != {(arm, run) for arm in ARMS for run in (1, 2)}:
        raise InputError("測定走の不足")
    return reached


def validate_derivations(doc: object) -> dict[str, dict[str, Any]]:
    if not isinstance(doc, dict) or not isinstance(doc.get("derivations"), dict):
        raise InputError("導出結果の形式")
    values = doc["derivations"]
    if set(values) != set(DERIVATIONS):
        raise InputError("導出名の不足または余分")
    for name, item in values.items():
        if not isinstance(item, dict) or type(item.get("candidate_count")) is not int \
                or item["candidate_count"] < 0:
            raise InputError("導出項目の形式")
        allowed = CASE_JUDGMENTS + ("ambiguous",) if name == "E1" else STATUSES
        if item.get("status") not in allowed:
            raise InputError("導出分類")
        if item["status"] in ("derived",) + CASE_JUDGMENTS and "value" not in item:
            raise InputError("導出値の不足")
        if "reason" in item and (item["status"] != "not_found"
                                 or item["reason"] != "old_values_withheld"):
            raise InputError("not_found理由の形式")
    return values


def judge(derived: dict[str, Any], measurement: dict[str, Any]) -> tuple[Counter[str], dict[str, Any]]:
    values = validate_derivations(derived)
    counts: Counter[str] = Counter()
    for name in DERIVATIONS:
        counts[values[name]["status"]] += 1
    if not validate_measurement(measurement):
        overall = "m6f_b_inconclusive"
        counts["unreached"] += 1
    elif values["E1"]["status"] in CASE_JUDGMENTS[:-1] \
            and all(values[name]["status"] == "derived" for name in ("E2", "E3", "E4", "E5")):
        overall = "m6f_b_entry_fields_derived"
    else:
        overall = "m6f_b_entry_fields_incomplete"
    counts[overall] += 1
    return counts, values


def emit(counts: Counter[str], derivations: dict[str, Any], digest: str) -> None:
    judgments = [{"judgment": name, "count": counts[name], "present": counts[name] > 0}
                 for name in REGISTERED]
    print(json.dumps({"derivations": derivations, "judgments": judgments,
                      "sha256": digest}, sort_keys=True, separators=(",", ":")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", action="append", default=[])
    ap.add_argument("--derived", required=True, type=Path)
    ap.add_argument("--measurement", required=True, type=Path)
    args = ap.parse_args()
    digest = hashlib.sha256()
    try:
        gates = parse_gates(args.gate)
        for name in sorted(gates):
            digest.update(f"{name}={str(gates[name]).lower()}\n".encode("ascii"))
        if not all(gates.values()):
            emit(Counter({"gate_failed": 1}), {}, digest.hexdigest())
            return 1
        draw, mraw = args.derived.read_bytes(), args.measurement.read_bytes()
        digest.update(draw)
        digest.update(mraw)
        counts, derivations = judge(json.loads(draw), json.loads(mraw))
        emit(counts, derivations, digest.hexdigest())
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, ValueError):
        emit(Counter({"gate_failed": 1}), {}, digest.hexdigest())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
