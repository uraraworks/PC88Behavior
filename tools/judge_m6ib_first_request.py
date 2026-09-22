#!/usr/bin/env python3
"""m6i-bの各腕2走の解析JSONを、事前登録済み判定名だけへ写像する。"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


B6_BRANCHES = ("B6-A0", "B6-A1", "B6-A2", "B6-A4-cont", "B6-A4-pair", "B6-A5")
ARMS = ("B0", "B1", "B2", "B3", "B4", "B5") + B6_BRANCHES

ARM_RESULTS = {
    "B0": ("immediate_failure_reproduced", "immediate_failure_not_reproduced"),
    "B1": ("elapsed_only_sufficient", "elapsed_only_rejected"),
    "B2": ("b_only_sufficient", "b_only_insufficient"),
    "B3": ("a_without_b_sufficient", "a_without_b_insufficient"),
    "B4": ("ab_without_c_sufficient", "ab_without_c_insufficient"),
    "B5": ("abc_sufficient", "abc_insufficient"),
}
B6_RESULTS = {
    "B6-A0": ("read_matches_generated_sector", "read_data_mismatch"),
    "B6-A1": ("sector_select_changes_signature", "fixed_value_suspected"),
    "B6-A2": ("no_media_returns", "no_media_hangs_or_completes"),
    "B6-A4-cont": ("sequence_negative_detected", "sequence_negative_escaped"),
    "B6-A4-pair": ("sequence_negative_detected", "sequence_negative_escaped"),
    "B6-A5": ("integration_regression_free", "integration_regressed"),
}
B6_REGISTERED = tuple(dict.fromkeys(
    name for pair in B6_RESULTS.values() for name in pair))
OVERALL = (
    "m6i_b_startup_consumption_boundary",
    "m6i_b_init_without_startup_boundary",
    "m6i_b_either_a_or_b_boundary",
    "m6i_b_init_and_startup_boundary",
    "m6i_b_round0_completion_boundary",
    "m6i_b_elapsed_time_only",
    "m6i_b_no_registered_boundary",
    "m6i_b_nonmonotonic",
    "m6i_b_inconclusive",
)
REGISTERED = (
    "gate_failed", "unreached",
    *(name for pair in ARM_RESULTS.values() for name in pair),
    "m6ia_arms_reached_after_abc",
    *B6_REGISTERED,
    *OVERALL,
)

PATTERNS = {
    "m6i_b_startup_consumption_boundary": (
        "elapsed_only_rejected", "b_only_sufficient", "a_without_b_insufficient",
        "ab_without_c_sufficient", "abc_sufficient"),
    "m6i_b_init_without_startup_boundary": (
        "elapsed_only_rejected", "b_only_insufficient", "a_without_b_sufficient",
        "ab_without_c_sufficient", "abc_sufficient"),
    "m6i_b_either_a_or_b_boundary": (
        "elapsed_only_rejected", "b_only_sufficient", "a_without_b_sufficient",
        "ab_without_c_sufficient", "abc_sufficient"),
    "m6i_b_init_and_startup_boundary": (
        "elapsed_only_rejected", "b_only_insufficient", "a_without_b_insufficient",
        "ab_without_c_sufficient", "abc_sufficient"),
    "m6i_b_round0_completion_boundary": (
        "elapsed_only_rejected", "b_only_insufficient", "a_without_b_insufficient",
        "ab_without_c_insufficient", "abc_sufficient"),
}


class InputError(Exception):
    """関門より後へ進めない解析入力。"""


def parse_gates(entries: list[str]) -> dict[str, bool]:
    gates: dict[str, bool] = {}
    for entry in entries:
        name, separator, raw_value = entry.partition("=")
        if separator != "=" or name not in {f"G{i}" for i in range(1, 10)}:
            raise InputError
        if name in gates or raw_value not in ("true", "false"):
            raise InputError
        gates[name] = raw_value == "true"
    if set(gates) != {f"G{i}" for i in range(1, 10)}:
        raise InputError
    return gates


def _bool(value: object) -> bool:
    if type(value) is not bool:
        raise InputError
    return value


def classify_run(arm: str, value: dict[str, object]) -> str:
    """1走を到達判定の後にだけ結果判定する。"""
    if value.get("arm") != arm or value.get("fault_injection") is not None:
        raise InputError
    if not _bool(value.get("analysis_ok")):
        return "unreached"
    digest = value.get("rom_set_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise InputError
    try:
        int(digest, 16)
    except ValueError as exc:
        raise InputError from exc

    if arm in ARM_RESULTS:
        result_kind = value.get("result_kind")
        if not isinstance(result_kind, str):
            raise InputError
        if arm == "B0":
            return ARM_RESULTS[arm][0 if result_kind == "timeout" else 1]
        return ARM_RESULTS[arm][0 if result_kind == "positions_256_match" else 1]

    if not _bool(value.get("m6ia_reached")):
        return "unreached"
    judgment = value.get("m6ia_judgment")
    if judgment not in B6_RESULTS[arm]:
        raise InputError
    return str(judgment)


def judge(values: dict[str, list[dict[str, object]]]) -> Counter[str]:
    """全腕を2走一致、到達、結果、総合の順に判定する。"""
    arm_judgments: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for arm in ARMS:
        if len(values.get(arm, [])) != 2:
            raise InputError
        runs = values[arm]
        pair = [classify_run(arm, row) for row in runs]
        judgment = pair[0] if pair[0] == pair[1] else "unreached"
        if (judgment != "unreached"
                and runs[0].get("rom_set_sha256") != runs[1].get("rom_set_sha256")):
            raise InputError
        arm_judgments[arm] = judgment
        counts[judgment] += 1

    # B6副問は総合判定と独立し、全6枝が到達した場合だけ付ける。
    if all(arm_judgments[arm] != "unreached" for arm in B6_BRANCHES):
        counts["m6ia_arms_reached_after_abc"] = 1

    # 共通前提のB0を満たしB1が成立すれば、後続腕の形を読まず境界判定を止める。
    if (arm_judgments["B0"] == "immediate_failure_reproduced"
            and arm_judgments["B1"] == "elapsed_only_sufficient"):
        counts["m6i_b_elapsed_time_only"] = 1
        return counts
    if any(value == "unreached" for value in arm_judgments.values()):
        counts["m6i_b_inconclusive"] = 1
        return counts

    b0_b5 = tuple(arm_judgments[f"B{i}"] for i in range(1, 6))
    if arm_judgments["B0"] == "immediate_failure_reproduced":
        for name, pattern in PATTERNS.items():
            if b0_b5 == pattern:
                counts[name] = 1
                return counts
        if (arm_judgments["B1"] == "elapsed_only_rejected"
                and arm_judgments["B5"] == "abc_insufficient"):
            counts["m6i_b_no_registered_boundary"] = 1
            return counts
    counts["m6i_b_nonmonotonic"] = 1
    return counts


def emit(counts: Counter[str], digest: str) -> None:
    rows = [{"judgment": name, "count": counts[name], "present": counts[name] > 0}
            for name in REGISTERED]
    print(json.dumps({"judgments": rows, "sha256": digest},
                     sort_keys=True, separators=(",", ":")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", action="append", default=[],
                    help="関門真偽（G1=true〜G9=trueを各1回指定）")
    ap.add_argument("--result", action="append", default=[], type=Path,
                    help="解析器JSON（全12腕を各2本、計24回指定）")
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
            value = json.loads(raw)
            if not isinstance(value, dict) or value.get("arm") not in ARMS:
                raise InputError
            grouped.setdefault(str(value["arm"]), []).append(value)
        emit(judge(grouped), hasher.hexdigest())
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, OverflowError):
        emit(Counter({"gate_failed": 1}), hasher.hexdigest())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
