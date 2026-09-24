#!/usr/bin/env bash
# tools/m6fc_fdc_by_drive.py の自己検査ラッパ。中身は
# tools/m6fc_fdc_by_drive_selftest.py（合成データのみ、公式ROM・公式
# ディスク・私物には一切触れない）。
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$REPO/tools/m6fc_fdc_by_drive_selftest.py"
