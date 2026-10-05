#!/usr/bin/env bash
# l4-s9j。合成対照と自作ROMの既存機能対照のみ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_onwhile_measure.py" selftest "$@"
