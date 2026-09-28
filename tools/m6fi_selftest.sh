#!/usr/bin/env bash
# run_all_selftests.sh は各登録項目を bash で起動する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/m6fi_selftest.py"
