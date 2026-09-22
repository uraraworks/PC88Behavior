#!/usr/bin/env bash
# m6i-c判定器の総合5種、副問5種、関門と2走不一致を合成JSONで検査する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
python3 - "$REPO" "$WORK" <<'PY'
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

repo, scratch = map(Path, sys.argv[1:])
sys.path.insert(0, str(repo / "tools"))
import judge_m6ic as j

DIGEST = "1" * 64


def dataset(c2=True, c3=False):
    outcomes = {"C0": False, "C1": True, "C2": c2, "C3": c3}
    rows = {}
    for arm in j.ARMS:
        gate = arm in ("C0", "C3")
        row = {
            "arm": arm, "fault_injection": None, "reached": True,
            "result": "success" if outcomes[arm] else "failure",
            "rom_set_sha256": DIGEST,
            "gate_entered": gate, "gate_released": gate,
            "gate_run_count": int(gate), "gate_run_max_length": 32 if gate else 0,
            "request_runs": 1 if outcomes[arm] else 0,
        }
        rows[arm] = [copy.deepcopy(row), copy.deepcopy(row)]
    return rows


def run(rows, failed_gate=None):
    with tempfile.TemporaryDirectory(dir=scratch) as raw:
        tmp = Path(raw)
        cmd = [sys.executable, str(repo / "tools/judge_m6ic.py")]
        for number in range(1, 10):
            value = "false" if failed_gate == f"G{number}" else "true"
            cmd += ["--gate", f"G{number}={value}"]
        index = 0
        for arm in j.ARMS:
            for row in rows[arm]:
                path = tmp / f"{index}.json"
                path.write_text(json.dumps(row, sort_keys=True), encoding="utf-8")
                cmd += ["--result", str(path)]
                index += 1
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=False)
    value = json.loads(proc.stdout)
    if set(value) != {"judgments", "sha256"}:
        raise SystemExit("判定器の出力形式が不正")
    return proc.returncode, {row["judgment"]: row for row in value["judgments"]}


def only_overall(result):
    names = [name for name in j.OVERALL if result[name]["present"]]
    if len(names) != 1:
        raise SystemExit(f"総合判定が一意でない: {names}")
    return names[0]


overall_cases = {
    "m6i_c_sub_gate_only": dataset(True, False),
    "m6i_c_branch_tag_only": dataset(False, True),
    "m6i_c_interaction_required": dataset(False, False),
    "m6i_c_no_single_factor": dataset(True, True),
}
inconclusive = dataset(True, False)
for row in inconclusive["C0"]:
    row["result"] = "success"
overall_cases["m6i_c_inconclusive"] = inconclusive
for expected, rows in overall_cases.items():
    rc, result = run(rows)
    if rc != 0 or only_overall(result) != expected:
        raise SystemExit(f"総合判定取り違え: {expected}")


def set_side(rows, entered, released, requests):
    for arm in ("C0", "C3"):
        for row in rows[arm]:
            row.update({
                "gate_entered": entered, "gate_released": released,
                "gate_run_count": int(entered),
                "gate_run_max_length": 32 if entered else 0,
                "request_runs": requests,
            })


side_cases = {}
for name, shape in {
    "gate_not_entered": (False, False, 0),
    "gate_never_released": (True, False, 0),
    "gate_released_but_request_lost": (True, True, 0),
    "gate_released_and_request_ran": (True, True, 1),
}.items():
    rows = dataset(True, False)
    set_side(rows, *shape)
    side_cases[name] = rows
unusable = dataset(True, False)
for row in unusable["C1"]:
    row.update({"gate_entered": True, "gate_released": False,
                "gate_run_count": 1, "gate_run_max_length": 32})
side_cases["gate_observation_unusable"] = unusable

for expected, rows in side_cases.items():
    rc, result = run(rows)
    present = {name for name in j.GATE_RESULTS if result[name]["present"]}
    if rc != 0 or present != {expected}:
        raise SystemExit(f"副問判定取り違え: {expected}/{sorted(present)}")

# 主問の2走不一致はunreached、関門偽はgate_failedだけになる。
rows = dataset(True, False)
rows["C2"][1]["result"] = "failure"
_rc, result = run(rows)
if not result["unreached"]["present"] or only_overall(result) != "m6i_c_inconclusive":
    raise SystemExit("2走不一致をunreachedにできない")
rc, result = run(dataset(), failed_gate="G4")
if rc != 1 or not result["gate_failed"]["present"]:
    raise SystemExit("関門偽をgate_failedにできない")

# 副問だけの2走不一致は帰属名を付けず、主問の総合判定を維持する。
rows = dataset(True, False)
for arm in ("C0", "C3"):
    rows[arm][1].update({"gate_entered": False, "gate_released": False,
                         "gate_run_count": 0, "gate_run_max_length": 0})
rc, result = run(rows)
side_present = {name for name in j.GATE_RESULTS if result[name]["present"]}
if rc != 0 or side_present or only_overall(result) != "m6i_c_sub_gate_only":
    raise SystemExit("副問2走不一致を主問から分離できない")

print("judge_m6ic_selftest: 項目数=13、総合5種・副問5種・保護3種 OK")
PY
