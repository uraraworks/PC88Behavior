#!/usr/bin/env bash
# m6f-j: 作業先・結果は引数または PC88_M6FJ_WORK で指定する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/tools/m6fj_measure.py" "$@"
