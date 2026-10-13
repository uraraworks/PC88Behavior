#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${1:-$REPO/tmp/s9z-impl-work/conform}"
EXPECTED="$REPO/tests/conformance/expected_l4_input.tsv"
if [ "$#" -gt 0 ]; then shift; fi
case "$WORK" in "$REPO"/tmp/s9z-work/*|"$REPO"/tmp/s9z-impl-work/*) ;; *) echo '作業先はtmp/s9z-workまたはtmp/s9z-impl-work内の絶対パス必須' >&2; exit 2;; esac
if [ ! -f "$EXPECTED" ]; then echo '公式期待値未作成（第1回は公式を実行しない）' >&2; exit 2; fi
mkdir -p "$WORK" "$WORK/temp"
export TMPDIR="$WORK/temp"
# ビルド出力も捕捉し、画面本文をツール出力へ流さない。
if ! python3 "$REPO/src/build_main_rom.py" "$WORK/rom" --work-dir "$WORK/asm" >"$WORK/build.log" 2>&1; then
  echo '自作ROMビルド失敗' >&2; exit 1
fi
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_input_measure.py" measure --rom-dir "$WORK/rom" --work-dir "$WORK/measure" --out "$WORK/own.tsv" "$@"
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_input_measure.py" check --expected "$EXPECTED" --measured "$WORK/own.tsv"
