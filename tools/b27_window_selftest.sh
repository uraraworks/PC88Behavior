#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
python3 tools/b27_window.py --selftest
