#!/usr/bin/env bash
# l4-s5jの合成対照と自作ROMの陰性対照。公式ROMは使わない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_s5j_measure.py" selftest "$@"
