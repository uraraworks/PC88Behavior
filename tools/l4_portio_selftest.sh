#!/usr/bin/env bash
# 合成自己検査と現行srcの自作ROMだけ。画面本文を出さない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -eq 0 ]; then set -- --work-dir "$REPO/tmp/t3-work/selftest"; fi
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_portio_measure.py" selftest "$@"
