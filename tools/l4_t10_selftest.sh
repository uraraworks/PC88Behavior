#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
work=tmp/t10-work/selftest
python3 tools/l4_t10_editmotor_measure.py selftest
python3 tools/l4_t10_editmotor_measure.py expected --measured "$work/actual.json" --out "$work/expected-cli.json"
python3 tools/l4_t10_editmotor_measure.py check --measured "$work/actual.json" --expected "$work/expected-cli.json"
python3 - "$work/expected-cli.json" "$work/broken.json" <<'PY'
import json, sys
from pathlib import Path
source,target=map(Path,sys.argv[1:]); data=json.loads(source.read_text())
for run in data['records']['ref-none']['runs']: run['screen']['operationa']['6'][0]^=1
target.write_text(json.dumps(data,ensure_ascii=False))
PY
if python3 tools/l4_t10_editmotor_measure.py check --measured "$work/actual.json" --expected "$work/broken.json"; then
    echo 'CLI陰性対照失敗' >&2; exit 1
fi
printf '%s\n' 'CLI陰性対照: 壊した期待値を拒否'
