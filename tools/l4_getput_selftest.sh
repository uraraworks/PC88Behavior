#!/usr/bin/env bash
# 公式ROM・公式期待値を開かない。陰性対照と自作HEADのみ。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -eq 0 ]; then
  set -- --work-dir "$REPO/tmp/s9x-work/selftest"
fi
python3 "$REPO/tools/l4_getput_measure.py" selftest "$@"
