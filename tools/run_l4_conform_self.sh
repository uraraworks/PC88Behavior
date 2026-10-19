#!/usr/bin/env bash
# 自作ROMのみ。run_allとは別に実行し、器具単位で成功をキャッシュする。
set -euo pipefail
for q1_ref_name in ${!PC88_REF_@}; do unset "$q1_ref_name"; done
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$REPO/tools/l4_conform_self.py" "$@"
