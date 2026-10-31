#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$REPO/tools:$REPO/src" python3 - <<'PY'
import io, tempfile, pathlib
from judge_b19 import FIELDS, judge, load
from build_main_rom import b19_payload, b19_boot

def record(n,r):
    d=dict.fromkeys(FIELDS,'-'); d.update(row=str(n),run=str(r),complete='1',sent='40',timeout='0',out_fd='0',sub_dropped='0')
    if n==3: d.update(read1='256',stamp1='0,0,1')
    d['ram'] = ('7810-7810:1' if n in (1,4) else '7821-7821:1')
    d['crossings']='0038:2,0,2,0,0'
    return d
base={(n,r):record(n,r) for n in range(1,6) for r in (1,2)}
j=judge(base); assert j['controls'] and j['row1']=='enabled' and j['row2']=='disabled'
for n,key,val in ((4,'ram','7811-7811:1'),(2,'timeout','1'),(3,'sub_dropped','1')):
    a={k:v.copy() for k,v in base.items()}; a[n,1][key]=val
    assert not judge(a)['controls']
a={k:v.copy() for k,v in base.items()};del a[1,2]; assert not judge(a)['controls']
a={k:v.copy() for k,v in base.items()}
for r in (1,2): a[2,r]['ram']='7820-7821:2'
assert judge(a)['row2']=='inconclusive'
for enabled in (False,True):
    p=b19_payload(0x7810,enabled); offset=3 if enabled else 0
    assert len(p)==20 and p[offset:offset+3]==[0xed,0x57,0xe2] and p[offset+3:offset+5]==[0x0b+offset,0x78]
for n in range(1,6):
    t=b19_boot(n); assert ('CALL _b17_read\n' in t)==(n==3)
    assert ('LD HL,_b17_data2\n' in t)==(n in (2,3,5))
with tempfile.TemporaryDirectory() as tmp:
    path=pathlib.Path(tmp)/'x'; row=base[3,1]
    path.write_text('\t'.join(FIELDS)+'\n'+'\t'.join(row[k] for k in FIELDS)+'\n')
    assert load([path])[(3,1)]==row
    path.write_text(path.read_text().replace('7810','secret').replace('7821-7821:1','secret'))
    try: load([path])
    except ValueError: pass
    else: raise AssertionError('不正な入力')
print('B19 自己検査 OK')
PY
