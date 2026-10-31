#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$REPO/tools:$REPO/src" python3 - <<'PY'
import csv,io
from build_main_rom import b35_boot,b35_payload
from analyze_b35 import analyze
from judge_b35 import FIELDS,load,judge,PREVIOUS
records={}
for n in range(1,7):
    assert b35_boot(n) and b35_payload().startswith(bytes([0x32,0x30,0x78]))
    for run in (1,2):
        data=list(range(14))+[0x5a,0xa5]; lines=['1 0 1000 DE04 5A\n','2 0 1000 DE00 00\n']
        lines += [f'{i+3} 0 1000 {0xe000+i:04X} {v:02X}\n' for i,v in enumerate(data)]
        lines += ['19 0 1000 DE01 01\n','取りこぼし: 0件\n']
        v=analyze(n,run,lines); assert v[2:] == ['1','00','0201','0403','0605','0807','0A09','0C0B','0D']
        f=io.StringIO();w=csv.writer(f,delimiter='\t',lineterminator='\n');w.writerow(FIELDS);w.writerow(v);f.seek(0);records.update(load([f]))
assert judge(records,records)['controls_passed']
assert judge(records)['registers']['bc']['constant']
records[1,2]['bc']='1234'; assert not judge(records)['controls_passed']
records[1,2]['bc']='0201'
for run in (1,2): records[6,run].update(PREVIOUS)
assert all(judge(records)['registers'][k]['retains_row6_previous'] for k in PREVIOUS)
for lines in ([*lines[:-1]], ['1 0 1000 DE04 5A\n','3 0 1000 E000 00\n','取りこぼし: 0件\n']):
    try: analyze(1,1,lines)
    except ValueError: pass
    else: raise AssertionError('不正なログ')
print('B35 自己検査 OK')
PY
