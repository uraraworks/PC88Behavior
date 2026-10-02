#!/usr/bin/env bash
# l4-s5i器具・候補N_A/N_Bの自己検査。探り対照は自作ROMだけを一時ビルド。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/tools/l4_listnum_measure.py" selftest
