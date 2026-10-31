#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
python3 tools/b13_sub_fdc.py --selftest
