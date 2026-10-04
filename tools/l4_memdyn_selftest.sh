#!/usr/bin/env bash
# 段D/Eの動的メモリ。自作ROM・自作D88だけを使う。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/tools/l4_memdyn_selftest.py" "$@"
