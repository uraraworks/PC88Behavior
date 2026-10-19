#!/usr/bin/env python3
"""l4-t1 直接モードGO TO / GO SUB。画面本文・ROMバイト列は採取しない。"""
import argparse
import copy
import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
from l4_work_paths import allowed_path
import sys
import tempfile
import traceback
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

sys.dont_write_bytecode = True
import l4_listkw_measure as kw
REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'tmp/t1-work'
BASE = 0xE600
FIELDS = ('line10', 'line30', 'returned', 'a', 'err', 'cal', 'ready', 'phase',
          'stage', 'first_err', 'first_stage', 'last_stage', 'error_count',
          'first_erl_lo', 'first_erl_hi', 'last_erl_lo', 'last_erl_hi',
          'statement_err', 'following_err', 'initialization_err', 'marker_err', 'next_line')
# erl_hiは上位バイトではなく未取得印：0=取得、255=1バイト範囲外。
RANGE = 'E600-E615'


def arms():
    # 予測は公式観測前の仮説。観測の関門には使わない。
    specs = [
        ('cal-poke', 'poke &he605,213', False, '較正cal=213、ERR0'),
        ('cal-error', 'error 13', False, '較正ERR13、飛び先なし'),
        ('goto-packed', 'goto 30', False, '30へ、ERR0'),
        ('goto-spaced', 'go to 30', False, '30へ、ERR0（弱い予測）'),
        ('gosub-packed', 'gosub 30:poke &he602,77', True, '30へ、戻り77、ERR0'),
        ('gosub-spaced', 'go sub 30:poke &he602,77', True, '30へ、戻り77、ERR0（弱い予測）'),
        ('goto-two-spaces', 'go  to 30', False, '飛び先なし、ERR2'),
        ('goto-adjacent', 'go to30', False, '飛び先なし、ERR2'),
        ('goto-name', 'go tox', False, '飛び先なし、ERR2'),
        ('gosub-two-spaces', 'go  sub 30:poke &he602,77', True, '飛び先なし、ERR2'),
        ('colon-spaced', 'a=1:go to 30', False, 'a=1、30へ、ERR0（弱い予測）'),
        ('if-spaced', 'if 1 then go to 30', False, '30へ、ERR0（弱い予測）'),
        ('on-spaced', 'on 1 go to 30', False, '30へ、ERR0（弱い予測）'),
        ('goto-missing', 'go to 99', False, '飛び先なし、ERR8（弱い予測）'),
        ('goto-packed-missing', 'goto 99', False, '飛び先なし、ERR8'),
        ('goto-line10', 'goto 10', False, '10へ、ERR0'),
    ]
    return [dict(id=i, stmt=s, sub=b, prediction=p) for i,s,b,p in specs]


def plan(a):
    # 段1=初期化、2=前印、3=測る文、4=RETURN後同じ行、5=次行、6=完了印。
    stmt=a['stmt'].replace(':poke &he602,77', ':poke &he608,4:poke &he602,77')
    return ['new', '10 poke &he600,10:end',
            '30 poke &he601,30:'+('return' if a['sub'] else 'end'),
            '9000 e=err:l=erl',
            '9001 if peek(&he60c)<>0 then 9006',
            '9002 poke &he609,e:poke &he60a,peek(&he608)',
            '9003 if l<256 then poke &he60d,l:poke &he60e,0',
            '9004 if l>255 then poke &he60d,0:poke &he60e,255',
            '9006 poke &he604,e:poke &he60b,peek(&he608)',
            '9007 if l<256 then poke &he60f,l:poke &he610,0',
            '9008 if l>255 then poke &he60f,0:poke &he610,255',
            '9009 if peek(&he608)=3 then poke &he611,e',
            '9010 if peek(&he608)>3 then poke &he612,e',
            '9011 if peek(&he608)=1 then poke &he613,e',
            '9012 if peek(&he608)=2 then poke &he614,e',
            '9013 poke &he60c,peek(&he60c)+1:resume 9020', '9020 end',
            'a=0', 'for i=9 to 21:poke &he600+i,0:next i',
            'on error goto 9000', 'poke &he608,1',
            'for i=0 to 7:poke &he600+i,0:next i',
            'poke &he608,2', 'poke &he606,151', 'poke &he607,162',
            'poke &he608,3', stmt,
            'poke &he608,5', 'poke &he615,88', 'poke &he603,a',
            'poke &he608,6', 'poke &he607,163']


def schedule(a, official):
    at = 700 if official else 100
    typed = []
    if official: typed.append((300, '\n'))
    for cmd in plan(a):
        typed.append((at, cmd+'\n'))
        at += (len(cmd)+1)*8 + 240 + (1200 if cmd==plan(a)[-6] else 0)
    return typed, at


def parse_log(raw, start, finish):
    # PC・ROMパス等の見出しは外へ出さない。限定RAMの数値だけを残す。
    if not re.search(rf'^range\s+: {RANGE}$', raw, re.M): raise ValueError('範囲')
    if not re.search(r'^# 取りこぼし: 0件 / 総イベント数: \d+件$', raw, re.M): raise ValueError('取りこぼし')
    events = []
    seq = 0
    for row in raw.splitlines():
        if re.match(r'^\s*\d+\s', row):
            m = re.fullmatch(r'\s*(\d+)\s+(\d+)\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})', row)
            if not m: raise ValueError('記録形')
            n,frame,addr,val = int(m[1]),int(m[2]),int(m[3],16),int(m[4],16)
            if n != seq+1 or not BASE<=addr<BASE+len(FIELDS): raise ValueError('記録連番/範囲')
            seq=n
            if frame>=start: events.append([frame,addr-BASE,val])
    total=re.search(r'^# 取りこぼし: 0件 / 総イベント数: (\d+)件$',raw,re.M)
    if seq!=int(total[1]): raise ValueError('総件数')
    if not events: raise ValueError('記録なし')
    values={}; logical=[]
    for frame,index,val in events:
        values[FIELDS[index]]=val; logical.append([index,val])
    if set(values)!=set(FIELDS): raise ValueError('初期化欠落')
    if values['ready']!=151 or values['phase']!=163: raise ValueError('到達/完了')
    if sum(x==[7,163] for x in logical)!=1 or events[-1][0]>finish-300: raise ValueError('安定/完了重複')
    result=dict(values=values, writes=logical, stable=True)
    if not valid(result): raise ValueError('論理書込み')
    return result


def capture(rom, official, a, work):
    typed,at=schedule(a,official)
    path=work/'memory.txt'
    args=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom)]
    for frame,cmd in typed: args+=['--type-at',str(frame),'--type',cmd]
    start=next(frame for frame,cmd in typed if cmd.startswith('for i=9'))
    finish=at+600
    args+=['--mem-write-log',str(path),'--mem-write-range',RANGE,
           '--mem-write-from-frame',str(start),'--frames',str(finish)]
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode or b'untypable' in p.stderr.lower(): raise RuntimeError('実行/打鍵拒否')
        return parse_log(path.read_text(),start,finish)
    finally:
        path.unlink(missing_ok=True)


def prefix():
    return [[i,0] for i in range(9,22)]+[[8,1]]+[[i,0] for i in range(8)]+[[8,2],[6,151],[7,162],[8,3]]


def error_writes(err,stage,count,erl=0):
    erl_first=[[13,erl if erl<256 else 0],[14,0 if erl<256 else 255]]
    erl_last=[[15,erl if erl<256 else 0],[16,0 if erl<256 else 255]]
    first=[] if count else [[9,err],[10,stage]]+erl_first
    category={1:19,2:20,3:17,4:18,5:18,6:18}[stage]
    return first+[[4,err],[11,stage]]+erl_last+[[category,err],[12,count+1]]


def valid(o):
    if not isinstance(o,dict) or set(o)!={'values','writes','stable'} or o['stable'] is not True: return False
    v=o['values']; ws=o['writes']
    if not isinstance(v,dict) or set(v)!=set(FIELDS) or any(type(x) is not int or not 0<=x<=255 for x in v.values()): return False
    if not isinstance(ws,list) or any(not isinstance(x,list) or len(x)!=2 or type(x[0]) is not int or not 0<=x[0]<len(FIELDS) or type(x[1]) is not int or not 0<=x[1]<=255 for x in ws): return False
    # 初期化FOR途中の誤りも、消さずに同じブロック規則で検査する。
    setup=[[i,0] for i in range(9,22)]+[[8,1]]
    if ws[:len(setup)]!=setup: return False
    pos=len(setup); stage=1; count=0; init=[]; marks=[]; seen=set()
    while pos<len(ws):
        i,n=ws[pos]
        if i in (9,4) and not (stage==1 and i==4 and n==0):
            first=count==0
            head=4 if first else 0
            size=head+6
            block=ws[pos:pos+size]
            if len(block)!=size: return False
            err=block[head][1]
            erl_item=block[head+2:head+4]
            if erl_item[0][0]!=15: return False
            if erl_item[1]==[16,0]: erl=erl_item[0][1]
            elif erl_item==[[15,0],[16,255]]: erl=256
            else: return False
            if err==0 or block!=error_writes(err,stage,count,erl): return False
            count+=1; pos+=size; continue
        if i==8:
            if (stage,n) not in ((1,2),(2,3),(3,4),(3,5),(4,5),(5,6)): return False
            stage=n
        elif stage==1 and 0<=i<=7 and n==0: init.append(i)
        elif (stage,i,n) in ((2,6,151),(2,7,162),(6,7,163)):
            marks.append((stage,i,n))
        elif (stage,i) in ((3,0),(3,1),(3,5),(4,2),(5,21),(5,3)):
            if i in seen: return False
            if i==21 and n!=88: return False
            seen.add(i)
        else: return False
        pos+=1
    if init!=list(range(8)) or marks!=[(2,6,151),(2,7,162),(6,7,163)]: return False
    if stage!=6 or ws[-1]!=[7,163] or 21 not in seen: return False
    # a診断が失敗する場合はstage5のエラーが必要。
    if 3 not in seen and not any(ws[k][0]==4 and ws[k][1]!=0 and ws[k+1]==[11,5] for k in range(len(ws)-1)):
        return False
    return {FIELDS[i]:n for i,n in ws}==v


def calibrated(rs):
    by={r['arm']['id']:r for r in rs}
    for aid in ('cal-poke','cal-error'):
        r=by.get(aid)
        reference=synth(next(a for a in arms() if a['id']==aid))['values']
        if not r or not r['gate'] or any(not valid(o) or any(o['values'][k]!=n for k,n in reference.items() if 'erl_' not in k) for o in r['obs']): return False
    return True


def write_tsv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w') as f:
        w=csv.writer(f,delimiter='\t',lineterminator='\n'); w.writerow(fields); w.writerows(rows)


def emit(path,rs):
    cal=calibrated(rs)
    write_tsv(path,['arm','repeat','plan','observation','gate',
                    'statement_err','following_err','returned','next_line','first_stage','last_stage'],
              [[r['arm']['id'],i+1,json.dumps(plan(r['arm'])),json.dumps(o),
                'pass' if r['gate'] and cal else 'gate_failed',
                *[o.get('values',{}).get(k,'不明') for k in
                  ('statement_err','following_err','returned','next_line','first_stage','last_stage')]] for r in rs for i,o in enumerate(r['obs'])])
    return cal and all(r['gate'] for r in rs)


def read_passed(path):
    known={a['id']:a for a in arms()}; groups={}
    with path.open() as f:
        for row in csv.DictReader(f,delimiter='\t'): groups.setdefault(row['arm'],[]).append(row)
    rs=[]
    for aid,rows in groups.items():
        if aid not in known or len(rows)!=2 or {r['repeat'] for r in rows}!={'1','2'}: raise ValueError('腕/反復')
        if any(r['gate']!='pass' or json.loads(r['plan'])!=plan(known[aid]) for r in rows): raise ValueError('関門/予定')
        obs=[json.loads(r['observation']) for r in rows]
        for row,o in zip(rows,obs):
            if any(row.get(k)!=str(o.get('values',{}).get(k)) for k in
                   ('statement_err','following_err','returned','next_line','first_stage','last_stage')):
                raise ValueError('結果欄不一致')
        if not all(valid(o) for o in obs) or obs[0]!=obs[1]: raise ValueError('観測/2走')
        rs.append(dict(arm=known[aid],obs=obs,gate=True))
    if not calibrated(rs): raise ValueError('較正')
    return {r['arm']['id']:r['obs'][0]['values'] for r in rs}


def expected(out,paths):
    values={}
    for path in paths:
        got=read_passed(path)
        if set(values)&set(got): raise ValueError('重複腕')
        values.update(got)
    if set(values)!={a['id'] for a in arms()}: raise ValueError('全腕必要')
    write_tsv(out,['arm','values'],[[k,json.dumps(v)] for k,v in sorted(values.items())])
    return len(values)


def check(exp,measured):
    with exp.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
    want={r['arm']:json.loads(r['values']) for r in rows}
    if len(rows)!=len(want) or set(want)!={a['id'] for a in arms()}: raise ValueError('期待値腕')
    if any(set(v)!=set(FIELDS) or any(type(n) is not int or not 0<=n<=255 for n in v.values()) or v['ready']!=151 or v['phase']!=163 for v in want.values()): raise ValueError('期待値形')
    try: got=read_passed(measured)
    except (ValueError,KeyError,TypeError): got={}
    bad=[k for k,v in want.items() if got.get(k)!=v]
    return len(want)-len(bad),bad


def synth(a):
    ws=prefix()
    if a['id']=='cal-poke': ws.append([5,213])
    if a['id']=='cal-error': ws.extend(error_writes(13,3,0))
    ws.extend([[8,5],[21,88],[3,0],[8,6],[7,163]])
    return dict(values={FIELDS[i]:n for i,n in ws},writes=ws,stable=True)


def fake_log(o):
    return f'range     : {RANGE}\n'+''.join(f'{k+1} {100+k} 0000 {BASE+i:04X} {n:02X}\n' for k,(i,n) in enumerate(o['writes']))+f'# 取りこぼし: 0件 / 総イベント数: {len(o["writes"])}件\n'


def safety_selftest(work):
    work.mkdir(parents=True,exist_ok=True)
    known=arms()
    assert 10<=len(known)<=20 and len({a['id'] for a in known})==len(known)
    for a in known:
        assert all(cmd==cmd.lower() and len(cmd)<80 for cmd in plan(a))
    rs=[dict(arm=a,obs=[synth(a),synth(a)],gate=True) for a in known]
    assert calibrated(rs)
    # 最初/最後の保存、同一段の再発、ERL範囲外と取得への遷移。
    ws=prefix()+error_writes(8,3,0,256)+error_writes(2,3,1,0)
    ws+=[[8,5],[21,88]]+error_writes(2,5,2,0)+[[8,6],[7,163]]
    multiple=dict(values={FIELDS[i]:n for i,n in ws},writes=ws,stable=True)
    assert valid(multiple) and parse_log(fake_log(multiple),100,1000)==multiple
    assert multiple['values']['first_err']==8 and multiple['values']['first_stage']==3
    assert multiple['values']['err']==2 and multiple['values']['last_stage']==5
    assert multiple['values']['error_count']==3 and multiple['values']['last_erl_hi']==0
    good=synth(known[0]); assert valid(good) and parse_log(fake_log(good),100,1000)==good
    for mode in ('missing','duplicate','noninteger','unstable','ready','finish','last','extra-phase','duplicate-err'):
        bad=copy.deepcopy(good)
        if mode=='missing': bad['values'].pop('err')
        elif mode=='duplicate': bad['writes'].append([7,163])
        elif mode=='noninteger': bad['values']['err']='hidden-body'
        elif mode=='unstable': bad['stable']=False
        elif mode=='ready': bad['values']['ready']=0
        elif mode=='finish': bad['writes'].pop()
        elif mode=='last': bad['values']['line30']=30
        elif mode=='extra-phase': bad['writes'].insert(10,[7,162])
        else:
            bad['writes'][len(prefix()):len(prefix())]=[[4,2],[4,2]]; bad['values']['err']=2
        assert not valid(bad)
    for raw,finish in [(fake_log(good).replace('取りこぼし: 0','取りこぼし: 1'),1000),
                       (fake_log(good).replace(RANGE,'E600-E608'),1000),
                       (fake_log(good).replace(f'総イベント数: {len(good["writes"])}件','総イベント数: 1件'),1000),
                       (fake_log(good).replace('1 100','2 100'),1000),(fake_log(good),300),
                       (fake_log(good).replace(' E603 00',' E603 hidden-body'),1000)]:
        try: parse_log(raw,100,finish)
        except ValueError: pass
        else: raise AssertionError('壊れたログ受理')
    with tempfile.TemporaryDirectory(prefix='synthetic-',dir=work) as td:
        td=Path(td); measured=td/'good.tsv'; exp=td/'expected.tsv'; badpath=td/'bad.tsv'
        assert emit(measured,rs); assert expected(exp,[measured])==len(known); assert check(exp,measured)==(len(known),[])
        for mode in ('unequal','calibration','gate','missing','plan','repeat'):
            broken=copy.deepcopy(rs)
            if mode=='unequal': broken[2]['obs'][0]['stable']=False
            elif mode=='calibration':
                for o in broken[0]['obs']: o['writes'][len(prefix())][1]=212; o['values']['cal']=212
            elif mode=='gate': broken[2]['gate']=False
            elif mode=='missing': broken.pop()
            emit(badpath,broken)
            if mode in ('plan','repeat'):
                text=badpath.read_text()
                badpath.write_text(text.replace('goto 30','goto 10') if mode=='plan' else text.replace('\t2\t','\t1\t'))
            try: expected(td/'reject.tsv',[badpath])
            except ValueError: pass
            else: raise AssertionError('壊れた期待値受理')
            assert check(exp,badpath)[1]
        broken=copy.deepcopy(rs)
        for o in broken[2]['obs']: o['writes'].insert(len(prefix()),[1,30]); o['values']['line30']=30
        assert emit(badpath,broken); assert check(exp,badpath)==(len(known)-1,[known[2]['id']])
        stage_bad=copy.deepcopy(rs)
        for o in stage_bad[1]['obs']:
            for item in o['writes']:
                if item[0] in (10,11): item[1]=5
            o['values']['first_stage']=5; o['values']['last_stage']=5
        assert not valid(stage_bad[1]['obs'][0])
        emit(badpath,stage_bad)
        assert check(exp,badpath)[1]
        # 関門上は正しい後続エラーへの変更も、欄の照合でNG。
        stage_changed=copy.deepcopy(rs)
        for o in stage_changed[2]['obs']:
            ws=prefix()+[[8,5],[21,88]]+error_writes(2,5,0)+[[8,6],[7,163]]
            o['writes']=ws; o['values']={FIELDS[i]:n for i,n in ws}
        assert emit(badpath,stage_changed)
        assert check(exp,badpath)==(len(known)-1,[known[2]['id']])
        cli=subprocess.run([sys.executable,str(Path(__file__).resolve()),'check','--expected',str(exp),'--measured',str(badpath)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        assert cli.returncode==1
        assert b'hidden-body' not in cli.stdout+cli.stderr
        # 実行経路も偽フロントエンドで検査。ROMは空の名前のみ。
        def fake(argv,**kwargs):
            path=Path(argv[argv.index('--mem-write-log')+1])
            start=int(argv[argv.index('--mem-write-from-frame')+1])
            raw=fake_log(good)
            raw=re.sub(r'^(\d+) (\d+)',lambda m:f'{m[1]} {start+int(m[2])}',raw,flags=re.M)
            path.write_text(raw)
            return subprocess.CompletedProcess(argv,0,b'hidden-body',b'hidden-body')
        sink=io.StringIO()
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=fake),redirect_stdout(sink),redirect_stderr(sink):
            assert capture(Path('synthetic'),False,known[0],td)==good
        assert not sink.getvalue() and not (td/'memory.txt').exists()
        def rejected(argv,**kwargs):
            Path(argv[argv.index('--mem-write-log')+1]).write_text('hidden-body')
            return subprocess.CompletedProcess(argv,1,b'hidden-body',b'hidden-body')
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=rejected),redirect_stdout(sink),redirect_stderr(sink):
            try: capture(Path('synthetic'),False,known[0],td)
            except RuntimeError as exc: assert 'hidden-body' not in str(exc)
            else: raise AssertionError('実行失敗受理')
        assert not sink.getvalue() and not (td/'memory.txt').exists()
    print('OK 合成自己検査: 較正・初期化・到達・完了・安定・2走・expected/check・誤り段取り違え陰性対照・本文非出力',flush=True)


def measure(rom,official,work):
    safety_selftest(work)
    rs=[]
    for a in arms():
        obs=[]
        for repeat in (1,2):
            dest=work/(a['id']+'-'+str(repeat)); dest.mkdir(exist_ok=True)
            try: obs.append(capture(rom,official,a,dest))
            except Exception: obs.append(dict(failure='capture-gate'))
        gate=all(valid(o) for o in obs) and obs[0]==obs[1]
        rs.append(dict(arm=a,obs=obs,gate=gate))
        print(a['id']+': '+('pass' if gate else 'gate_failed'),flush=True)
    return rs


def selftest(work):
    safety_selftest(work)
    rom=work/'rom'
    p=subprocess.run([sys.executable,str(REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    if p.returncode: raise RuntimeError('自作ビルド拒否/失敗')
    rs=measure(rom,False,work)
    passed=emit(work/'selfrun.tsv',rs)
    rows=['# l4-t1 自作ROM試走（第1回追加修正）', '2026-10-14。公式ROM未実行。src変更・commit・run_all実行なし。',
          f'全{len(rs)}腕×2走。関門通過{sum(r["gate"] for r in rs)}/{len(rs)}、較正{calibrated(rs)}。予測との一致は関門にしない。',
          '採取は限定RAMへの書込みだけ。生ログ・PC・画面本文は保存しない。',
          '段1=初期化FOR、2=前印POKE、3=測る文（RETURNも含む）、4=同一直接行の戻りPOKE、5=次直接行とa診断、6=完了印。',
          'ERR/段は最初と最後を保存。ERLは予測せず0〜255なら取得、範囲外は不明。各表値は2走一致時の値（不一致・欠測は不明）。',
          '', '| 腕 | 関門 | line10/line30/a/cal | 測る文ERR | 後続ERR | 同一行戻り/次行 | 最初ERR@段 | 最後ERR@段 | 回数 | 最初/最後ERL |',
          '|---|---|---|---|---|---|---|---|---|---|']
    for r in rs:
        v=r['obs'][0].get('values',{}) if r['gate'] else {}
        def get(k): return v.get(k,'不明')
        def erl(pre):
            return v[pre+'_erl_lo'] if v and v[pre+'_erl_hi']==0 else '不明'
        rows.append(f'| {r["arm"]["id"]} | {"pass" if r["gate"] else "gate_failed"} | '
                    +'/'.join(str(get(k)) for k in ('line10','line30','a','cal'))
                    +f' | {get("statement_err")} | {get("following_err")} | {get("returned")}/{get("next_line")} | '
                    +f'{get("first_err")}@{get("first_stage")} | {get("err")}@{get("last_stage")} | {get("error_count")} | {erl("first")}/{erl("last")} |')
    rows.extend(['', '誤り発生の全記録（ERR@段、各走）。値はハンドラの書込みから復元する。',
                 '', '| 腕 | 1走 | 2走 |', '|---|---|---|'])
    for r in rs:
        columns=[]
        for o in r['obs']:
            if not valid(o): columns.append('不明'); continue
            ws=o['writes']
            events=[f'{n}@{ws[k+1][1]}' for k,(i,n) in enumerate(ws[:-1])
                    if i==4 and n!=0 and ws[k+1][0]==11]
            columns.append(', '.join(events) or 'なし')
        rows.append('| '+r['arm']['id']+' | '+' | '.join(columns)+' |')
    ((work if any(work.resolve().is_relative_to(r.resolve()) for r in (REPO/'tmp/t1-impl-work', REPO/'tmp/t2-impl-work')) else ROOT)/'selfrun.md').write_text('\n'.join(rows)+'\n')
    print(f'自作ROM試走: {len(rs)}腕×2走、'+('pass' if passed else 'gate_failed'))
    return int(not passed)


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('measure'); m.add_argument('--official',action='store_true'); m.add_argument('--rom-dir',type=Path); m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True)
    s=sub.add_parser('selftest'); s.add_argument('--work-dir',type=Path,default=ROOT/'selftest'); s.add_argument('--synthetic-only',action='store_true')
    sub.add_parser('describe')
    e=sub.add_parser('expected'); e.add_argument('--out',type=Path,required=True); e.add_argument('paths',type=Path,nargs='+')
    c=sub.add_parser('check'); c.add_argument('--expected',type=Path,required=True); c.add_argument('--measured',type=Path,required=True)
    args=p.parse_args()
    if hasattr(args,'work_dir'):
        if not allowed_path(args.work_dir, (ROOT, REPO/'tmp/t1-impl-work', REPO/'tmp/t2-impl-work')): p.error('作業先はtmp/t1-workまたはtmp/t1-impl-workまたはtmp/t2-impl-work内の絶対パス必須')
        args.work_dir.mkdir(parents=True,exist_ok=True)
    if args.command=='describe':
        for a in arms(): print(f'- `{a["id"]}`: `{a["stmt"]}` — {a["prediction"]}')
        return 0
    if args.command=='expected': print(f'期待値{expected(args.out,args.paths)}腕'); return 0
    if args.command=='check':
        ok,bad=check(args.expected,args.measured); print(f'一致{ok}腕、不一致{len(bad)}腕'); return int(bool(bad))
    if args.command=='selftest':
        if args.synthetic_only: safety_selftest(args.work_dir); return 0
        return selftest(args.work_dir)
    rom=os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir): p.error('公式はPC88_REF_ROM_DIRのみ、自作は--rom-dir必須')
    rs=measure(rom,args.official,args.work_dir); return int(not emit(args.out,rs))


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        tb=traceback.extract_tb(exc.__traceback__)
        print(f'NG 器具: {type(exc).__name__}、行{tb[-1].lineno}（本文非出力）')
        raise SystemExit(1)
