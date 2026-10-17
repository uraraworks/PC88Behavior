#!/usr/bin/env bash
# 合成対照と自作ROMだけ。公式ROMは使わない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -eq 0 ]; then set -- --work-dir "$REPO/tmp/t4-work/bsave-selftest-addendum1"; fi
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_bsave_measure.py" selftest "$@"
