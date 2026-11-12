#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec python3 tools/l4_binary_type_selftest.py
