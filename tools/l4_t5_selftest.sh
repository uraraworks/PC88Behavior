#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 tools/l4_t5_delete_measure.py selftest
work=tmp/t5-work/selftest
python3 tools/l4_t5_delete_measure.py expected --measured "$work/actual.json" --out "$work/expected-cli.json"
python3 tools/l4_t5_delete_measure.py check --measured "$work/actual.json" --expected "$work/expected-cli.json"
python3 - "$work/expected-cli.json" "$work/broken.json" <<'PY'
import json, sys
from pathlib import Path
source, target = map(Path, sys.argv[1:])
data = json.loads(source.read_text())
for run in data['records']['ref-none']['runs']:
    run['memory']['err'] ^= 1
target.write_text(json.dumps(data, ensure_ascii=False))
PY
if python3 tools/l4_t5_delete_measure.py check --measured "$work/actual.json" --expected "$work/broken.json"; then
    printf '%s\n' '陰性対照: 壊した期待値を拒否できなかった'
    exit 1
fi
printf '%s\n' '陰性対照: 壊した期待値を拒否'
