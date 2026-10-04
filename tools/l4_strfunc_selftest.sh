#!/usr/bin/env bash
# l4-s9a の合成対照と自作ROM定数対照。公式ROMは使わない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_strfunc_measure.py" selftest "$@"
