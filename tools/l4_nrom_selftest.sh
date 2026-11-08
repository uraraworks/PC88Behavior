#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 tools/l4_nrom_selftest.py
