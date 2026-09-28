#!/usr/bin/env python3
"""m6f-i の導出JSONを再判定し、登録済みの判定名だけを返す。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import predict_m6fi as predict


def recompute(doc: dict) -> dict:
    if (not isinstance(doc, dict) or set(doc) !=
            {"format", "overall", "gates", "matches", "judgments", "input_sha256"}
            or doc["format"] != "m6fi-derived-v1" or
            not re.fullmatch(r"[0-9a-f]{64}", doc["input_sha256"])):
        raise ValueError("導出形式")
    gates = doc["gates"]
    if (not isinstance(gates, dict) or set(gates) != {f"G{i}" for i in range(9, 14)}
            or any(type(value) is not bool for value in gates.values())):
        raise ValueError("関門")
    if set(doc["matches"]) != set(predict.ARMS) or set(doc["judgments"]) != set(predict.ARMS):
        raise ValueError("腕")
    judgments = {}
    for arm in predict.ARMS:
        values = doc["matches"][arm]
        if (not isinstance(values, list) or len(values) != len(set(values)) or
                any(value not in predict.candidate_ids(arm) for value in values)):
            raise ValueError("候補")
        judgments[arm] = (values[0] if len(values) == 1 else
                          f"inconclusive_{arm}" if len(values) > 1 else
                          "not_trapped" if arm.startswith("E-") else "other")
    overall = "classified" if all(gates.values()) else "gate_failed"
    if doc["judgments"] != judgments or doc["overall"] != overall:
        raise ValueError("判定不一致")
    return {"overall": overall,
            "judgments": [judgments[arm] for arm in predict.ARMS] if overall == "classified"
                         else ["gate_failed"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--derived", required=True, type=Path)
    args = ap.parse_args()
    digest = hashlib.sha256()
    try:
        raw = args.derived.read_bytes()
        digest.update(raw)
        result = recompute(json.loads(raw))
        result["sha256"] = digest.hexdigest()
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, KeyError, TypeError):
        print(json.dumps({"overall": "gate_failed", "judgments": ["gate_failed"],
                          "sha256": digest.hexdigest()}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
