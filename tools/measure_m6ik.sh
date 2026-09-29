#!/usr/bin/env bash
# m6i-k 器具。通常は6腕×2走、--dry-run-sub-romでは6腕×1走。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
work="${PC88_M6IK_WORK:-}"; g1=""; dry=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --work) work="${2:-}"; shift 2 ;;
    --g1-result) g1="${2:-}"; shift 2 ;;
    --dry-run-sub-rom) dry="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
[ -n "$work" ] && [ ! -e "$work" ] || exit 2
gate_failed() { printf '{"judgment":"gate_failed","reason":"%s"}\n' "$1"; exit 1; }
mkdir -p "$work"
python3 "$REPO/tools/check_m6ik_preregistration.py" >"$work/g8.out" 2>"$work/g8.err" || gate_failed G8
[ -n "$g1" ] && [ -f "$g1" ] && grep -q -E '^rc=0$' "$g1" \
  && grep -q -E 'tools/' "$g1" || gate_failed G1
"$REPO/tools/check_cleanroom.sh" >"$work/g2.out" 2>"$work/g2.err" || gate_failed G2
if [ -z "$dry" ] && [ -n "$(git -C "$REPO" status --porcelain)" ]; then gate_failed G6_dirty; fi
"$REPO/tools/analyze_m6ik_selftest.sh" >"$work/g7-g9.out" 2>"$work/g7-g9.err" || gate_failed G7_G9
"$REPO/tools/judge_m6ik_selftest.sh" >"$work/judge-selftest.out" 2>"$work/judge-selftest.err" || gate_failed G8_judge
"$REPO/tools/check_m6ik_preregistration_selftest.sh" >"$work/prereg-selftest.out" 2>"$work/prereg-selftest.err" || gate_failed G8_selftest
GEOM=(--cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header)
python3 "$REPO/tools/make_l3_testdisk.py" "$work/a.d88" "${GEOM[@]}" --disk-id 0xA1 >"$work/disk-a.out" 2>"$work/disk-a.err" || gate_failed G3
python3 "$REPO/tools/make_l3_testdisk.py" "$work/b.d88" "${GEOM[@]}" --disk-id 0xB2 >"$work/disk-b.out" 2>"$work/disk-b.err" || gate_failed G3
if [ -n "$dry" ]; then sub="$dry"; else
  [ -n "${PC88_REF_ROM_DIR:-}" ] || gate_failed G4
  sub="$PC88_REF_ROM_DIR/DISK.ROM"
fi
for arm in K-00 K-01 K-F0 K-F1 K-M1 K-FR; do
  python3 "$REPO/src/build_main_rom.py" "$work/rom-$arm" --inject-m6ik-arm "$arm" \
    --work-dir "$work/build-$arm" >"$work/build-$arm.out" 2>"$work/build-$arm.err" || gate_failed G5
  cp "$sub" "$work/rom-$arm/DISK.ROM" || gate_failed G4
done
extra=(); [ -z "$dry" ] || extra=(--dry-run)
python3 "$REPO/tools/check_m6ik_gates.py" --work "$work" --sub-rom "$sub" \
  ${extra[@]+"${extra[@]}"} >"$work/g3-g6.out" 2>"$work/g3-g6.err" || gate_failed G3_G4_G5_G6
CORE="$(find_l3_core)"; [ -n "$CORE" ] || gate_failed core_missing
ensure_l3_frontend >"$work/frontend-build.out" 2>"$work/frontend-build.err" || gate_failed frontend_missing
FRONTEND="${M6IK_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"
runs=2; [ -z "$dry" ] || runs=1
for arm in K-00 K-01 K-F0 K-F1 K-M1 K-FR; do
  for run in $(seq 1 "$runs"); do
    prefix="$work/$arm-$run"
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 300 "$FRONTEND" \
      --core "$CORE" --rom-dir "$work/rom-$arm" --frames 2010 \
      --io-log "$prefix.io.txt" --mem-write-log "$prefix.mem.txt" \
      --mem-write-range DF00-E03B --disk "$work/a.d88" --disk2 "$work/b.d88" \
      >"$prefix.frontend.out" 2>"$prefix.frontend.err" || gate_failed emulator_run
    if python3 "$REPO/tools/analyze_m6ik.py" --arm "$arm" --iolog "$prefix.io.txt" \
        --memlog "$prefix.mem.txt" >"$prefix.json"; then
      :
    else
      rc=$?; [ "$rc" -eq 1 ] || gate_failed analysis
    fi
    if [ -n "$dry" ]; then
      python3 - "$prefix.json" <<'PY'
import json,sys
p=sys.argv[1]; v=json.load(open(p)); v['dry_run']=True
with open(p,'w') as f: json.dump(v,f,sort_keys=True,separators=(',',':'))
PY
    fi
    python3 - "$prefix.json" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); print(v['arm'],v['reached'],
  ','.join(r['classification'] for r in v['rows']))
PY
  done
done
if [ -z "$dry" ]; then
  judge_args=()
  for gate in G1 G2 G3 G4 G5 G6 G7 G8 G9; do judge_args+=(--gate "$gate=true"); done
  for arm in K-00 K-01 K-F0 K-F1 K-M1 K-FR; do
    for run in 1 2; do judge_args+=(--result "$work/$arm-$run.json"); done
  done
  python3 "$REPO/tools/judge_m6ik.py" "${judge_args[@]}" >"$work/judgment.json" || gate_failed judgment
fi
printf 'm6i-k %s: 6腕×%s走 完了\n' "${dry:+試走}" "$runs"
