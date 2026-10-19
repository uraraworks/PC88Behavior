#!/usr/bin/env python3
"""l4-s9z INPUT/LINE INPUT測定。画面本文は出力しない。"""
import argparse, copy, csv, io, json, os, re, subprocess, sys, tempfile, traceback
from contextlib import redirect_stdout, redirect_stderr
from l4_work_paths import allowed_path
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools'))
import l4_dim_measure as dm
import check_l3_screen_output as screen
kw, lm = dm.kw, dm.lm
ROOT=kw.REPO/'tmp/s9z-work'
IMPL_ROOT=kw.REPO/'tmp/s9z-impl-work'
WAIT=3000


def arm(aid,stmt,inputs=(),variables=('a',),prediction='正常入力',direct=False):
    return dict(id=aid,stmt=stmt,inputs=list(inputs),variables=list(variables),prediction=prediction,direct=direct)


def arms():
    out=[arm('cal-num','a=0:b=-32768:c=32767',variables=('a','b','c'),prediction='0,-32768,32767'),
         arm('cal-error','error 13',variables=('a',),prediction='ERR13、初期値12')]
    for tag,stmt in [('semi','input "ab";a'),('comma','input "ab",a'),('plain','input a'),('nonewline','input; a')]:
        out.append(arm('prompt-'+tag,stmt,['1'],prediction='semiは接尾?と空白、commaは接尾なし、plainは?と空白。nonewlineは改行抑止'))
    for n in range(1,9):
        vs=list('abcdfghj'[:n]); out.append(arm('count-'+str(n),'input '+','.join(vs),[','.join(map(str,range(1,n+1)))],vs,prediction='左から1..'+str(n)))
    for tag,v in [('default','a'),('int','a%'),('single','a!'),('double','a#'),('string','a$'),('array','a%(1)')]:
        out.append(arm('type-'+tag,'input '+v,['xyz' if '$' in v else '23'],[v],prediction='文字列xyz、数値23'))
    out.append(arm('type-mixed','input a%,b!,c#,d$,a%(1)',['1,2,3,xy,4'],['a%','b!','c#','d$','a%(1)'],prediction='型別に1,2,3,xy,4'))
    for tag,data in [('sign','-12'),('plus','+12'),('decimal','1.25'),('exp','1e2'),('dexp','1d2'),('hex','&h10'),('oct','&o10'),('spaces','  12  '),('empty','')]:
        out.append(arm('number-'+tag,'input a',[data],prediction='数値変換。空入力は0と弱く予測、基数表記は予測なし'))
    for tag,data in [('bare','xy'),('quoted','"xy"'),('comma','"x,y"'),('spaces','  xy  '),('quoted-spaces','" xy "'),('empty','')]:
        out.append(arm('string-'+tag,'input a$',[data],['a$'],prediction='引用符を除去、引用符内コンマ/空白保持。非引用空白は除去、空は空文字と弱く予測'))
    for tag,data,vs in [('short',['1','2'],['a','b']),('excess',['1,2,3','4,5'],['a','b']),('bad-first',['x,2','4,5'],['a','b']),('bad-last',['1,x','4,5'],['a','b']),('overflow',['1e100','4'],['a']),('int-overflow',['32768','4'],['a%'])]:
        out.append(arm('retry-'+tag,'input '+','.join(vs),data,vs,prediction='shortは追加要求、excess/型違いは再入力、桁あふれは再入力またはERR6（予測なし）。完了後全変数を取得'))
    for tag,stmt in [('semi','line input "ab";a$'),('plain','line input a$'),('nonewline','line input; a$')]:
        out.append(arm('line-'+tag,stmt,[' x,"y"  '],['a$'],prediction='コンマ・引用符・両端空白を保持、semiは接尾なし、nonewlineは改行抑止'))
    out.append(arm('line-empty','line input a$',[''],['a$'],prediction='空文字'))
    out.append(arm('line-numeric','line input a',prediction='ERR13と弱く予測'))
    for tag,stmt in [('input-separator','input "ab" a'),('input-missing','input'),('input-variable','input "ab";'),('line-separator','line input "ab" a$'),('line-missing','line input'),('line-variable','line input "ab";')]:
        out.append(arm('syntax-'+tag,stmt,prediction='ERR2と予測'))
    for tag,stmt,v in [('input','input a','a'),('line','line input a$','a$')]:
        out.append(arm('direct-'+tag,stmt,['7'],[v],prediction='ERR12と弱く予測、受理なら値も取得',direct=True))
    for n in (79,80,81,127,128,129,254,255,256,260):
        for tag,stmt in [('input','input a$'),('line','line input a$')]:
            out.append(arm('length-'+tag+'-'+str(n),stmt,['x'*n],['a$'],prediction='上限255と弱く予測。LEN/先頭末尾ASC/文字コード和を取得、打鍵到達境界とは分離'))
    for a in out:
        if a['id']=='retry-short': a['inputs'].append('4,5')
        if a['id'] in ('syntax-input-missing','syntax-input-variable'): a['inputs']=['0']
    return out


def program(a):
    lines={5:'clear ,58877',6:'on error goto 9000',7:'e=0:n=0:q=0',8:'cls'}
    num=10
    for v in a['variables']:
        lines[num]=v+'='+('"seed"' if '$' in v else '12'); num+=10
    lines[num]='locate 0,14:print "s9zw;";:locate 0,0'; num+=10
    if not a['direct']: lines[num]=a['stmt']; num+=10
    else: lines[num]='end'; num+=10
    num=1000
    lines[num]='print "s9zc";'; num+=10
    lines[num]='locate 0,15'; num+=10
    expressions=['e','n']
    for v in a['variables']:
        if '$' in v:
            expressions += ['len('+v+')',f'asc(left$({v}+" ",1))',f'asc(right$(" "+{v},1))']
            lines[num]='q=0'; num+=10
            lines[num]=f'for i=1 to len({v})+1:q=q+asc(mid$({v}+" ",i,1)):next i:q=q-32'; num+=10
            expressions.append('q')
        elif a['id']=='retry-overflow':
            # 大きな値のPRINTが指数表記になっても、採取は整数印だけにする。
            lines[num]='q=0:b=0'; num+=10
            lines[num]=f'if abs({v})>32768 then q=1'; num+=10
            lines[num]=f'if abs({v})<=32768 then b=fix({v})'; num+=10
            expressions += [f'sgn({v})','q','b']
        else: expressions.append(f'fix({v}*100)' if a['id']=='number-decimal' else f'fix({v})')
    for k,x in enumerate(expressions):
        lines[num]=f'print "s9zp{k}:";0;",";{x};";";'; num+=10
    lines[num]='print "s9zn:";n;";s9zz;";'; num+=10
    lines[num]=f'goto {num}'
    lines[9000]='e=err:n=n+1:'+('goto 1000' if a['direct'] else 'resume next')
    assert all(len(f'{n} {s}')<80 and s==s.lower() for n,s in lines.items())
    return lines,len(expressions)


def signature(raw):
    if len(raw)!=3000: raise ValueError('画面長')
    # PRINT対照も同じ14行・80桁。空白と行座標を保存し、属性は除外。
    return vars(screen.signature([(r,raw[r*120:r*120+80].decode('latin1')) for r in range(14)]))


def parse(raw,a):
    o=dm.parse_results(raw.replace(b's9zp',b's9yp').replace(b's9zn',b's9yn').replace(b's9zz',b's9yz'))
    return dict(arm=a['id'],**o)


def base_plan(a):
    return ['new']+[f'{n} {s}' for n,s in sorted(program(a)[0].items())]+['cls','run']+([a['stmt']] if a['direct'] else [])


def capture_many(rom,official,plans,work):
    if not 1<=len(plans)<=8: raise ValueError('写し組数')
    # 待機ループ中の次候補への打鍵は実行されない。必ず独立起動。
    if len(plans)>1:
        return [capture_many(rom,official,[plan],work)[0] for plan in plans]
    args=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom)]
    at=700 if official else 100
    if official: args+=['--type-at','300','--type','\n']
    paths=[]
    for k,commands in enumerate(plans):
        for cmd in commands:
            args+=['--type-at',str(at),'--type',cmd+'\n']
            at+=(len(cmd)+1)*8+240+(WAIT if cmd=='run' or cmd.startswith(('goto ','input','line input')) or (cmd not in ('new','cls') and not re.match(r'^\d+ ',cmd)) else 0)
        for j,t in enumerate((at,at+300)):
            base=work/f'capture{k}-{j}.bin'
            args+=['--vram-dump',str(base),'--vram-dump-at',str(t)]
            paths.append(base.with_name(base.stem+f'.f{t:06d}'+base.suffix))
        at+=600
    args+=['--frames',str(at+100)]
    try:
        proc=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower(): raise RuntimeError('実行/打鍵拒否')
        raw=[x.read_bytes() for x in paths]
        return [raw[i:i+2] for i in range(0,len(raw),2)]
    finally:
        for path in paths:
            path.unlink(missing_ok=True); Path(str(path)+'.info.txt').unlink(missing_ok=True)


def capture(rom,official,commands,work):
    return capture_many(rom,official,[commands],work)[0]


def done(raw,a):
    return b's9zz;' in b''.join(raw[r*120:r*120+80] for r in range(15,25))


def ready(pair,a):
    return len(pair)==2 and all(len(x)==3000 for x in pair) and pair[0]==pair[1] and not done(pair[1],a) and b's9zw;' in pair[1][14*120:14*120+80]


def candidate_program(rows,newline=True,completed=False):
    # 候補は事前に組み立てた打鍵文字列。画面からの本文転記はしない。
    p=['new','10 cls']; n=20
    for row in rows:
        chunks=[row[i:i+24] for i in range(0,len(row),24)] or ['']
        for ci,chunk in enumerate(chunks):
            parts=[]; literal=''
            for ch in chunk:
                if ch=='"' or ch.isupper():
                    if literal: parts.append('"'+literal+'"'); literal=''
                    parts.append(f'chr$({ord(ch)})')
                else: literal+=ch
            if literal or not parts: parts.append('"'+literal+'"')
            expr='+'.join(parts)
            p.append(f'{n} print {expr}'+('' if newline and ci==len(chunks)-1 else ';')); n+=10
    if completed:
        p.append(f'{n} print "s9zc";'); n+=10
    p.append(f'{n} locate 0,14:print "s9zw;";'); n+=10
    p.extend([f'{n} goto {n}','cls','run']); return p


def candidate_rows(a,stage):
    prefix='ab' if '"ab"' in a['stmt'] else ''
    data=a['inputs'][:stage]
    out={}
    for tag,suffix in [('q-space','? '),('q','?'),('space',' '),('none','')]:
        prompt=prefix+suffix
        out[tag]=[prompt+(data[0] if data else '')]+data[1:]
        if stage and a['id'].startswith('retry-'):
            for rt,msg in [('redo-q','?redo from start'),('redo','redo from start'),('extra','?extra ignored'),('redo-upper','?Redo from start'),('extra-upper','?Extra ignored')]:
                out[tag+'-'+rt]=[prompt+data[0],msg,prompt+(data[1] if len(data)>1 else '')]
            out[tag+'-more']=[prompt+data[0],'?? '+(data[1] if len(data)>1 else '')]
        if a['id']=='retry-short' and stage>=2:
            for rt,msg in [('redo-q','?redo from start'),('redo','redo from start'),('extra','?extra ignored'),('redo-upper','?Redo from start'),('extra-upper','?Extra ignored')]:
                out[tag+'-'+rt+'-twice']=[prompt+data[0],msg,prompt+data[1],msg,prompt+(data[2] if len(data)>2 else '')]
    # 未入力時の末尾空白は空セルと同じ。既知の等価組を除外。
    if stage==0:
        out.pop('q'); out.pop('none')
    return out


def row_metrics(raw):
    import hashlib
    return [dict(row=r,char_count=80,nonblank=sum(c not in (0,32) for c in raw[r*120:r*120+80]),sha256=hashlib.sha256(raw[r*120:r*120+80]).hexdigest()) for r in range(14)]


def input_cells(raw,before,data,rows=range(14)):
    chars=set(data.encode('ascii'))-{32}
    return sum(raw[r*120+c] in chars and raw[r*120+c]!=before[r*120+c] for r in rows for c in range(80))


def run_arm(rom,official,a,work,cache=None):
    if cache is None: cache={}
    commands=base_plan(a); stages=[]; before=None
    for stage in range(len(a['inputs'])+1):
        pair=capture(rom,official,commands,work); raw=pair[1]
        stable=pair[0]==pair[1]
        completed=done(raw,a)
        # 直接モードの受理腕は、固定入力後に通常の診断へ進む。
        # エラー腕はハンドラ自身が診断へ進むため、診断文字列をINPUTへ渡さない。
        if a['direct'] and stage>0 and not completed:
            commands+=['goto 1000']
            pair=capture(rom,official,commands,work); raw=pair[1]
            stable=pair[0]==pair[1]; completed=done(raw,a)
            if not completed: raise ValueError('直接モード入力後診断未完了')

        sig=signature(raw); matches=[]; candidates={}
        if (a['inputs'] and not a['id'].startswith('syntax-')) or a['id']=='line-numeric':
            programs={tag:candidate_program(rows,newline=not (stage and 'nonewline' in a['id']),completed=completed) for tag,rows in candidate_rows(a,stage).items()}
            missing=list(dict.fromkeys(tuple(cp) for cp in programs.values() if tuple(cp) not in cache))
            for start in range(0,len(missing),8):
                chunk=missing[start:start+8]
                refs=[capture_many(rom,official,chunk,work) for _ in range(2)]
                for j,key in enumerate(chunk):
                    if not refs[0][j][0]==refs[0][j][1]==refs[1][j][0]==refs[1][j][1]: raise ValueError('PRINT対照2走不一致')
                    rr=refs[0][j][0]
                    if b's9zw;' not in rr[14*120:14*120+80]: raise ValueError('PRINT候補到達印なし')
                    cache[key]=signature(rr)
            for tag,cp in programs.items():
                candidates[tag]=cache[tuple(cp)]
                if candidates[tag]==sig: matches.append(tag)

        stages.append(dict(signature=sig,matches=matches,candidates=candidates,stable=stable,completed=completed,ready=ready(pair,a),rows=row_metrics(raw),candidate_distinct=len({v['sha256'] for v in candidates.values()})==len(candidates),input_cells=0 if stage==0 else input_cells(raw,before,a['inputs'][stage-1])))
        before=raw
        if completed:
            o=dict(parse(raw,a),stages=stages,consumed=stage)
            o['screen']=screen_comparison(o,a)
            return o
        if stage==len(a['inputs']) or not ready(pair,a):
            exc=ValueError('要求/完了関門')
            exc.diagnostic=dict(arm=a['id'],failure='request-completion-gate',consumed=stage,stages=stages,
                exhausted=stage==len(a['inputs']),request_ready=ready(pair,a))
            raise exc
        # 別プロセスで前段を再現。確認した同じ予定・十分な待機の後でだけ入力する。
        commands.append(a['inputs'][stage])
    raise ValueError('完了なし')


EMPTY_SCREEN_ARMS={'number-empty','string-empty','line-empty'}


def screen_comparison(o,a):
    # 事前除外を先に適用。観測に応じて等価候補を自動削除しない。
    if a['id'] in EMPTY_SCREEN_ARMS:
        return dict(state='excluded',reason='empty-input',equivalent=[['q-space','q'],['space','none']])
    if a['id'].startswith('syntax-') or (not a['inputs'] and a['id']!='line-numeric'):
        return dict(state='excluded',reason='no-screen-plan')
    ss=o.get('stages',[])
    def unavailable(reason): return dict(state='incomparable',reason=reason)
    if not ss: return unavailable('missing-screen')
    for i,st in enumerate(ss):
        tags=set(candidate_rows(a,i))
        candidates=st.get('candidates',{})
        if set(candidates)!=tags: return unavailable('missing-candidates')
        for sig in [st.get('signature',{})]+list(candidates.values()):
            if not isinstance(sig,dict) or set(sig)!={'line_count','char_count','sha256'} or sig['line_count']!=14 or sig['char_count']!=1120 or not isinstance(sig['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',sig['sha256']):
                return unavailable('invalid-signature')
        if st.get('candidate_distinct') is not True or len({v['sha256'] for v in candidates.values()})!=len(candidates):
            return unavailable('identical-candidates')
        if st.get('matches')!=[k for k,v in candidates.items() if v==st['signature']]:
            return unavailable('invalid-matches')
        if type(st.get('input_cells')) is not int or st['input_cells']<0:
            return unavailable('missing-input-cells')
    if a['inputs'] and (o.get('consumed',0)==0 or sum(st['input_cells'] for st in ss)<1):
        return unavailable('no-input-cells')
    return dict(state='valid',reason='screen-gates-passed',matches=[st['matches'] for st in ss])


def screen_field(o,a):
    """保存欄の比較不能・欠落も採用する。有効宣言は証拠と一致した場合だけ。"""
    actual=screen_comparison(o,a)
    declared=o.get('screen')
    if not isinstance(declared,dict): return dict(state='incomparable',reason='missing-screen-field')
    if declared.get('state')=='incomparable': return dict(state='incomparable',reason=declared.get('reason','declared-incomparable'))
    if declared==actual: return actual
    return dict(state='incomparable',reason='invalid-screen-field')


def valid(o,a):
    # 従来の関門のみ。画面分類の追加関門は値印・ERR等を無効にしない。
    if not isinstance(o,dict): return False
    if not dm.valid({k:v for k,v in o.items() if k in ('arm','probes','errors','sent')},dict(a,steps=[0]*program(a)[1],speed=False)): return False
    if type(o.get('consumed')) is not int or not 0<=o['consumed']<=len(a['inputs']): return False
    ss=o.get('stages',[])
    if not isinstance(ss,list) or len(ss)!=o['consumed']+1 or o['errors']!=o['probes']['1'][1] or not 0<=o['probes']['0'][1]<=255: return False
    for i,st in enumerate(ss):
        if not isinstance(st,dict) or st.get('stable') is not True or st.get('completed')!=(i==len(ss)-1): return False
        if i<len(ss)-1 and st.get('ready') is not True: return False
    return True


def calibrated(rs):
    by={r['arm']['id']:r for r in rs}
    for aid,vals in [('cal-num',[0,0,0,-32768,32767]),('cal-error',[13,1,12])]:
        r=by.get(aid)
        if not r or not r['gate']: return False
        for o in r['obs']:
            if not valid(o,r['arm']) or [o['probes'][str(k)][1] for k in range(len(vals))]!=vals: return False
    return True


def measure(rom,official,selected,work):
    safety_selftest(work)
    # 腕は独立したプロセス/作業先。時間はエミュレーションのフレームで固定。
    from concurrent.futures import ThreadPoolExecutor
    from threading import local
    per_thread=local()
    checkpoints=work/'checkpoints'; checkpoints.mkdir(exist_ok=True)
    import hashlib
    identity=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rom_identity=None if official else {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(rom).glob('*')) if p.is_file()}
    def one(a):
        checkpoint=checkpoints/(a['id']+'.json')
        if not official and checkpoint.exists():
            saved=json.loads(checkpoint.read_text())
            r=saved.get('record',{})
            if saved.get('instrument')==identity and saved.get('rom')==rom_identity and r.get('arm')==a and r.get('gate') and len(r.get('obs',[]))==2 and all(valid(o,a) for o in r['obs']) and r['obs'][0]==r['obs'][1]:
                print('保存済み '+a['id']+': pass',flush=True)
                return r
        if not hasattr(per_thread,'cache'): per_thread.cache={}
        with tempfile.TemporaryDirectory(prefix=a['id']+'-',dir=work) as td:
            obs=[]
            for _ in range(2):
                try: obs.append(run_arm(rom,official,a,Path(td),per_thread.cache))
                except Exception as exc:
                    tb=traceback.extract_tb(exc.__traceback__)
                    obs.append(getattr(exc,'diagnostic',dict(arm=a['id'],failure=type(exc).__name__,line=tb[-1].lineno)))
            gate=all(valid(o,a) for o in obs) and obs[0]==obs[1]
            print('進捗 '+a['id']+': '+('pass' if gate else 'gate_failed'),flush=True)
            record=dict(arm=a,obs=obs,gate=gate)
            pending=checkpoint.with_suffix('.pending')
            pending.write_text(json.dumps(dict(instrument=identity,rom=rom_identity,record=record)))
            pending.replace(checkpoint)
            return record
    with ThreadPoolExecutor(max_workers=3) as pool:
        return list(pool.map(one,selected))


def emit(path,rs):
    for r in rs:
        r['gate']=r['gate'] and len(r['obs'])==2 and all(valid(o,r['arm']) for o in r['obs']) and r['obs'][0]==r['obs'][1]
    cal=calibrated(rs)
    lm.write_tsv(path,['arm','repeat','plan','observation','gate','screen_state'],[(r['arm']['id'],i+1,json.dumps(base_plan(r['arm'])+r['arm']['inputs']),json.dumps(o),'pass' if cal and r['gate'] else 'gate_failed',screen_field(o,r['arm'])['state'] if cal and r['gate'] else 'incomparable') for r in rs for i,o in enumerate(r['obs'])])
    return cal and all(r['gate'] for r in rs)


def apply_screen_column(obs,rows,a):
    # TSVの状態欄の欠落・比較不能宣言も画面欄だけに反映する。
    if any(r.get('screen_state')!=screen_field(o,a)['state'] for r,o in zip(rows,obs)):
        for o in obs: o['screen']=dict(state='incomparable',reason='missing-or-inconsistent-screen-state')


def read_passed(path):
    known={a['id']:a for a in arms()}; values={}; rs=[]
    for aid,rows in lm.read_runs(path).items():
        if aid not in known or len(rows)!=2 or {r['repeat'] for r in rows}!={'1','2'} or any(r['gate']!='pass' for r in rows): raise ValueError('2走関門')
        if any(json.loads(r['plan'])!=base_plan(known[aid])+known[aid]['inputs'] for r in rows): raise ValueError('事前操作列不一致')
        obs=[json.loads(r['observation']) for r in rows]
        if not all(valid(o,known[aid]) for o in obs) or obs[0]!=obs[1]: raise ValueError('2走不一致/形')
        apply_screen_column(obs,rows,known[aid])
        values[aid]=obs[0]; rs.append(dict(arm=known[aid],obs=obs,gate=True))
    if not calibrated(rs): raise ValueError('較正')
    return values


def expected(out,paths):
    values={}
    for p in paths:
        got=read_passed(p)
        if values.keys() & got.keys(): raise ValueError('重複腕')
        values.update(got)
    if set(values)!={a['id'] for a in arms()}: raise ValueError('全腕必要')
    lm.write_tsv(out,['arm','observation'],[(k,json.dumps(v)) for k,v in sorted(values.items())])
    return len(values)


def read_measured(path):
    # 照合では腕の欠落や測定不能も不一致として返す。期待値生成はread_passedで厳格。
    known={a['id']:a for a in arms()}; values={}; rs=[]
    for aid,rows in lm.read_runs(path).items():
        if aid not in known: continue
        try:
            if len(rows)!=2 or {r['repeat'] for r in rows}!={'1','2'} or any(r['gate']!='pass' for r in rows): continue
            if any(json.loads(r['plan'])!=base_plan(known[aid])+known[aid]['inputs'] for r in rows): continue
            obs=[json.loads(r['observation']) for r in rows]
            if not all(valid(o,known[aid]) for o in obs) or obs[0]!=obs[1]: continue
            apply_screen_column(obs,rows,known[aid])
            values[aid]=obs[0]; rs.append(dict(arm=known[aid],obs=obs,gate=True))
        except (ValueError,KeyError,TypeError): continue
    return values if calibrated(rs) else {}


def check(exp,measured):
    with exp.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
    want={r['arm']:json.loads(r['observation']) for r in rows}; known={a['id']:a for a in arms()}
    if len(rows)!=len(want) or set(want)!=set(known) or not all(valid(v,known[k]) for k,v in want.items()): raise ValueError('期待値の形')
    got=read_measured(measured)
    def matches(a,w,g):
        # 値印・ERR・誤り件数・終了印・入力回数は常に照合。
        if any(w[k]!=g[k] for k in ('probes','errors','sent','consumed')): return False
        ws=screen_field(w,a)
        if ws['state']!='valid': return True
        gs=screen_field(g,a)
        # 期待値が有効なら測定側の比較不能・欠落・対象外もNG。
        return gs['state']=='valid' and gs['matches']==ws['matches']
    bad=[k for k,v in want.items() if k not in got or not matches(known[k],v,got[k])]
    return len(want)-len(bad),bad


def synth(a):
    vals=([0,0,0,-32768,32767] if a['id']=='cal-num' else [13,1,12] if a['id']=='cal-error' else [0]*program(a)[1])
    sig=signature(bytes(3000))
    o=dict(arm=a['id'],probes={str(k):[0,v] for k,v in enumerate(vals)},errors=1 if a['id']=='cal-error' else 0,sent=1,consumed=int(bool(a['inputs'])),stages=[dict(signature=sig,candidates={},matches=[],stable=True,completed=True,ready=False,candidate_distinct=True,input_cells=0,rows=[])])
    if a['inputs']:
        o['stages'].insert(0,copy.deepcopy(o['stages'][0]))
        o['stages'][0].update(completed=False,ready=True)
        o['stages'][1]['input_cells']=1
    for i,st in enumerate(o['stages']):
        tags=candidate_rows(a,i) if a['inputs'] or a['id']=='line-numeric' else {}
        st['candidates']={tag:signature(bytes([k+1])*3000) for k,tag in enumerate(tags)}
    o['screen']=screen_comparison(o,a)
    return o



def safety_selftest(work):
    work.mkdir(parents=True,exist_ok=True)
    known=arms()
    for a in known: program(a)
    a=known[0]; o=synth(a); assert valid(o,a)
    assert not valid(dict(arm=a['id'],failure='request-completion-gate',stages=o['stages'],consumed=0,exhausted=True,request_ready=True),a)
    raw=lm.synth_text(['s9zw;'])
    raw=bytearray(raw); raw[:80]=bytes(80); raw[14*120:14*120+5]=b's9zw;'
    assert ready([raw,raw],a)
    assert not ready([raw,bytes(3000)],a)
    assert not ready([bytes(3000),bytes(3000)],a)
    sink=io.StringIO()
    with redirect_stdout(sink),redirect_stderr(sink):
        raw=lm.synth_text(['s9zp0:0,hidden-body;s9zn:0;s9zz;'])
        try: parse(raw,a)
        except ValueError: pass
        else: raise AssertionError('非整数受理')
        assert screen.compare_rows([(0,'hidden-body')],[(0,'hidden-body')])
        assert not screen.compare_rows([(0,'hidden-body')],[(0,'other-body')])
    assert 'hidden-body' not in sink.getvalue() and 'other-body' not in sink.getvalue()
    for field,value in [('sent',2),('consumed',99),('errors',-1)]:
        bad=copy.deepcopy(o); bad[field]=value; assert not valid(bad,a)
    for mode in ('missing','duplicate','noninteger','error','unstable','request',):
        bad=copy.deepcopy(o)
        if mode=='missing': bad['probes'].pop('0')
        elif mode=='duplicate': bad['probes']['99']=[0,1]
        elif mode=='noninteger': bad['probes']['0'][1]='hidden-body'
        elif mode=='error': bad['probes']['0'][0]=256
        elif mode=='unstable': bad['stages'][0]['stable']=False
        elif mode=='request': bad['stages'][0]['completed']=False
        assert not valid(bad,a)
    # 候補同一化と範囲ずらしは画面だけ比較不能にし、基本関門を保持する。
    aa=next(x for x in known if x['id']=='prompt-plain'); positive=synth(aa)
    assert valid(positive,aa) and screen_comparison(positive,aa)['state']=='valid'
    bad=copy.deepcopy(positive); st=bad['stages'][1]
    tags=list(st['candidates']); st['candidates'][tags[1]]=st['candidates'][tags[0]]
    assert valid(bad,aa) and screen_comparison(bad,aa)['state']=='incomparable'
    rr=bytearray(b' '*3000); bb=bytes(rr); rr[2*120+2]=49
    assert input_cells(rr,bb,'1')==1 and input_cells(rr,bb,'1',range(3,14))==0
    bad=copy.deepcopy(positive); bad['stages'][1]['input_cells']=input_cells(rr,bb,'1',range(3,14))
    assert valid(bad,aa) and screen_comparison(bad,aa)['state']=='incomparable'
    raw=lm.synth_text(['s9zp0:0,1;s9zp0:0,2;s9zn:0;s9zz;'])
    try: parse(raw,a)
    except ValueError: pass
    else: raise AssertionError('重複受理')
    rs=[dict(arm=x,obs=[synth(x),synth(x)],gate=True) for x in known]
    assert calibrated(rs)
    with tempfile.TemporaryDirectory(prefix='fixture-',dir=work) as td:
        td=Path(td); good=td/'good.tsv'; exp=td/'exp.tsv'; bad=td/'bad.tsv'
        assert emit(good,rs); assert expected(exp,[good])==len(known); assert check(exp,good)==(len(known),[])
        for mode in ('unequal','repeat','gate','missing','calibration'):
            broken=copy.deepcopy(rs)
            if mode=='unequal': broken[2]['obs'][0]['probes']['2'][1]+=1
            elif mode=='gate': broken[0]['gate']=False
            elif mode=='missing': broken.pop()
            elif mode=='calibration':
                for ob in broken[0]['obs']: ob['probes']['0'][1]+=1
            emit(bad,broken)
            if mode=='repeat': bad.write_text(bad.read_text().replace('\t2\t','\t1\t'))
            try: expected(td/'reject.tsv',[bad])
            except ValueError: pass
            else: raise AssertionError('壊れた入力受理')
        altered=copy.deepcopy(rs)
        for ob in altered[2]['obs']: ob['probes']['2'][1]+=1
        emit(bad,altered); assert check(exp,bad)[1]==[altered[2]['arm']['id']]
    # 永続TSVの陰性対照。画面だけを壊した測定も診断は採用されるがcheckはNG。
    controls=work/'check-controls'; controls.mkdir(exist_ok=True)
    good=controls/'good.tsv'; exp=controls/'expected.tsv'
    assert emit(good,rs); expected(exp,[good])
    for mode in ('identical-candidates','shifted-range','missing-screen','missing-arm','diagnostic-error','candidate-mismatch','declared-incomparable','missing-screen-field'):
        broken=copy.deepcopy(rs); target=broken[4]
        if mode=='missing-arm': broken.pop(4)
        else:
            for ob in target['obs']:
                if mode=='identical-candidates':
                    st=ob['stages'][1]; tags=list(st['candidates']); st['candidates'][tags[1]]=st['candidates'][tags[0]]
                    st['candidate_distinct']=False
                elif mode=='shifted-range': ob['stages'][1]['input_cells']=0
                elif mode=='missing-screen':
                    for st in ob['stages']: st.pop('candidates')
                elif mode=='diagnostic-error': ob['probes']['2'][1]+=1
                elif mode=='declared-incomparable': ob['screen']=dict(state='incomparable',reason='negative-control')
                elif mode=='missing-screen-field': ob.pop('screen')
                else:
                    st=ob['stages'][1]; st['signature']=copy.deepcopy(next(iter(st['candidates'].values())))
                    st['matches']=[next(iter(st['candidates']))]
                if mode not in ('declared-incomparable','missing-screen-field'): ob['screen']=screen_comparison(ob,target['arm'])
                assert valid(ob,target['arm'])
        negative=controls/(mode+'.tsv'); assert emit(negative,broken)
        assert check(exp,negative)==(len(known)-1,[aa['id']])
        if mode not in ('missing-arm','diagnostic-error','candidate-mismatch','declared-incomparable','missing-screen-field'):
            # 比較不能な期待値は画面を照合せず、数値欄の誤りは引き続きNG。
            unavailable=controls/(mode+'-expected.tsv'); expected(unavailable,[negative])
            assert check(unavailable,good)==(len(known),[])
            numeric=copy.deepcopy(broken)
            for ob in numeric[4]['obs']: ob['probes']['2'][1]+=1
            changed=controls/(mode+'-numeric.tsv'); assert emit(changed,numeric)
            assert check(unavailable,changed)==(len(known)-1,[aa['id']])
    for mode in ('declared-screen-column','missing-screen-column'):
        with good.open() as f: rr=list(csv.DictReader(f,delimiter='\t'))
        fields=list(rr[0])
        if mode=='missing-screen-column': fields.remove('screen_state')
        else:
            for row in rr:
                if row['arm']==aa['id']: row['screen_state']='incomparable'
        bad=controls/(mode+'.tsv')
        lm.write_tsv(bad,fields,[[row[k] for k in fields] for row in rr])
        result=check(exp,bad)
        assert result==(len(known)-1,[aa['id']]) if mode=='declared-screen-column' else result[0]<len(known)
    # 自己検査内でもCLIの終了コードを確認（出力は捕捉）。
    cli=subprocess.run([sys.executable,str(Path(__file__).resolve()),'check','--expected',str(exp),'--measured',str(controls/'shifted-range.tsv')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert cli.returncode!=0
    (controls/'shifted-range-cli.log').write_bytes(cli.stdout+cli.stderr)
    for aid in EMPTY_SCREEN_ARMS:
        ob=synth(next(x for x in known if x['id']==aid))
        assert screen_comparison(ob,next(x for x in known if x['id']==aid))['state']=='excluded'
    from unittest.mock import patch
    # 固定入力列枯渇は安定要求でも拒否。本文は外へ出さない。
    control=arm('syntax-control','input',inputs=[])
    rr=bytearray(3000); rr[14*120:14*120+5]=b's9zw;'
    with patch.dict(run_arm.__globals__,capture=lambda *args:[rr,rr]):
        try: run_arm(Path('synthetic'),False,control,work)
        except ValueError as exc:
            assert exc.diagnostic['exhausted'] and exc.diagnostic['request_ready']
            assert not valid(exc.diagnostic,control)
        else: raise AssertionError('入力列枯渇を受理')
    rr[15*120:15*120+5]=b's9zz;'
    with patch.dict(run_arm.__globals__,capture=lambda *args:[rr,rr]):
        try: run_arm(Path('synthetic'),False,control,work)
        except ValueError: pass
        else: raise AssertionError('値印なし完了を受理')
    with tempfile.TemporaryDirectory(prefix='capture-fixture-',dir=work) as td:
        td=Path(td)
        def fake(argv,**kwargs):
            for i,arg in enumerate(argv):
                if arg=='--vram-dump':
                    dest=Path(argv[i+1]); t=int(argv[i+3])
                    dest=dest.with_name(dest.stem+f'.f{t:06d}'+dest.suffix)
                    dest.write_bytes(bytes(3000))
            return subprocess.CompletedProcess(argv,0,b'hidden-body',b'hidden-body')
        sink=io.StringIO()
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=fake),redirect_stdout(sink),redirect_stderr(sink):
            pair=capture(Path('synthetic'),False,['new'],td)
        assert pair==[bytes(3000),bytes(3000)] and not sink.getvalue() and not list(td.iterdir())
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=fake):
            assert capture_many(Path('synthetic'),False,[['new']]*8,td)==[[bytes(3000),bytes(3000)]]*8
        assert not list(td.iterdir())
        def broken(argv,**kwargs): return subprocess.CompletedProcess(argv,1,b'hidden-body',b'hidden-body')
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=broken),redirect_stdout(sink),redirect_stderr(sink):
            try: capture(Path('synthetic'),False,['new'],td)
            except RuntimeError as exc: assert 'hidden-body' not in str(exc)
            else: raise AssertionError('実行失敗受理')
        assert not sink.getvalue() and not list(td.iterdir())
    print('OK 自己検査: 画面限定関門・候補同一化/範囲ずらし/欠落のNG・対象外・診断保持・本文漏洩・較正・2走',flush=True)


def selftest(work):
    safety_selftest(work)
    rom=work/'rom'
    p=subprocess.run([sys.executable,str(kw.REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: raise RuntimeError('自作ビルド拒否/失敗')
    rs=measure(rom,False,arms(),work)
    passed=emit(work/'selfrun.tsv',rs)
    summary=['# l4-s9z 自作ROM試走（追加修正その2）',
    '2026-10-13。公式ROM未実行。src変更・commit・run_all実行なし。全75腕×2走を新規実行。',
    f'従来関門通過 {sum(r["gate"] for r in rs)}/75、較正 {int(calibrated(rs))}。保存: repair2-rerun/selfrun.tsv。',
    '候補の独立起動・2走各2時点一致・到達印を維持。新しい候補署名の相異・入力文字セル関門は画面比較だけに適用。値印・ERR・誤り件数・終了印・入力回数は従来関門通過時に有効。',
    '空入力3腕は事前登録で画面比較対象外。区別できない組はq-space/q、space/none。カーソルは使用しない。候補ゼロ一致は有効な分類の候補外（不明）で、比較不能と区別。',
    '自己検査: 期待値の有効な画面を測定側で比較不能・欠落にしたTSVはNG。期待値の比較不能・対象外の画面は照合しないが、数値診断は照合。生VRAMとプロセス画面本文は保存・出力しない。',
    '', '| 腕 | 従来関門（2走） | 画面比較（第1走 / 第2走） | 各段の一致候補（第1走 / 第2走） | 画面の理由 | ERR / 誤り件数 / 入力回数 |', '|---|---|---|---|---|---|']
    states={'valid':'有効','incomparable':'比較不能','excluded':'対象外'}
    for r in rs:
        comparisons=[screen_field(o,r['arm']) for o in r['obs']]
        lists=[[st.get('matches',[]) for st in o.get('stages',[])] for o in r['obs']]
        diag=[[o.get('probes',{}).get('0',[None,None])[1],o.get('errors'),o.get('consumed')] for o in r['obs']]
        summary.append('| '+r['arm']['id']+' | '+('pass' if r['gate'] and calibrated(rs) else 'gate_failed')+' | '+' / '.join(states[c['state']] for c in comparisons)+' | '+json.dumps(lists)+' | '+' / '.join(c['reason'] for c in comparisons)+' | '+json.dumps(diag)+' |')
    ((work if any(work.resolve().is_relative_to(r.resolve()) for r in (kw.REPO/'tmp/t1-impl-work', kw.REPO/'tmp/t2-impl-work')) else ROOT)/'selfrun.md').write_text('\n'.join(summary)+'\n')
    print(f'自作ROM {len(rs)}腕×2走: '+('pass' if passed else 'gate_failed'))
    return int(not passed)


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('measure'); m.add_argument('--official',action='store_true'); m.add_argument('--rom-dir',type=Path); m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True); m.add_argument('--only',default='')
    s=sub.add_parser('selftest'); s.add_argument('--work-dir',type=Path,required=True)
    sub.add_parser('describe')
    e=sub.add_parser('expected'); e.add_argument('--out',type=Path,required=True); e.add_argument('paths',type=Path,nargs='+')
    c=sub.add_parser('check'); c.add_argument('--expected',type=Path,required=True); c.add_argument('--measured',type=Path,required=True)
    args=p.parse_args()
    if hasattr(args,'work_dir'):
        if not allowed_path(args.work_dir, (ROOT,IMPL_ROOT,kw.REPO/'tmp/t1-impl-work',kw.REPO/'tmp/t2-impl-work')): p.error('作業先はtmp/s9z-work、tmp/s9z-impl-workまたはtmp/t1-impl-workまたはtmp/t2-impl-work内の絶対パス必須')
        args.work_dir.mkdir(parents=True,exist_ok=True)
    if args.command=='describe':
        for a in arms(): print('- `'+a['id']+'`: `'+a['stmt']+'` 入力='+json.dumps(a['inputs'])+' 予測='+a['prediction'])
        return 0
    if args.command=='selftest': return selftest(args.work_dir)
    if args.command=='expected': print(f'期待値 {expected(args.out,args.paths)}腕'); return 0
    if args.command=='check':
        ok,bad=check(args.expected,args.measured); print(f'一致 {ok}腕 / 不一致 {len(bad)}腕'); return int(bool(bad))
    rom=os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom: p.error('公式PC88_REF_ROM_DIR／自作--rom-dirが必要')
    prefixes=tuple(filter(None,args.only.split(',')))
    selected=[a for a in arms() if not prefixes or a['id'].startswith(prefixes) or a['id'].startswith('cal-')]
    rs=measure(rom,args.official,selected,args.work_dir); return int(not emit(args.out,rs))


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as e:
        tb=traceback.extract_tb(e.__traceback__)
        print(f'NG 器具 ({type(e).__name__}, 行{tb[-1].lineno}、画面本文非出力)')
        raise SystemExit(1)
