#!/usr/bin/env bash
# 公式ROMは使わない。固定期待値との照合・陰性対照・自作ROMで器具を検査。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -eq 0 ]; then
  set -- --work-dir "$REPO/tmp/s9x-work/selftest"
fi
python3 "$REPO/tools/l4_getput_measure.py" selftest "$@"
