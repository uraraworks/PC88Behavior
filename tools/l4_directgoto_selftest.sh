#!/usr/bin/env bash
# 合成自己検査と現行srcの自作ROMだけ。公式ROM・保存観測は開かない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -eq 0 ]; then set -- --work-dir "$REPO/tmp/t1-work/selftest"; fi
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_directgoto_measure.py" selftest "$@"
