#!/usr/bin/env bash
# 合成自己検査と現行srcの自作ROMだけ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -eq 0 ]; then set -- --work-dir "$REPO/tmp/t2-work/selftest"; fi
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_key_measure.py" selftest "$@"
