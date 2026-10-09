#!/usr/bin/env bash
# 公式ROM・公式保存観測は開かない。合成陰性対照と自作HEADのみ。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -eq 0 ]; then set -- --work-dir "$REPO/tmp/s9y-work/selftest"; fi
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_dim_measure.py" selftest "$@"
