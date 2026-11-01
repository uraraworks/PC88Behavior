#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
PYTHONPATH="$REPO/tools" python3 - <<'PY'
import csv, io
from analyze_b52b import analyze, FIELDS
from analyze_b52 import LENGTHS
for row in range(1, 6):
    length = LENGTHS[row - 1]
    start = 0x20 if row == 4 else 0x10
    data = bytearray((i * 7 + 13) & 255 for i in range(64))
    data[start] = 0xa0 + length - 1
    data[start + 1] = 0x55
    lines = ['1 0 1000 DE04 5A\n', '2 0 1000 DE03 A5\n']
    lines += [f'{i+3} 0 1000 {0xe000+i:04X} {v:02X}\n' for i, v in enumerate(data)]
    lines += ['67 0 1000 DE01 01\n', '取りこぼし: 0件\n']
    result = analyze(row, 1, lines)
    expected = [f'p{length-1}', '?']
    expected += [f'p{data[i]-0xa0}' if 0xa0 <= data[i] < 0xa0 + length else 'b'
                 for i in range(start + 2, start + length)]
    assert result == [str(row), '1', ' '.join(expected)]
    out = io.StringIO()
    writer = csv.writer(out, delimiter='\t', lineterminator='\n')
    writer.writerow(FIELDS); writer.writerow(result)
    assert '55' not in out.getvalue()
PY
python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" > /dev/null
"$REPO/tools/measure_b52b.sh" --work "$work/run" --dry-run-sub-rom "$work/sub/DISK.ROM" --output-dir "$work/results"
python3 - "$work/results" <<'PY'
import csv, pathlib, sys
files = list(pathlib.Path(sys.argv[1]).glob('b52b-self-*.tsv'))
assert len(files) == 2
for path in files:
    with path.open() as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    assert len(rows) == 5 and [int(r['row']) for r in rows] == list(range(1, 6))
    assert all(len(r['layout'].split()) == n for r, n in zip(rows, (8, 2, 16, 8, 9)))
print('B52b 自己検査 OK')
PY
