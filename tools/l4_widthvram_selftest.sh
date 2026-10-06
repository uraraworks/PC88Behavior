#!/usr/bin/env bash
# l4-s9o。合成の写し・合成のI/O記録と、自作ROMの既知値対照（80桁の並び・印の残存）のみ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_widthvram_measure.py" selftest "$@"
