#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/tools/m6ij_add3_selftest.py" "$@"
