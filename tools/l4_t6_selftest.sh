#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 tools/l4_t6_inputdollar_measure.py selftest
work=tmp/t6-work/selftest
python3 tools/l4_t6_inputdollar_measure.py expected --measured "$work/actual.json" --out "$work/expected-cli.json"
python3 tools/l4_t6_inputdollar_measure.py check --measured "$work/actual.json" --expected "$work/expected-cli.json"
