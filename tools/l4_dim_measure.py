#!/usr/bin/env python3
"""l4-s9y 配列の値印測定。公式本文・ROMバイトを出力しない。"""
import argparse
import copy
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))
import l4_getput_measure as gp
lm, kw, cm, wv = gp.lm, gp.kw, gp.cm, gp.wv
SENT = b's9yz;'
# LOCATE 0,0 の文字セルだけを監視し、PRINT の自作印を時刻にする。
TIME_CELL = 'F3C8'
START_PRINT = 'locate 0,0:print "{";'
END_PRINT = 'locate 0,0:print "}";:locate 0,2'


def step(stmts=(), value=None, error=None, prediction=None):
    if isinstance(stmts, str): stmts = [stmts]
    return dict(stmts=list(stmts), value=value, error=error, prediction=prediction)


def arm(aid, steps, top=58877, speed=False, lifecycle=None):
    return dict(id=aid, steps=steps, top=top, speed=speed, lifecycle=lifecycle)


def arms():
    out = [arm('cal-num', [step(value=str(v), error=0, prediction=v)
                           for v in (0,32767,-32768,-1,23779)]),
           arm('cal-error', [step('error 9',error=9), step('error 10',error=10),step('error 7',error=7)])]
    for tag,t,size in [('int','%',2),('single','!',4),('double','#',8),('string','$',3)]:
        for u in (0,1,9,10,99,999,2999):
            out.append(arm(f'mem-{tag}-{u}', [step(['b=fre(0)',f'dim a{t}({u})','c=fre(0)','q=b-c']),
                         step([f'erase a{t}','q=fre(0)-c'])]))
        zero='len(a$(0))' if t=='$' else f'a{t}(0)'
        out.append(arm(f'zero-{tag}',[step(f'dim a{t}(2)',error=0),step(value=zero,error=0,prediction=0)]))
    for d, shape in [(1,'999'),(2,'9,99'),(3,'9,9,9')]:
        out.append(arm(f'mem-shape-{d}',[step(['b=fre(0)',f'dim a%({shape})','q=b-fre(0)']),
                                      step(['erase a%','q=fre(0)-b'])]))
    # 第14.16版4.10.10: 打鍵到達を確認できなかった9腕は期待値から保留。
    # 通常の測定/checkも、採用済み143腕に揃える。
    for d in (1,2,3,4,8,16,24,32):
        shape=','.join(['0']*d)
        out.append(arm(f'dims-{d}',[step(f'dim a%({shape})',error=0 if d<=255 else None),
                     step(value=f'a%({shape})')]))
    for u in (-1,0,1,10,255,256,32765,32766,32767,32768,65535):
        out.append(arm(f'upper-{str(u).replace("-","m")}',[step(f'dim a%({u})')]))
    for top in (49151,58877):
        for u in (4095,4999,5999,6999,9999,10999,11999,12000,16383,32766):
            out.append(arm(f'capacity-{top}-{u}',[step(['b=fre(0)',f'dim a%({u})','q=b-fre(0)'])],top))
        for shape in ('99,99','9,9,99','255,255'):
            out.append(arm(f'product-{top}-{shape.replace(",","x")}',[step(f'dim a%({shape})')],top))
    for d in (1,2,3,4):
        idx=','.join(['10']*d)
        beyond=','.join(['10']*(d-1)+['11'])
        out.append(arm(f'auto-{d}',[step(f'a%({idx})=7',error=0 if d<=3 else None),
                     step(value=f'a%({idx})',prediction=7 if d<=3 else None),
                     step(f'a%({beyond})=8',error=9 if d<=3 else None),
                     step('dim a%(1)',error=10 if d<=3 else None)]))
    for aid,stmt,err in [('low','a%(-1)=1',None),('high','a%(3)=1',9),
                         ('few','a%(1)=1',9),('many','a%(1,1,1)=1',9),
                         ('duplicate','dim a%(2,2)',10),('auto-redim','dim b%(2)',10)]:
        out.append(arm('error-'+aid,[step('dim a%(2,2)' if aid in ('few','many','duplicate') else 'dim a%(2)',error=0),
                     step('b%(0)=1',error=0),step(stmt,error=err)]))
    for val in ('-1','-.51','-.5','-.49','0','.49','.5','1.49','1.5','2.5','3.49','3.5','32767','32768','"x"'):
        aid=val.replace('-','m').replace('.','p').replace('"','')
        out.append(arm('round-'+aid,[step('dim a%(3)',error=0),
            step(['a%(0)=10','a%(1)=11','a%(2)=12','a%(3)=13'],error=0),
            step(value=f'cint({val})'),step(value=f'a%({val})')]))
    for val in ('.49','.5','1.5','2.5','-.49','-.5'):
        out.append(arm('dim-round-'+val.replace('-','m').replace('.','p'),
            [step(f'dim a%({val})'),step('a%(0)=1'),step('a%(1)=2'),step('a%(2)=3'),step('a%(3)=4')]))
    for aid,indices,target in [('half','1.5,2.5','2,3'),('near','1.49,2.49','1,2'),('negative','-.5,1','0,1')]:
        out.append(arm('round-multi-'+aid,[step('dim a%(3,3)',error=0),
            step(f'a%({target})=17',error=0),step(value=f'a%({indices})',
                 error=0 if aid!='negative' else None,prediction=17 if aid!='negative' else None)]))
    for aid,expr,err in [('left','a%(1/0,cint("x"))',11),('right','a%(cint("x"),1/0)',13),
                         ('bounds-left','a%(2,1/0)',11),('bounds-right','a%(1/0,2)',11),
                         ('both-bounds','a%(2,2)',9)]:
        out.append(arm('eval-'+aid,[step('dim a%(1,1)',error=0),step(value=expr,error=err)]))
    out += [arm('erase-redim',[step('dim a%(2,3)',error=0),step('a%(1,2)=7',error=0),
                step('erase a%',error=0),step('dim a%(4,1)',error=0),step(value='a%(1,1)',error=0,prediction=0)]),
            arm('erase-auto',[step('dim a%(2)',error=0),step('erase a%',error=0),
                step(value='a%(10)',error=0,prediction=0),step(value='a%(11)',error=9)]),
            arm('coexist',[step(['a%=9','dim a%(2),a!(2),a#(2),a$(2),b%(2)'],error=0),
                step(['a%(1)=3','a!(1)=4','a#(1)=5','a$(1)="xy"','b%(1)=8'],error=0),
                step(value='a%',error=0,prediction=9),step(value='a%(1)',error=0,prediction=3),
                step(value='a!(1)',error=0,prediction=4),step(value='a#(1)',error=0,prediction=5),
                step(value='len(a$(1))',error=0,prediction=2),step('erase a%',error=0),
                step(value='a%',error=0,prediction=9),step(value='b%(1)',error=0,prediction=8),
                step(value='a!(1)',error=0,prediction=4)]),
            arm('erase-multiple',[step('dim a%(2),b%(3)',error=0),step('erase a%,b%',error=0),
                step('dim a%(1),b%(1)',error=0)]),
            arm('erase-missing',[step('erase a%',error=5)])]
    for op in ('none','clear','run','insert','delete','replace','same','missing'):
        reset=op in ('clear','run','insert','delete','replace','same')
        out.append(arm('reset-'+op,[step(value='a%(1)',error=0,prediction=0 if reset else 7),
                     step('dim a%(2)',error=0 if reset else 10)],lifecycle=op))
    for aid,dims,offset in [('one','dim a%(7)',0),('offset','dim a%(10)',3),('two','dim a%(3,1)',0)]:
        sub=lambda i: f'{i},0' if aid=='two' else str(i+offset)
        ss=[step(dims,error=0),step(gp.drawing(8,1),error=0),
            step([f'get(10,10)-(17,10),a%'+(f'({offset})' if offset else ''),'ge=e'],error=0)]
        for i,v in enumerate((8,1,13141,15)):
            ss.append(step(f'if ge=0 then q=a%({sub(i)})',prediction=v))
        ss += [step(f'if ge=0 then put(40,30),a%'+(f'({offset})' if offset else '')+',pset',error=0),
               step(value='point(47,30)',prediction=7)]
        out.append(arm('get-values-'+aid,ss))
    out.append(arm('get-halfword',[step('dim a%(7)',error=0),
        step(['a%(3)=23130']+gp.drawing(8,1),error=0),
        step(['get(10,10)-(17,10),a%','ge=e'],error=0),
        step('if ge=0 then q=a%(3)',prediction=23055)]))
    for tag,t in [('int','%'),('single','!'),('double','#'),('string','$')]:
        out.append(arm('speed-'+tag,[step(f'dim a{t}(9999)'),
            step([START_PRINT,'for i=0 to 9999',
                  f'a{t}(i)='+('"x"' if t=='$' else 'i'),'next i',END_PRINT,'q=i'])],speed=True))
    out.append(arm('speed-nop',[step([START_PRINT,'for i=0 to 9999','next i',END_PRINT,'q=i'],error=0,prediction=10000)],speed=True))
    assert len({a['id'] for a in out})==len(out)
    return out


def program_lines(a):
    lines={5:f'clear ,{a["top"]}',6:'on error goto 9000',7:'cls',
           8:'e=0:n=0:q=0:b=0:c=0:i=0:ge=0',9:'locate 0,0'}
    if a['speed']:
        lines[9]='locate 0,1'
    if a['id'].startswith('get-'):
        lines[9]='screen 0,0:cls 3:locate 0,0'
    number=20
    if a['lifecycle']:
        lines={10:'dim a%(1)',20:'a%(1)=7',30:'end',
               1000:'cls',1001:'on error goto 9000',1002:'e=0:n=0:q=0:b=0:c=0:i=0:ge=0'}
        number=1020
    for k,s in enumerate(a['steps']):
        lines[number]='e=0:q=0'; number+=10
        for stmt in s['stmts']:
            lines[number]=stmt; number+=10
        if s['value'] is not None:
            lines[number]='q='+s['value']; number+=10
        lines[number]=f'print "s9yp{k}:";e;",";q;";";'; number+=10
    lines[number]='print "s9yn:";n;";s9yz;";'; number+=10
    lines[number]=f'goto {number}'
    lines[9000]='e=err:n=n+1:resume next'
    assert number<8000
    for k,s in lines.items():
        assert s.isascii() and s==s.lower() and '@' not in s
        # 高次元腕だけは通常の80字を超える打鍵を明示的に試す。
        assert len(f'{k} {s}')<80 or a['id'].startswith('dims-')
    return lines


def plan(a):
    p=['new']+[f'{n} {s}' for n,s in sorted(program_lines(a).items())]+['cls',('window',),'run']
    if a['lifecycle']:
        p += {'none':[], 'clear':['clear'], 'run':[], 'insert':['15 rem 1'],
              'delete':['30'],'replace':['30 rem 2'],'same':['30 end'],'missing':['50']}[a['lifecycle']]
        p += ['run 1000' if a['lifecycle']=='run' else 'goto 1000']
    return p


def parse_results(raw):
    if len(raw)!=3000: raise ValueError('画面写し長さ')
    joined=b''.join(raw[r*120:r*120+80] for r in range(25))
    probes={}
    pat=rb's9yp(\d+)\s*:([^;]*);'
    matches=list(re.finditer(pat,joined))
    for m in matches:
        key=str(int(m[1])); parts=m[2].split(b',')
        if key in probes: raise ValueError('重複プローブ')
        if len(parts)!=2 or any(not re.fullmatch(rb'\s*-?\d+\s*',v) for v in parts):
            raise ValueError('整数以外のプローブ')
        probes[key]=[int(v) for v in parts]
    if len(re.findall(rb's9yp\d+\s*:',joined))!=len(matches): raise ValueError('未完了プローブ')
    counts=list(re.finditer(rb's9yn\s*:([^;]*);',joined))
    if len(counts)!=1 or not re.fullmatch(rb'\s*\d+\s*',counts[0][1]): raise ValueError('誤り件数プローブ')
    return dict(probes=probes, errors=int(counts[0][1]), sent=joined.count(SENT))


def marks_summary(text):
    events=[]
    for line in text.splitlines():
        m=re.fullmatch(rf'\s*\d+\s+(\d+)\s+[0-9A-F]+\s+{TIME_CELL}\s+([0-9A-F]+)\s*',line)
        if m and int(m[2],16) in (123,125): events.append((int(m[1]),int(m[2],16)))
    start=[f for f,v in events if v==123]; end=[f for f,v in events if v==125]
    return dict(n1=len(start),n2=len(end),
                frames=end[0]-start[0] if len(start)==len(end)==1 else None,
                ordered=[v for f,v in events]==[123,125])


def valid(o,a):
    if not isinstance(o,dict) or o.get('arm')!=a['id'] or o.get('sent')!=1: return False
    if set(o.get('probes',{}))!={str(k) for k in range(len(a['steps']))}: return False
    if type(o.get('errors')) is not int or o['errors']<0: return False
    for v in o['probes'].values():
        if not isinstance(v,list) or len(v)!=2 or any(type(x) is not int for x in v) or not 0<=v[0]<=255: return False
    if a['speed']:
        m=o.get('marks',{})
        if not (m.get('n1')==m.get('n2')==1 and m.get('ordered') is True and type(m.get('frames')) is int and m['frames']>=0): return False
    elif 'marks' in o: return False
    return True


def run_arm(rom,official,a,work):
    args=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom)]
    at=700 if official else 100
    if official: args+=['--type-at','300','--type','\n']
    window=at
    for s in plan(a):
        if isinstance(s,tuple): window=at; continue
        args+=['--type-at',str(at),'--type',s+'\n']
        at+=(len(s)+1)*8+240+(wv.RUN_WAIT+(60000 if a['speed'] else 0) if s in ('run','run 1000','goto 1000') else 0)
    raw,marks=work/'text.bin',work/'marks.txt'
    cap=at+200
    args+=['--vram-dump',str(raw),'--vram-dump-at',str(cap),'--frames',str(cap+100)]
    if a['speed']: args+=['--mem-write-log',str(marks),'--mem-write-range',f'{TIME_CELL}-{TIME_CELL}','--mem-write-from-frame',str(window)]
    try:
        proc=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower(): raise RuntimeError('実行/打鍵失敗')
        o=dict(arm=a['id'],**parse_results(raw.read_bytes()))
        if a['speed']: o['marks']=marks_summary(marks.read_text())
        return o
    finally:
        for p in (raw,marks):
            p.unlink(missing_ok=True); Path(str(p)+'.info.txt').unlink(missing_ok=True)


def measure(rom,official,selected,work):
    work.mkdir(parents=True,exist_ok=True); records=[]
    with tempfile.TemporaryDirectory(prefix='measure-',dir=work) as td:
        for a in selected:
            obs=[]
            for _ in range(2):
                try: obs.append(run_arm(rom,official,a,Path(td)))
                except Exception: obs.append({})
            gate=all(valid(o,a) for o in obs) and obs[0]==obs[1]
            records.append(dict(arm=a,obs=obs,gate=gate))
            print(f'進捗 {a["id"]}: '+('pass' if gate else 'gate_failed'),flush=True)
    return records


def calibrated(records):
    by={r['arm']['id']:r for r in records}
    for aid in ('cal-num','cal-error'):
        r=by.get(aid)
        if not r or not r['gate']: return False
        for o in r['obs']:
            if not valid(o,r['arm']): return False
            for k,s in enumerate(r['arm']['steps']):
                e,q=o['probes'][str(k)]
                if e!=s['error'] or (s['prediction'] is not None and q!=s['prediction']): return False
            if o['errors']!=(3 if aid=='cal-error' else 0): return False
    return True


def judge(o,a):
    result={}
    for k,s in enumerate(a['steps']):
        got=o.get('probes',{}).get(str(k))
        for j,field in enumerate(('error','prediction')):
            if s[field] is not None: result[f'{k}-{field}']='agree' if got and got[j]==s[field] else 'differ'
    return result


def emit(path,records,strict=True):
    cal=calibrated(records) if strict else True
    lm.write_tsv(path,['arm','repeat','plan','observation','gate','prediction_judgement'],
        [(r['arm']['id'],i+1,json.dumps(plan(r['arm'])),json.dumps(o),
          'pass' if cal and r['gate'] else 'gate_failed',json.dumps(judge(o,r['arm'])))
         for r in records for i,o in enumerate(r['obs'])])
    return cal and all(r['gate'] for r in records)


def comparable(o):
    return {k:v for k,v in o.items() if k!='marks'}


def read_passed(paths):
    known={a['id']:a for a in arms()}; result={}
    for path in paths:
        for aid,rs in lm.read_runs(path).items():
            if aid not in known or len(rs)!=2 or {r['repeat'] for r in rs}!={'1','2'} or any(r['gate']!='pass' for r in rs):
                raise ValueError('2走の関門')
            obs=[json.loads(r['observation']) for r in rs]
            if not all(valid(o,known[aid]) for o in obs) or obs[0]!=obs[1]: raise ValueError('2走不一致/数値形')
            value=comparable(obs[0])
            if aid in result: raise ValueError('重複腕')
            result[aid]=value
    records=[dict(arm=known[k],obs=[v,v],gate=True) for k,v in result.items()]
    if not calibrated(records): raise ValueError('較正値の関門')
    return result


def expected(out,paths):
    values=read_passed(paths)
    if set(values)!={a['id'] for a in arms()}: raise ValueError('全腕が必要')
    lm.write_tsv(out,['arm','observation'],[(k,json.dumps(v)) for k,v in sorted(values.items())])
    return len(values)


def check(exp,measured,only=()):
    with exp.open(newline='') as f:
        rows=list(csv.DictReader(f,delimiter='\t'))
    want={r['arm']:json.loads(r['observation']) for r in rows}
    if len(want)!=len(rows): raise ValueError('重複期待値')
    if set(want)!={a['id'] for a in arms()}: raise ValueError('全腕の期待値が必要')
    runs=lm.read_runs(measured); ok=[]; bad={}
    known={a['id']:a for a in arms()}
    for aid,w in want.items():
        if only and not aid.startswith(tuple(only)): continue
        if aid not in known or not valid(w,dict(known[aid],speed=False)): raise ValueError('期待値の形')
        rs=runs.get(aid,[])
        if len(rs)!=2 or {r['repeat'] for r in rs}!={'1','2'} or any(r['gate']!='pass' for r in rs): bad[aid]=['測定欠落/関門落ち']; continue
        obs=[json.loads(r['observation']) for r in rs]
        if not all(valid(o,known[aid]) for o in obs) or obs[0]!=obs[1]: bad[aid]=['2走不一致/数値形']; continue
        if any(comparable(o)!=w for o in obs): bad[aid]=['値/誤り/件数']; continue
        ok.append(aid)
    if not ok and not bad: raise ValueError('照合対象なし')
    return ok,bad


def describe():
    return '\n'.join(f'- `{a["id"]}`（CLEAR上限{a["top"]}）: '+
        ' / '.join(';'.join(s['stmts'])+(' → '+s['value'] if s['value'] else '')+
                   f' [誤り={s["error"]} 値={s["prediction"]}]' for s in a['steps']) for a in arms())


def selftest(work):
    work.mkdir(parents=True,exist_ok=True); known={a['id']:a for a in arms()}
    for a in arms(): program_lines(a)
    def synth(a):
        return dict(arm=a['id'],probes={str(k):[s['error'] or 0,s['prediction'] or 0] for k,s in enumerate(a['steps'])},
                    errors=3 if a['id']=='cal-error' else 0,sent=1,
                    **({'marks':dict(n1=1,n2=1,frames=10,ordered=True)} if a['speed'] else {}))
    def record(a,o): return dict(arm=a,obs=[copy.deepcopy(o),copy.deepcopy(o)],gate=valid(o,a))
    for text in ('s9yp0:0,hidden-body;s9yn:0;s9yz;','s9yp0:0,1;s9yp0:0,2;s9yn:0;s9yz;',
                 's9yp0:0,1s9yn:0;s9yz;','s9yp0:0,1;s9yn:-1;s9yz;'):
        try: parse_results(lm.synth_text([text]))
        except ValueError as e: assert 'hidden-body' not in str(e)
        else: raise AssertionError('数値限定陰性')
    a=known['cal-num']; o=synth(a)
    labels=[f's9yp{k}:{v[0]},{v[1]};' for k,v in o['probes'].items()]
    got=parse_results(lm.synth_text(labels+['s9yn:0;s9yz;']))
    assert dict(arm=a['id'],**got)==o
    for mutate in ('sent','missing','extra','number','error'):
        bad=copy.deepcopy(o)
        if mutate=='sent': bad['sent']=2
        elif mutate=='missing': bad['probes'].pop('0')
        elif mutate=='extra': bad['probes']['99']=[0,1]
        elif mutate=='number': bad['probes']['0'][1]='hidden-body'
        else: bad['probes']['0'][0]=256
        assert not valid(bad,a)
    cal=[record(known[k],synth(known[k])) for k in ('cal-num','cal-error')]
    assert calibrated(cal)
    for key in ('probes','errors','sent'):
        bad=copy.deepcopy(cal)
        if key=='probes': bad[0]['obs'][0][key]['0'][1]=1
        else: bad[0]['obs'][0][key]+=1
        assert not calibrated(bad)
    assert not calibrated(cal[:1])
    a=known['speed-nop']; o=synth(a); assert valid(o,a)
    for key,value in [('n1',0),('n2',2),('frames',-1),('ordered',False)]:
        bad=copy.deepcopy(o); bad['marks'][key]=value; assert not valid(bad,a)
    timing='0 10 0000 F3C8 7B\n1 20 0000 F3C8 7D\n'
    assert marks_summary(timing)==dict(n1=1,n2=1,frames=10,ordered=True)
    for text in ('', timing.splitlines()[0], timing+timing,
                 timing.replace('7B','7D',1),
                 '0 20 0000 F3C8 7D\n1 10 0000 F3C8 7B\n',
                 timing.replace('1 20','1 5'), timing.replace('F3C8','FF80')):
        assert not valid(dict(o,marks=marks_summary(text)),a)
    fixtures=[record(a,synth(a)) for a in arms()]
    with tempfile.TemporaryDirectory(prefix='fixture-',dir=work) as td:
        td=Path(td); exp=td/'exp.tsv'; good=td/'good.tsv'; badfile=td/'bad.tsv'
        emit(good,fixtures); assert expected(exp,[good])==len(arms())
        assert len(check(exp,good)[0])==len(arms())
        for mode in ('value','error','missing','unequal','repeat','gate'):
            bad=copy.deepcopy(fixtures)
            if mode in ('value','error'): 
                for ob in bad[0]['obs']: ob['probes']['0'][1 if mode=='value' else 0]+=1
            elif mode=='missing': bad.pop(0)
            elif mode=='unequal': bad[0]['obs'][0]['probes']['0'][1]+=1
            elif mode=='gate': bad[0]['gate']=False
            emit(badfile,bad,strict=False)
            if mode=='repeat': badfile.write_text(badfile.read_text().replace('\t2\t','\t1\t'))
            assert check(exp,badfile)[1]
            if mode in ('missing','unequal','repeat','gate'):
                try: expected(td/'reject.tsv',[badfile])
                except ValueError: pass
                else: raise AssertionError('不正期待値を受理')
    print('OK 合成数値・較正・計時・欠落/重複/型/2走/期待値/check陰性対照',flush=True)
    with tempfile.TemporaryDirectory(prefix='own-',dir=work) as td:
        td=Path(td); rom=td/'rom'
        build=subprocess.run([sys.executable,str(kw.REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(td/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if build.returncode: raise RuntimeError('自作ROMビルド失敗')
        selected=[known[k] for k in ('cal-num','cal-error','mem-int-99','zero-string','auto-1','error-duplicate','erase-redim','coexist','reset-clear','reset-insert','get-values-one','speed-nop','speed-int')]
        records=measure(rom,False,selected,td)
        emit(work/'selftest_own.tsv',records)
        assert calibrated(records) and all(r['gate'] for r in records),'自作ROM関門'
        # 数値ダンプ故障は安全に捕捉し、生写しが失敗時も消えることを検査する。
        os.environ['Q88MEASURE_FAULT_CORRUPT_VRAM_DUMP']='1'
        try:
            faulty=run_arm(rom,False,known['cal-num'],td)
        except (ValueError,RuntimeError): faulty={}
        finally: del os.environ['Q88MEASURE_FAULT_CORRUPT_VRAM_DUMP']
        assert not valid(faulty,known['cal-num']), '実ダンプ故障を検出しない'
        # 同じ解析入口でもラベル破損を注入する。
        raw=bytearray(lm.synth_text(['s9yp0:0,0;s9yn:0;s9yz;']))
        raw[0]=0
        assert not valid(dict(arm='cal-num',**parse_results(raw)),known['cal-num'])
        assert not list(td.glob('*.bin')) and not list(td.glob('marks.txt'))
    print('OK 自作ROM13腕×2走・ラベル故障・生写し消去（公式比較ではない）',flush=True)
    return 0


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('measure'); m.add_argument('--rom-dir',type=Path); m.add_argument('--official',action='store_true')
    m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True)
    m.add_argument('--only',default=''); m.add_argument('--no-calibration',action='store_true')
    s=sub.add_parser('selftest'); s.add_argument('--work-dir',type=Path,required=True)
    sub.add_parser('describe')
    e=sub.add_parser('expected'); e.add_argument('--out',type=Path,required=True); e.add_argument('paths',type=Path,nargs='+')
    c=sub.add_parser('check'); c.add_argument('--expected',type=Path,required=True); c.add_argument('--measured',type=Path,required=True); c.add_argument('--only',default='')
    for name in ('report','speed'):
        r=sub.add_parser(name); r.add_argument('--measured',type=Path,required=True)
    args=p.parse_args()
    if hasattr(args,'work_dir') and not args.work_dir.is_absolute(): p.error('作業先は絶対パス必須')
    if args.command=='selftest': return selftest(args.work_dir)
    if args.command=='describe': print(describe()); return 0
    if args.command=='expected': print(f'期待値 {expected(args.out,args.paths)}腕'); return 0
    if args.command=='check':
        ok,bad=check(args.expected,args.measured,tuple(filter(None,args.only.split(','))))
        for aid,fields in bad.items(): print(f'DIFF {aid}: '+','.join(fields))
        print(f'一致 {len(ok)}腕 / 不一致 {len(bad)}腕'); return int(bool(bad))
    if args.command in ('report','speed'):
        for aid,rs in lm.read_runs(args.measured).items():
            o=json.loads(rs[0]['observation']); known={a['id']:a for a in arms()}
            if aid not in known or not valid(o,known[aid]):
                print(f'{aid}: 関門=0 数値形不正'); continue
            passed=len(rs)==2 and all(r['gate']=='pass' for r in rs) and o==json.loads(rs[1]['observation'])
            if args.command=='report': print(f'{aid}: 関門={int(passed)} 数値={o.get("probes")} 誤り件数={o.get("errors")}')
            elif 'marks' in o: print(f'{aid}: frames={o["marks"]["frames"]} 成功={int(passed and o["errors"]==0 and o["probes"][str(len(o["probes"])-1)]==[0,10000])}')
        return 0
    if args.official and (args.rom_dir or args.no_calibration): p.error('公式は環境変数のみ・較正必須')
    rom=os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom: p.error('公式PC88_REF_ROM_DIR／自作--rom-dirが必要')
    prefixes=tuple(filter(None,args.only.split(',')))
    selected=[a for a in arms() if not prefixes or a['id'].startswith(prefixes)]
    if not selected: p.error('選択腕なし')
    records=measure(rom,args.official,selected,args.work_dir)
    passed=emit(args.out,records,not args.no_calibration)
    print(f'記録 {len(records)}腕×2走: '+('pass' if passed else 'gate_failed'))
    return int(not passed)


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as e:
        tb=traceback.extract_tb(e.__traceback__)
        print(f'NG 器具 ({type(e).__name__}, 行{tb[-1].lineno}、画面本文非出力)')
        raise SystemExit(1)
