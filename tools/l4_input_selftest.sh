#!/usr/bin/env bash
# 合成対照と自作ROM全腕だけ。公式ROM・保存観測は開かない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -eq 0 ]; then set -- --work-dir "$REPO/tmp/s9z-work/selftest"; fi
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_input_measure.py" selftest "$@"
