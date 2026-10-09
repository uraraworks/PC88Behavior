#!/usr/bin/env bash
# l4-s9w。PAINT 文の塗りの規則（手計算）・タイル・判定の陽性/陰性・速さの腕の関門・期待値の照合（陰性対照つき）・
# 自作ROMの対照（グラフィックVRAM写しと印が採れる）・ハーネスの故障注入のみ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_paint_measure.py" selftest "$@"
