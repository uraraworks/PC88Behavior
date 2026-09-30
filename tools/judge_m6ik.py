#!/usr/bin/env python3
"""m6i-k 各腕2走から事前登録 §8 の判定名を出す。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analyze_m6ik import ARMS

GATES = tuple(f"G{i}" for i in range(1, 10))
JUDGMENTS = ("m6i_k_conversion_by_17", "m6i_k_conversion_needs_both",
             "m6i_k_conversion_by_p1_after_17", "m6i_k_no_conversion",
             "m6i_k_other", "m6i_k_measurement_blind", "m6i_k_inconclusive",
             "gate_failed")


def arm_class(rows: list[dict]) -> str:
    if any(row["classification"] != "agree" or row["success"] != "success"
           for row in (rows[0], rows[5])):
        return "control_failed"
    middle = rows[1:5]
    names = [row["classification"] for row in middle]
    if len(set(names)) == 1 and names[0] in ("logical", "cylinder"):
        return names[0]
    drive1 = {names[0], names[3]}
    drive2 = {names[1], names[2]}
    if len(drive1) == len(drive2) == 1 and drive1 != drive2 \
            and drive1 | drive2 == {"logical", "cylinder"}:
        return "split_by_drive"
    return "mixed"


def signature(run: dict) -> str:
    return json.dumps((run.get("pre_send_fd_count"), run.get("rows")),
                      sort_keys=True, separators=(",", ":"))


def judge(grouped: dict[str, list[dict]]) -> dict:
    results = {}
    success = {}
    for arm in ARMS:
        runs = grouped.get(arm, [])
        if len(runs) != 2 or any(not run.get("reached") or len(run.get("rows", [])) != 6
                                 for run in runs) or signature(runs[0]) != signature(runs[1]):
            results[arm] = "unreached"
            continue
        rows = runs[0]["rows"]
        if arm != "K-FR" and any(row["index_disagree"] for row in rows):
            results[arm] = "unreached"
        else:
            results[arm] = arm_class(rows)
        success[arm] = [row["success"] for row in rows]
    if any(value == "unreached" for value in results.values()):
        overall = "m6i_k_inconclusive"
    elif any(value == "control_failed" for arm, value in results.items() if arm != "K-FR"):
        overall = "m6i_k_inconclusive"
    elif any(row["classification"] != "other" or row["index_disagree"]
             for row in grouped["K-FR"][0]["rows"]):
        overall = "m6i_k_measurement_blind"
    elif results["K-F0"] == results["K-F1"] == "logical" \
            and results["K-00"] == results["K-01"] == "cylinder":
        overall = "m6i_k_conversion_by_17"
    elif results["K-F1"] == "logical" and results["K-F0"] == "cylinder" \
            and all(results[a] != "logical" for a in ("K-00", "K-01")):
        overall = "m6i_k_conversion_needs_both"
    elif any(results[a] == "logical" for a in ("K-00", "K-01", "K-F0", "K-F1")) \
            and all(a in ("K-01", "K-F1") for a in ("K-00", "K-01", "K-F0", "K-F1")
                    if results[a] == "logical"):
        overall = "m6i_k_conversion_by_p1_after_17"
    elif all(results[a] == "cylinder" for a in ("K-00", "K-01", "K-F0", "K-F1")):
        overall = "m6i_k_no_conversion"
    else:
        overall = "m6i_k_other"
    secondary = (results.get("K-M1") == "split_by_drive" and
                 [grouped["K-M1"][0]["rows"][i]["classification"] for i in (1, 4)]
                 == ["logical", "logical"])
    return {"judgment": overall, "arms": results, "success_by_arm": success,
            "m1_bit0_drive1": secondary}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", action="append", default=[])
    ap.add_argument("--result", action="append", type=Path, default=[])
    args = ap.parse_args()
    try:
        gates = dict(x.split("=", 1) for x in args.gate)
        if len(args.gate) != 9 or set(gates) != set(GATES) or \
                any(x not in ("true", "false") for x in gates.values()):
            raise ValueError
        if any(x == "false" for x in gates.values()):
            print(json.dumps({"judgment": "gate_failed"}))
            return 1
        grouped: dict[str, list[dict]] = {}
        for path in args.result:
            run = json.loads(path.read_text())
            if run.get("arm") not in ARMS or run.get("dry_run"):
                raise ValueError
            grouped.setdefault(run["arm"], []).append(run)
        result = judge(grouped)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"judgment": "gate_failed"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
