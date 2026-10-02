#!/usr/bin/env bash
# l4-s5i器具・候補N_Aの自己検査。ROM・期待値・私物は使わない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$REPO/tools/l4_listnum_measure.py" selftest
