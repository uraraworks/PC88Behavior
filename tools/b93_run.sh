#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$repo/tools/b93_run.py" "$@"
