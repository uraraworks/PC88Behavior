#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
python3 tools/b25_two_bytes.py --selftest
