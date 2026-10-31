#!/usr/bin/env bash
set -euo pipefail
python3 "$(dirname "$0")/b20_sub_interrupts.py" --selftest
