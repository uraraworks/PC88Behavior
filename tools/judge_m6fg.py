#!/usr/bin/env python3
"""m6f-g の導出JSONを独立に再判定し、登録済み判定名だけを返す。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import predict_m6fg as predict  # noqa: E402

SHA_RE = re.compile(r"[0-9a-f]{64}")


class InputError(ValueError):
    pass


def recompute(doc: dict[str, Any]) -> tuple[str, list[str]]:
    required = {"format", "overall", "gates", "mark_candidates",
                "mark_judgments", "mixed_match_pairs", "mixed_judgment",
                "size_judgment", "input_sha256"}
    if set(doc) != required or doc.get("format") != "m6fg-derived-v1":
        raise InputError("導出形式")
    gates = doc["gates"]
    if (not isinstance(gates, dict) or set(gates) != {"G9", "G10", "G11", "G12", "G13"}
            or any(not isinstance(value, bool) for value in gates.values())):
        raise InputError("関門形式")
    valid = set(predict.mark_candidate_ids())
    candidates = doc["mark_candidates"]
    judgments = doc["mark_judgments"]
    if (not isinstance(candidates, dict) or set(candidates) != set(predict.MARK_ARMS)
            or not isinstance(judgments, dict) or set(judgments) != set(predict.MARK_ARMS)):
        raise InputError("印形式")
    expected_marks: dict[str, str] = {}
    for arm in predict.MARK_ARMS:
        values = candidates[arm]
        if (not isinstance(values, list) or len(values) != len(set(values))
                or any(value not in valid for value in values)):
            raise InputError("印候補")
        expected_marks[arm] = (values[0] if len(values) == 1 else
                               f"inconclusive_{arm}_no_candidate" if not values else
                               f"inconclusive_{arm}_multiple")
    if judgments != expected_marks:
        raise InputError("印判定不一致")
    pairs = doc["mixed_match_pairs"]
    if not isinstance(pairs, list):
        raise InputError("混在組")
    normalized = []
    for pair in pairs:
        if (not isinstance(pair, list) or len(pair) != 2
                or pair[0] not in candidates["G-P"] or pair[1] not in candidates["G-B"]):
            raise InputError("混在組値")
        normalized.append(tuple(pair))
    if len(normalized) != len(set(normalized)):
        raise InputError("混在組重複")
    mixed = "mixed_row_consistent" if pairs else "mixed_row_inconsistent"
    if doc["mixed_judgment"] != mixed:
        raise InputError("混在判定不一致")
    if doc["size_judgment"] not in ("size_min_digits", "size_other"):
        raise InputError("大きさ判定")
    if not isinstance(doc["input_sha256"], str) or not SHA_RE.fullmatch(doc["input_sha256"]):
        raise InputError("入力SHA")
    overall = "classified" if all(gates.values()) else "gate_failed"
    if doc["overall"] != overall:
        raise InputError("overall不一致")
    result = ([expected_marks["G-P"], expected_marks["G-B"], mixed,
               doc["size_judgment"]] if overall == "classified" else ["gate_failed"])
    return overall, result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--derived", required=True, type=Path)
    args = parser.parse_args()
    digest = hashlib.sha256()
    try:
        raw = args.derived.read_bytes()
        digest.update(raw)
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise InputError("導出形式")
        overall, judgments = recompute(doc)
        print(json.dumps({"overall": overall, "judgments": judgments,
                          "sha256": digest.hexdigest()}, ensure_ascii=True,
                         sort_keys=True, separators=(",", ":")))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, InputError):
        print(json.dumps({"overall": "gate_failed", "judgments": ["gate_failed"],
                          "sha256": digest.hexdigest()}, ensure_ascii=True,
                         sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
