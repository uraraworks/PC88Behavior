#!/usr/bin/env bash
# 自作ROM・規則生成媒体だけで固定入口を実走する。
set -euo pipefail
cd "$(dirname "$0")/.."
for name in ${!PC88_REF_@}; do unset "$name"; done
make -s -C tools/harness/frontend
python3 tools/main_rom_entry_selftest.py
