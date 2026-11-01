#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
PYTHONPATH="$REPO/tools" python3 - <<'PY'
from analyze_b52d import analyze, BASE, PATTERN, CODE
from analyze_b52 import LENGTHS

assert not set(PATTERN) & set(BASE)
def record(data):
    lines = ['1 0 1000 DE04 5A\n', '2 0 1000 DE00 00\n', '3 0 1000 DE03 A5\n']
    lines += [f'{i+4} 0 1000 {0xe000+i:04X} {v:02X}\n' for i, v in enumerate(data)]
    lines += ['68 0 1000 DE01 01\n', '取りこぼし: 0件\n']
    return lines
for row in range(1, 9):
    length = LENGTHS[row-1]
    start = 0x20 if row == 4 else 0x10
    data = BASE.copy()
    data[start:start+length] = CODE if row == 7 else PATTERN[:length]
    if row == 7:
        data[63] = 0x5a
    result = analyze(row, 1, record(data))
    assert result[2:5] == ['1', '0', '64']
    if row == 8:
        assert result[6] == '1' and result[5] != ' '.join(f'p{i}' for i in range(length))
    else:
        assert result[5] == ' '.join(f'p{i}' for i in range(length))
        assert result[6:8] == ['0', '0']
    if row == 7:
        assert result[8] == '1'
    broken = data.copy()
    target = start + 1 if row == 8 else start
    broken[target] = next(v for v in range(256) if v != BASE[target] and v not in PATTERN and v not in CODE)
    negative = analyze(row, 2, record(broken))
    assert negative[5:8] != result[5:8]
PY
python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" >/dev/null
"$REPO/tools/measure_b52d.sh" --work "$work/run" --dry-run-sub-rom "$work/sub/DISK.ROM" --output-dir "$work/results"
python3 - "$work/results" <<'PY'
import csv, pathlib, sys
files = list(pathlib.Path(sys.argv[1]).glob('b52d-self-*.tsv'))
assert len(files) == 2
for path in files:
    with path.open() as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    assert len(rows) == 8 and [int(r['row']) for r in rows] == list(range(1, 9))
print('B52d 自己検査 OK')
PY
