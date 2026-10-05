#!/usr/bin/env bash
# l4-s9i: 合成画面と自作ROMの定数対照のみ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/tools/l4_wrap_measure.py" selftest "$@"
