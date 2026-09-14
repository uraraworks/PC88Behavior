#!/usr/bin/env bash
# tools/asm/z80text_selftest.sh — z80text.py 単体（境界・代表命令）の自己検査。
#
# 中身は tools/asm/z80text_selftest.py。python3 だけで完結する。
#
# 使い方: tools/asm/z80text_selftest.sh
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

python3 tools/asm/z80text_selftest.py
exit $?
