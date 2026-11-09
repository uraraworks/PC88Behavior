#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
work=tmp/impl2-work/t56-conform
mkdir -p "$work"
status=0
sh tools/l4_t5_selftest.sh || status=1
sh tools/l4_t6_selftest.sh || status=1
sh tools/l4_t7_selftest.sh || status=1
sh tools/l4_t8_selftest.sh || status=1
for kind in t5 t6 t7 t8; do
    measured="tmp/$kind-work/selftest/actual.json"
    expected="tests/conformance/expected_l4_$kind.json"
    python3 tools/l4_t56_conform.py check --kind "$kind" --measured "$measured" --expected "$expected" || status=1
    python3 - "$expected" "$work/$kind-broken.json" <<'PY'
import json, sys
from pathlib import Path
source, target = map(Path, sys.argv[1:])
data = json.loads(source.read_text())
item = next(iter(data.values()))
key = next(iter(item))
item[key] = {'故障注入': True}
target.write_text(json.dumps(data, ensure_ascii=False))
PY
    if python3 tools/l4_t56_conform.py check --kind "$kind" --measured "$measured" --expected "$work/$kind-broken.json"; then
        echo "陰性対照 $kind: 検出失敗"
        status=1
    fi
done
exit "$status"
