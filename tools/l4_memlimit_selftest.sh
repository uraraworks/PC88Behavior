#!/usr/bin/env bash
# l4-s9d: 合成採取と自作ROMだけ。公式ROMは使用しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_memlimit_measure.py" selftest "$@"
