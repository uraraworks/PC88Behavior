#!/usr/bin/env bash
# 公式環境なし。保護方法4種類と修正前相当のハングを検出する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$REPO/tools/l4_write_protect_selftest.py" "$@"
