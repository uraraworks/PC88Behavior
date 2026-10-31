#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
python3 tools/b23_first_request.py --selftest
