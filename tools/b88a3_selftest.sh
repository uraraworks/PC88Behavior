#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
for prefix in PC88_REF_ B88_ B88A1_ B88A2_ B88A3_ Q88MEASURE_FAULT_; do
  while IFS= read -r name; do unset "$name"; done < <(compgen -A variable "$prefix" || true)
done
export PYTHONDONTWRITEBYTECODE=1
work="$(mktemp -d "${TMPDIR:-/tmp}/b88a3-selftest.XXXXXX")"
trap 'rm -rf "$work"' EXIT
bash "$repo/tools/b88a3_run.sh" "$work/run"
python3 "$repo/tools/b88a3_selftest.py" "$work/run"
printf 'B88追補3 自己検査 PASS\n'
