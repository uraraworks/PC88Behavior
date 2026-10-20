#!/usr/bin/env bash
# 合成陰性対照と自作ROMのみ。公式測定はmeasure --officialで独立実施。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAND_ROOT="${PC88_L4_RANDFILE_WORK:-$REPO/tmp/f2-work}"
if [ "$#" -eq 0 ]; then set -- --work-dir "$RAND_ROOT/selftest"; fi
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_randfile_measure.py" selftest "$@"
