#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$REPO/tools:$REPO/src" python3 - <<'PY'
import io,csv
from analyze_b24 import analyze,LENGTHS
from judge_b24 import FIELDS,load,judge
from build_main_rom import b24_boot
records={}
for row in range(1,9):
    length=LENGTHS[row-1]
    if row in (5,6):
        from make_l3_testdisk import coord_header_pattern
        data=b''.join(coord_header_pattern(0xa1,0,0,i+1) for i in range(length//256))
    else: data=bytes((((i+(8 if row==3 else 1 if row==8 else 0))*7+13)&255) for i in range(length))
    for run in (1,2):
        lines=['1 0 0000 DE04 5A\n','2 0 0000 DE00 00\n','3 0 0000 DE03 A5\n']+[f'{i+4} 0 0000 {0xe000+i:04X} {v:02X}\n' for i,v in enumerate(data)]+[f'{len(data)+4} 0 0000 DE01 01\n','取りこぼし: 0件\n']
        values=analyze(row,run,lines)
        out=io.StringIO(newline='');w=csv.writer(out,delimiter='\t');w.writerow(FIELDS);w.writerow(values);out.seek(0);records.update(load([out]))
    assert b24_boot(row)
assert judge(records)['transfer']=='confirmed'
# 末尾は値そのものを残さず、各位置の一致だけを記録する。
lines=['1 0 0000 DE04 5A\n','2 0 0000 DE00 00\n','3 0 0000 DE03 A5\n']
lines += [f'{i+4} 0 0000 {0xe000+i:04X} {((i*7+13) if i != 17 else 0)&255:02X}\n' for i in range(18)]
lines += ['22 0 0000 DE01 01\n','取りこぼし: 0件\n']
r=analyze(1,1,lines)
assert r[3:7]==['18','0','16','1;0']
try: analyze(1,1,lines[:-1])
except ValueError: pass
else: raise AssertionError('欠落情報が必要')
records[8,1]['prefix']='1';records[8,2]['prefix']='1';assert not judge(records)['controls_passed']
records[8,1]['prefix']='0';records[8,2]['prefix']='0';records[1,2]['prefix']='0';assert not judge(records)['controls_passed']
print('B24 自己検査 OK')
PY
