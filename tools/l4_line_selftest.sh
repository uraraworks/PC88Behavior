#!/usr/bin/env bash
# l4-s9u。LINE 文の線の規則（手計算）・復号・判定の陽性/陰性・モデルの手計算・較正の関門・自作ROMの対照（グラフィックVRAM写しが採れる）、
# ハーネスの故障注入のみ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_line_measure.py" selftest "$@"
