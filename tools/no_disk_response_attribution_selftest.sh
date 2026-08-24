#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cc -std=c99 -Wall -Wextra -Werror -I"$REPO/tools/harness/core" \
  "$REPO/tools/harness/exchange_intervention_selftest.c" \
  "$REPO/tools/harness/core/q88h_exchange_intervention.c" \
  -o "$WORK/exchange-intervention-selftest"
"$WORK/exchange-intervention-selftest"

python3 - "$REPO" <<'PY'
import importlib.util
import sys
import tempfile
from pathlib import Path

repo = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "no_disk_attribution_search", repo / "tools/search_error_response_candidate.py")
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)

official = (("main→sub", 2), ("sub→main", 256), ("main→sub", 1),
            ("sub→main", 1), ("main→sub", 5))
mixed = official[:-1] + (("main→sub", 6),)
axis = 4
if (search.extract_request_length(official, axis),
        search.extract_request_length(mixed, axis)) != (5, 6):
    raise SystemExit("NG: +0要求長を抽出できない")
print("OK: +0要求長の5対6を抽出")

twice = mixed + (("sub→main", 7),) + mixed
targets256, targets1 = search.no_disk_target_runs(twice)
if targets256 != (1, 7) or targets1 != (3, 9):
    raise SystemExit("NG: 観測区間内の同形窓を全出現数えられない")
print("OK: 同形窓が2回現れる故障注入で全対象runを列挙")

# 介入scopeは全同形窓ではなく、校正軸に属する-3/-1の一組だけでなければならない。
cal_result = search.AbstractResult(twice, (), 0, 0, "screen")
calibration = {
    "legacy_mixed": search.result_to_json(cal_result),
    "axis_mixed": 4, "target_response256": 1, "target_response1": 3,
}
specs = search.no_disk_target_specs(calibration)
if (specs["response256"]["run"], specs["response1"]["run"]) != (1, 3):
    raise SystemExit("NG: 校正軸の対象を全同形窓へ広げている")
print("OK: 複数の同形窓があっても校正軸の-3/-1だけを介入対象に限定")

# 故障注入0: 方向も長さも同じ別runへ対象番号だけをずらす。
identity_exchange = (("main→sub", 2), ("sub→main", 1),
                     ("main→sub", 2), ("sub→main", 1))
identity = {
    "run": 1, "direction": "sub→main", "length": 1,
    "context_sha256": search.run_context_sha256(identity_exchange, 1),
}
search.verify_run_identity(identity_exchange, identity)
wrong_identity = dict(identity, run=3)
try:
    search.verify_run_identity(identity_exchange, wrong_identity)
except search.SearchError as exc:
    if "文脈指紋" not in str(exc):
        raise
else:
    raise SystemExit("NG: 同一方向・同一長の別runへのずれを検出できない")
print("OK: 同一方向・同一長の別runを指す故障注入を文脈指紋で検出")

# 故障注入1: +0でなく直前runの長さを読む。
wrong = (search.extract_request_length(official, axis, "previous"),
         search.extract_request_length(mixed, axis, "previous"))
if wrong == (5, 6):
    raise SystemExit("NG: 長さ取り違え故障を検出できない")
print("OK: 長さを取り違える故障を検出")

# 故障注入2: 入力にかかわらず常に同じ長さを返す。
constant = (search.extract_request_length(official, axis, "constant"),
            search.extract_request_length(mixed, axis, "constant"))
if constant == (5, 6):
    raise SystemExit("NG: 長さ定数化故障を検出できない")
print("OK: 常に同じ長さを返す故障を検出")

tables = {
    "response256": {"control": 6, "response256": 5, "response1": 6, "both": 5},
    "response1": {"control": 6, "response256": 6, "response1": 5, "both": 5},
    "interaction_only": {"control": 6, "response256": 6, "response1": 6, "both": 5},
}
for expected, table in tables.items():
    actual = search.attribution_kind(table)
    if actual != expected:
        raise SystemExit(f"NG: 相補表 {expected} を {actual} と誤判定")
print("OK: 相補表から単独帰属と交互作用を区別")

base = search.AbstractResult((), (), 0, 0, "screen", (("main_IN_00FC", 1, "a"),))
changed = search.AbstractResult((), (), 0, 0, "screen", (("main_IN_00FC", 1, "b"),))
# 故障注入3: response256 armが介入を踏んだ体裁でも、成果物は対照をそのまま返す。
ineffective = search.ineffective_intervention_arms({
    "control": base, "response256": base, "response1": changed,
})
if ineffective != ["response256"]:
    raise SystemExit("NG: 対照と同一成果物の介入armを失敗にできない")
print("OK: 対照と同一成果物を返す介入armの故障注入を検出")

# 分類selftest: 同じ指標表でも、成果物不変なら測定失敗、成果物が変わって
# いれば「入力は指標に無影響」という有効結論に分ける。
ref_exchange = (("main→sub", 2), ("sub→main", 256), ("main→sub", 1),
                ("sub→main", 1), ("main→sub", 5))
same_exchange = ref_exchange[:-1] + (("main→sub", 6),)
reference = search.AbstractResult(ref_exchange, (), 0, 0, "screen")
control = search.AbstractResult(same_exchange, (), 0, 0, "screen",
                                (("main_IN_00FC", 1, "control"),))
changed_arms = {
    name: search.AbstractResult(same_exchange, (), 0, 0, "screen",
                                (("main_IN_00FC", 1, name),))
    for name in ("response256", "response1", "both")
}

def measured_with(arm_results):
    ordered = [("control", control)] + list(arm_results.items())
    return [(name, search.compare_result(reference, result, ordinal, request_axis=4),
             result, ()) for ordinal, (name, result) in enumerate(ordered)]

ineffective_result, bad_arms = search.attribution_outcome(measured_with({
    "response256": control,
    "response1": changed_arms["response1"],
    "both": changed_arms["both"],
}))
if (ineffective_result != "intervention_ineffective" or bad_arms != ["response256"]
        or search.attribution_exit_code(ineffective_result) != 2):
    raise SystemExit("NG: 介入不成立を測定失敗へ分類できない")
print("OK: 全指標同一かつ成果物不変の介入armを測定失敗へ分類")

no_effect_result, bad_arms = search.attribution_outcome(measured_with(changed_arms))
if (no_effect_result != "intervention_effective_no_metric_change" or bad_arms
        or search.attribution_exit_code(no_effect_result) != 0):
    raise SystemExit("NG: 成立した介入の無影響を有効結論へ分類できない")
print("OK: 全指標同一でも全介入armの成果物が変われば有効な無影響結論へ分類")

complete = search.InterventionEvidence(1, "xor-all", 256, 256, 256, 256, 256)
missed = search.InterventionEvidence(1, "xor-all", 1, 256, 1, 256, 1)
if not complete.complete or missed.complete:
    raise SystemExit("NG: 実測回数と期待回数の不一致を検出できない")
print("OK: matched/appliedの実測回数不足を検出")

def fixture(path, response_tail):
    rows = [
        (1, "OUT", "00FD", "AA", "37F4"),
        (2, "OUT", "00FD", "BB", "3811"),
        (3, "IN", "00FC", "10", "3863"),
        (4, "IN", "00FC", response_tail, "3880"),
        (5, "OUT", "00FD", "20", "37F4"),
    ]
    path.write_text("\n".join(
        f"{seq} {seq * 10} 800 main {kind} {port} {value} {pc}"
        for seq, kind, port, value, pc in rows) + "\n", encoding="utf-8")

with tempfile.TemporaryDirectory() as tmp:
    off, mix = Path(tmp) / "off.txt", Path(tmp) / "mix.txt"
    fixture(off, "11")
    fixture(mix, "12")
    first = search.first_exchange_difference(off, mix, 2, 2)
    if (first["event_position"], first["kind"],
            first["relative_to_axis_official"],
            first["relative_to_axis_mixed"]) != (3, "value", -1, -1):
        raise SystemExit("NG: 交換列先頭からの最初の値差を位置へ射影できない")
print("OK: 値を出さず交換列の最初の差異位置と軸からの距離を算出")
PY
