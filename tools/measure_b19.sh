#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO/tools/lib_l3_measure.sh"
work="${PC88_B19_WORK:-}"; dry=""; core=""
while (($#)); do
  case "$1" in
    --work) work="$2"; shift 2;;
    --dry-run-sub-rom) dry="$2"; shift 2;;
    --core) core="$2"; shift 2;;
    *) exit 2;;
  esac
done
[[ -n "$work" && ! -e "$work" ]] || exit 2
mkdir -p "$work"
if [[ -n "$dry" ]]; then sub="$dry"; else sub="${PC88_REF_ROM_DIR:?}/DISK.ROM"; fi
[[ -f "$sub" ]] || exit 2
[[ -n "$core" ]] || core="$(find_l3_core)"
[[ -f "$core" ]] || exit 1
geom=(--cylinders 40 --double-sided --sectors-per-track 16 --content-rule coord-header)
python3 "$REPO/tools/make_l3_testdisk.py" "$work/a.d88" "${geom[@]}" --disk-id 0xA1 >"$work/disk-a.log" 2>&1
python3 "$REPO/tools/make_l3_testdisk.py" "$work/b.d88" "${geom[@]}" --disk-id 0xB2 >"$work/disk-b.log" 2>&1
ensure_l3_frontend >"$work/frontend-build.log" 2>&1
for row in $(seq 1 5); do
  TMPDIR="$work" python3 "$REPO/src/build_main_rom.py" "$work/rom-$row" --inject-b19-row "$row" >"$work/build-$row.log" 2>&1
  cp "$sub" "$work/rom-$row/DISK.ROM"
  for run in 1 2; do
    prefix="$work/$row-$run"
    /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 "$REPO/tools/harness/frontend/q88measure" \
      --core "$core" --rom-dir "$work/rom-$row" --frames 2010 \
      --io-log "$prefix.io.txt" --mem-write-log "$prefix.mem.txt" --mem-write-range DF00-DF57 \
      --sub-boundary-log "$prefix.boundary.txt" --disk "$work/a.d88" --disk2 "$work/b.d88" >"$prefix.out" 2>"$prefix.err"
    python3 "$REPO/tools/analyze_b19.py" --row "$row" --run "$run" --iolog "$prefix.io.txt" --memlog "$prefix.mem.txt" --boundary "$prefix.boundary.txt" >"$prefix.tsv"
  done
done
if [[ -z "$dry" ]]; then python3 "$REPO/tools/judge_b19.py" "$work/"*.tsv >"$work/judgment.json"; fi
