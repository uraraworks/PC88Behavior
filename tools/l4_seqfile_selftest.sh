#!/usr/bin/env bash
# 合成陰性対照と自作ROM試走。公式ROMの実行はしない。
# 追補1: PC88_L4_SEQFILE_WORK=... tools/l4_seqfile_selftest.sh --round addendum1 --work-dir ...
# 条件別の失敗記録と、凍結86腕に対する合成照合の不変性もPython側で検査する。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEQ_ROOT="${PC88_L4_SEQFILE_WORK:-$REPO/tmp/f1-work}"
if [ "$#" -eq 0 ]; then set -- --work-dir "$SEQ_ROOT/selftest"; fi
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_seqfile_measure.py" selftest "$@"
