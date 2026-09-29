#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 - "$REPO" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'tools'))
import analyze_m6ik as a
from analyze_main_to_sub import Ev
from analyze_m6ia_main_sub import MemEvent

def sample(fault=None, raw=False):
    events=[]; memory=[]; clock=0
    def io(cpu,kind,port,value,frame=0):
        nonlocal clock
        clock+=1; events.append(Ev(clock,clock,frame,cpu,kind,port,value,'0000'))
    def mem(addr,value): memory.append(MemEvent(len(memory)+1,0,0,addr,value))
    io('main','OUT','00FD',0)
    io('main','OUT','00FD',0x17); io('main','OUT','00FD',0x0F)
    mem(a.PRE_MARKER,1)
    for n,d,t,r in a.ROWS:
        mem(a.MARKER,n)
        for value in (2,1,d,t,r): io('main','OUT','00FD',value)
        if fault != ('missing',n):
            c,h=t>>1,t&1
            if fault == ('ch',n): c,h=h,c
            actual_r=r+(fault==('r',n))
            for value in (0x46,d|(h<<2),c,h,actual_r,1,1,14,255):
                io('sub','OUT','00FB',value)
            # 合成データ部の目印。結果の7位置だけをステータスに使う。
            for _ in range(256): io('sub','IN','00FB',0xD7)
            for _ in range(7): io('sub','IN','00FB',0)
        stamp=bytes((0xA1 if d==0 else 0xB2,t>>1,t&1,r))
        data=stamp+bytes((0xD7,))*252
        for i,value in enumerate(data): mem(0xDF00+i,value)
        mem(0xE002,1)
    io('main','IN','0040',0,2001)
    return (events,memory) if raw else a.analyze_events('K-F1',events,memory)

base=sample(); assert base['reached']
assert [x['classification'] for x in base['rows']]==['agree','logical','logical','logical','logical','agree']
assert sample(('ch',2))['rows'][1]['classification']=='other'
assert sample(('r',2))['rows'][1]['classification']=='other'
assert sample(('missing',2))['rows'][1]['classification']=='no_read'
output=json.dumps(base,sort_keys=True)
assert '215,215,215' not in output and 'D7D7D7' not in output
assert all('receive_sha256' in x for x in base['rows'])
import subprocess,tempfile
with tempfile.TemporaryDirectory() as temp:
    p=Path(temp); events,memory=sample(raw=True)
    (p/'io').write_text(''.join(f'{e.seq} {e.clock} {e.frame} {e.cpu} {e.kind} '
        f'{e.port} {e.value:02X} {e.pc}\n' for e in events))
    (p/'mem').write_text('取りこぼし: 0件\n'+''.join(
        f'{e.seq} {e.frame} {e.pc:04X} {e.addr:04X} {e.value:02X}\n' for e in memory))
    proc=subprocess.run([sys.executable,str(Path(sys.argv[1])/'tools/analyze_m6ik.py'),
        '--arm','K-F1','--iolog',str(p/'io'),'--memlog',str(p/'mem')],
        capture_output=True,text=True,check=True)
    (p/'result.json').write_text(proc.stdout)
    assert 'D7'*8 not in proc.stdout.upper()
    assert '215,215,215' not in (p/'result.json').read_text()
print('analyze_m6ik_selftest: G7陰性対照3種・G9目印非出力 OK')
PY
