#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO" <<'PY'
import importlib.util
import sys
from pathlib import Path

repo = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location(
    "ready_sweep", repo / "tools/search_error_response_candidate.py")
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)

if search.READY_SHIFT_SWEEP != tuple(range(-5, 9)):
    raise SystemExit("NG: 掃引範囲が-5..+8でない")
if not (-3 in search.READY_SHIFT_SWEEP and 0 in search.READY_SHIFT_SWEEP
        and min(5 + x for x in search.READY_SHIFT_SWEEP) == 0
        and max(5 + x for x in search.READY_SHIFT_SWEEP) == 13):
    raise SystemExit("NG: 公式2clockまたは混成5clock前後を覆わない")
print("OK: 掃引-5..+8は名目0..13clockを覆い公式2/混成5を含む")

try:
    search.ready_sweep_no_disk(None)
except search.SearchError as exc:
    if "ready-handoff-probe" not in str(exc):
        raise SystemExit("NG: 無効な旧数値掃引が新probeを案内しない")
else:
    raise SystemExit("NG: state0方式の旧数値掃引が停止しない")
print("OK: 無効なstate0数値掃引は結論生成前に停止")

if search.validate_ready_shift(-3, -3, 5, 2) != -3:
    raise SystemExit("NG: 指定量どおりの実効shiftを受理できない")
for kwargs in ({"requested": -3, "applied": -2, "control_clock": 5, "ready_clock": 2},
               {"requested": -3, "applied": -3, "control_clock": 5, "ready_clock": 3},
               {"requested": -3, "applied": -3, "control_clock": 5,
                "ready_clock": 2, "fault": 1}):
    try:
        search.validate_ready_shift(**kwargs)
    except search.SearchError:
        pass
    else:
        raise SystemExit("NG: 指定/適用/実測clockの量ずれ故障を検出できない")
print("OK: 指定・コア適用・実測clock差の三者一致と量ずれ故障注入を検出")

if search.READY_HANDOFF_ARMS != (("handoff_now", "now", 1),
                                 ("defer_once", "defer-once", 2)):
    raise SystemExit("NG: PIO handoffの即時/一回抑止armが揃っていない")
print("OK: 新probeは実支配点PIO handoffの即時/一回抑止を比較")

sources = {"control": "a" * 64, "shift_-3": "b" * 64, "shift_+1": "c" * 64}
if len(set(sources.values())) != len(sources):
    raise SystemExit("NG: arm別metric_sourceを区別できない")
print("OK: armごとに異なるmetric_sourceを要求する契約")
PY
