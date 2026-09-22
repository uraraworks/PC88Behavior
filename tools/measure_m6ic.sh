#!/usr/bin/env bash
# m6i-c C0〜C3の同期ドライバ。測定前にG3/G9、次にG4を必ず通す。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FROZEN_CONFIG="${M6IC_FROZEN_CONFIG:-$REPO/tools/m6ic_frozen.tsv}"
if ! python3 "$REPO/tools/check_m6ic_preregistration.py" --config "$FROZEN_CONFIG"; then
  printf '%s\n' '{"judgment":"gate_failed","reason":"preregistration_mismatch"}'
  exit 1
fi

source "$REPO/tools/lib_l3_measure.sh"
FRONTEND="${M6IC_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"

cfg() {
  awk -F '\t' -v key="$1" '$1==key { if (++n==1) value=$2 } END { if (n==1) print value; else exit 1 }' "$FROZEN_CONFIG"
}

arm=""
result=""
fault=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arm) arm="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    --g6-fault) fault="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
case "$arm" in C0|C1|C2|C3) ;; *) exit 2 ;; esac
[ -n "$result" ] && [ -d "$(dirname "$result")" ] || exit 2
case "$fault" in
  ""|preamble_marker_deleted|read_issue_frame_changed|gate_run_deleted|request_counter_fixed) ;;
  *) exit 2 ;;
esac

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 4腕を生成してG4を通すまではfrontendへ到達しない。
for gate_arm in C0 C1 C2 C3; do
  python3 "$REPO/tools/build_m6ic_measure_rom.py" "$WORK/rom-$gate_arm" \
    --arm "$gate_arm" --work-dir "$WORK/build-$gate_arm" \
    >"$WORK/build-$gate_arm.out" 2>"$WORK/build-$gate_arm.err" || {
      printf '%s\n' '{"judgment":"gate_failed","reason":"rom_build_failed"}' | tee "$result"
      exit 1
    }
done
if ! python3 "$REPO/tools/check_m6ic_rom_gate.py" \
    "$WORK/rom-C0" "$WORK/rom-C1" "$WORK/rom-C2" "$WORK/rom-C3" \
    --config "$FROZEN_CONFIG" >"$WORK/rom-gate.out" 2>"$WORK/rom-gate.err"; then
  printf '%s\n' '{"judgment":"gate_failed","reason":"rom_gate_failed"}' | tee "$result"
  exit 1
fi

python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/generated.d88" \
  --cylinders 40 --double-sided --sectors-per-track 16 \
  >"$WORK/disk.out" 2>"$WORK/disk.err" || exit 1
disk_sha="$(shasum -a 256 "$WORK/generated.d88" | awk '{print $1}')"
if [ "$disk_sha" != "$(cfg normal_media_sha256)" ]; then
  printf '%s\n' '{"judgment":"gate_failed","reason":"media_sha_mismatch"}' | tee "$result"
  exit 1
fi

CORE="$(find_l3_core)"
[ -n "$CORE" ] && ensure_l3_frontend || exit 1
frames="$(cfg arm_frames)"
alarm_seconds=180
key_frame=$((frames - 50))
qargs=(--core "$CORE" --rom-dir "$WORK/rom-$arm" --frames "$frames"
       --io-log "$WORK/run.io.txt" --int-log "$WORK/run.int.txt"
       --mem-write-log "$WORK/run.mem.txt" --mem-write-range DF00-E038
       --out "$WORK/run.report.txt" --key-matrix "0x04:1:${key_frame}:10"
       --disk "$WORK/generated.d88")
/usr/bin/perl -e 'alarm shift; exec @ARGV' "$alarm_seconds" "$FRONTEND" \
  "${qargs[@]}" >"$WORK/run.stdout.txt" 2>"$WORK/run.stderr.txt" || exit 1

extra_fault=()
if [ -n "$fault" ]; then extra_fault+=(--fault "$fault"); fi
python3 "$REPO/tools/analyze_m6ic.py" --arm "$arm" \
  --iolog "$WORK/run.io.txt" --memlog "$WORK/run.mem.txt" \
  --report "$WORK/run.report.txt" --intlog "$WORK/run.int.txt" \
  --rom-dir "$WORK/rom-$arm" --config "$FROZEN_CONFIG" \
  ${extra_fault[@]+"${extra_fault[@]}"} | tee "$result"
exit "${PIPESTATUS[0]}"
