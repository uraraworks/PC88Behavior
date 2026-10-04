#!/usr/bin/env bash
# l4-s9g。合成対照と自作ROMの定数・無操作対照のみ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_editinv_measure.py" selftest "$@"
