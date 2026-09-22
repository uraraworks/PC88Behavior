#!/usr/bin/env bash
# m6i-b B1/B2/B5の同期ドライバ。既存q88measure経路だけを使う。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
FRONTEND="$REPO/tools/harness/frontend/q88measure"

arm=""
result=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --arm) arm="${2:-}"; shift 2 ;;
    --result) result="${2:-}"; shift 2 ;;
    *) exit 2 ;;
  esac
done
case "$arm" in B1|B2|B5) ;; *) exit 2 ;; esac
[ -n "$result" ] && [ -d "$(dirname "$result")" ] || exit 2

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CORE="$(find_l3_core)"
[ -n "$CORE" ] && ensure_l3_frontend || exit 1

python3 "$REPO/tools/make_l3_testdisk.py" "$WORK/generated.d88" \
  --cylinders 40 --double-sided --sectors-per-track 16 \
  >"$WORK/disk.out" 2>"$WORK/disk.err" || exit 1
python3 "$REPO/tools/build_m6ib_measure_rom.py" "$WORK/rom" --arm "$arm" \
  --work-dir "$WORK/asm" >"$WORK/build.out" 2>"$WORK/build.err" || exit 1

/usr/bin/perl -e 'alarm shift; exec @ARGV' 180 "$FRONTEND" \
  --core "$CORE" --rom-dir "$WORK/rom" --disk "$WORK/generated.d88" \
  --frames 120 --io-log "$WORK/run.io.txt" \
  --mem-write-log "$WORK/run.mem.txt" --mem-write-range DF00-E00C \
  >"$WORK/run.stdout.txt" 2>"$WORK/run.stderr.txt" || exit 1

extra_stop=""
if [ "$arm" = B1 ]; then
  python3 "$REPO/tools/build_m6ib_measure_rom.py" "$WORK/stop-rom" --arm B1 \
    --work-dir "$WORK/stop-asm" >"$WORK/stop-build.out" 2>"$WORK/stop-build.err" || exit 1
  /usr/bin/perl -e 'alarm shift; exec @ARGV' 180 "$FRONTEND" \
    --core "$CORE" --rom-dir "$WORK/stop-rom" --disk "$WORK/generated.d88" \
    --frames 60 --io-log "$WORK/stop-report.io.txt" \
    >"$WORK/stop-report" 2>"$WORK/stop.stderr.txt" || exit 1
  extra_stop="$WORK/stop-report"
fi

if [ -n "$extra_stop" ]; then
  python3 "$REPO/tools/analyze_m6ib_first_request.py" --arm "$arm" \
    --iolog "$WORK/run.io.txt" --memlog "$WORK/run.mem.txt" \
    --rom-dir "$WORK/rom" --stop-report "$extra_stop" | tee "$result"
else
  python3 "$REPO/tools/analyze_m6ib_first_request.py" --arm "$arm" \
    --iolog "$WORK/run.io.txt" --memlog "$WORK/run.mem.txt" \
    --rom-dir "$WORK/rom" | tee "$result"
fi
exit "${PIPESTATUS[0]}"
