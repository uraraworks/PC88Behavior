#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$REPO/tools" python3 - <<'PY'
import io
from types import SimpleNamespace as E
from judge_b17 import FIELDS,load,judge
from analyze_b17 import analyze

def rec(n,r):
    d=dict.fromkeys(FIELDS,'-');d.update(row=str(n),run=str(r),complete='1',sent='0',timeout='0',out_fd='0',sub_dropped='0')
    if n in (3,7):d.update(read1='256',stamp1='0,0,1')
    if n==7:d.update(read2='256',stamp2='0,0,1')
    return d
base={(n,r):rec(n,r) for n in range(1,8) for r in (1,2)}
for r in (1,2):
    base[1,r]['rom']='7800-780F:16';base[2,r].update(ram='7810-7810:1',crossings='00C1:1,0,1,0,0')
    base[4,r].update(rom='6000-600F:16',ram='6010-6010:1');base[5,r].update(rom='7900-79FF:256',ram='7A10-7A10:1')
j=judge(base);assert j['controls_passed'] and all(j[k]=='confirmed' for k in ('writing','execution','return'))
for n,field,val in ((1,'crossings','0100:1,0,1,0,0'),(6,'ram','7810-7810:1')):
    a={k:v.copy() for k,v in base.items()}
    for r in (1,2):a[n,r][field]=val
    assert not judge(a)['controls_passed']
for n,field in ((4,'rom'),(2,'ram'),(2,'crossings'),(7,'stamp2')):
    a={k:v.copy() for k,v in base.items()}
    for r in (1,2):a[n,r][field]='-'
    assert 'not_confirmed' in judge(a).values()
a={k:v.copy() for k,v in base.items()};a[3,2]['timeout']='1';assert not judge(a)['controls_passed']
a={k:v.copy() for k,v in base.items()}
for r in (1,2):a[4,r].update(complete='0',sent='-',timeout='-')
assert judge(a)['writing']=='inconclusive' and 4 in judge(a)['incomplete']
for n,expected in ((2,('execution','return')),(3,('return',)),(5,('writing','execution')),(7,('return',))):
    a={k:v.copy() for k,v in base.items()}
    for r in (1,2):
        a[n,r].update(complete='0',sent='-',timeout='-',read1='-',stamp1='-',read2='-',stamp2='-')
    j=judge(a)
    assert j['controls_passed'] and all(j[k]=='inconclusive' for k in expected)
a={k:v.copy() for k,v in base.items()};del a[5,2];assert not judge(a)['controls_passed']
a={k:v.copy() for k,v in base.items()};a[3,1]['sub_dropped']='1';a[3,1]['out_fd']='9';assert judge(a)['controls_passed']
def tsv(d):return '\t'.join(FIELDS)+'\n'+'\t'.join(d[k] for k in FIELDS)+'\n'
assert len(load([io.StringIO(tsv(base[1,1]))]))==1
for data in (tsv(base[1,1])*2,tsv(base[1,1]).replace('7800-780F:16','780F-7800:16'),tsv(base[1,1]).replace('7800-780F:16','secret')):
    try:load([io.StringIO(data)])
    except ValueError:pass
    else:raise AssertionError('不正 TSV')
m=[E(addr=x,value=0) for x in (0xdf50,0xdf51,0xdf52,0xdf54,0xdf55,0xdf56,0xdf57)]+[E(addr=0xdf53,value=1)]
ev=[E(cpu='main',kind='OUT',port='00FD',value=x) for x in (0,0x17,0x0f)]
v=analyze(1,1,ev,m,['W 7EFF rom 1','W 7F00 rom 1','A 00C1 1 0 1 0 0']);assert v[5]=='7EFF-7EFF:1' and v[7]=='7F00-7F00:1'
v=analyze(1,1,[],[],['W 7800 ram 1'],2);assert v[2:5]==['0','-','-']
for lines in (['secret'],['W 7800 rom 1','W 7800 rom 1']):
    try:analyze(1,1,ev,m,lines)
    except ValueError:pass
    else:raise AssertionError('不正境界')
print('B17 自己検査 OK')
PY
