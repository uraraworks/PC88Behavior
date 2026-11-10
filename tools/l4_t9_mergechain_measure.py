#!/usr/bin/env python3
"""MERGE・CHAIN・COMMON 測定。画面本文は取得しない。"""
import argparse
import concurrent.futures
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
sys.dont_write_bytecode = True
import build_blank_data_disk as blank
import l4_t7_autorenum_measure as base
import l4_t5_delete_measure as common
import l4_listkw_measure as kw
import struct

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'tmp/t9-work'
REFS={'none':'rem', **{'ERR'+str(n):'error '+str(n) for n in (2,5,8,52,53,54,61,64,71,76)}}
ARMS=['merge','merge-missing','merge-binary','merge-program','chain','chain-common','chain-array','chain-line','chain-merge-all','chain-delete','common-program','common-direct']
NAMES=['ref-'+x for x in REFS]+ARMS
ROUND='first'

def plan(name):
    c=[('type','clear 200,&hdfff'),('type','new')]
    if name.startswith(('merge','chain')) and name!='merge-missing':
        target=['20 poke &he011,22:end','40 poke &he013,44:end'] if name.startswith('merge') else [
            '10 poke &he010,11', '20 poke &he011,a:poke &he012,len(b$):poke &he013,c(1):end',
            '40 poke &he014,44:end']
        c += [('type',x) for x in target]
        c += [('type','cls:locate 0,5'),('type','save "2:x"'+('' if name=='merge-binary' else ',a')),('snap2','save'),('type','new')]
    if name.startswith('merge'):
        c += [('type',x) for x in ['10 poke &he010,10:end','20 poke &he011,20:end','30 poke &he012,30:end']]
        if name=='merge-program': c += [('type','80 on error goto 90:merge "2:x":poke &he015,1:end'),('type','90 poke &he016,err:end')]
    if name.startswith('chain'):
        setup=['10 on error goto 90']
        if name=='chain-common': setup += ['20 common a,b$']
        if name=='chain-array': setup += ['20 common c()']
        setup += ['30 dim c(2):a=7:b$="xyz":c(1)=9']
        cmd={'chain':'chain "2:x"','chain-common':'chain "2:x"','chain-array':'chain "2:x"',
             'chain-line':'chain "2:x",40','chain-merge-all':'chain merge "2:x",40,all',
             'chain-delete':'chain merge "2:x",40,all,delete 10-20'}[name]
        setup += ['40 '+cmd+':poke &he015,1:end','90 poke &he016,err:end']
        c += [('type',x) for x in setup]
    if name=='common-program': c += [('type','10 on error goto 90:common a,b$:poke &he015,1:end'),('type','90 poke &he016,err:end')]
    c += [('type','for i=&he000 to &he048:poke i,0:next'),('type','poke &he000,151'),('type','cls:locate 0,5'),('snap','before')]
    op=REFS[name[4:]] if name.startswith('ref-') else {'merge':'merge "2:x"','merge-missing':'merge "2:missing"','merge-binary':'merge "2:x"','common-direct':'common a,b$'}.get(name,'run')
    c += [('type',op),('snap2','operation'),('type','poke &he002,1')]
    if name.startswith('merge'):
        for i,n in enumerate((10,20,30,40)):
            c += [('type','cls:locate 0,5'),('type',f'goto {n}'),('snap2',f'p{i}'),('type',f'poke &he002,{i+2}')]
    c += [('type','poke &he001,163')]
    if ROUND=='addendum1':
        if name=='save-short':
            c=[('type','clear 200,&hdfff'),('type','new'),('type','10 end'),('type','for i=&he000 to &he048:poke i,0:next'),('type','poke &he000,151'),('type','cls:locate 0,5'),('snap','before'),('type','save "2:x",a'),('snap2','operation'),('type','poke &he002,1'),('type','poke &he001,163')]
            op='save "2:x",a'
        else:
            c=[(k,v.replace('2:x','2:t9prog')) for k,v in c]
            op=op.replace('2:x','2:t9prog')
            if name=='merge-program':
                c=[(k,'goto 80' if k=='type' and v=='run' else v) for k,v in c]
                op='goto 80'
    return c,op

def disks(work):
    image=bytearray(blank.build())
    pos=struct.unpack_from('<I',image,32+(18*2+1)*4)[0]
    for _ in range(16):
        if tuple(image[pos:pos+3])==(18,1,13):
            image[pos+16:pos+272]=bytes([0x10])*256; break
        pos+=272
    else: raise ValueError('媒体')
    (work/'a.d88').write_bytes(image); (work/'b.d88').write_bytes(blank.build())
    return ['--disk',str(work/'a.d88'),'--disk2',str(work/'b.d88'),'--save-to-disk-image']

def capture(rom,name,work,official=False):
    cmds,op=plan(name); args=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom),'--screen-signature-only','--out',str(work/'sig.tsv')]+disks(work)
    at=700 if official else 100; first=at; ids=[]
    for kind,value in cmds:
        if kind=='type': args += ['--type-at',str(at),'--type',value+'\n']; at+=(len(value)+1)*8+240
        else:
            for delay in ((60,160) if kind=='snap2' else (60,)):
                sid=value+('a' if delay==60 else 'b'); ids.append(sid); args+=['--screen-signature-at',f'{sid}:{at+delay}']
            at+=260
    log=work/'ram.log'; sigfile=work/'sig.tsv'
    args+=['--mem-write-log',str(log),'--mem-write-range','E000-E048','--mem-write-from-frame','0','--frames',str(at+600)]
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode: raise ValueError('実行')
        sig=base.parse_signatures(sigfile)
        if set(sig)!=set(ids) or any(sig[x]!=sig[x[:-1]+'a'] for x in ids if x.endswith('b')): raise ValueError('署名安定')
        if 5 not in sig['beforea'] or any(i in sig['beforea'] for i in range(5)): raise ValueError('開始位置')
        for sid,command in ([('save','save "2:'+('t9prog' if ROUND=='addendum1' else 'x')+'"'+('' if name=='merge-binary' else ',a'))] if any(k=='snap2' and v=='save' for k,v in cmds) else [])+[('operation',op)]+[(f'p{i}',f'goto {n}') for i,n in enumerate((10,20,30,40)) if name.startswith('merge')]:
            expected=common.signature(6,command)
            if sig[sid+'a'].get(6)!=(expected['char_count'],expected['sha256']): raise ValueError('打鍵反映')
        mem=base.parse_memory(log,first)
        stages=[v for a,v in mem['writes'] if a==0xe002]
        if stages != (list(range(1,6)) if name.startswith('merge') else [1]): raise ValueError('段階')
        return {'screen':{k:v for k,v in sig.items() if not k.endswith('b')},'writes':mem['writes'],'boot_writes':mem['boot_writes']}
    finally:
        log.unlink(missing_ok=True); sigfile.unlink(missing_ok=True)
        (work/'a.d88').unlink(missing_ok=True); (work/'b.d88').unlink(missing_ok=True)

def measure(rom,work,official=False):
    records={n:{'runs':[None,None],'gate':False} for n in NAMES}
    def run(n,i):
        d=work/n/str(i); d.mkdir(parents=True,exist_ok=True); return capture(rom,n,d,official)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(run,n,i):(n,i) for n in NAMES for i in range(2)}
        for task in concurrent.futures.as_completed(tasks):
            n,i=tasks[task]
            try: records[n]['runs'][i]=task.result()
            except (ValueError,OSError) as exc: print(f'{n} {i+1}: 関門失敗 ({exc})',flush=True)
    for n in NAMES:
        records[n]['gate']=base.stable_pair(records[n]['runs'])
        print(f"{n}: {'通過' if records[n]['gate'] else '失敗'}",flush=True)
    if all(records['ref-'+x]['gate'] for x in REFS):
        refs={x:base.response(records['ref-'+x]['runs'][0]['screen']['operationa']) for x in REFS}
        prompts={}
        for x in REFS:
            lines=sorted((int(k),v) for k,v in records['ref-'+x]['runs'][0]['screen']['operationa'].items() if 7<=int(k)<19)
            if not lines: raise ValueError('参照プロンプト')
            row,value=lines[-1]
            if row in prompts and prompts[row]!=value: raise ValueError('参照プロンプト')
            prompts[row]=value
        for n in NAMES:
            if records[n]['gate']:
                try:
                    records[n]['responses']={k:base.identify(base.response(v,prompts),refs) for k,v in records[n]['runs'][0]['screen'].items() if k!='beforea'}
                except ValueError: records[n]['gate']=False
    return {'version':1,'records':records}

def valid(d):
    return d.get('version')==1 and set(d.get('records',{}))==set(NAMES) and all(r['gate'] and base.stable_pair(r['runs']) and 'responses' in r for r in d['records'].values())
def save(p,d): p.write_text(json.dumps(d,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
def selftest():
    work=WORK/'selftest'; work.mkdir(parents=True,exist_ok=True); rom=work/'rom'
    p=subprocess.run([sys.executable,'-B',str(ROOT/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise ValueError('自作ROMビルド')
    d=measure(rom,work); save(work/'actual.json',d)
    if not valid(d): return 1
    d=json.loads((work/'actual.json').read_text()); save(work/'expected.json',d)
    bad=copy.deepcopy(d)
    for r in bad['records'][NAMES[0]]['runs']: r['screen']['operationa']['6'][0]^=1
    assert valid(bad) and d!=bad
    assert base.identify([(7,'a')],{'ERR8':[(7,'b')]})=='候補外'
    bad=copy.deepcopy(d); bad['records'][NAMES[0]]['runs'][1]['screen']['operationa']['6'][0]^=1
    assert not valid(bad)
    common.unexpected_selftest(lambda p:base.parse_memory(p,10),work/'synthetic.log',[(0xe001,163)])
    p=work/'sweep.log'; prefix=[(a,0) for a in range(0xe000,0xe049)]+[(0xe000,151),(0xe001,163)]
    for sweep in ([(a,0) for a in range(0xe000,0xe049)],[(a,(a*7)&255) for a in reversed(range(0xe000,0xe049))]):
        rows=[(9,a,v) for a,v in sweep]+[(10,a,v) for a,v in prefix]
        p.write_text('range : E000-E048\n# 取りこぼし: 0件 / 総イベント数: %d件\n'%len(rows)+''.join('%d %d 0000 %04X %02X\n'%(i,f,a,v) for i,(f,a,v) in enumerate(rows,1)))
        assert base.parse_memory(p,10)['boot_writes']==len(sweep)
    p.unlink(); print(f'全腕関門: {len(NAMES)}/{len(NAMES)}; 陰性対照・起動時掃引2種: 通過'); return 0

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='command',required=True); st=sub.add_parser('selftest'); st.add_argument('--round',choices=['first','addendum1'],default='first')
    m=sub.add_parser('measure'); m.add_argument('--rom-dir',type=Path,required=True); m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True); m.add_argument('--official',action='store_true')
    e=sub.add_parser('expected'); e.add_argument('--measured',type=Path,required=True); e.add_argument('--out',type=Path,required=True)
    c=sub.add_parser('check'); c.add_argument('--measured',type=Path,required=True); c.add_argument('--expected',type=Path,required=True)
    for parser in (m,e,c): parser.add_argument('--round',choices=['first','addendum1'],default='first')
    a=ap.parse_args()
    global ROUND, REFS, NAMES, WORK
    ROUND=a.round
    if ROUND=='addendum1':
        REFS={**REFS, 'ERR33':'error 33', 'ERR56':'error 56'}
        NAMES=['ref-'+x for x in REFS]+ARMS+['save-short']
        WORK=ROOT/'tmp/t9a1-work'
    if a.command=='selftest': return selftest()
    if a.command=='measure':
        d=measure(a.rom_dir,a.work_dir,a.official); save(a.out,d); return int(not valid(d))
    d=json.loads(a.measured.read_text())
    if a.command=='expected':
        if not valid(d): return 1
        save(a.out,d); return 0
    e=json.loads(a.expected.read_text()); ok=valid(d) and valid(e) and d==e; print('照合: '+('一致' if ok else '不一致')); return int(not ok)
if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError,KeyError) as exc: print('NG 器具:',type(exc).__name__,'（本文非出力）'); raise SystemExit(1)
