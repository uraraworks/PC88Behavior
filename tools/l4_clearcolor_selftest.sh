#!/usr/bin/env bash
# l4-s9q。合成の写し・合成のポート記録・合成モデルでの k 分探索と、自作ROMでの複数プローブ方式の動作確認のみ。公式ROMは実行しない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_clearcolor_measure.py" selftest "$@"
