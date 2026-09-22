#!/usr/bin/env bash
# m6i-b B0〜B6の同期ドライバ。既存q88measure経路だけを使う。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
FRONTEND="$REPO/tools/harness/frontend/q88measure"

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
  B6-A5) frames=6000; alarm_seconds=600 ;;
  *) frames=600; alarm_seconds=180 ;;
esac

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CORE="$(find_l3_core)"
[ -n "$CORE" ] && ensure_l3_frontend || exit 1

python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/generated.d88" \
  --cylinders 40 --double-sided --sectors-per-track 16 \
  >"$WORK/disk.out" 2>"$WORK/disk.err" || exit 1
disk_sha="$(shasum -a 256 "$WORK/generated.d88" | awk '{print $1}')"
[ "$disk_sha" = d3becfe5051f7002d268824a2da2824f543442e71ae3226e4d22139e0adce05c ] || exit 1

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
