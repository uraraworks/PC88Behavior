#!/usr/bin/env python3
"""l4-t3追補1: 限定RAM印で囲んだパレットOUTのみを測定する。"""
import argparse, copy, csv, json, os, re, subprocess, sys, traceback
import io
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
from pathlib import Path
sys.dont_write_bytecode = True
import l4_portio_measure as base
ROOT = base.ROOT
CASES = [('v0','84','0'),('v1','84','1'),('v255','84','255'),
         ('v1-49','84','1.49'),('v1-5','84','1.5'),('v254-5','84','254.5'),
         ('v255-49','84','255.49'),('v255-5','84','255.5'),('v256','84','256'),
         ('p-plus256','340','1'),('p-plus65280','65364','1'),
         ('p-near65535','65371','1'),('p-negative','-172','1'),
         ('p84-49','84.49','1'),('p84-5','84.5','1'),('p-negative-half','-171.5','1')]

def arms():
    return base.arms()[:2] + [dict(id=i,commands=[f'out {p},{v}']) for i,p,v in CASES]

def program(a):
    lines = base.program(a)
    lines.remove('11 '+a['commands'][0])
    lines.remove('12 poke &he780+18,77')
    lines.remove('9010 if s=1 then resume 12')
    lines += ['11 for j=1 to 200:next j','12 '+a['commands'][0],
              '13 for j=1 to 200:next j','14 poke &he780+18,77',
              '9010 if s=1 then resume 14']
    # new/runは数値ソートの対象にしない。
    return ['new'] + sorted([x for x in lines if x not in ('new','run')],key=lambda x:int(x.split()[0])) + ['run']

def schedule(a,official):
    at=1200 if official else 120
    typed=[(300,'\n')] if official else []
    for line in program(a):
        assert len(line)<80
        typed.append((at,line+'\n'))
        at+=(len(line)+1)*(12 if official else 8)+(360 if official else 120)
    return typed,at+12000

def extract(raw,mem,start,finish,a):
    ram=base.parse_log(mem,start,finish,a)
    events=[]
    for row in mem.splitlines():
        m=re.fullmatch(r'\s*(\d+)\s+(\d+)\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})',row)
        if m and int(m[2])>=start: events.append((int(m[2]),int(m[3],16)-base.BASE,int(m[4],16)))
    lo=[t for t,i,v in events if (i,v)==(1,1)]
    hi=[t for t,i,v in events if (i,v)==(18,77)]
    if len(lo)!=1 or len(hi)!=1 or lo[0]>=hi[0]: raise ValueError('区間印')
    cpu=None; seq=0; last=-1; completed=[]; outputs=[]
    for row in raw.splitlines():
        if row in ('# main','# sub'):
            if cpu is not None: raise ValueError('IO節')
            cpu=row[2:]; seq=0; last=-1
        elif row.startswith('# 取りこぼし:'):
            m=re.fullmatch(r'# 取りこぼし: 0件 / 総イベント数: (\d+)件',row)
            if not m or cpu is None or seq!=int(m[1]): raise ValueError('IO件数')
            completed.append(cpu); cpu=None
        elif re.match(r'^\s*\d+\s',row):
            m=re.fullmatch(r'\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(OUT|IN)\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s+[0-9A-F]{4}',row)
            if not m or cpu!=m[4]: raise ValueError('IO形')
            k,t,port=int(m[1]),int(m[3]),int(m[6],16)
            if k!=seq+1 or t<last or not start<=t<finish: raise ValueError('IO連番時点')
            seq=k; last=t
            if cpu=='main' and m[5]=='OUT' and 0x54<=(port&255)<=0x5b:
                if not lo[0]<t<hi[0]: raise ValueError('区間外または境界OUT')
                value=int(m[7],16)
                if value not in (0,1,2,254,255): raise ValueError('未知OUT値')
                outputs.append([port,value])
    if completed!=['main','sub'] or cpu is not None: raise ValueError('IO節完了')
    return dict(ram=ram,outputs=outputs)

def valid(o,a):
    return (type(o) is dict and set(o)=={'ram','outputs'} and base.valid(o['ram'],a)
            and type(o['outputs']) is list and len(o['outputs'])<=1
            and all(type(x) is list and len(x)==2 and type(x[0]) is int and type(x[1]) is int
                    and 0x54<=x[0]<=0x5b and x[1] in (0,1,2,254,255) for x in o['outputs']))

def capture(rom,official,a,work):
    typed,finish=schedule(a,official); start=typed[-1][0]
    mp=work/'memory.txt'; ip=work/'io.txt'
    argv=[str(base.kw.FRONT),'--core',str(base.kw.find_core()),'--rom-dir',str(rom)]
    for t,c in typed: argv+=['--type-at',str(t),'--type',c]
    argv+=['--mem-write-log',str(mp),'--mem-write-range',base.RANGE,
           '--mem-write-from-frame',str(start),'--io-log',str(ip),
           '--io-log-from-frame',str(start),'--frames',str(finish)]
    try:
        p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode or b'untypable' in p.stderr.lower(): raise ValueError('実行打鍵')
        o=extract(ip.read_text(),mp.read_text(),start,finish,a)
        if not valid(o,a): raise ValueError('抽出形')
        return o
    finally:
        mp.unlink(missing_ok=True); ip.unlink(missing_ok=True)

def calibrated(rs):
    return all(r['gate'] and all(o==dict(ram=base.synth(r['arm']),outputs=[]) for o in r['obs']) for r in rs[:2]) and [r['arm']['id'] for r in rs[:2]]==['cal-poke','cal-error']

def emit(path,rs):
    cal=calibrated(rs)
    base.write_tsv(path,['arm','repeat','plan','observation','gate'],
                   [[r['arm']['id'],j+1,json.dumps(program(r['arm'])),json.dumps(o),
                     'pass' if r['gate'] and cal else 'gate_failed'] for r in rs for j,o in enumerate(r['obs'])])
    return cal and all(r['gate'] for r in rs)

def read_passed(path):
    with path.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
    aa=arms(); rs=[]
    if len(rows)!=2*len(aa): raise ValueError('全腕')
    for j,a in enumerate(aa):
        rr=rows[j*2:j*2+2]
        if [r['repeat'] for r in rr]!=['1','2'] or any(r['arm']!=a['id'] or r['gate']!='pass' or json.loads(r['plan'])!=program(a) for r in rr): raise ValueError('固定予定反復関門')
        oo=[json.loads(r['observation']) for r in rr]
        if not all(valid(o,a) for o in oo) or oo[0]!=oo[1]: raise ValueError('観測反復')
        rs.append(dict(arm=a,obs=oo,gate=True))
    if not calibrated(rs): raise ValueError('較正')
    return rs

def expected(source,out):
    rs=read_passed(source)
    base.write_tsv(out,['arm','observation'],[[r['arm']['id'],json.dumps(r['obs'][0])] for r in rs])

def check(exp,measured):
    rs=read_passed(measured)
    with exp.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
    if len(rows)!=len(rs): raise ValueError('期待全腕')
    bad=[]
    for row,r in zip(rows,rs):
        if row['arm']!=r['arm']['id'] or not valid(json.loads(row['observation']),r['arm']): raise ValueError('期待形')
        if json.loads(row['observation'])!=r['obs'][0]: bad.append(r['arm']['id'])
    print(f'一致{len(rs)-len(bad)}腕、不一致{len(bad)}腕')
    return bool(bad)

def synthetic():
    a=arms()[2]; ram=base.synth(a)
    mem=base.fake_log(ram)
    # stage1は122、復帰印は123。検出力検査用に後半を+10フレーム。
    mem=re.sub(r'^(\d+) (\d+) ',lambda m:f'{m[1]} {int(m[2])+(10 if int(m[1])>=24 else 0)} ',mem,flags=re.M)
    def fake_io(port='0054',value='01',frame=125):
        return f'# main\n1 1 {frame} main OUT {port} {value} 0000\n# 取りこぼし: 0件 / 総イベント数: 1件\n# sub\n# 取りこぼし: 0件 / 総イベント数: 0件\n'
    good=extract(fake_io(),mem,100,1000,a)
    assert good['outputs']==[[84,1]] and valid(good,a)
    assert extract(fake_io(port='0040',value='AB'),mem,100,1000,a)['outputs']==[]
    for raw in (fake_io(value='03'),fake_io(frame=122),fake_io(frame=133),fake_io().replace('取りこぼし: 0','取りこぼし: 1'),fake_io().replace('総イベント数: 1','総イベント数: 2'),fake_io().replace('1 1 125','2 1 125')):
        try: extract(raw,mem,100,1000,a)
        except ValueError: pass
        else: raise AssertionError('陰性IO受理')
    bad=copy.deepcopy(good); bad['body']='synthetic-secret'; assert not valid(bad,a)
    rs=[dict(arm=x,obs=[dict(ram=base.synth(x),outputs=[]) for _ in (1,2)],gate=True) for x in arms()]
    folder=ROOT/'addendum1-synthetic'; folder.mkdir(parents=True,exist_ok=True)
    m=folder/'m.tsv'; e=folder/'e.tsv'
    assert emit(m,rs); expected(m,e); assert not check(e,m)
    for mode in ('plan','repeat','gate','difference','body'):
        changed=copy.deepcopy(rs)
        if mode=='gate': changed[2]['gate']=False
        elif mode=='difference': changed[2]['obs'][1]['outputs']=[[84,1]]; changed[2]['obs'][0]['outputs']=[]
        elif mode=='body': changed[2]['obs'][0]['body']='synthetic-secret'
        emit(m,changed)
        if mode=='plan': m.write_text(m.read_text().replace('new','wrong'))
        if mode=='repeat': m.write_text(m.read_text().replace('\t2\t','\t1\t'))
        try: read_passed(m)
        except ValueError: pass
        else: raise AssertionError('陰性TSV受理')
    def fake(argv,**kwargs):
        mp=Path(argv[argv.index('--mem-write-log')+1])
        ip=Path(argv[argv.index('--io-log')+1])
        mp.write_text(mem); ip.write_text(fake_io())
        return subprocess.CompletedProcess(argv,0,b'synthetic-secret',b'synthetic-secret')
    # 生ログを画面へ出さないことと、成功・失敗の両方で削除すること。
    sink=io.StringIO()
    with patch.object(base.kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=fake),patch(__name__+'.schedule',return_value=([(100,'run\n')],1000)),redirect_stdout(sink),redirect_stderr(sink):
        assert capture(Path('synthetic'),False,a,folder)==good
    assert not sink.getvalue() and not (folder/'memory.txt').exists() and not (folder/'io.txt').exists()
    with patch.object(base.kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'synthetic-secret',b'synthetic-secret')),redirect_stdout(sink),redirect_stderr(sink):
        try: capture(Path('synthetic'),False,a,folder)
        except ValueError: pass
        else: raise AssertionError('実行失敗受理')
    assert not sink.getvalue() and not (folder/'memory.txt').exists() and not (folder/'io.txt').exists()
    print('OK 合成: IO分離・境界・未知値・欠落・固定plan・反復差・本文キー拒否')

def measure(rom,official,work,out):
    synthetic(); rs=[]
    def run_arm(a):
        obs=[]
        for j in (1,2):
            dest=work/(a['id']+'-'+str(j)); dest.mkdir(parents=True,exist_ok=True)
            try: obs.append(capture(rom,official,a,dest))
            except Exception as exc:
                # 例外本文・ハーネス出力は一切表示しない。
                print(f'{a["id"]} 走{j}: {type(exc).__name__} 行{traceback.extract_tb(exc.__traceback__)[-1].lineno}')
                obs.append(dict(failure='capture-gate'))
        gate=all(valid(o,a) for o in obs) and obs[0]==obs[1]
        print(a['id']+': '+('pass' if gate else 'gate_failed'),flush=True)
        return dict(arm=a,obs=obs,gate=gate)
    with ThreadPoolExecutor(max_workers=3) as pool:
        rs=list(pool.map(run_arm,arms()))
    passed=emit(out,rs)
    print(f'全{len(rs)}腕、関門{sum(r["gate"] for r in rs)}、較正{calibrated(rs)}')
    return not passed

def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('synthetic')
    m=sub.add_parser('measure'); m.add_argument('--official',action='store_true'); m.add_argument('--rom-dir',type=Path); m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True)
    e=sub.add_parser('expected'); e.add_argument('--measured',type=Path,required=True); e.add_argument('--out',type=Path,required=True)
    c=sub.add_parser('check'); c.add_argument('--measured',type=Path,required=True); c.add_argument('--expected',type=Path,required=True)
    args=p.parse_args()
    for name in ('work_dir','out','measured','expected'):
        path=getattr(args,name,None)
        if path is not None and (not path.is_absolute() or not any(path.resolve().is_relative_to(root.resolve()) for root in (ROOT,base.T3B_IMPL_ROOT))): p.error('作業・測定・期待値はtmp/t3-workまたはtmp/t3b-impl-work内の絶対パス')
    if args.command=='synthetic': synthetic(); return 0
    if args.command=='expected': expected(args.measured,args.out); print('期待値18腕'); return 0
    if args.command=='check': return int(check(args.expected,args.measured))
    rom=os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir): p.error('公式はPC88_REF_ROM_DIR、自作は--rom-dir')
    args.work_dir.mkdir(parents=True,exist_ok=True)
    return int(measure(rom,args.official,args.work_dir,args.out))

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print(f'NG 器具: {type(exc).__name__} 行{traceback.extract_tb(exc.__traceback__)[-1].lineno}（本文非出力）')
        raise SystemExit(1)
