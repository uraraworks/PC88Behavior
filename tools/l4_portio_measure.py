#!/usr/bin/env python3
"""l4-t3 INP/OUT/WAIT・予約語。限定RAMの数値印のみ採取する。"""
import argparse, copy, csv, io, json, os, re, subprocess, sys, tempfile, traceback
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
import l4_listkw_measure as kw
REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'tmp/t3-work'
IMPL_ROOT=REPO/'tmp/t3-impl-work'
T3B_IMPL_ROOT=REPO/'tmp/t3b-impl-work'
BASE=0xe780
FIELDS=('begin','stage','ready','finish','ERROR_FLAG','count','first_err','first_stage','last_err','last_stage',
        's1_first','s1_last','s2_first','s2_last','s3_first','s3_last','cal','result','returned1','returned2','returned3')
RANGE='E780-E794'
KNOWN_DIFFERENCES={} # 公式観測前に差を免除しない。
SECRET='synthetic-screen-secret'

def arms():
    out=[]
    def add(i,commands,prediction): out.append(dict(id=i,commands=commands,prediction=prediction))
    add('cal-poke',['poke &he790,213'],'cal213・ERR0')
    add('cal-error',['error 13'],'ERR13、段1')
    add('inp-range',['a=inp(0):poke &he791,abs(a>=0 and a<=255)',
                     'a=inp(0):poke &he791,a'],'段1範囲内印1、段2無押下のキー入力255（弱い）')
    add('inp-vrtc',['z=0:for j=1 to 2000:a=inp(64):z=z or (a and 32):next j',
                    'y=32:for j=1 to 2000:a=inp(64):y=y and (a and 32):next j',
                    'if peek(&he78a)=0 and peek(&he78c)=0 then poke &he791,abs(z<>y)'],'VRTC変化印1')
    for tag,p in [('negative','-1'),('256','256'),('65535','65535'),('fraction','64.5')]:
        add('inp-'+tag,[f'a=inp({p})'],'整数ポート0..255仮説、超過ERR5、小数丸め受理（弱い）')
    add('inp-syntax',['a=inp 64','a=inp()'],'各ERR2（弱い）')
    # 安全なOUT先を仕様で確定できなかった。出力前の異常引数だけ。
    for tag,p,v in [('value-negative','64','-1'),('value-256','64','256'),
                    ('port-negative','-1','256'),('port-256','256','256'),('port-65535','65535','256')]:
        add('out-'+tag,[f'out {p},{v}']+(['out 64,256,1'] if tag=='port-negative' else []),'出力前ERR5（弱い）。正常OUT/副作用は未測定')
    add('out-syntax',['out','out 64','out 64,'],'各ERR2または22（弱い）')
    for tag,s in [('two','wait 64,32'),('three','wait 64,32,32'),('port-320','wait 320,32'),
                  ('fraction','wait 64.5,32.5,0.5'),('mask-negative','wait 64,-1'),
                  ('mask-288','wait 64,288'),('xor-range','wait 64,32,256')]:
        add('wait-'+tag,[s]+(['wait 256,32','wait -192,32'] if tag=='port-320' else ['wait 64,255'] if tag=='mask-negative' else ['wait 64,32,-1','wait 64,32,255'] if tag=='xor-range' else []),'有効VRTC条件は復帰、範囲外ERR5（弱い）')
    add('wait-syntax',['wait','wait 64','wait 64,32,0,1'],'各ERR2または22（弱い）')
    words='ATTR$ CVD CVI CVS DATE$ DSKF DSKI$ EOF FPOS INP KACNV$ AKCNV$ KLEN KPOS LOC LOF LPOS MAP MKD$ MKI$ MKS$ PEN SEARCH STATUS TIME$ USR VARPTR'.lower().split()
    for w in words:
        lhs='x$' if w.endswith('$') else 'x'
        bare=f'{lhs}={w}'; call=f'{lhs}={w}(1)'
        assign=f'{w}="a"' if w.endswith('$') else f'{w}=1'
        add('word-'+w.replace('$','-s'),[bare,call,assign],
            '段1/3は文字列型を一致。予約語なら引数欠如・左辺構文ERR2/22等、時計代入は受理の可能性。段2の引数型ERR13・機器ERRは未確定'
            if w.endswith('$') else '予約語として解析、引数欠如ERR2/22・型ERR13・機器ERR（無確定）。時計は長さのみ')
    return out

def program(a):
    lines={1:'poke &he780,197',2:'for i=1 to 20:poke &he780+i,0:next i',
           3:'on error goto 9000',4:'poke &he782,151'}
    for j,cmd in enumerate(a['commands'],1):
        n=10*j; lines[n]=f'poke &he781,{j}'; lines[n+1]=cmd
        lines[n+2]=f'poke &he780+{17+j},77'
    lines[100]='poke &he781,90'; lines[101]='poke &he783,163'; lines[102]='goto 102'
    lines.update({9000:'e=err:s=peek(&he781)',9001:'poke &he784,1',
        9002:'if peek(&he785)<>0 then 9005',9003:'poke &he786,e',9004:'poke &he787,s',
        9005:'poke &he788,e:poke &he789,s',
        9006:'if peek(&he780+8+s*2)<>0 then 9008',9007:'poke &he780+8+s*2,e',
        9008:'poke &he780+9+s*2,e',9009:'poke &he785,peek(&he785)+1',
        9010:'if s=1 then resume 12',9011:'if s=2 then resume 22',
        9012:'if s=3 then resume 32',9013:'resume 102'})
    assert all(len(f'{n} {s}')<80 for n,s in lines.items())
    return ['new']+[f'{n} {s}' for n,s in sorted(lines.items())]+['run']

def error_block(err,stage,count,seen):
    return [[4,1]]+([[6,err],[7,stage]] if count==0 else [])+[[8,err],[9,stage]]+(
        [] if stage in seen else [[8+stage*2,err]])+[[9+stage*2,err],[5,count+1]]

def valid(o,a):
    if type(o) is not dict or set(o)!={'values','writes'}: return False
    v=o['values']; ws=o['writes']
    if type(v) is not dict or set(v)!=set(FIELDS) or any(type(n) is not int or not 0<=n<=255 for n in v.values()): return False
    if type(ws) is not list or any(type(x) is not list or len(x)!=2 or any(type(n) is not int for n in x) or not 0<=x[0]<21 or not 0<=x[1]<=255 for x in ws): return False
    init=[[0,197]]+[[i,0] for i in range(1,21)]+[[2,151]]
    if ws[:len(init)]!=init: return False
    pos=len(init); stage=0; stages=[]; count=0; seen=set(); returned=set(); results=set()
    while pos<len(ws):
        i,n=ws[pos]
        if i==4:
            offset=3 if count==0 else 1
            if pos+offset>=len(ws) or stage not in range(1,len(a['commands'])+1): return False
            err=ws[pos+offset][1]; block=error_block(err,stage,count,seen)
            if not err or ws[pos:pos+len(block)]!=block: return False
            count+=1; seen.add(stage); pos+=len(block); continue
        if i==1: stage=n; stages.append(n)
        elif i==16 and a['id']=='cal-poke' and stage==1:
            if stage in results: return False
            results.add(stage)
        elif i==17 and stage in range(1,len(a['commands'])+1) and '&he791' in a['commands'][stage-1]:
            if stage in results: return False
            results.add(stage)
        elif i==17+stage and 1<=stage<=3 and n==77:
            if stage in returned: return False
            returned.add(stage)
        elif stage==90 and (i,n)==(3,163): pass
        else: return False
        pos+=1
    required={j for j,c in enumerate(a['commands'],1) if ('&he791' in c or a['id']=='cal-poke') and j not in seen}
    if a['id']=='inp-vrtc' and seen & {1,2}: required.discard(3)
    if results!=required: return False
    return stages==list(range(1,len(a['commands'])+1))+[90] and returned==set(range(1,len(a['commands'])+1)) and ws[-1]==[3,163] and sum(x==[3,163] for x in ws)==1 and {FIELDS[i]:n for i,n in ws}==v

def parse_log(raw,start,finish,a):
    if not re.search(rf'^range\s+: {RANGE}$',raw,re.M): raise ValueError('範囲')
    total=re.search(r'^# 取りこぼし: 0件 / 総イベント数: (\d+)件$',raw,re.M)
    if not total: raise ValueError('取りこぼし')
    events=[]; seq=0; last=-1
    for row in raw.splitlines():
        if not re.match(r'^\s*\d+\s',row): continue
        m=re.fullmatch(r'\s*(\d+)\s+(\d+)\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})',row)
        if not m: raise ValueError('記録形')
        k,t,addr,val=int(m[1]),int(m[2]),int(m[3],16),int(m[4],16)
        if k!=seq+1 or t<last or not BASE<=addr<BASE+21: raise ValueError('連番/時点/番地')
        seq=k; last=t
        if t>=start: events.append((t,addr-BASE,val))
    if seq!=int(total[1]): raise ValueError('件数')
    # RUN前後の余分な書込みは初期化開始印より前だけ区切る。値列を残さない。
    begins=[j for j,(_,i,v) in enumerate(events) if (i,v)==(0,197)]
    if len(begins)!=1: raise ValueError('開始印')
    events=events[begins[0]:]
    if not events or events[-1][0]>finish-600: raise ValueError('安定')
    ws=[[i,v] for _,i,v in events]; o=dict(values={FIELDS[i]:v for i,v in ws},writes=ws)
    if not valid(o,a): raise ValueError('論理印')
    return o

def schedule(a,official):
    at=1200 if official else 120; typed=[]
    if official: typed.append((300,'\n'))
    for cmd in program(a):
        typed.append((at,cmd+'\n')); at+=(len(cmd)+1)*(12 if official else 8)+(360 if official else 120)
    return typed,at+(12000 if official or a['id']=='inp-vrtc' else 2400) # 長いINPループと公式の誤り復帰を待つ。

def capture(rom,official,a,work):
    typed,finish=schedule(a,official); start=typed[-1][0]; path=work/'memory.txt'
    argv=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom)]
    for frame,cmd in typed: argv+=['--type-at',str(frame),'--type',cmd]
    argv+=['--mem-write-log',str(path),'--mem-write-range',RANGE,'--mem-write-from-frame',str(start),'--frames',str(finish)]
    try:
        p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode or b'untypable' in p.stderr.lower(): raise RuntimeError('実行/打鍵拒否')
        return parse_log(path.read_text(),start,finish,a)
    finally: path.unlink(missing_ok=True)

def synth(a):
    ws=[[0,197]]+[[i,0] for i in range(1,21)]+[[2,151]]
    for j,_ in enumerate(a['commands'],1):
        ws.append([1,j])
        if a['id']=='cal-poke': ws.append([16,213])
        if a['id']=='cal-error': ws+=error_block(13,j,0,set())
        if '&he791' in a['commands'][j-1]: ws.append([17,0])
        ws.append([17+j,77])
    ws+=[[1,90],[3,163]]
    return dict(values={FIELDS[i]:v for i,v in ws},writes=ws)

def calibrated(rs):
    by={r['arm']['id']:r for r in rs}
    return all(k in by and by[k]['gate'] and all(o==synth(by[k]['arm']) for o in by[k]['obs']) for k in ('cal-poke','cal-error'))

def write_tsv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w') as f:
        w=csv.writer(f,delimiter='\t',lineterminator='\n'); w.writerow(fields); w.writerows(rows)

def emit(path,rs):
    cal=calibrated(rs)
    write_tsv(path,['arm','repeat','plan','observation','gate'],[[r['arm']['id'],j+1,json.dumps(program(r['arm'])),json.dumps(o),'pass' if r['gate'] and cal else 'gate_failed'] for r in rs for j,o in enumerate(r['obs'])])
    return cal and all(r['gate'] for r in rs)

def read_passed(path):
    known={a['id']:a for a in arms()}; groups={}
    with path.open() as f:
        for row in csv.DictReader(f,delimiter='\t'): groups.setdefault(row['arm'],[]).append(row)
    if set(groups)!=set(known): raise ValueError('全腕')
    rs=[]
    for aid,rows in groups.items():
        if len(rows)!=2 or {r['repeat'] for r in rows}!={'1','2'}: raise ValueError('反復')
        if any(r['gate']!='pass' or json.loads(r['plan'])!=program(known[aid]) for r in rows): raise ValueError('関門/予定')
        obs=[json.loads(r['observation']) for r in rows]
        if not all(valid(o,known[aid]) for o in obs) or obs[0]!=obs[1]: raise ValueError('観測/2走')
        rs.append(dict(arm=known[aid],obs=obs,gate=True))
    if not calibrated(rs): raise ValueError('較正')
    return {r['arm']['id']:r['obs'][0]['values'] for r in rs}

def expected(out,paths):
    if len(paths)!=1: raise ValueError('全腕TSV一つ')
    got=read_passed(paths[0]); write_tsv(out,['arm','values'],[[k,json.dumps(v)] for k,v in sorted(got.items())]); return len(got)

def check(exp,measured):
    with exp.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
    want={r['arm']:json.loads(r['values']) for r in rows}
    if len(rows)!=len(want) or set(want)!={a['id'] for a in arms()} or any(set(v)!=set(FIELDS) or any(type(n) is not int or not 0<=n<=255 for n in v.values()) for v in want.values()): raise ValueError('期待値形')
    for a in arms()[:2]:
        if want[a['id']]!=synth(a)['values']: raise ValueError('期待値較正')
    try: got=read_passed(measured)
    except (ValueError,KeyError,TypeError): got={}
    bad=[]
    for k,v in want.items():
        if got.get(k)==v: continue
        rule=KNOWN_DIFFERENCES.get(k)
        if rule and rule.get('reason') and rule.get('expected')==v and rule.get('measured')==got.get(k):
            print(f'KNOWN {k}: {rule["reason"]}')
        else: bad.append(k)
    return len(want)-len(bad),bad

def fake_log(o,prefix=()):
    ws=list(prefix)+o['writes']
    return f'range     : {RANGE}\n'+''.join(f'{j+1} {100+j} 0000 {BASE+i:04X} {v:02X}\n' for j,(i,v) in enumerate(ws))+f'# 取りこぼし: 0件 / 総イベント数: {len(ws)}件\n'

def safety_selftest(work):
    work.mkdir(parents=True,exist_ok=True); aa=arms(); assert 30<=len(aa)<=50 and len({a['id'] for a in aa})==len(aa)
    for a in aa:
        if not a['id'].startswith('word-'): continue
        w=a['id'][5:].replace('-s','$'); lhs='x$' if w.endswith('$') else 'x'
        assert a['commands']==[f'{lhs}={w}',f'{lhs}={w}(1)',
                               f'{w}="a"' if w.endswith('$') else f'{w}=1']
    rs=[dict(arm=a,obs=[synth(a),synth(a)],gate=True) for a in aa]
    assert all(valid(r['obs'][0],r['arm']) for r in rs) and calibrated(rs)
    a=aa[0]; good=synth(a)
    assert parse_log(fake_log(good,[[18,0],[19,0],[3,99]]),100,1000,a)==good
    for mode in ('begin','finish','stage','flag','missing','noninteger'):
        bad=copy.deepcopy(good)
        if mode=='begin': bad['writes'].insert(23,[0,197])
        elif mode=='finish': bad['writes'].pop()
        elif mode=='stage': bad['writes'][22]=[1,2]
        elif mode=='flag': bad['values']['ERROR_FLAG']=1
        elif mode=='missing': bad['values'].pop('count')
        else: bad['values']['cal']=SECRET
        assert not valid(bad,a)
    a=aa[-1]; multi=synth(a); ws=multi['writes']; j=ws.index([1,1])+1
    ws[j:j]=error_block(13,1,0,set())+error_block(2,1,1,{1})
    j=ws.index([1,3])+1; ws[j:j]=error_block(5,3,2,{1})
    multi['values']={FIELDS[i]:v for i,v in ws}
    assert valid(multi,a) and multi['values']['s1_first']==13 and multi['values']['s1_last']==2 and multi['values']['last_stage']==3
    for raw in (fake_log(good).replace('取りこぼし: 0','取りこぼし: 1'),fake_log(good).replace('総イベント数: 27','総イベント数: 999'),fake_log(good).replace('1 100','2 100')):
        try: parse_log(raw,100,1000,aa[0])
        except ValueError: pass
        else: raise AssertionError('陰性ログ受理')
    for start,finish in ((300,1000),(100,200)):
        try: parse_log(fake_log(good),start,finish,aa[0])
        except ValueError: pass
        else: raise AssertionError('時点の陰性受理')
    with tempfile.TemporaryDirectory(dir=work,prefix='synthetic-') as td:
        td=Path(td); m=td/'m.tsv'; e=td/'e.tsv'; b=td/'b.tsv'
        assert emit(m,rs); assert expected(e,[m])==len(aa); assert check(e,m)==(len(aa),[])
        for mode in ('gate','repeat','plan','body','calibration','two-runs','missing'):
            br=copy.deepcopy(rs)
            if mode=='gate': br[2]['gate']=False
            elif mode=='body': br[2]['obs'][0]['body']=SECRET
            elif mode=='calibration': br[0]['obs']=[synth(aa[1])]*2
            elif mode=='two-runs': br[2]['obs'][1]=synth(aa[0])
            elif mode=='missing': br.pop()
            emit(b,br)
            if mode=='repeat': b.write_text(b.read_text().replace('\t2\t','\t1\t'))
            if mode=='plan': b.write_text(b.read_text().replace('new','wrong'))
            try: expected(td/'reject.tsv',[b])
            except (ValueError,KeyError,TypeError): pass
            else: raise AssertionError('陰性TSV受理')
            assert check(e,b)[1]
        p=subprocess.run([sys.executable,__file__,'check','--expected',str(e),'--measured',str(b)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert p.returncode==1 and SECRET.encode() not in p.stdout+p.stderr
        sink=io.StringIO()
        def fake(argv,**kwargs):
            # 単調なフレームに補正。
            path=Path(argv[argv.index('--mem-write-log')+1]); raw=fake_log(good); start=int(argv[argv.index('--mem-write-from-frame')+1])
            raw=re.sub(r'^(\d+) (\d+) ',lambda m:f'{m[1]} {start+int(m[1])} ',raw,flags=re.M); path.write_text(raw)
            return subprocess.CompletedProcess(argv,0,SECRET.encode(),SECRET.encode())
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=fake),redirect_stdout(sink),redirect_stderr(sink):
            assert capture(Path('synthetic'),False,aa[0],td)==good
        assert not sink.getvalue() and not (td/'memory.txt').exists()
        for failing in (lambda argv,**kwargs:subprocess.CompletedProcess(argv,1,SECRET.encode(),SECRET.encode()),):
            with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=failing),redirect_stdout(sink),redirect_stderr(sink):
                try: capture(Path('synthetic'),False,aa[0],td)
                except RuntimeError: pass
                else: raise AssertionError('実行拒否受理')
        assert not sink.getvalue() and not (td/'memory.txt').exists()
        changed=copy.deepcopy(rs); target=changed[2]
        for o in target['obs']:
            [x for x in o['writes'] if x[0]==17][-1][1]=1; o['values']['result']=1
        assert emit(b,changed) and check(e,b)[1]==['inp-range']
        rule=dict(expected=rs[2]['obs'][0]['values'],measured=copy.deepcopy(target['obs'][0]['values']),reason='合成の完全一致差')
        with patch.dict(KNOWN_DIFFERENCES,{'inp-range':rule}),redirect_stdout(sink):
            assert check(e,b)==(len(aa),[])
            for o in target['obs']:
                o['values']['result']=2
                [x for x in o['writes'] if x[0]==17][-1][1]=2
            emit(b,changed); assert check(e,b)[1]==['inp-range']
    print('OK 合成自己検査: 関門・開始前書込分離・段別最初/最後・2走・TSV拒否・本文非出力',flush=True)

def measure(rom,official,work):
    safety_selftest(work); rs=[]
    for a in arms():
        obs=[]
        for repeat in (1,2):
            dest=work/(a['id']+'-'+str(repeat)); dest.mkdir(exist_ok=True)
            try: obs.append(capture(rom,official,a,dest))
            except Exception as exc:
                condition=str(exc) if type(exc) is ValueError and str(exc) in ('範囲','取りこぼし','記録形','連番/時点/番地','件数','開始印','安定','論理印') else type(exc).__name__
                typed,finish=schedule(a,official)
                print(f'腕={a["id"]} 走={repeat} 条件={condition} start={typed[-1][0]} finish={finish}（本文非出力）',flush=True)
                obs.append(dict(failure='capture-gate'))
        gate=all(valid(o,a) for o in obs) and obs[0]==obs[1]
        rs.append(dict(arm=a,obs=obs,gate=gate)); print(a['id']+': '+('pass' if gate else 'gate_failed'),flush=True)
    return rs

def summary(rs,work=None):
    rows=['# l4-t3 自作試走','公式ROM未実行。src変更・commit・run_allなし。',f'{len(rs)}腕×2走、関門{sum(r["gate"] for r in rs)}/{len(rs)}、較正{calibrated(rs)}。値の仮説一致は関門にしない。',
          '|腕|関門|ERROR_FLAG/回数|最初ERR@段/最後ERR@段|段別最初/最後ERR（1,2,3）|cal|結果|復帰印|','|---|---|---|---|---|---|---|---|']
    for r in rs:
        v=r['obs'][0].get('values',{}); g=lambda k:v.get(k,'不明')
        rows.append(f'|{r["arm"]["id"]}|{r["gate"]}|{g("ERROR_FLAG")}/{g("count")}|{g("first_err")}@{g("first_stage")}/{g("last_err")}@{g("last_stage")}|'+','.join(f'{g("s"+str(j)+"_first")}/{g("s"+str(j)+"_last")}' for j in (1,2,3))+f'|{g("cal")}|{"未測定" if not any("&he791" in c for c in r["arm"]["commands"]) else "不明" if (r["arm"]["id"]=="inp-vrtc" and (g("s1_first")!=0 or g("s2_first")!=0)) or (r["arm"]["id"]=="inp-range" and g("s1_first")!=0) else g("result")}|'+','.join(str(g('returned'+str(j))) for j in (1,2,3))+'|')
    ((ROOT if work is None else work)/'selfrun.md').write_text('\n'.join(rows)+'\n')

def selftest(work):
    safety_selftest(work); rom=work/'rom'
    p=subprocess.run([sys.executable,str(REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    if p.returncode: raise RuntimeError('自作ビルド失敗')
    rs=measure(rom,False,work); passed=emit(work/'selfrun.tsv',rs)
    summary(rs,work if any(work.resolve().is_relative_to(root.resolve()) for root in (T3B_IMPL_ROOT,REPO/'tmp/c2-work')) else None)
    if passed: expected(work/'self-expected.tsv',[work/'selfrun.tsv']); assert check(work/'self-expected.tsv',work/'selfrun.tsv')==(len(rs),[])
    return int(not passed)

def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('measure'); m.add_argument('--official',action='store_true'); m.add_argument('--rom-dir',type=Path); m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True)
    s=sub.add_parser('selftest'); s.add_argument('--work-dir',type=Path,default=ROOT/'selftest'); s.add_argument('--synthetic-only',action='store_true')
    sub.add_parser('describe')
    e=sub.add_parser('expected'); e.add_argument('--out',type=Path,required=True); e.add_argument('paths',type=Path,nargs='+')
    c=sub.add_parser('check'); c.add_argument('--expected',type=Path,required=True); c.add_argument('--measured',type=Path,required=True)
    args=p.parse_args()
    for name in ('work_dir','out','expected','measured'):
        path=getattr(args,name,None)
        if path is not None and (not path.is_absolute() or not any(path.resolve().is_relative_to(root.resolve()) for root in (ROOT,IMPL_ROOT,T3B_IMPL_ROOT,REPO/'tmp/c2-work'))): p.error('作業・結果はtmp/t3-work、tmp/t3-impl-workまたはtmp/t3b-impl-workまたはtmp/c2-work内の絶対パス必須')
    if hasattr(args,'paths') and any(not x.is_absolute() or not any(x.resolve().is_relative_to(root.resolve()) for root in (ROOT,IMPL_ROOT,T3B_IMPL_ROOT,REPO/'tmp/c2-work')) for x in args.paths): p.error('入力もtmp/t3-work、tmp/t3-impl-workまたはtmp/t3b-impl-work内')
    if hasattr(args,'work_dir'): args.work_dir.mkdir(parents=True,exist_ok=True)
    if args.command=='describe':
        for a in arms(): print(json.dumps(a,ensure_ascii=False))
        return 0
    if args.command=='expected': print(f'期待値{expected(args.out,args.paths)}腕'); return 0
    if args.command=='check':
        ok,bad=check(args.expected,args.measured); print(f'一致{ok}腕、不一致{len(bad)}腕'); return int(bool(bad))
    if args.command=='selftest':
        if args.synthetic_only: safety_selftest(args.work_dir); return 0
        return selftest(args.work_dir)
    rom=os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir): p.error('公式はPC88_REF_ROM_DIRのみ、自作は--rom-dir必須')
    return int(not emit(args.out,measure(rom,args.official,args.work_dir)))

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        tb=traceback.extract_tb(exc.__traceback__); print(f'NG 器具: {type(exc).__name__}、行{tb[-1].lineno}（本文非出力）'); raise SystemExit(1)
