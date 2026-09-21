#!/usr/bin/env python3
"""A0〜A5の伏せ字済みJSON結果を事前登録どおり総合判定する。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EXPECTED = {
    "A0": {"read_matches_generated_sector", "read_data_mismatch", "unreached", "gate_failed"},
    "A1": {"sector_select_changes_signature", "fixed_value_suspected", "unreached", "gate_failed"},
    "A2": {"no_media_returns", "no_media_hangs_or_completes", "unreached", "gate_failed"},
    "A3": {"wait_negative_detected", "wait_negative_escaped", "unreached", "gate_failed"},
    "A4": {"sequence_negative_detected", "sequence_negative_escaped", "unreached", "gate_failed"},
    "A5": {"integration_regression_free", "integration_regressed", "unreached", "gate_failed"},
}
PASS = {
    "read_matches_generated_sector", "sector_select_changes_signature",
    "no_media_returns", "wait_negative_detected", "sequence_negative_detected",
    "integration_regression_free",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for arm in EXPECTED:
        ap.add_argument(f"--{arm.lower()}", required=True, type=Path)
    args = ap.parse_args()
    try:
        results = {}
        for arm in EXPECTED:
            value = json.loads(getattr(args, arm.lower()).read_text(encoding="utf-8"))
            if value.get("arm") != arm or value.get("judgment") not in EXPECTED[arm]:
                raise ValueError
            results[arm] = value

        judgments = [results[arm]["judgment"] for arm in EXPECTED]
        # A0/A1の横断条件は両腕の実データ署名でも再確認する。
        a0_sha = results["A0"].get("receive_sha256")
        a1_sha = results["A1"].get("receive_sha256")
        cross_ok = (a0_sha == "4ed6e24a1fb78f8c79423740e05a311c438bae0f09b9974e50619050fdb8540a"
                    and a1_sha == "f0cb8924325dbf2dece67fbebf41a9ee1ffbcd88fe8493ca18cbb49129d3ab0f"
                    and a0_sha != a1_sha)
        if "gate_failed" in judgments:
            overall = "gate_failed"
        elif "unreached" in judgments:
            overall = "m6i_a_inconclusive"
        elif set(judgments) == PASS and cross_ok:
            overall = "m6i_a_pass"
        else:
            overall = "m6i_a_fail"
        print(json.dumps({"judgment": overall, "arm_judgments": judgments,
                          "a0_a1_cross_signature_match": cross_ok},
                         sort_keys=True, separators=(",", ":")))
        return 0 if overall == "m6i_a_pass" else 1
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        print('{"judgment":"gate_failed","reason":"result_input_error"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
