#!/usr/bin/env python3
"""生通信をリポジトリ外で処理し、長さ・真偽・件数のみ出す。"""
import json
import os
import sys
from collections import Counter
from pathlib import Path
from analyze_m6ia_main_sub import read_memlog
from b85_addendum2_rom import ARMS, pattern

def prefix_matches(received, pattern):
    return received[:len(pattern)] == list(pattern)

def analyze(root, row, run):
    p=root/'raw'/f'{row}-{run}'
    io=p.with_suffix('.io'); mem=p.with_suffix('.mem')
    # ログ全行を逐次検査し、通信に必要なイベントだけ保持する。
    from types import SimpleNamespace
    ev=[]; section=None; count=0; ends=[]; previous=None; marks=[]
    with io.open() as f:
        for line in f:
            if line.rstrip() in ('# main','# sub'):
                section=line.split()[1]; count=0; previous=None; continue
            if line.startswith('# 取りこぼし:'):
                import re
                match=re.fullmatch(r'# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件\s*',line)
                if not match or int(match[1]) or int(match[2])!=count: raise ValueError('drops')
                ends.append(section); section=None; continue
            if not section or line.startswith('#') or not line.strip(): continue
            parts=line.split()
            if len(parts)!=8 or parts[3]!=section or int(parts[0])!=count+1: raise ValueError('sequence')
            count+=1
            kind,port=parts[4],parts[5]
            if section=='main' and kind=='IN' and port=='0040' and previous and previous[0:2]==('IN','0040') and previous[2]!=parts[7]:
                marks.append(((previous[2],parts[7]), int(parts[1])))
            previous=(kind,port,parts[7])
            if port in ('00FC','00FD') and ((kind=='IN' and port=='00FC') or (kind=='OUT' and port=='00FD')):
                ev.append(SimpleNamespace(cpu=section,kind=kind,port=port,value=int(parts[6],16),clock=int(parts[1])))
    frequencies=Counter(key for key, _ in marks)
    marks=[clock for key,clock in marks if frequencies[key]==1]
    if ends!=['main','sub'] or len(marks)!=1: raise ValueError('marker')
    import re
    foot=re.findall(r'取りこぼし: (\d+)件 / 総イベント数: (\d+)件',mem.read_text())
    records=read_memlog(mem)
    if len(foot)!=1 or int(foot[0][0]) or int(foot[0][1])!=len(records): raise ValueError('memory log')
    m={e.addr:e.value for e in records}
    if m.get(0xdf52) not in (1,2,3,4): raise ValueError('state')
    window=[e for e in ev if e.clock>marks[0]]
    addr,end,size=ARMS[row-1]
    before=[e.value for e in ev if e.clock<marks[0] and e.cpu=='main' and e.kind=='OUT' and e.port=='00FD']
    setup=[12,addr>>8,addr&255,size>>8,size&255,*pattern(size)]
    if setup and before[-len(setup):]!=setup: raise ValueError('setup')
    sent=[e.value for e in window if e.cpu=='main' and e.kind=='OUT' and e.port=='00FD']
    expected=[9,addr>>8,addr&255,end>>8,end&255]
    if sent != expected[:len(sent)] or len(sent)>5: raise ValueError('send')
    recv=[e.value for e in window if e.cpu=='main' and e.kind=='IN' and e.port=='00FC']
    sub=[e.value for e in window if e.cpu=='sub' and e.kind=='OUT' and e.port=='00FD']
    if recv != sub[:len(recv)] or len(sub)>len(recv)+1: raise ValueError('transfer')
    received_requests=[e.value for e in window if e.cpu=='sub' and e.kind=='IN' and e.port=='00FC']
    if received_requests != sent[:len(received_requests)] or len(received_requests)>len(sent): raise ValueError('request transfer')
    status=m[0xdf52]
    if status==4 and (len(recv)!=65537 or m.get(0xdf53)!=1): raise ValueError('cap')
    if status==3 and len(sub)!=len(recv): raise ValueError('incomplete transfer')
    if status==3 and m.get(0xdf53)!=1: raise ValueError('end')
    if status==2 and m.get(0xdf53)==1: raise ValueError('state')
    if status!=1 and (len(sent)!=5 or len(received_requests)!=5): raise ValueError('incomplete')
    # 正常停止時のみ完全な長さと模様を判定する。上限到達は下限。
    expected_length=(end-addr) & 0xffff
    stopped=status==3
    match=prefix_matches(recv, pattern(size)) if stopped and len(recv)>=size else None
    return {'send_count':len(sent), 'sub_received_count':len(received_requests), 'reply_length':len(recv), 'sub_sent_count':len(sub), 'time_limit':status==2,
            'send_timeout':status==1, 'receive_stopped':stopped, 'receive_cap':status==4,
            'length_matches_hypothesis':len(recv)==expected_length if stopped else None,
            'pattern_scope':'full' if row<=4 else 'prefix', 'pattern_match':match}

def main():
    root=Path(sys.argv[1]); arms=[]; invalid=False
    for row in range(1,len(ARMS)+1):
        runs=[]
        for run in (1,2):
            try:
                result=analyze(root,row,run)
                if not os.environ.get('PC88_REF_ROM_DIR'): result['pattern_match']=None; result['length_matches_hypothesis']=None
                runs.append(result)
            except Exception: runs.append(None); invalid=True
        arms.append({'arm':row,'runs':runs})
    controls=(root/'raw/controls.status').read_text().strip()=='pass'
    for arm in arms:
        x,y=arm['runs']
        arm['two_runs_match']=x==y if x is not None and y is not None else None
        arm['judgment']='instrument_invalid' if invalid else 'controls_failed' if not controls else 'record_only' if not os.environ.get('PC88_REF_ROM_DIR') else 'not_reproducible' if x!=y else 'time_limit' if x['time_limit'] else 'send_timeout' if x['send_timeout'] else 'receive_cap' if x['receive_cap'] else 'observed'
    data={'controls_passed':controls,'arms':arms}
    (root/'summary/b85-addendum2.json').write_text(json.dumps(data,indent=2)+'\n')
    return 1 if invalid or not controls else 0
if __name__=='__main__': sys.exit(main())
