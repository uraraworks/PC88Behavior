#!/usr/bin/env bash
# m6i-d G5: 全区間のゲートrun 3状態と、最後のrun基準の陰性対照。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO" <<'PY'
from pathlib import Path
import sys

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / "tools"))
import analyze_main_to_sub as m2s
import analyze_m6id as a


def event(seq, clock, cpu, kind, port):
    return m2s.Ev(seq, clock, 1, cpu, kind, port, 0, "0000")


# 32未満はゲートrunではない。
no_run = [event(i + 1, i + 1, "sub", "IN", "00FE") for i in range(31)]
runs, released = a.gate_observation(no_run, 32)
if runs or released:
    raise SystemExit("G5ゲートrunなしを識別できない")

# m6i-cならラウンド#0応答より前として除外した位置にrunを置く。
# m6i-dは全区間を見るため、この早いrunも検出し、その後のsub I/Oで解除とする。
early = [event(i + 1, 10 + i, "sub", "IN", "00FE") for i in range(32)]
early += [event(33, 50, "sub", "OUT", "00FD"),
          event(34, 60, "sub", "OUT", "00F8")]
runs, released = a.gate_observation(early, 32)
if len(runs) != 1 or runs[0].length != 32 or not released:
    raise SystemExit("G5全区間の解除runを識別できない")

permanent = [event(i + 1, 10 + i, "sub", "IN", "00FE") for i in range(32)]
runs, released = a.gate_observation(permanent, 32)
if len(runs) != 1 or released:
    raise SystemExit("G5最後まで未解除のrunを識別できない")

# 1本目だけ解除され、2本目は最後まで続く。最後のrun基準なら未解除である。
two = [event(i + 1, 10 + i, "sub", "IN", "00FE") for i in range(32)]
two.append(event(33, 50, "sub", "OUT", "00F8"))
two.extend(event(34 + i, 60 + i, "sub", "IN", "00FE") for i in range(32))
runs, released = a.gate_observation(two, 32)
old_released = any(
    row.cpu == "sub" and not (row.kind == "IN" and row.port == "00FE")
    and row.clock > run.end_clock for run in runs for row in two
)
if len(runs) != 2 or released or not old_released:
    raise SystemExit("G5最後のrun基準の陰性対照を検出できない")

print("analyze_m6id_selftest: 項目数=4、G5の3状態・最後のrun陰性対照 OK")
PY
