#!/usr/bin/env bash
# 作業先は --work または PC88_M6IJ_ADD5_WORK（未作成のみ）。結果は作業先の中だけに置く。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/tools/m6ij_add5.py" "$@"
