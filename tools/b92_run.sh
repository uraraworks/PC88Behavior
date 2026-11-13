#!/usr/bin/env bash
# PC88_REF_ROM_DIR / PC88_GAME_DIR / PC88_CORE は環境から受け取る。
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$repo/tools/b92_run.py" "$@"
