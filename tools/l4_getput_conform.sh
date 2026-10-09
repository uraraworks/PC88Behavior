#!/usr/bin/env bash
# 自作ROMを測定し、次回生成する公式の期待値と比較する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${1:-$REPO/tmp/s9x-work/conform}"
EXPECTED="$REPO/tests/conformance/expected_l4_getput.tsv"
case "$WORK" in /*) ;; *) echo '作業ディレクトリは絶対パス必須' >&2; exit 2;; esac
if [ ! -f "$EXPECTED" ]; then
  echo '公式期待値は未作成（第1回では測定しない）' >&2
  exit 2
fi
shift $(( $# > 0 ? 1 : 0 ))
mkdir -p "$WORK"
python3 "$REPO/src/build_main_rom.py" "$WORK/rom" --work-dir "$WORK/asm" >"$WORK/build.log" 2>&1
python3 "$REPO/tools/l4_getput_measure.py" measure --rom-dir "$WORK/rom" --no-calibration \
  --out "$WORK/own.tsv" --work-dir "$WORK/measure" "$@"
python3 "$REPO/tools/l4_getput_measure.py" check --expected "$EXPECTED" --measured "$WORK/own.tsv" "$@"
