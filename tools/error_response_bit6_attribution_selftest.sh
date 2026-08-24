#!/usr/bin/env bash
# 公式環境なしでmeasure_once戻り値とbit6判定関数の型契約を検査する。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO" <<'PY'
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "tools"))
import error_response_bit6_attribution as attribution
import search_error_response_candidate as search

exchange = tuple(("main→sub", 6) if pos % 2 == 0 else ("sub→main", 1)
                 for pos in range(60))
reference = search.AbstractResult(exchange, tuple("R" for _ in range(60)),
                                  *attribution.EXPECTED_SCREEN)
default = search.AbstractResult(exchange, tuple("D" for _ in range(55)),
                                *attribution.EXPECTED_SCREEN)
broken = search.AbstractResult(exchange[:38] + (("main→sub", 2),),
                               tuple("B" for _ in range(55)), 0, 0, "0" * 64)
measurements = ((reference, {}), (default, {}), (broken, {}))

passed, _, _ = attribution.judge_measurements(*measurements)
if not passed:
    raise SystemExit("NG: measure_onceの(result, receipts)型をbit6判定へ渡せない")
print("OK: 合成measure_once戻り値を展開し、bit6判定関数まで型が整合")

# 故障注入: 今回の回帰と同じく、タプルを展開せずcompare_resultへ渡す。
try:
    search.compare_result(measurements[0], measurements[1], 0)
except AttributeError as exc:
    if "exchange" not in str(exc):
        raise
else:
    raise SystemExit("NG: 未展開タプルの型不整合を検出できない")
print("OK: 未展開タプルを渡す同型の故障注入を検出")
PY
