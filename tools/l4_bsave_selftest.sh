#!/usr/bin/env bash
# 合成対照と自作ROMを使う。実ROM走には公式の参照媒体が要る。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$#" -eq 0 ]; then set -- --work-dir "$REPO/tmp/t4-work/bsave-selftest-addendum1"; fi
if [ -z "${PC88_REF_DISK_DIR:-}" ]; then
    echo 'SKIP 実ROM走: PC88_REF_DISK_DIR が無いので未実行（合成部分のみ実行）'
    set -- "$@" --synthetic-only
fi
PYTHONDONTWRITEBYTECODE=1 python3 "$REPO/tools/l4_bsave_measure.py" selftest "$@"
