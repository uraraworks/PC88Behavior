#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$REPO/tmp/b10-work"
TMPDIR="$REPO/tmp/b10-work" PYTHONPATH="$REPO/tools" python3 - <<'PY'
from types import SimpleNamespace as E
import io, contextlib
from judge_b10 import load
from analyze_b10 import analyze
from analyze_m6ik import status_names
from judge_b10 import judge, ROWS

def record(n,run,blocks,count=None,timeout='1',reads='-'):
    return dict(row=str(n),run=str(run),count=str(len(blocks)*256 if count is None else count), timeout=timeout, blocks=';'.join(blocks) or '-',read_count=str(0 if reads=='-' else len(reads.split(';'))),reads=reads,st0='-',st1='-')
def expect(n):
    t,r,p=ROWS[n]; return [f'{t//2},{t%2},{r+i}' for i in range(p)]
assert len({status_names(i << 6,0)['st0'][0] for i in range(4)}) == 4
assert len(status_names(0x3f,0xb7)['st0']) == 7
assert len(status_names(0x3f,0xb7)['st1']) == 6
base={}
for n in ROWS:
    blocks=expect(n) if n not in (2,11) else ([] if n==2 else ['0,0,3','0,0,4'])
    for run in (1,2): base[n,run]=record(n,run,blocks)
r=judge(base); assert r['controls_passed'] and r['p1']=='count'
assert r['crossing'][8]['judgment']=='does_not_cross'
a={k:v.copy() for k,v in base.items()}; a[3,1]['timeout']='0'; a[3,2]['timeout']='0'; assert judge(a)['p1']=='not_count'
a={k:v.copy() for k,v in base.items()}; a[3,2]['timeout']='0'; assert judge(a)['p1']=='inconclusive'
a={k:v.copy() for k,v in base.items()}; a[11,1]['blocks']=a[11,2]['blocks']='0,0,2;0,0,3'; assert not judge(a)['controls_passed']
a={k:v.copy() for k,v in base.items()}; a[8,1]['blocks']=a[8,2]['blocks']='0,0,16;0,1,1'; assert judge(a)['crossing'][8]['judgment']=='crosses'
a={k:v.copy() for k,v in base.items()}; a[8,1]['blocks']=a[8,2]['blocks']='other'; assert judge(a)['crossing'][8]['judgment']=='fails'
a={k:v.copy() for k,v in base.items()}; a[8,2]['timeout']='0'; assert judge(a)['crossing'][8]['judgment']=='inconclusive'
m=[E(addr=0xDF50,value=4),E(addr=0xDF51,value=0),E(addr=0xDF52,value=1),E(addr=0xDF53,value=1)]
m += [E(addr=0xDF00+i,value=x) for i,x in enumerate((0xDE,0xAD,0xBE,0xEF))]
assert analyze(1,1,[],m)[4]=='other'
assert '222' not in '\t'.join(analyze(1,1,[],m))
m[-4:]=[E(addr=0xDF00+i,value=x) for i,x in enumerate((0xA1,0,0,1))]
assert analyze(1,1,[],m)[4]=='0,0,1'
# 合成ログを実パーサーに通して、未一致の刻印を出さない。
from analyze_main_to_sub import parse_iolog
from analyze_m6ia_main_sub import read_memlog
from pathlib import Path
import tempfile
with tempfile.TemporaryDirectory(dir=__import__('os').environ.get('TMPDIR')) as tmp:
    io_path=Path(tmp)/'io'; mem_path=Path(tmp)/'mem'
    io_path.write_text('\n'.join(f'{i} {i} 0 main OUT 00FD {v:02X} 0000' for i,v in enumerate((2,1,0,0,1),1))+'\n# 取りこぼし: 0件\n')
    mem_path.write_text('\n'.join(f'{i} 0 0000 {e.addr:04X} {e.value:02X}' for i,e in enumerate(m,1))+'\n取りこぼし: 0件\n')
    events,masked=parse_iolog(io_path); assert events and not masked
    assert analyze(1,1,events,read_memlog(mem_path))[4]=='0,0,1'
    import subprocess, sys, os
    tool=Path(os.environ['PYTHONPATH'])/'analyze_b10.py'
    proc=subprocess.run([sys.executable,str(tool),'--row','1','--run','1','--iolog',str(io_path),'--memlog',str(mem_path)],capture_output=True,text=True)
    assert proc.returncode==0 and '0,0,1' in proc.stdout
    mem_path.write_text(mem_path.read_text().replace('DF00 A1','DF00 DE'))
    proc=subprocess.run([sys.executable,str(tool),'--row','1','--run','1','--iolog',str(io_path),'--memlog',str(mem_path)],capture_output=True,text=True)
    assert proc.returncode==0 and 'other' in proc.stdout and '222' not in proc.stdout
    mem_path.write_text(mem_path.read_text().replace('取りこぼし: 0件','取りこぼし: 1件'))
    try: read_memlog(mem_path)
    except Exception: pass
    else: raise AssertionError("取りこぼしを検出できなかった")
try:
    load([io.StringIO('row\trun\n1\t1\n')]); assert False
except ValueError: pass
print('B10 自己検査 OK')
PY
