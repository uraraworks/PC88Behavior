#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable PC88_REF_ || true)
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable B88_ || true)
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable B88A1_ || true)
while IFS= read -r name; do unset "$name"; done < <(compgen -A variable Q88MEASURE_FAULT_ || true)
export PYTHONDONTWRITEBYTECODE=1
work="$(mktemp -d "${TMPDIR:-/tmp}/b88a1-selftest.XXXXXX")"
trap 'rm -rf "$work"' EXIT
bash "$repo/tools/b88a1_run.sh" "$work/run"
python3 "$repo/tools/b88a1_selftest.py" "$work/run"
printf 'B88追補1 自己検査 PASS\n'
