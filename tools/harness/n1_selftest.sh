#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$repo/tmp/n1-work"
export TMPDIR="$repo/tmp/n1-work"
python3 "$repo/tools/harness/n1_run.py" --selftest
