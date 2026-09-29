#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
CHECK="$REPO/tools/check_m6ik_preregistration.py"
python3 "$CHECK" >"$WORK/ok"
sed 's/K-FR:0x17,0x0F:0x01:R+1/K-FR:0x17,0x0F:0x01:R+2/' \
  "$REPO/tools/m6ik_frozen.tsv" >"$WORK/bad.tsv"
if python3 "$CHECK" --config "$WORK/bad.tsv" >"$WORK/out" 2>"$WORK/err"; then exit 1; fi
grep -q -E gate_failed "$WORK/err"
sed 's/| 3 | 2 | 37 | 13 |/| 3 | 2 | 37 | 12 |/' \
  "$REPO/docs/notes/m6i-k-read-request-geometry-preregistration.md" >"$WORK/bad.md"
if python3 "$CHECK" --prereg "$WORK/bad.md" >"$WORK/out" 2>"$WORK/err"; then exit 1; fi
grep -q -E gate_failed "$WORK/err"
printf '%s\n' 'check_m6ik_preregistration_selftest: 凍結表・事前登録の陰性対照 OK'
