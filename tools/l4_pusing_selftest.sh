#!/usr/bin/env bash
# l4-s9h の合成画面と自作ROMの普通PRINT定数対照。公式ROMは使わない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/tools/l4_pusing_measure.py" selftest "$@"
