#!/usr/bin/env bash
# l4-s9r。合成のPPM・合成のI/O記録・合成の観測での判定と、自作ROMの対照（st-goto・bg-base・px0-n0/n1）のみ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_crtcpix_measure.py" selftest "$@"
