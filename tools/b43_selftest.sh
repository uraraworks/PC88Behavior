#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
PYTHONPATH="$REPO/tools:$REPO/src" python3 - <<'PY'
import csv, io
from build_main_rom import b43_boot, b43_payload
from analyze_b43 import analyze
from judge_b43 import FIELDS, load, judge
records = {}; baseline = {}
for n in range(1,7):
    assert b43_boot(n)
    p = b43_payload(address=0x6000 if n == 5 else 0x7800)
    assert p[0] == 0x22 and p[3:5] == bytes([0xf5, 0xe1])
    for run in (1,2):
        data = list(range(15)) + [0x5a,0xa5,0]
        lines = ['1 0 1000 DE04 5A\n','2 0 1000 DE00 00\n']
        lines += [f'{i+3} 0 1000 {0xe000+i:04X} {v:02X}\n' for i,v in enumerate(data)]
        lines += ['21 0 1000 DE01 01\n','取りこぼし: 0件\n']
        values = analyze(n,run,lines)
        assert values[2:] == ['1','00','0201','0403','0605','0807','0A09','0C0B','0D','0E']
        f=io.StringIO(); w=csv.writer(f,delimiter='\t',lineterminator='\n'); w.writerow(FIELDS); w.writerow(values); f.seek(0)
        records.update(load([f])); baseline[n,run] = dict(records[n,run])
assert judge(records,baseline)['controls_passed']
records[1,2]['f']='44'; assert not judge(records,baseline)['controls_passed']
records[1,2]['f']='0E'; baseline[2,1]['a']='FF'; assert not judge(records,baseline)['controls_passed']
try: analyze(1,1,lines[:-1])
except ValueError: pass
else: raise AssertionError('取りこぼし記録なし')
PY
python3 "$REPO/src/l3_service/make_subrom.py" "$work/sub" > /dev/null
"$REPO/tools/measure_b43.sh" --work "$work/run" --dry-run-sub-rom "$work/sub/DISK.ROM" --output-dir "$work/results"
python3 - "$work/results" <<'PY'
import csv, pathlib, sys
for path in sorted(pathlib.Path(sys.argv[1]).glob('b43-self-*.tsv')):
    with path.open() as f:
        rows = list(csv.DictReader(f, delimiter='\t'))
    assert len(rows) == 6 and all(r['complete'] == '1' and r['f'] == 'C1' for r in rows), rows
assert len(list(pathlib.Path(sys.argv[1]).glob('b43-self-*.tsv'))) == 2
print('B43 自己検査 OK: F=C1')
PY
