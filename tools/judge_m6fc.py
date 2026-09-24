#!/usr/bin/env python3
"""m6f-c の derive_m6fc.py 出力から、事前登録第7節の総合判定を出す。

derive_m6fc.py 自身も内部で overall を1つスタンプするが、judge はそれを
鵜呑みにせず、C0/C1/C2 の分類だけから独立に再計算し、両者が食い違えば
`gate_failed` を返す（導出器内部のバグで overall が実体と食い違ったまま
静かに通るのを防ぐ、二重チェックの層）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

DERIVATION_NAMES = tuple(f"C{i}" for i in range(12))
STATUSES = ("derived", "ambiguous", "not_found")
OVERALL = (
    "m6f_c_boot_blocked", "m6f_c_no_free_mark",
    "m6f_c_blank_disk_accepted", "m6f_c_blank_disk_not_accepted",
)
REGISTERED = ("gate_failed",) + STATUSES + OVERALL


class InputError(ValueError):
    pass


def _status(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("status")
    return None


def compute_overall(derivations: dict[str, Any]) -> str:
    c0 = _status(derivations.get("C0"))
    if c0 != "derived":
        return "m6f_c_boot_blocked"
    c1 = _status(derivations.get("C1"))
    if c1 == "not_found":
        return "m6f_c_no_free_mark"
    c2 = derivations.get("C2")
    accepted = isinstance(c2, dict) and c2.get("status") == "accepted"
    if c1 in ("derived", "ambiguous") and accepted:
        return "m6f_c_blank_disk_accepted"
    return "m6f_c_blank_disk_not_accepted"


def judge(doc: dict[str, Any]) -> tuple[Counter[str], str]:
    if not isinstance(doc, dict) or not isinstance(doc.get("derivations"), dict):
        raise InputError("導出結果の形式")
    derivations = doc["derivations"]
    if "C0" not in derivations or "C1" not in derivations:
        raise InputError("C0/C1が無い")
    recomputed = compute_overall(derivations)
    stamped = doc.get("overall")
    if stamped != recomputed:
        raise InputError(f"overallの食い違い: stamped={stamped} recomputed={recomputed}")
    counts: Counter[str] = Counter()
    for name in DERIVATION_NAMES:
        item = derivations.get(name)
        status = _status(item)
        if status in STATUSES:
            counts[status] += 1
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
