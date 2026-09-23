#!/usr/bin/env bash
# m6f-a凍結照合器の陽性・陰性対照とfrontend前停止を検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
CHECK="$REPO/tools/check_m6fa_preregistration.py"; CONFIG="$REPO/tools/m6fa_frozen.tsv"
python3 "$CHECK" >"$WORK/positive.out" 2>"$WORK/positive.err"; : >"$WORK/check-positive"
expect_fail() { local name="$1"; shift; if "$@" >"$WORK/$name.out" 2>"$WORK/$name.err"; then exit 1; fi; grep -q gate_failed "$WORK/$name.err"; : >"$WORK/check-$name"; }
mutate() { local old="$1" new="$2" out="$3"; sed "s|$old|$new|" "$CONFIG" >"$out"; }
mutate $'measurement_frames\t9000' $'measurement_frames\t8999' "$WORK/frames.tsv"; expect_fail frames python3 "$CHECK" --config "$WORK/frames.tsv"
mutate $'run_timeout_seconds\t300' $'run_timeout_seconds\t299' "$WORK/timeout.tsv"; expect_fail timeout python3 "$CHECK" --config "$WORK/timeout.tsv"
mutate $'repetitions\t2' $'repetitions\t3' "$WORK/repetitions.tsv"; expect_fail repetitions python3 "$CHECK" --config "$WORK/repetitions.tsv"
mutate $'reference_disk\tN88_FE.D88' $'reference_disk\tOTHER.D88' "$WORK/disk.tsv"; expect_fail disk python3 "$CHECK" --config "$WORK/disk.tsv"
mutate $'arm\tF3' $'arm\tFX' "$WORK/arm.tsv"; expect_fail arm python3 "$CHECK" --config "$WORK/arm.tsv"
mutate 'QZ7D' 'QZ7E' "$WORK/f6.tsv"; expect_fail f6 python3 "$CHECK" --config "$WORK/f6.tsv"
mutate 'D7:allocation_table_sector' 'D7:program_sector' "$WORK/d7.tsv"; expect_fail d7 python3 "$CHECK" --config "$WORK/d7.tsv"
mutate $'judgment\tnot_found' $'judgment\tmissing' "$WORK/judgment.tsv"; expect_fail judgment python3 "$CHECK" --config "$WORK/judgment.tsv"

cat >"$WORK/fake_frontend" <<'SH'
#!/usr/bin/env bash
: >"$M6FA_FRONTEND_SENTINEL"
exit 99
SH
chmod +x "$WORK/fake_frontend"
set +e
M6FA_FROZEN_CONFIG="$WORK/frames.tsv" M6FA_FRONTEND="$WORK/fake_frontend" \
M6FA_FRONTEND_SENTINEL="$WORK/started" "$REPO/tools/measure_m6fa.sh" \
  --raw-dir "$WORK/raw" --result "$WORK/result.json" >"$WORK/measure.out" 2>"$WORK/measure.err"
rc_bad=$?
env -u PC88_REF_ROM_DIR -u PC88_REF_DISK_DIR M6FA_FRONTEND="$WORK/fake_frontend" \
M6FA_FRONTEND_SENTINEL="$WORK/started2" "$REPO/tools/measure_m6fa.sh" \
  --raw-dir "$WORK/raw2" --result "$WORK/result2.json" >"$WORK/missing.out" 2>"$WORK/missing.err"
rc_missing=$?
mkdir -p "$WORK/dummy-rom"
env -u PC88_REF_DISK_DIR PC88_REF_ROM_DIR="$WORK/dummy-rom" M6FA_FRONTEND="$WORK/fake_frontend" \
M6FA_FRONTEND_SENTINEL="$WORK/started3" "$REPO/tools/measure_m6fa.sh" \
  --raw-dir "$WORK/raw3" --result "$WORK/result3.json" >"$WORK/missing-disk.out" 2>"$WORK/missing-disk.err"
rc_missing_disk=$?
set -e
[ "$rc_bad" -ne 0 ] && [ ! -e "$WORK/started" ] && grep -q preregistration_mismatch "$WORK/measure.out"
[ "$rc_bad" -ne 0 ] && : >"$WORK/check-start_bad_config"
[ "$rc_missing" -ne 0 ] && [ ! -e "$WORK/started2" ] && grep -q PC88_REF_ROM_DIR_missing "$WORK/missing.out"
[ "$rc_missing" -ne 0 ] && : >"$WORK/check-start_missing_env"
[ "$rc_missing_disk" -ne 0 ] && [ ! -e "$WORK/started3" ] && grep -q PC88_REF_DISK_DIR_missing "$WORK/missing-disk.out"
[ "$rc_missing_disk" -ne 0 ] && : >"$WORK/check-start_missing_disk_env"
bash -n "$REPO/tools/measure_m6fa.sh"; : >"$WORK/check-shell_syntax"
python3 - "$WORK" <<'PY'
import sys
from pathlib import Path
w=Path(sys.argv[1])
expected={'positive','frames','timeout','repetitions','disk','arm','f6','d7','judgment',
          'start_bad_config','start_missing_env','start_missing_disk_env','shell_syntax'}
found={p.name.removeprefix('check-') for p in w.glob('check-*')}
if found!=expected: raise SystemExit('NG集合 '+str(expected-found)+' extra='+str(found-expected))
checks={x:True for x in expected}
for target in checks:
    negative=dict(checks); negative[target]=False
    if {k for k,v in negative.items() if not v}!={target}: raise SystemExit('NG集合 '+target)
    mutant=dict(negative); mutant[target]=True
    if {k for k,v in mutant.items() if not v}=={target}: raise SystemExit('常時真変異 '+target)
PY
echo "check_m6fa_preregistration_selftest: 項目数=13、陰性対照=11、常時真変異=13件拒否、起動前停止=3 OK"
