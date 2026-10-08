#!/usr/bin/env bash
# l4-s9t。合成のグラフィックVRAM・結果行・I/O記録での解析と判定（陽性・陰性）、手計算のモデル、自作ROMの対照（グラフィックVRAM写しが採れる）、
# ハーネスの故障注入（写しの1バイトを化けさせると lit に現れる）のみ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_gfx_measure.py" selftest "$@"
