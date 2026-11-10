#!/usr/bin/env python3
"""INPUT$ の独立2走測定。画面本文を出力・保存しない。"""
import argparse, copy, json, os, re, subprocess, sys
from pathlib import Path
import l4_t5_delete_measure as base
import l4_listkw_measure as kw
import l4_key_measure as key

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(os.environ.get('PC88_T6_WORK', ROOT/'tmp/t6-work'))
ARMS={}
for n in (1,3,10):
    ARMS[f'n{n}-exact']=(str(n),('k7q9m2v4b6'[:n]),False)
    ARMS[f'n{n}-extra']=(str(n),('k7q9m2v4b6'[:n]+'xz'),False)
ARMS.update({'return':('3','k\nq',False),'early':('3','k7q',True),
             'n0':('0','',False),'n255':('255','k'*255,False),
             'n256':('256','',False),'negative':('-1','',False),
             'string':('"k"','',False)})
NAMES=['ref-'+x for x in base.REFS]+['direct']+list(ARMS)

def plan(name):
    if name.startswith('ref-') or name=='direct':
        op=base.REFS[name[4:]] if name.startswith('ref-') else 'print input$(1)'
        return ['clear 200,&hdfff','new','for i=&he000 to &he048:poke i,0:next','poke &he000,151','cls:locate 0,5','@before',op,'@direct','@after','@cleanup','poke &he001,163'],op
    expr,typed,early=ARMS[name]
    lines=['clear 200,&hdfff','new','10 on error goto 9000','20 cls:locate 0,5',
           '30 poke &he002,csrlin:poke &he003,pos(0)']
    if early: lines+=['35 for j=1 to 3000:next j']
    lines += ['39 poke &he00a,1',f'40 a$=input$({expr})',
              '50 poke &he004,csrlin:poke &he005,pos(0)',
              '60 poke &he006,len(a$)',
              '70 for i=1 to len(a$):poke &he010,asc(mid$(a$,i,1)):next i',
              '75 for j=1 to 1000:next j',
              '80 b$=inkey$:if len(b$)>0 then poke &he007,asc(b$)',
              '90 poke &he008,1:goto 100',
              '100 poke &he001,163:end',
              '9000 poke &he009,err:resume 100',
              'for i=&he000 to &he048:poke i,0:next','poke &he000,151','run']
    return lines,'run'

def parse_log(path, name, first_type_frame):
    raw=path.read_text(); m=re.search(r'^# 取りこぼし: 0件 / 総イベント数: (\d+)件$',raw,re.M)
    if not m or not re.search(r'^range\s+: E000-E048$',raw,re.M): raise ValueError('RAM記録')
    writes=[]; times=[]; boot_writes=0; count=0
    for line in raw.splitlines():
        if re.match(r'^\s*\d+\s',line):
            x=re.fullmatch(r'\s*(\d+)\s+(\d+)\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})',line)
            if not x or int(x[1])!=count+1: raise ValueError('RAM形式')
            count+=1
            if int(x[2]) < first_type_frame: boot_writes+=1
            else:
                writes.append([int(x[3],16),int(x[4],16)]); times.append(int(x[2]))
    if count!=int(m[1]): raise ValueError('件数')
    prefix=[[a,0] for a in range(0xe000,0xe049)]+[[0xe000,151]]
    if writes[:74]!=prefix:
        bad=[(i+1,writes[i][0]) for i in range(min(74,len(writes))) if writes[i]!=prefix[i]]
        raise ValueError('初期化: 不一致%d件 %s' % (len(bad), ','.join('%d:%04X' % item for item in bad)))
    tail=writes[74:]
    base.reject_unexpected(tail, set(range(0xe001,0xe00b)) | {0xe010}, 74)
    addresses=[a for a,v in tail]
    if name.startswith('ref-') or name=='direct':
        if addresses != [0xe001]: raise ValueError('書込み順序')
    else:
        # 正常経路、エラー経路、入力待ちの途中を受け入れる。
        normal=[0xe002,0xe003,0xe00a,0xe004,0xe005,0xe006]
        error=[0xe002,0xe003,0xe00a,0xe009,0xe001]
        valid_prefix = addresses == normal[:len(addresses)] or addresses == error[:len(addresses)]
        if addresses[:6] == normal and len(addresses) >= 6:
            count=tail[5][1]
            suffix=addresses[6:]
            expected=[0xe010]*count
            if suffix[:len(expected)] == expected:
                remainder=suffix[len(expected):]
                valid_prefix = remainder in ([], [0xe007], [0xe008], [0xe007,0xe008],
                                             [0xe008,0xe001], [0xe007,0xe008,0xe001])
        if not valid_prefix: raise ValueError('書込み順序')
    if sum(a==0xe001 and v==163 for a,v in tail)>1: raise ValueError('完了印')
    return {'boot_writes':boot_writes,'writes':tail,'completed':bool(tail and tail[-1]==[0xe001,163]),'input_stage_frame':next((times[i] for i in range(74,len(writes)) if writes[i]==[0xe00a,1]),None)}

def capture(rom,name,work,official):
    cmds,op=plan(name); at=700 if official else 100
    first_type_frame=at
    args=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom),'--key-hold','4','--key-gap','8']
    frames=[]; paths=[]; key_frame=None
    def snap(frame):
        p=work/'screen.bin'; args.extend(['--vram-dump',str(p),'--vram-dump-at',str(frame)])
        paths.append(work/f'screen.f{frame:06d}.bin'); frames.append(frame)
    for cmd in cmds:
        if cmd=='@before': snap(at+60); at+=260
        elif cmd=='@direct':
            if name=='direct':
                snap(at+100);snap(at+300)
                args+=['--type-at',str(at+600),'--type','k']
            at+=4000
        elif cmd=='@after': snap(at);snap(at+300);at+=600
        elif cmd=='@cleanup':
            if name=='direct': args+=['--type-at',str(at),'--type','\n'];at+=800
        else:
            args+=['--type-at',str(at),'--type',cmd+'\n']
            start=at+len(cmd)*12
            at+=(len(cmd)+1)*12+240
            if cmd.startswith('for i=&he000'): at+=5000
            if cmd=='run':
                expr,typed,early=ARMS[name]
                snap(start+(60 if early or name=='return' else 300))
                if typed:
                    when=start+(80 if early or name=='return' else 600)
                    key_frame=when
                    args+=['--type-at',str(when),'--type',typed]
                    at=max(at,when+len(typed)*12+(18000 if name in ('n255','early') else 3000))
                else: at+=3000
                snap(at);snap(at+300);at+=600
    log=work/'ram.log'; io=work/'io.log'
    args+=['--io-log',str(io),'--mem-write-log',str(log),'--mem-write-range','E000-E048','--mem-write-from-frame','0','--frames',str(at+400)]
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode or b'untypable' in p.stderr.lower(): raise ValueError('実行/打鍵')
        raw=[p.read_bytes() for p in paths]
        if raw[-1]!=raw[-2]: raise ValueError('画面安定')
        geometry=key.parse_geometry(io,frames[-2:])
        if geometry[0]!=geometry[1] or geometry[0]['columns']!=80 or geometry[0]['rows'] is None: raise ValueError('表示設定')
        rows=base.bodies(raw[-1]); result={'memory':parse_log(log,name,first_type_frame),'geometry':geometry[0],
                'rows':base.metrics(rows,raw[-1],geometry[0]['rows'])}
        if name in ARMS:
            result['key_frame']=key_frame
            stage=result['memory']['input_stage_frame']
            if stage is None or (key_frame is not None and ((name=='early' and not key_frame<stage) or (name!='early' and not stage<key_frame))): raise ValueError('入力時刻')
            result['before_rows']=base.metrics(base.bodies(raw[0]),raw[0],geometry[0]['rows'])
        if name.startswith('ref-') or name=='direct':
            if not result['memory']['completed']: raise ValueError('直接診断完了印')
            before=base.bodies(raw[0]); prompt=base.signature(0,before[5])
            if not before[5] or any(before[:5]) or before[6] or rows[6].strip().lower()!=op: raise ValueError('開始/打鍵')
            response_rows=rows
            if name=='direct':
                if raw[1]!=raw[2]: raise ValueError('打鍵前画面安定')
                prior=base.bodies(raw[1])
                if any(base.signature(0,prior[i])==prompt for i in range(7,min(geometry[0]['rows'],19))): response_rows=prior
            matches=[i for i in range(7,min(geometry[0]['rows'],19)) if base.signature(0,response_rows[i])==prompt]
            result['response']=[base.signature(i,response_rows[i]) for i in range(7,matches[0])] if len(matches)==1 else None
        return result
    finally:
        log.unlink(missing_ok=True);io.unlink(missing_ok=True)
        for p in paths: p.unlink(missing_ok=True);Path(str(p)+'.info.txt').unlink(missing_ok=True)

def measure(rom,work,official=False):
    work.mkdir(parents=True,exist_ok=True); records={}
    for name in NAMES:
        runs=[]
        for _ in range(2):
            try: runs.append(capture(rom,name,work,official))
            except (ValueError,OSError) as exc: print(name+': 関門失敗 '+str(exc),flush=True);runs.append(None)
        records[name]={'runs':runs,'gate':base.stable_pair(runs)}
        print(name+': '+('通過' if records[name]['gate'] else '失敗'),flush=True)
    refs={x:records['ref-'+x]['runs'][0]['response'] for x in base.REFS if records['ref-'+x]['gate']}
    if len(refs)==len(base.REFS) and records['direct']['gate']:
        target=records['direct']['runs'][0]['response']
        records['direct']['identification']=base.identify(target,refs) if target is not None else '欠測'
    return {'version':1,'records':records}

def valid(d):
    return d.get('version')==1 and set(d.get('records',{}))==set(NAMES) and all(r.get('gate') is True and base.stable_pair(r.get('runs',[])) for r in d['records'].values())
def check(a,b): return valid(a) and valid(b) and a==b
def save(path,data): Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
def selftest():
    work=WORK/'selftest';work.mkdir(parents=True,exist_ok=True);rom=work/'rom'
    base.unexpected_selftest(lambda p: parse_log(p, 'ref-none', 10), work/'synthetic.log', [(0xe001,163)])
    print('合成対照: 起動時書込みを除外、打鍵後の前置き前と器具外の書込みを拒否')
    p=subprocess.run([sys.executable,str(ROOT/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],capture_output=True)
    if p.returncode: raise ValueError('自作ROMビルド')
    data=measure(rom,work);save(work/'actual.json',data)
    if not valid(data): print('全腕関門失敗');return 1
    save(work/'expected.json',data);expected=json.loads((work/'expected.json').read_text());assert check(data,expected)
    broken=copy.deepcopy(expected)
    for run in broken['records'][NAMES[0]]['runs']: run['memory']['writes'][-1][1]^=1
    assert valid(broken) and not check(data,broken)
    a=[base.signature(7,'a')];b=[base.signature(7,'b')]
    assert base.identify(a,{'ERR2':a,'ERR5':b})=='ERR2' and base.identify(a,{'ERR2':b,'ERR5':b})=='候補外'
    mismatch=copy.deepcopy(data);mismatch['records'][NAMES[0]]['runs'][1]['memory']['writes'][-1][1]^=1
    assert not valid(mismatch)
    print('陰性対照3種: 通過');print(f'全腕関門: {len(NAMES)}/{len(NAMES)}');return 0

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='cmd',required=True)
    m=s.add_parser('measure');m.add_argument('--rom-dir',type=Path,required=True);m.add_argument('--work-dir',type=Path,default=WORK/'measure');m.add_argument('--out',type=Path,required=True);m.add_argument('--official',action='store_true')
    e=s.add_parser('expected');e.add_argument('--measured',type=Path,required=True);e.add_argument('--out',type=Path,required=True)
    c=s.add_parser('check');c.add_argument('--measured',type=Path,required=True);c.add_argument('--expected',type=Path,required=True)
    s.add_parser('selftest');a=p.parse_args()
    if a.cmd=='selftest': return selftest()
    if a.cmd=='measure':
        d=measure(a.rom_dir,a.work_dir,a.official);save(a.out,d);return int(not valid(d))
    d=json.loads(a.measured.read_text())
    if a.cmd=='expected':
        if not valid(d): return 1
        save(a.out,d);return 0
    ok=check(d,json.loads(a.expected.read_text()));print('照合: '+('一致' if ok else '不一致'));return int(not ok)
if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError,AssertionError) as e: print('NG 器具:',type(e).__name__);raise SystemExit(1)
