#!/usr/bin/env bash
# m6i-d判定器の総合6種、副問2種、腕別名、2走不一致を合成JSONで検査する。
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
import judge_m6id as j

DIGEST = "1" * 64


def dataset(never=(), not_entered=()):
    rows = {}
    for arm in j.ARMS:
        control = arm in j.CONTROL_ARMS
        entered = False if control or arm in not_entered else True
        released = entered and arm not in never
        row = {
            "arm": arm, "reached": True,
            "gate_entered": entered, "gate_released": released,
            "gate_run_count": int(entered),
            "gate_run_max_length": 32 if entered else 0,
            "rom_set_sha256": DIGEST,
        }
        rows[arm] = [copy.deepcopy(row), copy.deepcopy(row)]
    return rows


def run(rows, failed_gate=None):
    with tempfile.TemporaryDirectory(dir=scratch) as raw:
        tmp = Path(raw)
        cmd = [sys.executable, str(repo / "tools/judge_m6id.py")]
        for gate in j.GATES:
            cmd += ["--gate", f"{gate}={'false' if gate == failed_gate else 'true'}"]
        index = 0
        for arm in j.ARMS:
            for row in rows[arm]:
                path = tmp / f"{index}.json"
                path.write_text(json.dumps(row, sort_keys=True), encoding="utf-8")
                cmd += ["--result", str(path)]
                index += 1
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=False)
    payload = json.loads(proc.stdout)
    return proc.returncode, {row["judgment"]: row for row in payload["judgments"]}


def present(result, names):
    return {name for name in names if result[name]["present"]}


# 総合6種。B1は指定の追補1回帰入力で、未検証複数との併記も確認する。
cases = {}
unusable = dataset()
for row in unusable["D-B0"]:
    row.update(gate_entered=True, gate_released=False,
               gate_run_count=1, gate_run_max_length=32)
cases["m6i_d_observation_unusable"] = unusable
inconclusive = dataset()
for row in inconclusive["D-B3"]:
    row["reached"] = False
cases["m6i_d_inconclusive"] = inconclusive
cases["m6i_d_only_b5_unverified"] = dataset(("D-B5",))
cases["m6i_d_b1_control_void"] = dataset(("D-B5",), ("D-B1",))
cases["m6i_d_multiple_arms_unverified"] = dataset(("D-B3", "D-B5"))
cases["m6i_d_no_arm_unverified"] = dataset()

for expected, rows in cases.items():
    rc, result = run(rows)
    got = present(result, j.OVERALL)
    if rc != 0 or expected not in got:
        raise SystemExit(f"総合判定取り違え: {expected}/{sorted(got)}")
    if expected == "m6i_d_b1_control_void" and got != {
            "m6i_d_b1_control_void", "m6i_d_multiple_arms_unverified"}:
        raise SystemExit("B1未到達を複数未検証と併記できない、またはonly B5になった")

# 追補前の実装ではnever_releasedだけを数え、B1未到達をどこにも置けない。
regression = cases["m6i_d_b1_control_void"]
legacy_per_arm = {
    arm: ("arm_gate_not_entered" if not regression[arm][0]["gate_entered"]
          else "arm_gate_released" if regression[arm][0]["gate_released"]
          else "arm_gate_never_released")
    for arm in j.AUDIT_ARMS
}
legacy_never = {arm for arm, value in legacy_per_arm.items()
                if value == "arm_gate_never_released"}
legacy_overall = set()
if legacy_never == {"D-B5"} and all(
        legacy_per_arm[arm] == "arm_gate_released" for arm in j.AUDIT_ARMS[:-1]):
    legacy_overall.add("only_b5")
if "D-B1" in legacy_never:
    legacy_overall.add("b1_control_void")
if len(legacy_never) >= 2:
    legacy_overall.add("multiple")
if not legacy_never and all(value == "arm_gate_released"
                            for value in legacy_per_arm.values()):
    legacy_overall.add("no_arm")
if legacy_never != {"D-B5"} or legacy_overall:
    raise SystemExit("追補前ロジックを識別する回帰入力になっていない")

# 副問2種を、それぞれ専用入力で確認する。
for expected, rows in {
    "m6i_b_b2_b4_survive": dataset(("D-B5",)),
    "m6i_b_b2_b4_do_not_survive": dataset(not_entered=("D-B2",)),
}.items():
    rc, result = run(rows)
    if rc != 0 or present(result, j.SURVIVAL) != {expected}:
        raise SystemExit(f"副問判定取り違え: {expected}")

# 腕別3種・対照2種を個別に出せること。
rows = dataset(("D-B2",), ("D-B3",))
rc, result = run(rows)
expected_arm_names = {"arm_gate_released", "arm_gate_never_released",
                      "arm_gate_not_entered", "control_no_gate_run"}
if rc != 0 or not expected_arm_names <= present(result, (*j.ARM_RESULTS, *j.CONTROL_RESULTS)):
    raise SystemExit("腕別判定名を独立に出せない")
rows = dataset()
for row in rows["D-B6-A0"]:
    row.update(gate_entered=True, gate_released=False,
               gate_run_count=1, gate_run_max_length=32)
rc, result = run(rows)
if rc != 0 or not result["control_gate_run_observed"]["present"]:
    raise SystemExit("対照run観測を出せない")

# 観測またはROM SHAの2走不一致はいずれもunreached。
rows = dataset()
rows["D-B4"][1].update(gate_released=False)
rc, result = run(rows)
if rc != 0 or not result["unreached"]["present"] \
        or not result["m6i_d_inconclusive"]["present"]:
    raise SystemExit("観測2走不一致をunreachedにできない")
rows = dataset()
rows["D-B4"][1]["rom_set_sha256"] = "2" * 64
rc, result = run(rows)
if rc != 0 or not result["unreached"]["present"]:
    raise SystemExit("ROM SHAの2走不一致をunreachedにできない")

rc, result = run(dataset(), failed_gate="G4")
if rc != 1 or not result["gate_failed"]["present"]:
    raise SystemExit("関門偽をgate_failedにできない")

print("judge_m6id_selftest: 項目数=17、総合6種・副問2種・腕別5種・保護3種・旧ロジック識別1種 OK（B1未到達併記確認済み）")
PY
