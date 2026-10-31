#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$REPO/tools:$REPO/src" python3 - <<'PY'
import csv, io
from analyze_b26 import analyze, BASE
from judge_b26 import FIELDS, LENGTHS, PHASES, judge, load
from build_main_rom import b26_boot
from make_l3_testdisk import coord_header_pattern
records = {}
for row in range(1, 8):
    for run in (1, 2):
        writes = [(0xde04, 0x5a), (0xde00, 0), (0xde01, 0)]
        for phase in PHASES[row-1]:
            writes.append((0xde03, phase))
            if phase == 1:
                count = LENGTHS[row-1] // 256
                blocks = b''.join(coord_header_pattern(0xa1, 1 if row == 5 else 0, 0, i + (1 if row == 4 else 2)) for i in range(count))
            else: blocks = b''
            blocks += bytes([0x12, 0xab])
            writes += [(BASE[phase]+i, v) for i, v in enumerate(blocks)]
            writes.append((0xde05, phase))
        writes.append((0xde01, 1))
        lines = [f'{i} 0 0000 {a:04X} {v:02X}\n' for i, (a, v) in enumerate(writes, 1)] + ['取りこぼし: 0件\n']
        values = analyze(row, run, lines)
        assert values[6] == '|'.join(['2'] * len(PHASES[row-1]))
        assert values[7] == '|'.join(['12;AB'] * len(PHASES[row-1]))
        assert values[8] == '|'.join(['1'] * len(PHASES[row-1]))
        out = io.StringIO(newline=''); writer = csv.writer(out, delimiter='\t'); writer.writerow(FIELDS); writer.writerow(values); out.seek(0); records.update(load([out]))
    assert b26_boot(row)
assert judge(records)['controls_passed']
records[1,2]['extra'] = 'FF'; assert not judge(records)['controls_passed']
records[1,2]['extra'] = records[1,1]['extra']
records[1,1]['stamps'] = records[1,2]['stamps'] = 'other'; assert not judge(records)['controls_passed']
try: analyze(1, 1, ['取りこぼし: 1件\n'])
except ValueError: pass
else: raise AssertionError('欠落を検出できない')
print('B26 自己検査 OK')
PY
