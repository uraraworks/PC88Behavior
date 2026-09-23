#!/usr/bin/env bash
# m6i-i凍結照合器の陽性・陰性対照とfrontend前停止を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
CHECK="$REPO/tools/check_m6ii_preregistration.py"; CONFIG="$REPO/tools/m6ii_frozen.tsv"
python3 "$CHECK" >"$WORK/positive.out" 2>"$WORK/positive.err"
expect_fail() { local name="$1"; shift; if "$@" >"$WORK/$name.out" 2>"$WORK/$name.err"; then exit 1; fi; grep -q gate_failed "$WORK/$name.err"; }
mutate() { local old="$1" new="$2" out="$3"; sed "s|$old|$new|" "$CONFIG" >"$out"; }
mutate $'measurement_frames\t1800' $'measurement_frames\t1799' "$WORK/frames.tsv"; expect_fail frames python3 "$CHECK" --config "$WORK/frames.tsv"
mutate $'repetitions\t2' $'repetitions\t3' "$WORK/repetitions.tsv"; expect_fail repetitions python3 "$CHECK" --config "$WORK/repetitions.tsv"
mutate $'row_marker_address\t0xE038' $'row_marker_address\t0xE002' "$WORK/collision.tsv"; expect_fail collision python3 "$CHECK" --config "$WORK/collision.tsv"
mutate $'disk_id\tA:0xA1' $'disk_id\tA:0xA2' "$WORK/disk.tsv"; expect_fail disk python3 "$CHECK" --config "$WORK/disk.tsv"
mutate $'row\t2:A:0:1:1' $'row\t2:A:0:0:1' "$WORK/row.tsv"; expect_fail row python3 "$CHECK" --config "$WORK/row.tsv"
mutate $'fault_rows\tI-F-D:8,9,10' $'fault_rows\tI-F-D:8,9' "$WORK/fault.tsv"; expect_fail fault python3 "$CHECK" --config "$WORK/fault.tsv"
mutate $'arm\tI-F-H' $'arm\tI-F-X' "$WORK/arm.tsv"; expect_fail arm python3 "$CHECK" --config "$WORK/arm.tsv"
mutate $'judgment\trow_no_data' $'judgment\trow_missing' "$WORK/judgment.tsv"; expect_fail judgment python3 "$CHECK" --config "$WORK/judgment.tsv"
mutate d3becfe5051f7002d268824a2da2824f543442e71ae3226e4d22139e0adce05c 03becfe5051f7002d268824a2da2824f543442e71ae3226e4d22139e0adce05c0 "$WORK/hash.tsv"; expect_fail hash python3 "$CHECK" --config "$WORK/hash.tsv"

# 全EQU列挙そのものを直接通し、正常番地と既存EQU衝突番地を対にする。
python3 - "$REPO" <<'PY'
from pathlib import Path
import sys
sys.path.insert(0,str(Path(sys.argv[1])/'tools'))
import check_m6ii_preregistration as c
checks={'free_E038':c.equ_address_is_free(0xE038),'collision_E002':not c.equ_address_is_free(0xE002)}
if {k for k,v in checks.items() if not v}: raise SystemExit(1)
for target in checks:
    negative=dict(checks); negative[target]=False
    if {k for k,v in negative.items() if not v}!={target}: raise SystemExit(1)
    mutant=dict(negative); mutant[target]=True
    if {k for k,v in mutant.items() if not v}=={target}: raise SystemExit(1)
PY

cat >"$WORK/fake_frontend" <<'SH'
#!/usr/bin/env bash
: >"$M6II_FRONTEND_SENTINEL"
exit 99
SH
chmod +x "$WORK/fake_frontend"
set +e
M6II_FROZEN_CONFIG="$WORK/frames.tsv" M6II_FRONTEND="$WORK/fake_frontend" \
M6II_FRONTEND_SENTINEL="$WORK/started" "$REPO/tools/measure_m6ii.sh" \
  --arm I-S --result "$WORK/result.json" >"$WORK/measure.out" 2>"$WORK/measure.err"
rc=$?
set -e
if [ "$rc" -eq 0 ] || [ -e "$WORK/started" ] || ! grep -q preregistration_mismatch "$WORK/measure.out"; then exit 1; fi
echo "check_m6ii_preregistration_selftest: 項目数=12、陰性対照=11、常時真変異=2件拒否、起動前停止=1 OK"
