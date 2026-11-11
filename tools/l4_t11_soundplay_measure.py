#!/usr/bin/env python3
"""SOUND・PLAY の署名、印、音源 OUT を採取する。"""
import argparse
import concurrent.futures
import copy
import json
import os
import re
import subprocess
import sys
from unittest.mock import patch
from pathlib import Path
sys.dont_write_bytecode = True
import l4_listkw_measure as kw
import l4_t5_delete_measure as common
import l4_t7_autorenum_measure as base
import l4_t10_editmotor_measure as t10
import l4_t9_mergechain_measure as t9

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'tmp/t11-work'
REFS = {'none':'rem', 'ERR2':'error 2', 'ERR5':'error 5', 'ERR8':'error 8'}
SOUND = {'mixer':'sound 7,&h38', 'tone':'sound 0,100', 'zero':'sound 0,0',
         'reg-negative':'sound -1,0', 'reg-256':'sound 256,0', 'reg-ff':'sound &hff,0',
         'data-negative':'sound 0,-1', 'data-256':'sound 0,256', 'program':'goto 90'}
PLAY = {'c':'play "c"', 'scale':'play "cdefgab"', 'octave':'play "o5c"',
        'length':'play "l8c"', 'tempo':'play "t200c"', 'volume':'play "v10c"',
        'rest':'play "r"', 'sharp':'play "c#"', 'plus':'play "c+"',
        'flat':'play "c-"', 'number':'play "n60"', 'channels':'play "c","e","g"',
        'invalid':'play "x"', 'octave-invalid':'play "o9c"', 'length-invalid':'play "l0c"'}
CONFIGS = {'A': ('N88 V2', 'OPNA'), 'B': ('N88 V1H', 'OPN'),
           'C': ('N88 V1S', 'OPN'), 'D': ('N88 V2', 'OPN')}
ROUND = 'first'
NAMES = ['ref-'+x for x in REFS] + ['sound-'+x for x in SOUND] + ['play-'+x for x in PLAY]


def plan(name):
    cmds = [('type','clear 200,&hdfff'), ('type','new')]
    if name == 'sound-program':
        if ROUND == 'addendum1':
            cmds += [('type','90 on error goto 95:sound 7,&h38:poke &he017,1:poke &he002,20:end'),
                     ('type','95 poke &he018,err:poke &he002,20:end')]
        else:
            cmds += [('type','90 on error goto 95:sound 7,&h38:poke &he017,1:end'),
                     ('type','95 poke &he018,err:end')]
    cmds += [('type','for i=&he000 to &he048:poke i,0:next'),
             ('type','poke &he000,151'), ('type','cls:locate 0,5'), ('snap','before')]
    op = REFS[name[4:]] if name.startswith('ref-') else SOUND[name[6:]] if name.startswith('sound-') else PLAY[name[5:]]
    # 同一文列の印は文が復帰した場合だけ実行される。
    if name.startswith('play-'): op += ':poke &he017,1'
    cmds += [('operation',op), ('snap','operation')]
    if ROUND != 'addendum1' or name != 'sound-program': cmds += [('type','poke &he002,20')]
    cmds += [('type','poke &he001,163')]
    return cmds, op


def sound_outputs(path, start, end):
    pattern = re.compile(r'^\s*\d+\s+\d+\s+(\d+)\s+main\s+OUT\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s+[0-9A-F]{4}\s*$')
    out=[]
    with path.open() as f:
        for line in f:
            m=pattern.match(line)
            if m:
                frame,port,value=int(m[1]),int(m[2],16)&255,int(m[3],16)
                if start <= frame < end and port in (0x44,0x45,0x46,0x47):
                    out.append([frame,port,value])
    return out


def timed_marks(path, first):
    marks=[]
    for line in path.read_text().splitlines():
        m=re.fullmatch(r'\s*\d+\s+(\d+)\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s*',line)
        if m and int(m[1]) >= first and int(m[2],16) in (0xe017,0xe018):
            marks.append([int(m[1]),int(m[2],16),int(m[3],16)])
    return marks


def capture(rom,name,work,official=False):
    config, arm = name.split('/', 1) if ROUND == 'addendum2' else (None, name)
    cmds,op=plan(arm)
    args=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom),'--screen-signature-only','--out',str(work/'signatures.tsv')]
    if config:
        mode, board = CONFIGS[config]
        args += ['--basic-mode',mode,'--sound-board',board]
    if ROUND in ('addendum1','addendum2'):
        t9.ROUND = 'addendum2'
        args += t9.disks(work,official)
    at=700 if official else 100; first=at; frames={}; snapshots=[]; start=end=None
    for kind,value in cmds:
        if kind in ('type','operation'):
            if kind=='operation': start=at
            args += ['--type-at',str(at),'--type',value+'\n']
            at += (len(value)+1)*8 + (3600 if kind=='operation' else 240)
        else:
            for delay in ((60,160) if value=='operation' else (60,)):
                sid=value+('a' if delay==60 else 'b'); frames[sid]=at+delay
                args += ['--screen-signature-at',f'{sid}:{at+delay}']; snapshots.append(sid)
            at += 260
            if value=='operation': end=at
    log=work/'ram.log'; report=work/'signatures.tsv'; io=work/'io.log'
    args += ['--io-log',str(io),'--mem-write-log',str(log),'--mem-write-range','E000-E048','--mem-write-from-frame','0','--frames',str(at+600)]
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode: raise ValueError('実行/打鍵')
        sigs=base.parse_signatures(report)
        if set(sigs)!=set(snapshots) or sigs['operationa']!=sigs['operationb']: raise ValueError('画面安定')
        if 5 not in sigs['beforea'] or any(i in sigs['beforea'] for i in range(5)): raise ValueError('開始位置')
        expected=common.signature(6,op)
        if sigs['operationa'].get(6)!=(expected['char_count'],expected['sha256']): raise ValueError('打鍵反映')
        memory=base.parse_memory(log,first); writes=memory['writes']
        if [v for a,v in writes if a==0xe002]!=[20]: raise ValueError('段階')
        t10.validate_io(io)
        return {'config': list(CONFIGS[config]) if config else None, 'screen':{k:v for k,v in sigs.items() if not k.endswith('b')},'writes':writes,
                'boot_writes':memory['boot_writes'],'operation_start':start,'operation_end':end,
                'marks':timed_marks(log,first),'sound_out':sound_outputs(io,start,end)}
    finally:
        for path in (log,report,io): path.unlink(missing_ok=True)


def measure(rom,work,official=False):
    work.mkdir(parents=True,exist_ok=True)
    records={n:{'runs':[None,None],'gate':False} for n in NAMES}
    def one(n,i):
        d=work/n/str(i); d.mkdir(parents=True,exist_ok=True); return capture(rom,n,d,official)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tasks={pool.submit(one,n,i):(n,i) for n in NAMES for i in range(2)}
        for task in concurrent.futures.as_completed(tasks):
            n,i=tasks[task]
            try: records[n]['runs'][i]=task.result()
            except (ValueError,OSError) as exc: print(f'{n}: 関門失敗 ({exc})',flush=True)
            print(f'{n}: {i+1}走終了',flush=True)
    for n in NAMES:
        records[n]['gate']=base.stable_pair(records[n]['runs'])
        print(f'{n}: '+('通過' if records[n]['gate'] else '失敗'),flush=True)
    for prefix in ([c+'/' for c in CONFIGS] if ROUND == 'addendum2' else ['']):
        identify_records(records, prefix)
    return {'version':1,'round':ROUND,'records':records}


def identify_records(records, prefix):
    names=[n for n in NAMES if n.startswith(prefix)]
    if all(records[prefix+'ref-'+x]['gate'] for x in REFS):
        refs={x:base.response(records[prefix+'ref-'+x]['runs'][0]['screen']['operationa']) for x in REFS}; prompts={}
        for x in REFS:
            rows=records[prefix+'ref-'+x]['runs'][0]['screen']['operationa']; lines=sorted((int(k),v) for k,v in rows.items() if 7<=int(k)<19)
            if not lines: raise ValueError('参照プロンプト')
            row,value=lines[-1]
            if row in prompts and prompts[row]!=value: raise ValueError('参照プロンプト不一致')
            prompts[row]=value
        start=records[prefix+'ref-none']['runs'][0]['screen']['beforea'].get(5)
        for n in names:
            if not n[len(prefix):].startswith('ref-') and records[n]['gate']:
                run=records[n]['runs'][0]
                if run['screen']['beforea'].get(5)!=start: records[n]['gate']=False; continue
                try: response=base.identify(base.response(run['screen']['operationa'],prompts),refs)
                except ValueError: response='入力中またはプロンプト欠測'
                records[n]['result']={'response':response,'marks':run['marks']}
    else:
        for n in names: records[n]['gate']=False


def valid(d):
    return d.get('version')==1 and d.get('round')==ROUND and set(d.get('records',{}))==set(NAMES) and all(r['gate'] and base.stable_pair(r['runs']) and (ROUND != 'addendum2' or all(run.get('config') == list(CONFIGS[n.split('/')[0]]) for run in r['runs'])) for n,r in d['records'].items())

def check(a,b): return valid(a) and valid(b) and a==b


def selftest():
    work=WORK/('selftest' if ROUND == 'first' else 'selftest-'+ROUND); work.mkdir(parents=True,exist_ok=True); rom=work/'rom'
    p=subprocess.run([sys.executable,'-B',str(ROOT/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise ValueError('自作ROMビルド')
    if ROUND in ('addendum1','addendum2'):
        ref=work/'synthetic-ref'; ref.mkdir(exist_ok=True)
        (ref/'synthetic.d88').write_bytes(b'synthetic disk')
        config=work/'synthetic-config.tsv'; config.write_text('reference_disk\tsynthetic.d88\n')
        diskwork=work/'disk-test'; diskwork.mkdir(exist_ok=True)
        t9.ROUND='addendum2'
        with patch.dict(os.environ,{'PC88_REF_DISK_DIR':str(ref),'M6FF_FROZEN_CONFIG':str(config)}):
            t9.disks(diskwork,True)
        assert (diskwork/'a.d88').read_bytes()==b'synthetic disk'
        assert (diskwork/'b.d88').is_file()
    if ROUND == 'addendum2':
        for label, (mode, board) in CONFIGS.items():
            probe=work/('config-probe-'+label); probe.mkdir(exist_ok=True)
            def verify_args(args, **kwargs):
                assert args[args.index('--basic-mode')+1] == mode
                assert args[args.index('--sound-board')+1] == board
                raise ValueError('probe complete')
            with patch.object(subprocess, 'run', side_effect=verify_args):
                try: capture(rom,label+'/ref-none',probe)
                except ValueError as exc: assert str(exc) == 'probe complete'
                else: raise AssertionError('構成指定未検査')
    data=measure(rom,work); base.save(work/'actual.json',data)
    if not valid(data): return 1
    data=json.loads((work/'actual.json').read_text()); assert check(data,data)
    refname='A/ref-none' if ROUND == 'addendum2' else 'ref-none'
    if ROUND == 'addendum2':
        wrong=copy.deepcopy(data)
        wrong['records']['A/ref-none']['runs'][0]['config'] = list(CONFIGS['B'])
        assert not valid(wrong)
    broken=copy.deepcopy(data)
    for r in broken['records'][refname]['runs']: r['screen']['operationa']['6'][0]^=1
    assert valid(broken) and not check(data,broken)
    a,b=[(7,[1,'a'])],[(7,[1,'b'])]
    assert base.identify(a,{'ERR8':a,'ERR2':b})=='ERR8' and base.identify(a,{'ERR8':b,'ERR2':b})=='候補外' and base.identify(a,{'ERR8':a,'ERR2':a})=='参照衝突'
    mismatch=copy.deepcopy(data); mismatch['records'][refname]['runs'][1]['screen']['operationa']['6'][0]^=1
    assert not valid(mismatch)
    common.unexpected_selftest(lambda p:base.parse_memory(p,10),work/'synthetic.log',[(0xe001,163)])
    p=work/'sweep.log'; prefix=[(a,0) for a in range(0xe000,0xe049)]+[(0xe000,151),(0xe001,163)]
    for sweep in ([(a,0) for a in range(0xe000,0xe049)],[(a,(a*7)&255) for a in reversed(range(0xe000,0xe049))]):
        for frame in (9,10):
            rows=[(frame,a,v) for a,v in sweep]+[(10,a,v) for a,v in prefix]
            p.write_text('range : E000-E048\n# 取りこぼし: 0件 / 総イベント数: %d件\n'%len(rows)+''.join('%d %d 0000 %04X %02X\n'%(i,f,a,v) for i,(f,a,v) in enumerate(rows,1)))
            if frame==9: assert base.parse_memory(p,10)['boot_writes']==len(sweep)
            else:
                try: base.parse_memory(p,10)
                except ValueError: pass
                else: raise AssertionError('打鍵後掃引')
    p.unlink()
    p=work/'synthetic-io.log'
    p.write_text(' 1 0 9 main OUT 0044 01 0000\n 2 0 10 main OUT 0144 07 0000\n 3 0 10 main OUT 0045 38 0000\n 4 0 11 main IN 0045 99 0000\n 5 0 12 main OUT 0046 AA 0000\n 6 0 13 main OUT 0047 BB 0000\n 7 0 14 main OUT 0044 02 0000\n')
    assert sound_outputs(p,10,14)==[[10,68,7],[10,69,56],[12,70,170],[13,71,187]]
    p.unlink()
    p=work/'synthetic-marks.log'
    p.write_text('1 9 0000 E017 01\n2 10 0000 E017 01\n3 11 0000 E018 05\n')
    assert timed_marks(p,10)==[[10,0xe017,1],[11,0xe018,5]]
    p.unlink()
    print(f'陰性対照通過、全腕関門: {len(data["records"])}/{len(data["records"])}'); return 0


def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='command',required=True)
    st=sub.add_parser('selftest'); st.add_argument('--round',choices=['first','addendum1','addendum2'],default='first')
    m=sub.add_parser('measure'); m.add_argument('--rom-dir',type=Path,required=True); m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True); m.add_argument('--official',action='store_true'); m.add_argument('--round',choices=['first','addendum1','addendum2'],default='first')
    e=sub.add_parser('expected'); e.add_argument('--measured',type=Path,required=True); e.add_argument('--out',type=Path,required=True); e.add_argument('--round',choices=['first','addendum1','addendum2'],default='first')
    c=sub.add_parser('check'); c.add_argument('--measured',type=Path,required=True); c.add_argument('--expected',type=Path,required=True); c.add_argument('--round',choices=['first','addendum1','addendum2'],default='first')
    args=ap.parse_args()
    global ROUND, NAMES
    ROUND=args.round
    if ROUND == 'addendum2':
        NAMES=[c+'/'+n for c in CONFIGS for n in (['ref-'+x for x in REFS]+['sound-mixer','sound-tone','play-c','play-scale','play-o5l8c'])]
        PLAY['o5l8c']='play "o5l8c"'
    if args.command=='measure' and args.official and ROUND in ('addendum1','addendum2') and not os.environ.get('PC88_REF_DISK_DIR'):
        print('PC88_REF_DISK_DIR_missing'); return 1
    if args.command=='selftest': return selftest()
    if args.command=='measure':
        data=measure(args.rom_dir,args.work_dir,args.official); base.save(args.out,data); return int(not valid(data))
    data=json.loads(args.measured.read_text())
    if args.command=='expected':
        if not valid(data) or data['round']!=args.round: return 1
        base.save(args.out,data); return 0
    ok=data.get('round')==args.round and check(data,json.loads(args.expected.read_text())); print('照合: '+('一致' if ok else '不一致')); return int(not ok)

if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError,KeyError) as exc:
        print('NG 器具:',type(exc).__name__,'（本文非出力）'); raise SystemExit(1)
