#!/usr/bin/env python3
"""l4-s9x GET@/PUT@測定。事前登録: docs/notes/l4-s9x-getput-preregistration.md。
画面本文は出力しない。自作の図形・成功GETの整数配列・誤り/LP・利用者の計時印だけを採る。
@はマニュアルで省略可。公式ROMの直接読み出し、PEEK、漢字PUTを使わない。
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))
import l4_line_measure as lm
import l4_circle_measure as cm
import l4_listkw_measure as kw
import l4_widthvram_measure as wv
import l4_crtcpix_measure as cp
import l4_gfx_measure as g

WORK = kw.REPO / 'tmp/s9x-work'
SENT = b's9xz;'
MARK_ADDR, MARK_HEX = cm.MARK_ADDR, cm.MARK_HEX


def pattern(w, h, mono=False, dest=False):
    return [[int(c != 0) if mono else c for c in
             [((7-u+v) if dest else (u+3*v)) % 8 for u in range(w)]] for v in range(h)]


def pack_hypothesis(rows, mono=False):
    """事前登録の弱い仮説だけ。公式を見て調整しない。"""
    w, h = len(rows[0]), len(rows)
    m = 1 if mono else 3
    out = bytearray((w*m).to_bytes(2, 'little') + h.to_bytes(2, 'little'))
    for row in rows:
        for plane in range(m):
            for x in range(0, w, 8):
                out.append(sum(((row[u] >> plane) & 1) << (7-(u-x)) for u in range(x, min(w, x+8))))
    if len(out) % 2:
        out.append(0)
    return [int.from_bytes(out[i:i+2], 'little', signed=True) for i in range(0, len(out), 2)]


def put_value(s, d, op, mono=False):
    mask = 1 if mono else 7
    return {'pset': s, 'preset': s ^ mask, 'or': s | d, 'and': s & d,
            'xor': s ^ d, 'default': s ^ d}[op]


def draw(rows, xy, plane=0, mono=False):
    return {(xy[0]+u, xy[1]+v): c << plane if mono else c
            for v, row in enumerate(rows) for u, c in enumerate(row) if c}


def drawing(w, h, xy=(10, 10), mono=False, dest=False):
    # ループで作ることで打鍵時間と行数を一定程度に抑える。
    expr = '(7-u+v)' if dest else '(u+3*v)'
    return [f'for v=0 to {h-1}', f'for u=0 to {w-1}', f'c={expr} mod 8',
            f'pset({xy[0]}+u,{xy[1]}+v),c', 'next u', 'next v']


def arm(aid, before=None, ops=None, dims='dim a%(255)', dump=0, offset=0,
        mono=False, plane=0, speed=False, pixels=None, preds=None, array=None):
    return dict(id=aid, before=before or [], ops=ops or [], dims=dims, dump=dump,
                offset=offset, mono=mono, plane=plane, speed=speed, pixels=pixels,
                preds=preds or {}, array=array, wait=12000 if speed else 0,
                pix=[(401, 150)] if aid == 'cal-vis' else [])


def capture_arm(aid, w, h, mono=False, plane=0, xy=(10, 10), offset=0,
                extra=None, get=None, pixels=None, preds=None):
    rows = pattern(w, h, mono)
    words = math.ceil((4+math.ceil(w/8)*h*(1 if mono else 3))/2)
    ops = [get or f'get({xy[0]},{xy[1]})-({xy[0]+w-1},{xy[1]+h-1}),a%'+(f'({offset})' if offset else '')]
    ops += extra or []
    values = [0]*offset + pack_hypothesis(rows, mono) + [0]
    return arm(aid, drawing(w, h, xy, mono), ops, dump=offset+words+1, offset=offset,
               mono=mono, plane=plane, pixels=draw(rows, xy, plane, mono) if pixels is None else pixels,
               preds=preds or {'0': [0, xy[0]+w-1, xy[1]+h-1]}, array=values)


def arms():
    out = [arm('base-cls3', pixels={}), arm('cal-vis', ['pset(401,150),7'], pixels={(401,150):7}),
           arm('cal-num', ['a%(0)=0', 'a%(1)=32767', 'a%(2)=-32768', 'a%(3)=-1'],
               dump=4, pixels={}, array=[0,32767,-32768,-1])]
    for mono in (False, True):
        for w in (1,7,8,9,15,16,17):
            for h in (1,3):
                out.append(capture_arm(f'fmt-{"m" if mono else "c"}-{w}-{h}', w, h, mono))
    for x in (0,3,7):
        out.append(capture_arm(f'align-{x}', 9, 3, xy=(x,10)))
    for aid, mono, plane, offset in [('offset-3',False,0,3), ('mono-page-1',True,1,0), ('mono-page-2',True,2,0)]:
        px = {**draw(pattern(9,3,mono),(10,10),plane,mono), **draw(pattern(9,3,mono),(40,30),plane,mono)}
        out.append(capture_arm(aid,9,3,mono,plane,offset=offset,
                    extra=[f'put(40,30),a%'+(f'({offset})' if offset else '')+',pset'],
                    pixels=px, preds={'0':[0,18,12],'1':[0,40,30]}))
    for suffix, size, tag in [('%',2,'int'), ('!',4,'single'), ('#',8,'double')]:
        for k, upper in [('minus',math.ceil(22/size)-2), ('exact',math.ceil(22/size)-1), ('safe',22//size+1)]:
            px = draw(pattern(9,3),(10,10))
            if k != 'minus': px.update(draw(pattern(9,3),(40,30)))
            out.append(arm(f'cap-{tag}-{k}', drawing(9,3), [f'get(10,10)-(18,12),a{suffix}',f'put(40,30),a{suffix},pset'],
                           dims=f'dim a{suffix}({upper})', pixels=None if k == 'minus' else px,
                           preds={'0':[5,None,None]} if k == 'minus' else {'0':[0,18,12],'1':[0,40,30]}))
    for mono in (False,True):
        for op in ('pset','preset','or','and','xor','default'):
            s, d = pattern(8,3,mono), pattern(8,3,mono,True)
            pasted = [[put_value(s[v][u], d[v][u], op, mono) for u in range(8)] for v in range(3)]
            out.append(arm(f'put-{"m" if mono else "c"}-{op}', drawing(8,3),
                ['get(10,10)-(17,12),a%', *drawing(8,3,(40,30),mono,True),
                 'put(40,30),a%'+('' if op == 'default' else ','+op)], mono=mono,
                pixels={**draw(s,(10,10),mono=mono), **draw(pasted,(40,30),mono=mono)},
                preds={'0':[0,17,12],'1':[0,40,30]}))
    out.append(arm('put-twice',drawing(8,3), ['get(10,10)-(17,12),a%',
        *drawing(8,3,(40,30),dest=True), 'put(40,30),a%', 'put(40,30),a%'],
        pixels={**draw(pattern(8,3),(10,10)), **draw(pattern(8,3,dest=True),(40,30))},
        preds={'0':[0,17,12],'1':[0,40,30],'2':[0,40,30]}))
    out.append(arm('mono-color',drawing(8,3), ['get(10,10)-(17,12),a%',
        'screen 0,0','cls 3','put(40,30),a%,pset,5,2'], mono=True,
        pixels=draw([[5 if c else 2 for c in row] for row in pattern(8,3,True)],(40,30)),
        preds={'0':[0,17,12],'1':[0,40,30]}))
    for tag,x,y in [('left',-1,10),('right',633,10),('top',10,-1),('bottom',10,198),('out',640,200)]:
        for put in (False,True):
            ops = ['get(10,10)-(17,12),a%'] if put else []
            ops.append(f'put({x},{y}),a%,pset' if put else f'get({x},{y})-({x+7},{y+2}),a%')
            out.append(arm(f'{"put" if put else "get"}-edge-{tag}',drawing(8,3),ops,
                pixels=draw(pattern(8,3),(10,10)), preds={str(int(put)):[5,None,None]}))
    out.append(capture_arm('get-corner',8,3,xy=(632,197)))
    out.append(arm('put-corner',drawing(8,3),['get(10,10)-(17,12),a%','put(632,197),a%,pset'],
        pixels={**draw(pattern(8,3),(10,10)),**draw(pattern(8,3),(632,197))},preds={'0':[0,17,12],'1':[0,632,197]}))
    out.append(capture_arm('get-reverse',9,3,get='get(18,12)-(10,10),a%',preds={'0':[0,None,None]}))
    out.append(capture_arm('get-step',9,3,get='get(10,10)-step(8,2),a%'))
    for tag, stmt, error, dims in [
        ('get-first-step','get step(10,10)-(17,12),a%',2,None),
        ('put-step','put step(40,30),a%,pset',2,None),
        ('string-array','get(10,10)-(17,12),b$',None,'dim a%(255),b$(255)'),
        ('two-dim','get(10,10)-(17,12),b%',None,'dim a%(255),b%(10,10)'),
        ('missing-array','get(10,10)-(17,12)',2,None),
        ('bad-op','put(40,30),a%,zzz',2,None),
        ('overflow','get(32768,10)-(17,12),a%',6,None),
        ('type','get("x",10)-(17,12),a%',13,None),
        ('color-one','put(40,30),a%,pset,5',None,None),
        ('color-range','put(40,30),a%,pset,8,0',None,None),
        ('color-type','put(40,30),a%,pset,"x",0',None,None)]:
        ops = (['get(10,10)-(17,12),a%'] if stmt.startswith('put') else [])+[stmt]
        out.append(arm('syntax-'+tag,drawing(8,3),ops,dims=dims or 'dim a%(255)',
                       preds={str(len(ops)-1):[error,None,None]} if error is not None else {}))
    for tag in ('nop','get','put'):
        out.append(arm('sp-'+tag,drawing(32,32)+['get(10,10)-(41,41),a%'] if tag=='put' else drawing(32,32),
                       ['get(10,10)-(41,41),a%'] if tag=='get' else ['put(100,100),a%,pset'] if tag=='put' else [],
                       speed=True))
    return out


def program_lines(a):
    lines = {5:'clear ,49151',6:'on error goto 9000',7:'cls',8:a['dims'],9:'e=0:g=0:n=0'}
    statements = [f'screen '+(f'1,0,{a["plane"]},7' if a['mono'] else '0,0'),'cls 3'] + a['before']
    number = 20
    def add(stmt):
        nonlocal number
        lines[number] = stmt; number += 10
    for stmt in statements: add(stmt)
    probe = 0
    if a['speed']:
        add('e=0:n=0')
        add(f'poke {MARK_ADDR},1'); add('for i=1 to 100')
        for stmt in a['ops']: add(stmt)
        add('next i'); add(f'poke {MARK_ADDR},2')
        add('x=point(0):y=point(1)')
        add('print "s9xr0:";e;",";x;",";y;";";')
        add('print "s9xn0:";n;";";')
    else:
        for stmt in a['ops']:
            if stmt.startswith(('get','put')):
                add('e=0:'+stmt); add('g=e:x=point(0):y=point(1)')
                add(f'print "s9xr{probe}:";g;",";x;",";y;";";')
                # GET成功直後だけ配列値を出す。PUTなどの後から覗かない。
                if stmt.startswith('get') and a['dump']:
                    add(f'if g=0 then gosub 8000')
                probe += 1
            else: add(stmt)
        if a['id']=='cal-num': add('gosub 8000')
    add('print "s9xz;";'); add(f'goto {number}')
    lines[9000]='e=err:n=n+1:resume next'
    if a['dump']:
        lines[8000]=f'for j=0 to {a["dump"]-1}'
        lines[8010]='print "s9xa";j;":";a%(j);";";'
        lines[8020]='next j:return'
    assert all(len(f'{k} {s}')<80 and s.isascii() and s==s.lower() and '@' not in s for k,s in lines.items())
    assert number<8000
    return lines


def plan(a):
    return ['new']+[f'{n} {s}' for n,s in sorted(program_lines(a).items())]+['cls',('window',),'run',('capture','all')]


def parse_results(vram):
    if len(vram)!=3000: raise ValueError('画面写し長さ')
    joined=b''.join(vram[r*120:r*120+80] for r in range(25))
    result={'res':{},'array':{},'counts':{},'sent':joined.count(SENT)}
    # 任意の文字列へ復号しない。自作ラベルと整数だけを許可。
    matches=list(re.finditer(rb's9x([ran])\s*(\d+)\s*:([^;]*);',joined))
    for match in matches:
        kind=match[1].decode('ascii'); key=str(int(match[2]))
        field={'r':'res','a':'array','n':'counts'}[kind]
        if key in result[field]: raise ValueError('重複した数値プローブ')
        parts=match[3].split(b',')
        if len(parts)!=(3 if kind=='r' else 1) or any(not re.fullmatch(rb'\s*-?\d+\s*',p) for p in parts):
            raise ValueError('整数以外の結果')
        vals=[int(p) for p in parts]
        result[field][key]=vals if kind=='r' else vals[0]
    # 閉じていないラベルも不正として拒否する。
    if len(re.findall(rb's9x[ran]\s*\d+\s*:',joined))!=len(matches): raise ValueError('未完了プローブ')
    return result


def analyze(a, gv, vram, ppm=None, memlog=None):
    px,tail,_=lm.decode_all(gv)
    obs=dict(arm=a['id'],n=len(px),hash=lm.pix_hash(px),tail=tail,spans=lm.to_spans(px),**parse_results(vram))
    if a['pix']: obs['pix']=g.pix_stat(ppm,a['pix'])
    if a['speed']: obs['marks']=marks_summary(memlog or '')
    return obs


def marks_summary(text):
    marks=cm.parse_marks(text)
    return dict(cm.marks_summary(marks), ordered=[value for _,value in marks if value in (1,2)]==[1,2])


def run_arm(rom, official, a, work):
    args=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom)]
    at=700 if official else 100
    if official: args+=['--type-at','300','--type','\n']
    window=None
    for step in plan(a):
        if isinstance(step,str):
            args+=['--type-at',str(at),'--type',step+'\n']
            at+=(len(step)+1)*8+240+(wv.RUN_WAIT+a['wait'] if step=='run' else 0)
        elif step[0]=='window': window=at
    cap=at+200
    vd,gd,ppm,ml=[work/name for name in ('text.bin','graphics.bin','shot.ppm','marks.txt')]
    args+=['--vram-dump',str(vd),'--vram-dump-at',str(cap),'--gvram-dump',str(gd),'--gvram-dump-at',str(cap),'--frames',str(cap+100)]
    if a['pix']: args+=['--screenshot',str(ppm)]
    if a['speed']: args+=['--mem-write-log',str(ml),'--mem-write-range',f'{MARK_HEX}-{MARK_HEX}','--mem-write-from-frame',str(window)]
    try:
        proc=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower(): raise RuntimeError('ハーネス実行/打鍵失敗')
        return analyze(a,gd.read_bytes(),vd.read_bytes(),cp.read_ppm(ppm) if a['pix'] else None,
                       ml.read_text() if a['speed'] else None)
    finally:
        for path in (vd,gd,ppm,ml):
            path.unlink(missing_ok=True); Path(str(path)+'.info.txt').unlink(missing_ok=True)


def n_probes(a):
    return 1 if a['speed'] else sum(s.startswith(('get','put')) for s in a['ops'])


def valid(o,a):
    if not o or o.get('arm')!=a['id'] or o.get('sent')!=1 or o.get('tail')!=0: return False
    if set(o['res'])!={str(i) for i in range(n_probes(a))}: return False
    px=lm.from_spans(o['spans'])
    if o['n']!=len(px) or o['hash']!=lm.pix_hash(px): return False
    if any(not isinstance(v,int) or not -32768<=v<=32767 for v in o['array'].values()): return False
    need=a['dump'] if a['id']=='cal-num' or (a['dump'] and o['res'].get('0',[1])[0]==0) else 0
    if set(o['array'])!={str(i) for i in range(need)}: return False
    if a['speed']:
        m=o.get('marks',{})
        if not (m.get('n1')==m.get('n2')==1 and m.get('frames') is not None and m['frames']>=0 and m.get('ordered') is True and set(o['counts'])=={'0'}): return False
    elif o['counts']: return False
    return True


def measure(rom,official,selected,work):
    work.mkdir(parents=True,exist_ok=True)
    records=[]
    with tempfile.TemporaryDirectory(prefix='measure-',dir=work) as tmp:
        for a in selected:
            obs=[]; failed=[]
            for repeat in range(2):
                try: obs.append(run_arm(rom,official,a,Path(tmp))); failed.append(False)
                except Exception: obs.append({}); failed.append(True)
            records.append(dict(arm=a,obs=obs,failed=failed,gate=not any(failed) and all(valid(o,a) for o in obs) and obs[0]==obs[1]))
            print(f'進捗 {a["id"]}: '+('pass' if records[-1]['gate'] else 'gate_failed'),flush=True)
    return records


def calibrated(records):
    by={r['arm']['id']:r for r in records}
    for aid in ('base-cls3','cal-vis','cal-num'):
        r=by.get(aid)
        if not r or not r['gate']: return False
        a=r['arm']
        for o in r['obs']:
            if not valid(o,a) or lm.from_spans(o['spans'])!=a['pixels']: return False
            if aid=='cal-num' and [o['array'][str(i)] for i in range(4)]!=a['array']: return False
            if aid=='cal-vis':
                p=o.get('pix') or []
                if len(p)!=1 or p[0]['at']!=[401,150] or p[0]['dot']!=['ffffff','ffffff'] or any(c!='000000' for c in p[0]['ref']): return False
    return True


def judge(o,a):
    if not o: return {}
    result={}
    def put(k,got,want): result[k]='agree' if got==want else 'differ'
    if a['pixels'] is not None: put('pixels',lm.from_spans(o['spans']),a['pixels'])
    for key,vals in a['preds'].items():
        got=o['res'].get(key)
        for i,want in enumerate(vals):
            if want is not None: put('p'+key+('_e','_x','_y')[i],None if got is None else got[i],want)
    if a['array'] is not None and o['array']:
        put('array',o['array'],{str(i):v for i,v in enumerate(a['array'])})
    return result


def emit(path,records,strict=True):
    cal=calibrated(records) if strict else True
    lm.write_tsv(path,['arm','repeat','plan','observation','gate','prediction_judgement','failed'],
        [(r['arm']['id'],i+1,json.dumps(plan(r['arm'])),json.dumps(o),
          'pass' if cal and r['gate'] else 'gate_failed',json.dumps(judge(o,r['arm'])),int(r['failed'][i]))
         for r in records for i,o in enumerate(r['obs'])])
    return cal and all(r['gate'] for r in records)


def comparable(o):
    return {k:o.get(k) for k in ('n','hash','tail','spans','res','array','counts','pix')}


def expected(out,paths):
    values={}
    for path in paths:
        for aid,rs in lm.read_runs(path).items():
            if len(rs)!=2 or any(r['gate']!='pass' for r in rs): raise ValueError('期待値生成の関門')
            obs=[comparable(json.loads(r['observation'])) for r in rs]
            if obs[0]!=obs[1] or values.get(aid,obs[0])!=obs[0]: raise ValueError('2走/ファイル間不一致')
            values[aid]=obs[0]
    lm.write_tsv(out,['arm','observation'],[(k,json.dumps(v)) for k,v in sorted(values.items())])
    return len(values)


def check(exp,measured,only=None):
    with exp.open(newline='') as f: want={r['arm']:json.loads(r['observation']) for r in csv.DictReader(f,delimiter='\t')}
    runs=lm.read_runs(measured); ok=[]; bad={}
    for aid,w in want.items():
        if only and not aid.startswith(tuple(only)): continue
        rs=runs.get(aid,[])
        if len(rs)!=2 or any(r['gate']!='pass' for r in rs): bad[aid]=['測定欠落/関門落ち']; continue
        obs=[comparable(json.loads(r['observation'])) for r in rs]
        if obs[0]!=obs[1]: bad[aid]=['2走不一致']; continue
        d=[k for k in w if w[k]!=obs[0].get(k)]
        if d: bad[aid]=d
        else: ok.append(aid)
    if only and not ok and not bad: raise ValueError('照合対象の腕がない')
    return ok,bad


def describe():
    return '\n'.join(f'- `{a["id"]}`: '+ ' / '.join([a['dims']]+a['before']+a['ops']) for a in arms())


def selftest(work):
    work.mkdir(parents=True,exist_ok=True)
    known={a['id']:a for a in arms()}
    assert len(known)==len(arms())
    for a in arms(): program_lines(a)
    assert pack_hypothesis([[0,1,2,3,4,5,6,7]])==[24,1,13141,15]
    assert pack_hypothesis([[1,0,0,0,0,0,0,0,1]],True)==[9,1,-32640]
    assert [put_value(3,6,o) for o in ('pset','preset','or','and','xor','default')]==[3,4,7,2,5,5]
    assert [put_value(1,0,o,True) for o in ('pset','preset','or','and','xor')]==[1,0,1,0,1]
    def text(s): return lm.synth_text([s])
    parsed=parse_results(text('s9xr0: 5,10,20;s9xa0:-32768;s9xz;'))
    assert parsed['res']=={'0':[5,10,20]} and parsed['array']=={'0':-32768} and parsed['sent']==1
    secret='private-screen-body'
    for s in ('s9xr0:5,10,'+secret+';s9xz;','s9xa0:1;s9xa0:2;s9xz;','s9xr0:5,10,20s9xz;'):
        try: parse_results(text(s))
        except ValueError as e: assert secret not in str(e)
        else: raise AssertionError('数値限定/重複/未完了の陰性失敗')
    def synth(a):
        avalues={str(i):v for i,v in enumerate(a['array'] or [])}
        px=a['pixels'] or {}
        return dict(arm=a['id'],n=len(px),hash=lm.pix_hash(px),tail=0,spans=lm.to_spans(px),res={},array=avalues,counts={},sent=1,
                    **({'pix':[dict(at=[401,150],dot=['ffffff']*2,ref=['000000']*2)]} if a['pix'] else {}))
    def record(a,o): return dict(arm=a,obs=[o,o],failed=[False,False],gate=valid(o,a))
    for aid in ('fmt-c-9-3','fmt-m-17-3','offset-3'):
        a=known[aid]
        labels=['s9xr'+key+':'+','.join(map(str,values))+';' for key,values in a['preds'].items()]
        labels+=['s9xa'+str(i)+':'+str(v)+';' for i,v in enumerate(a['array'])]+['s9xz;']
        chunks=[]; line=''
        for label in labels:
            if len(line+label)>80: chunks.append(line); line=''
            line+=label
        chunks.append(line)
        o=analyze(a,lm.synth_gv(a['pixels']),lm.synth_text(chunks))
        assert valid(o,a) and all(v=='agree' for v in judge(o,a).values())
        bad=dict(o,array=dict(o['array'])); bad['array']['0']+=1
        assert judge(bad,a)['array']=='differ'
        bad=dict(o,array=dict(o['array'])); bad['array'].pop('0')
        assert not valid(bad,a)
    cal=[record(known[k],synth(known[k])) for k in ('base-cls3','cal-vis','cal-num')]
    assert calibrated(cal)
    for key in ('n','spans','pix'):
        altered=json.loads(json.dumps(cal[1]['obs'][0]))
        if key=='n':
            # n/hash/span相互整合は解析器で保証する。較正では実画素の欠落を注入。
            altered['spans']=[]; altered['n']=0
        elif key=='spans': altered['spans']=[[150,400,400,7]]
        else: altered['pix'][0]['dot']=['000000']*2
        assert not calibrated([cal[0],record(known['cal-vis'],altered),cal[2]])
    assert not calibrated(cal[:2])
    ao=dict(cal[2]['obs'][0],array={'0':0,'1':32767,'2':32768,'3':-1})
    assert not calibrated([*cal[:2],record(known['cal-num'],ao)])
    assert not valid(dict(cal[2]['obs'][0],sent=0),known['cal-num'])
    assert not valid(dict(cal[0]['obs'][0],tail=1),known['base-cls3'])
    sp=known['sp-nop']; so=dict(synth(sp),res={'0':[0,0,0]},counts={'0':0},marks=dict(n1=1,n2=1,frames=3,ordered=True))
    assert valid(so,sp)
    for marks in (dict(n1=0,n2=1,frames=None),dict(n1=2,n2=1,frames=3),dict(n1=1,n2=1,frames=-1,ordered=True),dict(n1=1,n2=1,frames=0,ordered=False)):
        assert not valid(dict(so,marks=marks),sp)
    assert not valid(dict(so,counts={}),sp)
    assert marks_summary(' 1 590 0A12 FF80 01\n 2 640 0A20 FF80 02')==dict(n1=1,n2=1,frames=50,ordered=True)
    assert not marks_summary(' 1 590 0A12 FF80 02\n 2 590 0A20 FF80 01')['ordered']
    assert marks_summary(' 1 580 0A10 FF80 00\n 2 590 0A12 FF80 01\n 3 640 0A20 FF80 02')['ordered']
    with tempfile.TemporaryDirectory(prefix='numeric-check-',dir=work) as tmp:
        tmp=Path(tmp); good=tmp/'good.tsv'; exp=tmp/'expected.tsv'; bad=tmp/'bad.tsv'
        assert emit(good,cal)
        assert expected(exp,[good])==3
        assert check(exp,good)==(['base-cls3','cal-num','cal-vis'],{})
        for victim,key,value in [('cal-vis','spans',[[150,400,400,7]]),('cal-num','array',{'0':2,'1':32767,'2':-32768,'3':-1}),('cal-num','res',{'0':[2,0,0]})]:
            rs=[]
            for r in cal:
                o=json.loads(json.dumps(r['obs'][0]));
                if r['arm']['id']==victim: o[key]=value
                rs.append(dict(r,obs=[o,o]))
            emit(bad,rs,strict=False)
            assert victim in check(exp,bad)[1]
        emit(bad,cal[:2],strict=False); assert 'cal-num' in check(exp,bad)[1]
        unequal=[*cal[:2],dict(cal[2],obs=[cal[2]['obs'][0],ao])]
        emit(bad,unequal,strict=False); assert 'cal-num' in check(exp,bad)[1]
        try: expected(tmp/'reject.tsv',[bad])
        except ValueError: pass
        else: raise AssertionError('不一致期待値を受理')
    print('OK 手計算の配列・5演算・数値限定抽出・較正/計時/期待値/check陰性対照',flush=True)
    with tempfile.TemporaryDirectory(prefix='own-rom-',dir=work) as tmp:
        tmp=Path(tmp); rom=tmp/'rom'
        build=subprocess.run([sys.executable,str(kw.REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(tmp/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert build.returncode==0,'自作ROMビルド失敗'
        selected=[known[k] for k in ('base-cls3','cal-vis','cal-num','fmt-c-9-3','put-c-pset','sp-nop','sp-get','sp-put')]
        records=measure(rom,False,selected,tmp)
        assert all(r['gate'] for r in records),'自作ROM器具の関門'
        assert calibrated(records),'自作ROM較正'
        by={r['arm']['id']:r['obs'][0] for r in records}
        assert by['fmt-c-9-3']['res']['0'][0]==2 and not by['fmt-c-9-3']['array']
        assert [v[0] for v in by['put-c-pset']['res'].values()]==[2,2]
        assert by['sp-nop']['counts']['0']==0
        assert all(by[k]['counts']['0']==100 and by[k]['res']['0'][0]==2 for k in ('sp-get','sp-put'))
        emit(work/'selftest_own.tsv',records)
        os.environ['Q88MEASURE_FAULT_CORRUPT_GVRAM_DUMP']='1'
        try: faulty=run_arm(rom,False,known['base-cls3'],tmp)
        finally: del os.environ['Q88MEASURE_FAULT_CORRUPT_GVRAM_DUMP']
        assert faulty['n']==1 and judge(faulty,known['base-cls3'])['pixels']=='differ'
        assert not list(tmp.glob('*.bin')) and not list(tmp.glob('shot.ppm')) and not list(tmp.glob('marks.txt'))
    print('OK 自作ROM8腕×2走・未実装ERR2・100回エラー対照・VRAM故障注入・生写し消去',flush=True)
    return 0


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('measure'); m.add_argument('--rom-dir',type=Path); m.add_argument('--official',action='store_true')
    m.add_argument('--out',type=Path,required=True); m.add_argument('--work-dir',type=Path,required=True)
    m.add_argument('--only',default=''); m.add_argument('--no-calibration',action='store_true')
    s=sub.add_parser('selftest'); s.add_argument('--work-dir',type=Path,required=True)
    sub.add_parser('describe')
    for name in ('report','speed','tally'):
        r=sub.add_parser(name); r.add_argument('--measured',type=Path,required=True)
    e=sub.add_parser('expected'); e.add_argument('--out',type=Path,required=True); e.add_argument('official',type=Path,nargs='+')
    c=sub.add_parser('check'); c.add_argument('--expected',type=Path,required=True); c.add_argument('--measured',type=Path,required=True); c.add_argument('--only',default='')
    args=p.parse_args()
    if hasattr(args,'work_dir') and not args.work_dir.is_absolute(): p.error('--work-dirは絶対パス必須')
    if args.command=='selftest': return selftest(args.work_dir)
    if args.command=='describe': print(describe()); return 0
    if args.command=='expected': print(f'期待値 {expected(args.out,args.official)}腕'); return 0
    if args.command=='check':
        ok,bad=check(args.expected,args.measured,set(filter(None,args.only.split(','))))
        for aid,fields in bad.items(): print(f'DIFF {aid}: '+','.join(fields))
        print(f'一致 {len(ok)}腕 / 不一致 {len(bad)}腕'); return int(bool(bad))
    if args.command in ('report','speed','tally'):
        tally={'agree':0,'differ':0}
        for aid,rs in lm.read_runs(args.measured).items():
            o=json.loads(rs[0]['observation'])
            if args.command=='tally':
                if all(r['gate']=='pass' for r in rs):
                    for value in json.loads(rs[0]['prediction_judgement']).values(): tally[value]+=1
            elif args.command=='report':
                print(f'{aid}: 関門={rs[0]["gate"]} n={o.get("n")} 誤りLP={o.get("res")} 配列={o.get("array")}')
            elif 'marks' in o:
                success=all(r['gate']=='pass' for r in rs) and o['counts'].get('0')==0 and o['res'].get('0',[1])[0]==0
                print(f'{aid}: frames={o["marks"]["frames"]} 成功={int(success)}')
        if args.command=='tally': print(json.dumps(tally))
        return 0
    if args.official and (args.rom_dir or args.no_calibration): p.error('公式は環境変数指定のみ・較正免除不可')
    rom=os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom: p.error('公式PC88_REF_ROM_DIR／自作--rom-dirが必要')
    prefixes=tuple(filter(None,args.only.split(',')))
    selected=[a for a in arms() if not prefixes or a['id'].startswith(prefixes)]
    if not selected: p.error('腕が選択されていない')
    records=measure(rom,args.official,selected,args.work_dir)
    passed=emit(args.out,records,not args.no_calibration)
    print(f'記録 {len(records)}腕×2走: '+('pass' if passed else 'gate_failed'))
    return int(not passed)


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as e:
        tb=traceback.extract_tb(e.__traceback__)
        print(f'NG 器具検査/実行 ({type(e).__name__}, 行{tb[-1].lineno}、画面本文非出力)')
        raise SystemExit(1)
