#!/usr/bin/env bash
# l4-s9s。合成のVRAM写し・合成のI/O記録・合成の観測での解析と判定（陽性・陰性）、予測モデルの手計算、自作ROMの対照（はしご・スクロール・ac・cm）のみ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_console_measure.py" selftest "$@"
