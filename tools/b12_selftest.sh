#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$REPO/tmp/b12-work"
TMPDIR="$REPO/tmp/b12-work" PYTHONPATH="$REPO/tools" python3 - <<'PY'
import io, os, struct, subprocess, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as E
from make_b12_disk import build
import importlib.util
from judge_b12 import ROWS, FIELDS, judge, load
from analyze_b12 import analyze
from analyze_m6ik import status_names
from analyze_main_to_sub import parse_iolog
from analyze_m6ia_main_sub import read_memlog

spec=importlib.util.spec_from_file_location('build_main_rom', Path(os.environ['PYTHONPATH']).parent/'src/build_main_rom.py')
rom=importlib.util.module_from_spec(spec); spec.loader.exec_module(rom)
for row in range(1,13):
    text=rom.b12_boot(row)
    requests=[(0,2,1),(2,1,2)] if row==12 else [ROWS[row]]
    for i,(t,r,p) in enumerate(requests):
        sequence=f"""    LD A,002h
    CALL MAIN_SUB_SEND
    JP C,_b12_{i}_timeout
    LD A,0{p:02X}h
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_b12_{i}_timeout
    XOR A
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_b12_{i}_timeout
    LD A,0{t:02X}h
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_b12_{i}_timeout
    LD A,0{r+(row==11):02X}h
    CALL MAIN_SUB_SEND_REQUEST_CONT"""
        if row == 12: sequence=sequence.replace('JP C,', 'JR C,')
        assert sequence in text and f'CP 0{4*(p+1):02X}h' in text

d=build()
assert struct.unpack_from('<I',d,28)[0]==len(d)
for t in range(80):
    pos=struct.unpack_from('<I',d,32+t*4)[0]; c,h=divmod(t,2); size,n=(256,16) if t==0 else (1024,5)
    for r in range(1,n+1):
        assert tuple(d[pos:pos+4])==(c,h,r,1 if t==0 else 3)
        assert struct.unpack_from('<H',d,pos+4)[0]==n and struct.unpack_from('<H',d,pos+14)[0]==size
        for b in range(size//256):
            data=d[pos+16+256*b:pos+16+256*(b+1)]
            assert data[:5]==bytes((0xa1,c,h,r,b)) and data[5:]==bytes([0x55])*251
        pos+=16+size

def record(n,run,q=1):
    t,r,p=(2,1,2) if (n,q)==(12,2) else ROWS[n]
    blocks=[f'{t//2},{t%2},{r+i//4},{i%4}' for i in range(p*4)] if t else [f'0,0,{r},0']
    if n==11: blocks[0]='1,0,3,0'
    return dict(row=str(n),run=str(run),request=str(q),count=str(len(blocks)*256),timeout='1',blocks=';'.join(blocks),read_count='0',reads='-',read_id_count='0',other_commands='-',st0='-',st1='-')
base={(n,run,q):record(n,run,q) for n in ROWS for run in (1,2) for q in ((1,2) if n==12 else (1,))}
assert len({status_names(i << 6,0)['st0'][0] for i in range(4)})==4
assert len(status_names(0x3f,0xb7)['st0'])==7 and len(status_names(0x3f,0xb7)['st1'])==6
assert judge(base)['controls_passed'] and judge(base)['p1']=='sectors_1024' and judge(base)['after_track_zero'] is True
assert judge(base)['crossing'][7]=='partial'
a={k:v.copy() for k,v in base.items()}
for run in (1,2):
    for n in (2,3,4,5,6): a[n,run,1]['count']=str(ROWS[n][2]*256)
assert judge(a)['p1']=='units_256'
a[2,1,1]['count']='17'; a[2,2,1]['count']='17'; assert isinstance(judge(a)['p1'],dict)
a[2,2,1]['timeout']='0'; assert judge(a)['p1']=='inconclusive'
a={k:v.copy() for k,v in base.items()}
for run in (1,2): a[11,run,1]['blocks']='1,0,2,0'
assert not judge(a)['controls_passed']
a={k:v.copy() for k,v in base.items()}
for run in (1,2): a[7,run,1]['blocks']='-'; a[8,run,1]['blocks']='2,0,1,0'
assert judge(a)['crossing']=={7:'fails',8:'advances'}
a[8,2,1]['timeout']='0'; assert judge(a)['crossing'][8]=='inconclusive'
a={k:v.copy() for k,v in base.items()}; a[12,1,2]['timeout']='0'; a[12,2,2]['timeout']='0'; assert judge(a)['after_track_zero'] is False
# 2要求の境界、FDC 引数と種類ごとの回数、公開ステータスを検査する。
def ev(clock,cpu,kind,port,value): return E(clock=clock,cpu=cpu,kind=kind,port=port,value=value)
events=[]
for start,request in ((10,(2,1,0,0,2)),(100,(2,2,0,2,1))):
    events += [ev(start+i,'main','OUT','00FD',v) for i,v in enumerate(request)]
    events += [ev(start+10+i,'sub','OUT','00FB',v) for i,v in enumerate((0x4a,0,0x0f,0,0,0x46,0,1,0,1,3,5,0,0))]
    events += [ev(start+30+i,'sub','IN','00FB',v) for i,v in enumerate((0,0,0,1,0,1,3))]
values=[]
for q in (0,1):
    baseaddr=0xdfe0+4*q
    values += [E(addr=baseaddr+i,value=v) for i,v in enumerate((5,0,1,1))]
    values += [E(addr=0xdf00+q*0x90+i,value=v) for i,v in enumerate((0xa1,q,0,2 if q==0 else 1,0))]
rows=analyze(12,1,events,values)
assert len(rows)==2 and all(r[6:10]==['1','1,0,1,3,5','1','seek:1'] for r in rows)
assert rows[0][5]=='0,0,2,0' and rows[1][5]=='1,0,1,0'
# 実パーサーを通す合成ログ。未知の刻印は値を出さず other にする。
with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as tmp:
    io_path=Path(tmp)/'io'; mem=Path(tmp)/'mem'
    commands=[2,1,0,0,1]
    io_path.write_text('\n'.join(f'{i} {i} 0 main OUT 00FD {v:02X} 0000' for i,v in enumerate(commands,1))+'\n# 取りこぼし: 0件\n')
    vals={0xDFE0:5,0xDFE1:0,0xDFE2:1,0xDFE3:1,**{0xDF00+i:v for i,v in enumerate((0xde,0xad,0xbe,0xef,0xdd))}}
    def write(): mem.write_text('\n'.join(f'{i} 0 0000 {a:04X} {v:02X}' for i,(a,v) in enumerate(vals.items(),1))+'\n取りこぼし: 0件\n')
    write(); tool=Path(os.environ['PYTHONPATH'])/'analyze_b12.py'
    def run(): return subprocess.run([sys.executable,str(tool),'--row','1','--run','1','--iolog',str(io_path),'--memlog',str(mem)],capture_output=True,text=True)
    p=run(); assert p.returncode==0 and 'other' in p.stdout and all(x not in p.stdout for x in ('222','173','190','239','221'))
    for i,v in enumerate((0xa1,0,0,1,0)): vals[0xDF00+i]=v
    write(); p=run(); assert p.returncode==0 and '0,0,1,0' in p.stdout
    mem.write_text(mem.read_text().replace('取りこぼし: 0件','取りこぼし: 1件')); assert run().returncode!=0
try: load([io.StringIO('row\trun\n1\t1\n')]); assert False
except ValueError: pass
print('B12 自己検査 OK')
PY
