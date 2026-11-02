#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d /tmp/b72-selftest.XXXXXX)"; trap 'rm -rf "$work"' EXIT
export PC88_SUB_READ_CORE="${PC88_SUB_READ_CORE:-$REPO/tmp/b62-core/core/quasi88_libretro.dylib}"
export PC88_SUB_READ_CORE_SRC="${PC88_SUB_READ_CORE_SRC:-$REPO/tmp/b62-core/core/src}"
PYTHONPATH="$REPO/tools" python3 - <<'PY'
from analyze_b72 import analyze

def log(values, timeout=0, drops=0):
    writes = [(0xde04, 0x5a), (0xde00, 0), (0xde01, 0), (0xde03, 0xa5)]
    writes += [(0xe000+i, v) for i, v in enumerate(values)]
    writes += [(0xde00, timeout), (0xde01, 1)]
    return [f'{i} 0 1000 {a:04X} {v:02X}\n' for i, (a, v) in enumerate(writes, 1)] + [f'# 取りこぼし: {drops}件\n']
assert analyze(4, log([255,255]), (0x1000,0x1001)) == 'reply=2 match=2 timeout=0 executed=-'
assert analyze(4, log([255,0], 1), (0x1000,0x1001)) == 'reply=2 match=1 timeout=1 executed=-'
assert analyze(3, log([255,90]), (0x1000,0x1001)).endswith('executed=1')
assert analyze(3, log([255,0]), (0x1000,0x1001)).endswith('executed=0')
try:
    analyze(4, log([255,255], drops=1), (0x1000,0x1001))
except ValueError:
    pass
else:
    raise AssertionError('取りこぼしを検出できない')
PY
python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" >"$work/sub.log" 2>&1
PC88_B72_WORK="$work/measure" bash "$REPO/tools/measure_b72.sh" --dry-run-sub-rom "$work/sub/DISK.ROM" --output-dir "$work/result"
grep -qx 'row 4 S reply=2 match=2 timeout=0 executed=-' "$work/result/b72-sub-request-0e-followups.txt"
cat "$work/result/b72-sub-request-0e-followups.txt"
