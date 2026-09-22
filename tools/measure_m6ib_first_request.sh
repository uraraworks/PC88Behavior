#!/usr/bin/env bash
# m6i-b B0〜B6の同期ドライバ。既存q88measure経路だけを使う。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FROZEN_CONFIG="${M6IB_FROZEN_CONFIG:-$REPO/tools/m6ib_frozen.tsv}"
if ! python3 "$REPO/tools/check_m6ib_preregistration.py" --config "$FROZEN_CONFIG"; then
  printf '%s\n' '{"judgment":"gate_failed","reason":"preregistration_mismatch"}'
  exit 1
fi
source "$REPO/tools/lib_l3_measure.sh"
FRONTEND="${M6IB_FRONTEND:-$REPO/tools/harness/frontend/q88measure}"

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
    --g7-fault) fault="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
case "$arm" in
  B0|B1|B2|B3|B4|B5|B6-A0|B6-A1|B6-A2|B6-A4-cont|B6-A4-pair|B6-A5) ;;
  *) exit 2 ;;
esac
[ -n "$result" ] && [ -d "$(dirname "$result")" ] || exit 2

expected_fault=""
case "$arm" in
  B0) expected_fault=b0_send ;;
  B1) expected_fault=b1_sub_step ;;
  B2) expected_fault=b2_recv ;;
  B3) expected_fault=b3_init_batch ;;
  B4) expected_fault=b4_round0_insert ;;
  B5) expected_fault=b5_round0_delete ;;
  B6-*) expected_fault=b6_reach ;;
esac
if [ -n "$fault" ] && [ "$fault" != "$expected_fault" ]; then exit 2; fi

case "$arm" in
  B6-A5) frames="$(cfg b6_a5_frames)"; alarm_seconds=600 ;;
  B6-*) frames="$(cfg b6_a0_a4_frames)"; alarm_seconds=180 ;;
  B5) frames="$(cfg b5_frames)"; alarm_seconds=180 ;;
  *) frames="$(cfg b0_b4_frames)"; alarm_seconds=180 ;;
esac

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CORE="$(find_l3_core)"
[ -n "$CORE" ] && ensure_l3_frontend || exit 1

python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/generated.d88" \
  --cylinders 40 --double-sided --sectors-per-track 16 \
  >"$WORK/disk.out" 2>"$WORK/disk.err" || exit 1
disk_sha="$(shasum -a 256 "$WORK/generated.d88" | awk '{print $1}')"
[ "$disk_sha" = "$(cfg normal_media_sha256)" ] || exit 1

python3 "$REPO/tools/build_m6ib_measure_rom.py" "$WORK/rom" --arm "$arm" \
  --work-dir "$WORK/asm" >"$WORK/build.out" 2>"$WORK/build.err" || exit 1

key_frame=$((frames - 50))
qargs=(--core "$CORE" --rom-dir "$WORK/rom" --frames "$frames"
       --io-log "$WORK/run.io.txt" --int-log "$WORK/run.int.txt"
       --mem-write-log "$WORK/run.mem.txt" --mem-write-range DF00-E038
       --out "$WORK/run.report.txt" --key-matrix "0x04:1:${key_frame}:10")
if [ "$arm" != B6-A2 ]; then qargs+=(--disk "$WORK/generated.d88"); fi
/usr/bin/perl -e 'alarm shift; exec @ARGV' "$alarm_seconds" "$FRONTEND" \
  "${qargs[@]}" >"$WORK/run.stdout.txt" 2>"$WORK/run.stderr.txt" || exit 1

extra_stop=()
if [ "$arm" = B1 ]; then
  /usr/bin/perl -e 'alarm shift; exec @ARGV' 180 "$FRONTEND" \
    --core "$CORE" --rom-dir "$WORK/rom" --disk "$WORK/generated.d88" \
    --frames 60 --io-log "$WORK/stop-report.io.txt" \
    >"$WORK/stop-report" 2>"$WORK/stop.stderr.txt" || exit 1
  extra_stop+=(--stop-report "$WORK/stop-report")
fi
extra_fault=()
if [ -n "$fault" ]; then extra_fault+=(--fault "$fault"); fi

python3 "$REPO/tools/analyze_m6ib_first_request.py" --arm "$arm" \
  --iolog "$WORK/run.io.txt" --memlog "$WORK/run.mem.txt" \
  --report "$WORK/run.report.txt" --intlog "$WORK/run.int.txt" \
  --rom-dir "$WORK/rom" \
  ${extra_stop[@]+"${extra_stop[@]}"} ${extra_fault[@]+"${extra_fault[@]}"} \
  | tee "$result"
exit "${PIPESTATUS[0]}"
