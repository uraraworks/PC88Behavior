#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
round=${1:-first}
case "$round" in
  first) work=${PC88_T9_WORK:-tmp/t9-work}/selftest ;;
  addendum1) work=${PC88_T9_WORK:-tmp/t9-work}/addendum1/selftest ;;
  addendum2) work=${PC88_T9_WORK:-tmp/t9-work}/addendum2/selftest ;;
  *) exit 2 ;;
esac
python3 tools/l4_t9_mergechain_measure.py selftest --round "$round"
python3 tools/l4_t9_mergechain_measure.py expected --round "$round" --measured "$work/actual.json" --out "$work/expected-cli.json"
python3 tools/l4_t9_mergechain_measure.py check --round "$round" --measured "$work/actual.json" --expected "$work/expected-cli.json"
python3 - "$work/expected-cli.json" "$work/broken.json" <<'PY'
import json, sys
from pathlib import Path
x=json.loads(Path(sys.argv[1]).read_text())
for r in x['records']['ref-none']['runs']: r['screen']['operationa']['6'][0]^=1
Path(sys.argv[2]).write_text(json.dumps(x))
PY
if python3 tools/l4_t9_mergechain_measure.py check --round "$round" --measured "$work/actual.json" --expected "$work/broken.json"; then exit 1; fi
printf '%s\n' 'CLI陰性対照: 壊した期待値を拒否'
