#!/usr/bin/env bash
# 追補1の143腕を自作HEADで測り、公式期待値と照合する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${1:-$REPO/tmp/s9y-work/results-conform}"
case "$WORK" in /*) ;; *) echo '作業先は絶対パス必須' >&2; exit 2;; esac
mkdir -p "$WORK"
python3 "$REPO/src/build_main_rom.py" "$WORK/rom" --work-dir "$WORK/asm" >"$WORK/build.log" 2>&1
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_dim_results.py" measure \
  --rom-dir "$WORK/rom" --work-dir "$WORK/measure" --out "$WORK/own.tsv"
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_dim_results.py" check \
  --expected "$REPO/tests/conformance/expected_l4_dim.tsv" --measured "$WORK/own.tsv"
