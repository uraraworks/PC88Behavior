#!/usr/bin/env python3
"""m6f-d の derive_m6fd.py 出力から、事前登録第7節の総合判定を出す。

derive_m6fd.py 自身も内部で overall を1つスタンプするが、judge はそれを
鵜呑みにせず、D1〜D6 の分類だけから独立に再計算し、両者が食い違えば
`gate_failed` を返す（judge_m6fc.py と同じ二重チェックの層）。
D7〜D9 は事前登録どおり個別記録のみで、overall には効かない。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

CORE_NAMES = ("D1", "D2", "D3", "D4")
STATUSES = ("derived", "ambiguous", "not_found")
D2_STATUSES = ("link_is_next_index", "link_other")
D3_STATUSES = ("end_constant", "end_plus_used_sectors", "end_other")
OVERALL = ("m6f_d_rules_confirmed", "m6f_d_incomplete")
D5_STATUSES = ("relocated_readable", "not_readable", "control_failed")
D6_STATUSES = ("stops_at_unused", "scans_past_unused", "control_failed")
D8_STATUSES = ("reserve_needed", "reserve_not_needed", "reserve_other", "ambiguous")
REGISTERED = (
    ("gate_failed",) + STATUSES + D2_STATUSES + D3_STATUSES + OVERALL
    + D5_STATUSES + D6_STATUSES + D8_STATUSES
)


class InputError(ValueError):
    pass


def _status(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("status")
    return None


def compute_overall(derivations: dict[str, Any]) -> str:
    d1, d2, d3, d4 = (_status(derivations.get(n)) for n in CORE_NAMES)
    # D2(鎖)は"derived"という文字列を持たない(derive_m6fc.chain()と同型)。
    # link_is_next_index(不一致0件)をここでの「derived」とみなす(derive_m6fd.pyと同じ約束)。
    core_derived = (d1 == "derived" and d2 == "link_is_next_index" and d3 in D3_STATUSES and d4 == "derived")
    d5 = derivations.get("D5")
    d5_ok = isinstance(d5, dict) and d5.get("status") == "relocated_readable"
    d6 = derivations.get("D6")
    d6_ok = (isinstance(d6, dict) and d6.get("status") in ("stops_at_unused", "scans_past_unused")
              and len(d6.get("directory_sectors", [])) >= 1)
    if core_derived and d5_ok and d6_ok:
        return "m6f_d_rules_confirmed"
    return "m6f_d_incomplete"


def judge(doc: dict[str, Any]) -> tuple[Counter[str], str]:
    if not isinstance(doc, dict) or not isinstance(doc.get("derivations"), dict):
        raise InputError("導出結果の形式")
    derivations = doc["derivations"]
    for name in CORE_NAMES + ("D5", "D6"):
        if name not in derivations:
            raise InputError(f"{name}が無い")
    recomputed = compute_overall(derivations)
    stamped = doc.get("overall")
    if stamped != recomputed:
        raise InputError(f"overallの食い違い: stamped={stamped} recomputed={recomputed}")

    counts: Counter[str] = Counter()
    for name in CORE_NAMES:
        status = _status(derivations.get(name))
        if status in STATUSES:
            counts[status] += 1
    d2_status = _status(derivations.get("D2"))
    if d2_status in D2_STATUSES:
        counts[d2_status] += 1
    d3_status = _status(derivations.get("D3"))
    if d3_status in D3_STATUSES:
        counts[d3_status] += 1
    d5_status = _status(derivations.get("D5"))
    if d5_status in D5_STATUSES:
        counts[d5_status] += 1
    d6_status = _status(derivations.get("D6"))
    if d6_status in D6_STATUSES:
        counts[d6_status] += 1
    d8_status = _status(derivations.get("D8"))
    if d8_status in D8_STATUSES:
        counts[d8_status] += 1
    counts[recomputed] += 1
    return counts, recomputed


def emit(counts: Counter[str], overall: str | None, digest: str) -> None:
    judgments = [{"judgment": name, "count": counts[name], "present": counts[name] > 0}
                 for name in REGISTERED]
    print(json.dumps({"overall": overall, "judgments": judgments, "sha256": digest},
                      sort_keys=True, separators=(",", ":")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--derived", required=True, type=Path)
    args = ap.parse_args()
    digest = hashlib.sha256()
    try:
        raw = args.derived.read_bytes()
        digest.update(raw)
        doc = json.loads(raw)
        counts, overall = judge(doc)
        emit(counts, overall, digest.hexdigest())
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, ValueError):
        emit(Counter({"gate_failed": 1}), None, digest.hexdigest())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
