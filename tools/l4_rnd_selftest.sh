#!/usr/bin/env bash
# l4-s8a の合成対照と自作ROMの定数対照。公式ROMは使わない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_rnd_measure.py" selftest "$@"
python3 "$REPO/tools/l4_rnd_bank_conform.py"
