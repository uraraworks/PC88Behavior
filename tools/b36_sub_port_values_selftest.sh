#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
python3 tools/b36_sub_port_values.py --selftest
