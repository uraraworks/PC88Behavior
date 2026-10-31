#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$REPO/tools" python3 - <<'PY'
import io, json, tempfile
from pathlib import Path
from types import SimpleNamespace as E
from analyze_b16 import analyze, io_drops
from analyze_m6ia_main_sub import AnalysisError
from judge_b16 import FIELDS, load, judge

def rec(n,r,w='-'):
    return dict(row=str(n),run=str(r),count='0',timeout='0',writes=w,crossings='-',out_fd='0',sub_dropped='0')
base={(n,r):rec(n,r) for n in range(1,16) for r in (1,2)}
assert judge(base)['controls_passed'] and judge(base)['shape']=='undetermined'
a={k:v.copy() for k,v in base.items()}; a[1,1]['writes']=a[1,2]['writes']='7800-7800:1'; assert not judge(a)['controls_passed']
a={k:v.copy() for k,v in base.items()}; a[3,2]['timeout']='1'; assert not judge(a)['controls_passed']
a={k:v.copy() for k,v in base.items()}; del a[4,2]; assert not judge(a)['controls_passed']
a={k:v.copy() for k,v in base.items()}
for r in (1,2):
    a[8,r]['writes']='7800-780F:16'; a[15,r]['writes']='7800-781F:32'; a[12,r]['out_fd']='7'
j=judge(a); assert j['shape']['address_positions']==[1,2] and j['position']['starts_7800']==[8,15] and j['request_0d'][12]['out_fd']==7
a={k:v.copy() for k,v in base.items()}
a[14,1]['sub_dropped']='3'; a[14,1]['out_fd']='1'; a[14,2]['out_fd']='2'
assert judge(a)['controls_passed'] and judge(a)['request_0d'][14]['out_fd'] is None
with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'io.log'
    p.write_text('# main\n# 取りこぼし: 0件\n# sub\n# 取りこぼし: 3件\n')
    assert io_drops(p)==3
    p.write_text('# main\n# 取りこぼし: 1件\n# sub\n# 取りこぼし: 0件\n')
    try: io_drops(p)
    except AnalysisError: pass
    else: raise AssertionError('main の取りこぼしを拒否できない')
m=[E(addr=0xdf50,value=0),E(addr=0xdf52,value=0),E(addr=0xdf53,value=1),E(addr=0xdf51,value=0xde)]
e=[E(cpu='main',kind='OUT',port='00FD',value=x) for x in (0,0x17,0x0f)] + [E(cpu='sub',kind='OUT',port='00FD',value=0xde)]
v=analyze(1,1,e,m,['W 4000 rom 1','A 0100 1 1 0 0 1'])
assert '222' not in '\t'.join(v) and v[-2:] == ['1','0']
for lines in (['W 4000 rom 1','W 4000 rom 1'],['secret'],['A 2000 1 1 0 0 0']):
    try: analyze(1,1,e,m,lines)
    except ValueError: pass
    else: raise AssertionError('不正記録を拒否できない')
for text in ('row\trun\n1\t1\n', '\t'.join(FIELDS)+'\n1\t1\t0\t0\t4001-4000:1\t-\t0\t0\n', '\t'.join(FIELDS)+'\n1\t1\t0\t0\t-\t-\t0\t0\n'*2):
    try: load([io.StringIO(text)])
    except ValueError: pass
    else: raise AssertionError('不正 TSV を拒否できない')
assert '222' not in json.dumps(j)
print('B16 自己検査 OK')
PY
