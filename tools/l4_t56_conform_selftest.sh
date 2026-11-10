#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
work=${PC88_T56_WORK:-tmp/impl4-work/t56-conform}
mkdir -p "$work"
export PC88_T5_WORK="$work/t5" PC88_T6_WORK="$work/t6"
export PC88_T7_WORK="$work/t7" PC88_T8_WORK="$work/t8"
export PC88_T9_WORK="$work/t9"
status=0
sh tools/l4_t5_selftest.sh || status=1
sh tools/l4_t6_selftest.sh || status=1
sh tools/l4_t7_selftest.sh || status=1
sh tools/l4_t8_selftest.sh || status=1
sh tools/l4_t9_selftest.sh addendum2 || status=1
sh tools/l4_t10_selftest.sh || status=1
python3 tools/l4_t10_editmotor_measure.py selftest --round addendum1 || status=1
for kind in t5 t6 t7 t8 t9 t10 t10e; do
    case "$kind" in
        t9) measured="$work/t9/addendum2/selftest/actual.json" ;;
        t10) measured=tmp/t10-work/selftest/actual.json ;;
        t10e) measured=tmp/t10-work/selftest-addendum1/actual.json ;;
        *) measured="$work/$kind/selftest/actual.json" ;;
    esac
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
