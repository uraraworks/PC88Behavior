#!/usr/bin/env bash
# 自作ROMだけで文の重さ・打鍵位相・短い押下を掃引する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_inkey_robust_selftest.py" "$@"
