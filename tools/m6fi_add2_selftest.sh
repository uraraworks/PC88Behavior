#!/usr/bin/env bash
# 一括自己検査から実行する。公式ROM・公式媒体は使わない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/m6fi_add2_selftest.py"
