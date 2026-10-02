#!/usr/bin/env bash
# l4-s5i器具・候補N_A/N_Bの自己検査。探り対照は自作ROMだけを一時ビルド。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/l4_listnum_measure.py" selftest
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
if ! python3 "$REPO/src/build_main_rom.py" "$WORK/rom" >"$WORK/build.log" 2>&1; then
  rg -i 'error|エラー' "$WORK/build.log" >&2 || true
  exit 1
fi
python3 "$REPO/tools/l4_listnum_measure.py" check --rom-dir "$WORK/rom" \
  --expected "$REPO/tests/conformance/expected_l4_listnum.tsv"
