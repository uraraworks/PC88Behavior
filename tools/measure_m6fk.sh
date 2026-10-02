#!/usr/bin/env bash
# m6f-k: 作業先・結果は引数または PC88_M6FK_WORK で指定する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/tools/m6fk_measure.py" "$@"
