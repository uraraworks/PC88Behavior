#!/usr/bin/env bash
# m6i-b判定器を、測定値を使わない合成解析JSONで全判定名について検査する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO" <<'PY'
from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

repo = Path(sys.argv[1])
judge_path = repo / "tools" / "judge_m6ib_first_request.py"
spec = importlib.util.spec_from_file_location("judge_m6ib", judge_path)
assert spec and spec.loader
j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(j)

DIGEST = "1" * 64
B6_POSITIVE = {
    "B6-A0": "read_matches_generated_sector",
    "B6-A1": "sector_select_changes_signature",
    "B6-A2": "no_media_returns",
    "B6-A4-cont": "sequence_negative_detected",
    "B6-A4-pair": "sequence_negative_detected",
    "B6-A5": "integration_regression_free",
}
B6_NEGATIVE = {
    "B6-A0": "read_data_mismatch",
    "B6-A1": "fixed_value_suspected",
    "B6-A2": "no_media_hangs_or_completes",
    "B6-A4-cont": "sequence_negative_escaped",
    "B6-A4-pair": "sequence_negative_escaped",
    "B6-A5": "integration_regressed",
}


def dataset(bits=(False, True, False, True, True), *, b0_timeout=True,
            b6_negative=False):
    """bitsはB1〜B5の正常READ成立真偽。"""
    rows = {}
    for arm in j.ARMS:
        row = {"arm": arm, "fault_injection": None, "analysis_ok": True,
               "rom_set_sha256": DIGEST, "result_kind": "timeout"}
        if arm == "B0":
            row["result_kind"] = "timeout" if b0_timeout else "sha_mismatch"
        elif arm in j.ARM_RESULTS:
            row["result_kind"] = (
                "positions_256_match" if bits[int(arm[1]) - 1] else "timeout")
        else:
            row.update({"m6ia_reached": True,
                        "m6ia_judgment": (B6_NEGATIVE if b6_negative
                                           else B6_POSITIVE)[arm]})
        rows[arm] = [copy.deepcopy(row), copy.deepcopy(row)]
    return rows


def run(rows, *, omit_last=False, failed_gate=None):
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        cmd = [sys.executable, str(judge_path)]
        for number in range(1, 10):
            value = "false" if failed_gate == f"G{number}" else "true"
            cmd += ["--gate", f"G{number}={value}"]
        index = 0
        for arm in j.ARMS:
            for run_no, row in enumerate(rows[arm]):
                if omit_last and arm == j.ARMS[-1] and run_no == 1:
                    continue
                path = tmp / f"{index:02d}.json"
                path.write_text(json.dumps(row, sort_keys=True), encoding="utf-8")
                cmd += ["--result", str(path)]
                index += 1
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=False)
    value = json.loads(proc.stdout)
    if set(value) != {"judgments", "sha256"} or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]):
        raise SystemExit("出力が判定名・件数・真偽・SHA-256に限定されていない")
    if any(set(row) != {"judgment", "count", "present"}
           or type(row["count"]) is not int or type(row["present"]) is not bool
           for row in value["judgments"]):
        raise SystemExit("判定行の出力形式が不正")
    return proc.returncode, {row["judgment"]: row for row in value["judgments"]}


def overall(result):
    found = [name for name in j.OVERALL if result[name]["present"]]
    if len(found) != 1:
        raise SystemExit(f"総合判定が一意でない: {found}")
    return found[0]


seen_true = set()
seen_false = set()


def record(result):
    for name, row in result.items():
        (seen_true if row["present"] else seen_false).add(name)


# 5状態境界、時間のみ、登録境界なし、非単調をそれぞれ陽性にする。
cases = {
    "m6i_b_startup_consumption_boundary": (False, True, False, True, True),
    "m6i_b_init_without_startup_boundary": (False, False, True, True, True),
    "m6i_b_either_a_or_b_boundary": (False, True, True, True, True),
    "m6i_b_init_and_startup_boundary": (False, False, False, True, True),
    "m6i_b_round0_completion_boundary": (False, False, False, False, True),
    "m6i_b_elapsed_time_only": (True, False, False, False, False),
    "m6i_b_no_registered_boundary": (False, True, True, True, False),
}
for expected, bits in cases.items():
    rc, result = run(dataset(bits))
    if rc != 0 or overall(result) != expected:
        raise SystemExit(f"総合判定不一致: expected={expected}")
    record(result)

rc, result = run(dataset((False, True, False, False, True), b0_timeout=False))
if rc != 0 or overall(result) != "m6i_b_nonmonotonic":
    raise SystemExit("登録外の到達形をnonmonotonicにできない")
record(result)

# 7境界は、登録条件を1つだけ変えると元の名前のままにならない。
mutations = {
    "m6i_b_startup_consumption_boundary": (False, False, False, True, True),
    "m6i_b_init_without_startup_boundary": (False, True, True, True, True),
    "m6i_b_either_a_or_b_boundary": (False, True, False, True, True),
    "m6i_b_init_and_startup_boundary": (False, False, False, False, True),
    "m6i_b_round0_completion_boundary": (False, False, False, False, False),
    "m6i_b_elapsed_time_only": (False, False, False, False, False),
    "m6i_b_no_registered_boundary": (False, True, True, True, True),
}
allowed_changed = set(cases) | {"m6i_b_nonmonotonic"}
for original, bits in mutations.items():
    _rc, result = run(dataset(bits))
    changed = overall(result)
    if changed == original or changed not in allowed_changed:
        raise SystemExit(f"7境界の取り違え: {original} -> {changed}")

# 2走の結果不一致は、成功側へ寄せずunreachedにする。
rows = dataset()
rows["B2"][1]["result_kind"] = "timeout"
_rc, result = run(rows)
if not result["unreached"]["present"] or overall(result) != "m6i_b_inconclusive":
    raise SystemExit("2走不一致をunreachedにできない")
record(result)

# 未到達は結果条件へ読み替えず、その腕の両結果名を付けない。
rows = dataset()
rows["B2"] = [{"arm": "B2", "analysis_ok": False},
              {"arm": "B2", "analysis_ok": False}]
_rc, result = run(rows)
if (not result["unreached"]["present"]
        or result["b_only_sufficient"]["present"]
        or result["b_only_insufficient"]["present"]):
    raise SystemExit("未到達腕が結果判定へ読み替えられた")
record(result)

# B1成立なら、後続腕に不一致・未到達があっても時間のみで境界判定を止める。
rows = dataset((True, False, True, False, True))
rows["B2"][1]["result_kind"] = "positions_256_match"
for row in rows["B5"]:
    row["analysis_ok"] = False
_rc, result = run(rows)
if overall(result) != "m6i_b_elapsed_time_only" or any(
        result[name]["present"] for name in j.PATTERNS):
    raise SystemExit("elapsed_only_sufficientが後続腕の形に依存した")
record(result)

# B6の結果名は到達後だけ記録し、副問は全枝到達時だけ総合と独立に付く。
_rc, result = run(dataset(b6_negative=True))
if not result["m6ia_arms_reached_after_abc"]["present"]:
    raise SystemExit("B6全枝到達の副問が付かない")
record(result)
rows = dataset()
for row in rows["B6-A0"]:
    row["analysis_ok"] = False
    row["m6ia_reached"] = False
_rc, result = run(rows)
if (result["m6ia_arms_reached_after_abc"]["present"]
        or result["read_matches_generated_sector"]["present"]):
    raise SystemExit("B6未到達枝に副問または結果判定が付いた")
record(result)

# 各関門の偽は腕入力を読まずに止まり、腕ごとの成否を付けない。
for gate_no in range(1, 10):
    rc, result = run(dataset(), failed_gate=f"G{gate_no}")
    if rc != 1 or not result["gate_failed"]["present"] or any(
            row["present"] for name, row in result.items() if name != "gate_failed"):
        raise SystemExit(f"G{gate_no}不成立をgate_failedだけにできない")
    record(result)

# 関門通過後の入力不足も、結果へ進めずgate_failedにする。
rc, result = run(dataset(), omit_last=True)
if rc != 2 or not result["gate_failed"]["present"]:
    raise SystemExit("解析入力不足をgate_failedにできない")

missing_positive = set(j.REGISTERED) - seen_true
missing_negative = set(j.REGISTERED) - seen_false
if missing_positive or missing_negative:
    raise SystemExit(f"全判定名の陽性/陰性不足: +{sorted(missing_positive)} -{sorted(missing_negative)}")

print(f"judge_m6ib_first_request_selftest: 登録判定名{len(j.REGISTERED)}種・陽性/陰性・取り違え防止 OK")
PY
