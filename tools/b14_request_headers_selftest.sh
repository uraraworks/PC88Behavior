#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")/.."
python3 tools/b14_request_headers.py --selftest
