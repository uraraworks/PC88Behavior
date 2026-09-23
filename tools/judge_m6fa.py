#!/usr/bin/env python3
"""m6f-aのG1〜G7、到達、2走の導出一致から固定判定を出す。"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ARMS = tuple(f"F{i}" for i in range(7))
DERIVATIONS = tuple(f"D{i}" for i in range(1, 8))
STATUSES = ("derived", "ambiguous", "not_found")
REGISTERED = (
    "gate_failed", "unreached", *STATUSES,
    "m6f_a_directory_located", "m6f_a_directory_ambiguous",
    "m6f_a_inconclusive",
)


class InputError(ValueError):
    pass


def parse_gates(entries: list[str]) -> dict[str, bool]:
    gates: dict[str, bool] = {}
    for entry in entries:
        name, sep, value = entry.partition("=")
        if not sep or name not in {f"G{i}" for i in range(1, 8)} \
                or name in gates or value not in ("true", "false"):
            raise InputError("関門指定")
        gates[name] = value == "true"
    if set(gates) != {f"G{i}" for i in range(1, 8)}:
        raise InputError("関門の不足")
    return gates


def _key(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def consensus(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    for item in (first, second):
        if item.get("status") not in STATUSES or type(item.get("candidate_count")) is not int \
                or item["candidate_count"] < 0:
            raise InputError("導出結果の形式")
        if item["status"] == "derived" and "value" not in item:
            raise InputError("derivedに値が無い")
        if "reason" in item and (item["status"] != "not_found"
                                 or item["reason"] != "old_values_withheld"):
            raise InputError("not_found理由の形式")
    if first["status"] == second["status"] == "derived" \
            and _key(first["value"]) == _key(second["value"]):
        return {"status": "derived", "candidate_count": 1, "value": first["value"]}
    if first["status"] == second["status"] == "not_found":
        if first.get("reason") == second.get("reason"):
            out: dict[str, Any] = {"status": "not_found", "candidate_count": 0}
            if "reason" in first:
                out["reason"] = first["reason"]
            return out
    # 2走の分類・値が一致しない場合も、事前登録どおりambiguousへ倒す。
    count = max(2, int(first["candidate_count"]), int(second["candidate_count"]))
    return {"status": "ambiguous", "candidate_count": count}


def validate_measurement(doc: object) -> bool:
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        raise InputError("測定結果の形式")
    rows = doc["runs"]
    if len(rows) != 14:
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
        seen.add(key); reached = reached and row["reached"]
    if seen != {(arm, run) for arm in ARMS for run in (1, 2)}:
        raise InputError("測定走の不足")
    return reached


def judge(derived: dict[str, Any], measurement: dict[str, Any]) -> tuple[Counter[str], dict[str, Any]]:
    runs = derived.get("runs")
    if not isinstance(runs, list) or len(runs) != 2:
        raise InputError("導出走数")
    by_run = {}
    for row in runs:
        if not isinstance(row, dict) or row.get("repetition") not in (1, 2) \
                or not isinstance(row.get("derivations"), dict):
            raise InputError("導出走の形式")
        by_run[row["repetition"]] = row["derivations"]
    if set(by_run) != {1, 2}:
        raise InputError("導出走の不足")
    if set(by_run[1]) != set(DERIVATIONS) or set(by_run[2]) != set(DERIVATIONS):
        raise InputError("導出名の不足または余分")
    combined = {}
    counts: Counter[str] = Counter()
    for name in DERIVATIONS:
        combined[name] = consensus(by_run[1][name], by_run[2][name])
        counts[combined[name]["status"]] += 1
    if not validate_measurement(measurement):
        overall = "m6f_a_inconclusive"
        counts["unreached"] += 1
    elif all(combined[x]["status"] == "derived" for x in ("D1", "D2", "D3")):
        overall = "m6f_a_directory_located"
    else:
        overall = "m6f_a_directory_ambiguous"
    counts[overall] += 1
    return counts, combined


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
        digest.update(draw); digest.update(mraw)
        counts, derivations = judge(json.loads(draw), json.loads(mraw))
        emit(counts, derivations, digest.hexdigest())
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, ValueError):
        emit(Counter({"gate_failed": 1}), {}, digest.hexdigest())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
