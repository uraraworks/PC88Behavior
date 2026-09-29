#!/usr/bin/env bash
# 作業先は --work または PC88_M6IJ_WORK。未作成のみ受け付ける。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/tools/m6ij_measure.py" "$@"
