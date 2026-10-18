#!/usr/bin/env python3
"""l4-t2 KEY測定。画面本文とROMバイト列を出力しない。"""
import argparse, copy, csv, io, json, os, re, subprocess, sys, tempfile, traceback
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode = True
import l4_listkw_measure as kw
import check_l3_screen_output as screen
REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'tmp/t2-work'
BASE=0xE600
FIELDS=('stage','ready','finish','ERROR_FLAG','count','first_err','first_stage',
        'last_err','last_stage','setup_err','statement_err','post_err','diagnostic_err',
        'cal','csrlin','pos')
RANGE='E600-E60F'
SECRET='synthetic-screen-secret'

# 禁止事項6に基づく自作判断。bootのバナー2行だけは製品名が異なる。
KNOWN_DIFFERENCES = {
    'boot': dict(kind='banner-nonblank-rows-0-1',
                 reason='禁止事項6に従い自作名・版を表示するためバナー2行の非空白数が異なる',
                 section='docs/spec/l4-program.md §5.7')
}


class MeasurementFailure(ValueError):
    """器具自身が組み立てた数値/条件だけを外へ出す例外。"""


def arm(aid,stmt=(),setup=(),post=(),width=80,height=25,prediction='',display=False,boot=False):
    return dict(id=aid,stmt=list(stmt),setup=list(setup),post=list(post),width=width,
                height=height,prediction=prediction,display=display,boot=boot)


def arms():
    out=[arm('cal-poke',['poke &he60d,213'],prediction='cal=213、ERR0'),
         arm('cal-error',['error 13'],prediction='測る文ERR13、ERROR_FLAG1'),
         arm('boot',prediction='最下行が非空、行番号は起動設定による',boot=True)]
    for w,h in ((80,25),(40,25),(80,20),(40,20)):
        out.append(arm(f'width-{w}-{h}',setup=[f'width {w},{h}'],width=w,height=h,prediction=f'表示行は{h-1}、非空'))
    for tag,stmt,post,pred in [
        ('off',['key off'],[],'表示行消去、最下行使用可'),
        ('on',['key on'],[],'表示行あり'),
        ('off-on',['key off','key on'],[],'表示行復帰'),
        ('off-cls',['key off'],['cls'],'OFF保持'),
        ('off-width40',['key off'],['width 40,25'],'OFF保持、40桁'),
        ('off-width20',['key off'],['width 80,20'],'OFF保持、行19使用可'),
        ('on-cls',['key on'],['cls'],'ON保持')]:
        w=40 if tag=='off-width40' else 80; h=20 if tag=='off-width20' else 25
        out.append(arm(tag,stmt,setup=['width 80,25'],post=post,width=w,height=h,prediction=pred))
    for mode in ('on','off'):
        out.append(arm('bottom-'+mode,['key '+mode],setup=['width 80,25'],post=['locate 0,24','print "t2xyz";'],prediction='OFFなら行24へ印字、ONなら制限。CSRLIN/POSは無予測'))
        out.append(arm('scroll-'+mode,['key '+mode],setup=['width 80,25'],post=['locate 0,22','print "t2aaa"','print "t2bbb"','print "t2ccc"'],prediction='OFF下端24、ON下端23'))
    for mode in ('on','off'):
        out.append(arm('console-'+mode,['key '+mode],setup=['width 80,25','console 5,10'],post=['locate 0,14','print "t2xyz"'],prediction='窓5..14保持、表示行のみ切替'))
    for n in (0,1,5,6,10,11):
        out.append(arm('assign-'+str(n),[f'key {n},"t2abc"'],setup=['width 80,25','cls'],prediction='1..10受理、0/11はERR5（弱い仮説）',display=n in (1,5,6,10)))
    for n in (0,15,16,17,255,256):
        out.append(arm('length-'+str(n),[f'key 1,string$({n},"x")'],setup=['width 80,25','cls'],prediction='上限15と弱く予測、超過はERR5または切詰め（無確定）'))
    out.append(arm('assign-numeric',['key 1,12'],prediction='ERR13（弱い仮説）'))
    out.append(arm('list',['key list'],setup=['width 80,25','cls'],prediction='未対応ならERR2、受理なら行数/非空白数のみ'))
    for tag,cmd in [('missing','key'),('number','key 1'),('comma','key 1,'),('on-extra','key on 1')]:
        out.append(arm('syntax-'+tag,[cmd],prediction='ERR2またはERR22（番号は無確定）'))
    return out


def program(a):
    lines={5:'for i=0 to 15:poke &he600+i,0:next i',6:'on error goto 9000',
           7:'poke &he600,1',8:'poke &he601,151'}
    operations=[]
    for start,key in ((10,'setup'),(40,'stmt'),(60,'post')):
        operations.extend((start+j,cmd) for j,cmd in enumerate(a[key]))
    operations.extend([(80,'poke &he60e,csrlin'),(81,'poke &he60f,pos(0)'),(90,'poke &he602,163')])
    n=10
    for stage,cmd in operations:
        lines[n]=f'poke &he600,{stage}'; lines[n+1]=cmd; n+=2
    lines[n]=f'goto {n}'
    # 各誤りの最初/最後/発生段・段別欄。内部ERROR_FLAGは探索しない。
    lines.update({9000:'e=err',9001:'poke &he603,1',9002:'if peek(&he604)<>0 then 9005',
        9003:'poke &he605,e',9004:'poke &he606,peek(&he600)',9005:'poke &he607,e',
        9006:'poke &he608,peek(&he600)',9007:'if peek(&he600)<40 then poke &he609,e',
        9008:'if peek(&he600)>=40 and peek(&he600)<60 then poke &he60a,e',
        9009:'if peek(&he600)>=60 and peek(&he600)<80 then poke &he60b,e',
        9010:'if peek(&he600)>=80 then poke &he60c,e',
        9011:'poke &he604,peek(&he604)+1',9012:'resume next'})
    assert all(len(f'{n} {s}')<80 and s==s.lower() for n,s in lines.items())
    return ['new']+[f'{n} {s}' for n,s in sorted(lines.items())]+['run']


def error_block(err,stage,count):
    category=9 if stage<40 else 10 if stage<60 else 11 if stage<80 else 12
    return [[3,1]]+([[5,err],[6,stage]] if count==0 else [])+[[7,err],[8,stage],[category,err],[4,count+1]]


def valid_memory(o,a):
    if not isinstance(o,dict) or set(o)!={'values','writes'}: return False
    v=o['values']; ws=o['writes']
    if not isinstance(v,dict) or set(v)!=set(FIELDS) or any(type(x) is not int or not 0<=x<=255 for x in v.values()): return False
    if not isinstance(ws,list) or any(not isinstance(x,list) or len(x)!=2 or type(x[0]) is not int or not 0<=x[0]<16 or type(x[1]) is not int or not 0<=x[1]<=255 for x in ws): return False
    prefix=2 if ws[:2]==[[14,0],[15,0]] else 0
    if ws[prefix:prefix+18]!=[[i,0] for i in range(16)]+[[0,1],[1,151]]: return False
    stages=[10+j for j in range(len(a['setup']))]+[40+j for j in range(len(a['stmt']))]+[60+j for j in range(len(a['post']))]+[80,81,90]
    pos=prefix+18; stage=1; count=0; seen=[]
    while pos<len(ws):
        i,n=ws[pos]
        if i==3:
            head=3 if count==0 else 1
            if pos+head>=len(ws): return False
            err=ws[pos+head][1]; block=error_block(err,stage,count)
            if err==0 or ws[pos:pos+len(block)]!=block or stage not in stages: return False
            count+=1; pos+=len(block); continue
        if i==0:
            seen.append(n); stage=n
        elif (stage,i) in ((40,13),(80,14),(81,15),(90,2)):
            if i==2 and n!=163: return False
        else: return False
        pos+=1
    if seen!=stages or ws[-1]!=[2,163] or v['ready']!=151 or v['finish']!=163: return False
    if sum(x==[2,163] for x in ws)!=1: return False
    return {FIELDS[i]:n for i,n in ws}==v


def parse_log(raw,start,finish,a):
    if not re.search(rf'^range\s+: {RANGE}$',raw,re.M): raise ValueError('範囲')
    total=re.search(r'^# 取りこぼし: 0件 / 総イベント数: (\d+)件$',raw,re.M)
    if not total: raise ValueError('取りこぼし')
    events=[]; seq=0
    for row in raw.splitlines():
        if re.match(r'^\s*\d+\s',row):
            m=re.fullmatch(r'\s*(\d+)\s+(\d+)\s+[0-9A-F]{4}\s+([0-9A-F]{4})\s+([0-9A-F]{2})',row)
            if not m: raise ValueError('記録形')
            k,t,addr,val=int(m[1]),int(m[2]),int(m[3],16),int(m[4],16)
            if k!=seq+1 or not BASE<=addr<BASE+16: raise ValueError('連番/番地')
            seq=k
            if t>=start: events.append((t,addr-BASE,val))
    detail=f'腕={a["id"]} start={start} finish={finish} total={int(total[1])} seq={seq} events={len(events)} last={events[-1][0] if events else "none"}'
    if seq!=int(total[1]): raise MeasurementFailure('条件=件数不一致 '+detail)
    if not events: raise MeasurementFailure('条件=イベント空 '+detail)
    if events[-1][0]>finish-300: raise MeasurementFailure('条件=最終書込み不安定 '+detail)
    ws=[[i,v] for _,i,v in events]
    o=dict(values={FIELDS[i]:v for i,v in ws},writes=ws)
    if not valid_memory(o,a):
        raise MeasurementFailure('条件=論理印 '+detail+' indices='+json.dumps(ws,separators=(',',':')))
    return o


def sig(data):
    return vars(screen.signature([(0,data.decode('latin1'))]))


def geometry(params=None, port30=None, enabled=None):
    evidence=dict(crtc_reset=params,port30=port30,display_enabled=enabled)
    known=(isinstance(params,list) and len(params)==5 and
           all(type(x) is int and 0<=x<=255 for x in params) and
           (params[0]&127)+2==80 and 1<=(params[1]&63)+1<=25 and
           type(port30) is int and 0<=port30<=255 and enabled is True)
    return dict(source='crtc-reset-p2+port30-bit0' if known else 'unknown',
                evidence=evidence,rows=(params[1]&63)+1 if known else None,
                columns=(80 if port30&1 else 40) if known else None)


def parse_geometry(path,times):
    # 生I/OのPC・他ポートは保存しない。採取直前なので同フレームのOUTは除く。
    if not path.exists(): return [geometry() for _ in times]
    params=None; pending=None; port30=None; enabled=None; seq=0; results=[]; index=0
    main=False; complete=False
    with path.open() as f:
        for line in f:
            if line.strip()=='# main': main=True; continue
            if not main: continue
            total=re.fullmatch(r'# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件\s*',line)
            if total:
                complete=int(total[1])==0 and int(total[2])==seq
                break
            if not re.match(r'^\s*\d+\s',line): continue
            m=re.fullmatch(r'\s*(\d+)\s+\d+\s+(\d+)\s+main\s+(OUT|IN)\s+([0-9A-F]{4})\s+([0-9A-F]{2})\s+[0-9A-F]{4}\s*',line)
            if not m or int(m[1])!=seq+1: return [geometry() for _ in times]
            seq+=1; frame=int(m[2])
            while index<len(times) and frame>=times[index]:
                results.append(geometry(params,port30,enabled)); index+=1
            if m[3]!='OUT': continue
            port=int(m[4],16)&255; value=int(m[5],16)
            if port==0x30: port30=value
            elif port==0x51:
                pending=[] if value>>5==0 else None
                if value>>5==0: enabled=False; params=None
                elif value>>5==1: enabled=True
            elif port==0x50 and pending is not None:
                pending.append(value)
                if len(pending)==5: params=pending; pending=None
    while index<len(times): results.append(geometry(params,port30,enabled)); index+=1
    return results if complete else [geometry() for _ in times]


def row_metrics(raw,g):
    if len(raw)!=3000: raise ValueError('画面長')
    rows=[]
    for r in range(25):
        if g['rows'] is None: rows.append(dict(row=r,state='unknown')); continue
        if r>=g['rows']: rows.append(dict(row=r,state='hidden')); continue
        data=raw[r*120:r*120+80:80//g['columns']]
        rows.append(dict(row=r,state='visible',nonblank=sum(x not in (0,32) for x in data),**sig(data)))
    return rows


def observation(memory,raw,g,display):
    rows=row_metrics(raw,g); bottom=None if g['rows'] is None else g['rows']-1
    return dict(memory=memory,geometry=g,rows=rows,display=display,stable=True,
                bottom_row=bottom,bottom_nonblank=None if bottom is None else rows[bottom]['nonblank'])


def capture(rom,official,a,work,commands=None):
    boot=a['boot'] and commands is None
    cmds=[] if boot else (program(a) if commands is None else commands)
    args=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom)]
    at=700 if official else 100
    if official and not boot: args+=['--type-at','300','--type','\n']
    start=at
    for cmd in cmds:
        if cmd=='run': start=at
        args+=['--type-at',str(at),'--type',cmd+'\n']; at+=(len(cmd)+1)*8+240
    at=max(at+3000,3000); finish=at+700
    paths=[]
    for t in (at,at+300):
        path=work/'screen.bin'; args+=['--vram-dump',str(path),'--vram-dump-at',str(t)]
        paths.append(work/f'screen.f{t:06d}.bin')
    mem=work/'memory.txt'; hardware=work/'hardware.txt'
    args+=['--io-log',str(hardware)]
    if not boot: args+=['--mem-write-log',str(mem),'--mem-write-range',RANGE,'--mem-write-from-frame',str(start)]
    args+=['--frames',str(finish)]
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode or b'untypable' in p.stderr.lower(): raise RuntimeError('実行/打鍵拒否')
        raw=[x.read_bytes() for x in paths]
        if len(raw[0])!=3000 or raw[0]!=raw[1]: raise ValueError('画面安定')
        memory=None if boot else parse_log(mem.read_text(),start,finish,a)
        try: gs=parse_geometry(hardware,(at,at+300))
        except OSError: gs=[geometry(),geometry()]
        if gs[0]!=gs[1]: raise ValueError('表示設定安定')
        return memory,raw[1],gs[1]
    except MeasurementFailure:
        raise
    except ValueError as exc:
        safe_conditions={'範囲','取りこぼし','記録形','連番/番地','画面長','画面安定','表示設定安定'}
        condition=str(exc) if str(exc) in safe_conditions else '検証'
        raise MeasurementFailure(f'条件={condition} 腕={a["id"]} start={start} finish={finish} captures={at},{at+300}') from None
    finally:
        mem.unlink(missing_ok=True); hardware.unlink(missing_ok=True)
        for x in paths:
            x.unlink(missing_ok=True); Path(str(x)+'.info.txt').unlink(missing_ok=True)


def display_field(raw,before,refs,w,h):
    row=raw[(h-1)*120:(h-1)*120+80:80//w]
    old=before[(h-1)*120:(h-1)*120+80:80//w]
    changed=sum(c in b't2abc' and c!=old[i] for i,c in enumerate(row))
    distinct=len({v['sha256'] for v in refs.values()})==len(refs)==2
    windows=[sig(row[x:x+5]) for x in range(w-4)]
    matches={tag:[x for x,v in enumerate(windows) if v==ref] for tag,ref in refs.items()}
    state='valid' if distinct and changed>0 else 'incomparable'
    return dict(state=state,changed_cells=changed,candidate_distinct=distinct,candidates=refs,windows=windows,matches=matches if state=='valid' else {})


def run_arm(rom,official,a,work,refs):
    memory,raw,g=capture(rom,official,a,work)
    display=dict(state='excluded')
    if a['display']:
        baseline=copy.deepcopy(a); baseline['stmt']=[]; baseline['display']=False
        _,before,bg=capture(rom,official,baseline,work)
        if g['rows'] is not None and g==bg:
            display=display_field(raw,before,refs,g['columns'],g['rows'])
        else: display=dict(state='unknown')
    return observation(memory,raw,g,display)


def valid_sig(s,n):
    return isinstance(s,dict) and set(s)=={'line_count','char_count','sha256'} and type(s['line_count']) is int and s['line_count']==1 and type(s['char_count']) is int and s['char_count']==n and isinstance(s['sha256'],str) and bool(re.fullmatch('[a-f0-9]{64}',s['sha256']))


def valid(o,a):
    if not isinstance(o,dict) or set(o)!={'memory','geometry','rows','display','stable','bottom_row','bottom_nonblank'} or o['stable'] is not True: return False
    if a['boot']:
        if o['memory'] is not None: return False
    elif not valid_memory(o['memory'],a): return False
    g=o['geometry']
    if not isinstance(g,dict) or set(g)!={'source','evidence','rows','columns'}: return False
    e=g['evidence']
    if not isinstance(e,dict) or set(e)!={'crtc_reset','port30','display_enabled'}: return False
    if e['crtc_reset'] is not None and (not isinstance(e['crtc_reset'],list) or len(e['crtc_reset'])!=5 or any(type(x) is not int or not 0<=x<=255 for x in e['crtc_reset'])): return False
    if e['port30'] is not None and (type(e['port30']) is not int or not 0<=e['port30']<=255): return False
    if e['display_enabled'] is not None and type(e['display_enabled']) is not bool: return False
    if g!=geometry(e['crtc_reset'],e['port30'],e['display_enabled']): return False
    rows=o['rows']
    if not isinstance(rows,list) or len(rows)!=25: return False
    for r,v in enumerate(rows):
        if g['rows'] is None:
            if v!=dict(row=r,state='unknown'): return False
        elif r>=g['rows']:
            if v!=dict(row=r,state='hidden'): return False
        elif (not isinstance(v,dict) or set(v)!={'row','state','nonblank','line_count','char_count','sha256'} or
              v['row']!=r or v['state']!='visible' or type(v['nonblank']) is not int or
              not 0<=v['nonblank']<=g['columns'] or
              not valid_sig({k:v[k] for k in ('line_count','char_count','sha256')},g['columns'])): return False
    bottom=None if g['rows'] is None else g['rows']-1
    if o['bottom_row']!=bottom or o['bottom_nonblank']!=(None if bottom is None else rows[bottom]['nonblank']): return False
    d=o['display']
    if not a['display']: return d==dict(state='excluded')
    if d==dict(state='unknown'): return True
    if not isinstance(d,dict) or set(d)!={'state','changed_cells','candidate_distinct','candidates','windows','matches'}: return False
    if type(d['changed_cells']) is not int or g['columns'] is None or not 0<=d['changed_cells']<=g['columns']: return False
    refs=d['candidates']
    if not isinstance(refs,dict) or set(refs)!={'assigned','contrast'} or not all(valid_sig(s,5) for s in refs.values()): return False
    distinct=len({s['sha256'] for s in refs.values()})==2
    if d['candidate_distinct'] is not distinct: return False
    state='valid' if distinct and d['changed_cells']>0 else 'incomparable'
    if d['state']!=state: return False
    windows=d['windows']
    if not isinstance(windows,list) or len(windows)!=g['columns']-4 or not all(valid_sig(v,5) for v in windows): return False
    if state=='incomparable': return d['matches']=={}
    return d['matches']=={tag:[x for x,v in enumerate(windows) if v==ref] for tag,ref in refs.items()}


def calibrated(rs):
    by={r['arm']['id']:r for r in rs}
    for aid,value in (('cal-poke',213),('cal-error',13)):
        r=by.get(aid)
        if not r or not r['gate']: return False
        for o in r['obs']:
            if not valid(o,r['arm']): return False
            v=o['memory']['values']
            if aid=='cal-poke' and (v['cal']!=value or v['ERROR_FLAG'] or v['count']): return False
            if aid=='cal-error' and any(v[k]!=n for k,n in dict(ERROR_FLAG=1,count=1,first_err=13,first_stage=40,last_err=13,last_stage=40,statement_err=13,setup_err=0,post_err=0,diagnostic_err=0).items()): return False
    return True


def write_tsv(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w') as f:
        w=csv.writer(f,delimiter='\t',lineterminator='\n'); w.writerow(fields); w.writerows(rows)


def emit(path,rs):
    cal=calibrated(rs)
    write_tsv(path,['arm','repeat','plan','observation','gate'],[[r['arm']['id'],j+1,json.dumps(r['arm'],sort_keys=True),json.dumps(o,sort_keys=True),'pass' if r['gate'] and cal else 'gate_failed'] for r in rs for j,o in enumerate(r['obs'])])
    return cal and all(r['gate'] for r in rs)


def read_passed(path):
    known={a['id']:a for a in arms()}; groups={}
    with path.open() as f:
        reader=csv.DictReader(f,delimiter='\t')
        if reader.fieldnames!=['arm','repeat','plan','observation','gate']: raise ValueError('TSV列')
        for row in reader:
            if None in row or any(v is None for v in row.values()): raise ValueError('TSV行')
            groups.setdefault(row['arm'],[]).append(row)
    rs=[]
    for aid,rows in groups.items():
        if aid not in known or len(rows)!=2 or {r['repeat'] for r in rows}!={'1','2'}: raise ValueError('腕/反復')
        a=known[aid]
        if any(r['gate']!='pass' or json.loads(r['plan'])!=a for r in rows): raise ValueError('関門/予定')
        obs=[json.loads(r['observation']) for r in rows]
        if not all(valid(o,a) for o in obs) or obs[0]!=obs[1]: raise ValueError('観測/2走')
        rs.append(dict(arm=a,obs=obs,gate=True))
    if set(groups)!=set(known) or not calibrated(rs): raise ValueError('全腕/較正')
    return rs


def comparison(o):
    # 画面本文の署名を別ROMへ要求しない。表示分類と非空白数のみ。
    d=o['display']
    return dict(values=None if o['memory'] is None else o['memory']['values'],
                nonblank=[r.get('nonblank') for r in o['rows']],
                geometry={k:o['geometry'][k] for k in ('source','rows','columns')},
                bottom_row=o['bottom_row'],bottom_nonblank=o['bottom_nonblank'],
                display=dict(state='valid',matches=d['matches']) if d['state']=='valid' else dict(state=d['state']))


def expected(out,paths):
    if len(paths)!=1: raise ValueError('全腕TSV一つを指定')
    rs=read_passed(paths[0]); write_tsv(out,['arm','expected'],[[r['arm']['id'],json.dumps(comparison(r['obs'][0]),sort_keys=True)] for r in rs]); return len(rs)


def valid_expected_geometry(v):
    g=v['geometry']
    if not isinstance(g,dict) or set(g)!={'source','rows','columns'}: return False
    h,w=g['rows'],g['columns']; nb=v['nonblank']
    if not isinstance(nb,list) or len(nb)!=25: return False
    if h is None:
        return g==dict(source='unknown',rows=None,columns=None) and nb==[None]*25 and v['bottom_row'] is None and v['bottom_nonblank'] is None
    return (g['source']=='crtc-reset-p2+port30-bit0' and type(h) is int and 1<=h<=25 and
            type(w) is int and w in (40,80) and
            all(type(x) is int and 0<=x<=w for x in nb[:h]) and nb[h:]==[None]*(25-h) and
            v['bottom_row']==h-1 and v['bottom_nonblank']==nb[h-1])


def fake_hardware(height=25):
    events=[(0x30,35),(0x51,0)]+[(0x50,x) for x in (206,128+height-1,0,0,19)]+[(0x51,32)]
    return '# main\n'+''.join(f'{i} {i} 0 main OUT {p:04X} {v:02X} 0000\n' for i,(p,v) in enumerate(events,1))+f'# 取りこぼし: 0件 / 総イベント数: {len(events)}件\n'


def check(exp,measured):
    with exp.open() as f:
        reader=csv.DictReader(f,delimiter='\t')
        if reader.fieldnames!=['arm','expected']: raise ValueError('期待値列')
        rows=list(reader)
    want={r['arm']:json.loads(r['expected']) for r in rows}
    if len(rows)!=len(want) or set(want)!={a['id'] for a in arms()}: raise ValueError('期待腕')
    for a in arms():
        v=want[a['id']]
        if set(v)!={'values','nonblank','display','geometry','bottom_row','bottom_nonblank'} or not valid_expected_geometry(v): raise ValueError('期待形')
        if a['boot']:
            if v['values'] is not None: raise ValueError('期待起動')
        elif set(v['values'])!=set(FIELDS) or any(type(x) is not int or not 0<=x<=255 for x in v['values'].values()): raise ValueError('期待数値')
        d=v['display']
        if not isinstance(d,dict): raise ValueError('期待表示形')
        if d.get('state') not in ('valid','incomparable','excluded','unknown') or set(d)!=({'state','matches'} if d['state']=='valid' else {'state'}): raise ValueError('期待表示')
        if not a['display'] and d!=dict(state='excluded'): raise ValueError('期待表示対象')
        if a['display'] and d['state']=='excluded': raise ValueError('期待表示除外')
        if d['state']=='valid' and (not isinstance(d['matches'],dict) or set(d['matches'])!={'assigned','contrast'} or any(not isinstance(xs,list) or any(type(x) is not int or v['geometry']['columns'] is None or not 0<=x<=v['geometry']['columns']-5 for x in xs) or xs!=sorted(set(xs)) for xs in d['matches'].values())): raise ValueError('期待一致位置')
    try: got={r['arm']['id']:comparison(r['obs'][0]) for r in read_passed(measured)}
    except (ValueError,KeyError,TypeError): got={}
    bad=[]; known=[]; now_matches=[]
    for aid,v in want.items():
        g=got.get(aid)
        if (g is not None and g['values']==v['values'] and g['nonblank']==v['nonblank']
                and all(g[k]==v[k] for k in ('geometry','bottom_row','bottom_nonblank'))
                and (v['display']['state']!='valid' or g['display']==v['display'])):
            if aid in KNOWN_DIFFERENCES: now_matches.append(aid)
            continue
        # bootに限り、行0・1のnonblankのみを許す。他の全フィールドは公式値と同じ。
        if aid in KNOWN_DIFFERENCES and g is not None:
            strict=(g['values']==v['values'] and g['nonblank'][2:]==v['nonblank'][2:]
                    and all(g[k]==v[k] for k in ('geometry','bottom_row','bottom_nonblank'))
                    and (v['display']['state']!='valid' or g['display']==v['display']))
            if strict:
                known.append(aid); continue
        bad.append(aid)
    return len(want)-len(bad),bad,known,now_matches


def check_selftest(work):
    """合成TSVで許容範囲と3つの陰性対照を確認する。"""
    work.mkdir(parents=True,exist_ok=True)
    arms_by={a['id']:a for a in arms()}
    rs=[dict(arm=a,obs=[synth(a),synth(a)],gate=True) for a in arms()]
    with tempfile.TemporaryDirectory(dir=work,prefix='check-synthetic-') as td:
        td=Path(td); exp=td/'expected.tsv'; measured=td/'measured.tsv'
        assert emit(measured,rs) and expected(exp,[measured])==len(rs)
        want=json.loads(next(r['expected'] for r in csv.DictReader(exp.open(),delimiter='\t') if r['arm']=='boot'))
        boot_runs=next(r for r in rs if r['arm']['id']=='boot')['obs']
        # バナー2行だけの変化がKNOWN。完全一致はKNOWN-NOW-MATCHES。
        for boot in boot_runs:
            boot['rows'][0]['nonblank']=0 if boot['rows'][0]['nonblank'] else 1
            boot['rows'][1]['nonblank']=0 if boot['rows'][1]['nonblank'] else 1
        assert emit(measured,rs) and check(exp,measured)==(len(rs),[],['boot'],[])
        for boot in boot_runs:
            boot['rows'][0]['nonblank']=want['nonblank'][0]; boot['rows'][1]['nonblank']=want['nonblank'][1]
        assert emit(measured,rs) and check(exp,measured)==(len(rs),[],[],['boot'])
        negatives=[]
        for aid,mutate in (
            ('boot',lambda o:o['rows'].__setitem__(2,dict(o['rows'][2],nonblank=(o['rows'][2]['nonblank']+1)%81))),
            ('boot',lambda o:o.__setitem__('bottom_nonblank',(o['bottom_nonblank']+1)%81)),
            ('width-80-25',lambda o:o['rows'].__setitem__(0,dict(o['rows'][0],nonblank=(o['rows'][0]['nonblank']+1)%81)))):
            broken=copy.deepcopy(rs); target=next(r for r in broken if r['arm']['id']==aid)
            mutate(target['obs'][0]); mutate(target['obs'][1])
            assert emit(measured,broken)
            result=check(exp,measured)
            assert result[1], result
            negatives.append(aid)
    print('OK 合成check: boot許容・完全一致・行2/bottom/他腕行0の陰性対照',flush=True)


def synth(a):
    ws=[[i,0] for i in range(16)]+[[0,1],[1,151]]
    for start,key in ((10,'setup'),(40,'stmt'),(60,'post')):
        for j,cmd in enumerate(a[key]):
            ws.append([0,start+j])
            if a['id']=='cal-poke': ws.append([13,213])
            if a['id']=='cal-error': ws+=error_block(13,start+j,0)
    ws += [[0,80],[14,0],[0,81],[15,0],[0,90],[2,163]]
    memory=dict(values={FIELDS[i]:v for i,v in ws},writes=ws)
    raw=b' '*3000; refs={k:sig(v) for k,v in [('assigned',b't2abc'),('contrast',b't2abd')]}
    d=display_field(raw,raw,refs,80,25) if a['display'] else dict(state='excluded')
    return observation(None if a['boot'] else memory,raw,geometry([206,128+a['height']-1,0,0,19],35 if a['width']==80 else 34,True),d)


def fake_log(o,start=100):
    ws=o['memory']['writes']
    return f'range     : {RANGE}\n'+''.join(f'{k+1} {start+k} 0000 {BASE+i:04X} {v:02X}\n' for k,(i,v) in enumerate(ws))+f'# 取りこぼし: 0件 / 総イベント数: {len(ws)}件\n'


def safety_selftest(work):
    work.mkdir(parents=True,exist_ok=True); known=arms()
    assert 20<=len(known)<=40 and len({a['id'] for a in known})==len(known)
    rs=[dict(arm=a,obs=[synth(a),synth(a)],gate=True) for a in known]
    assert all(valid(r['obs'][0],r['arm']) for r in rs) and calibrated(rs)
    good=rs[0]['obs'][0]
    assert parse_log(fake_log(good),100,1000,known[0])==good['memory']
    prefixed=copy.deepcopy(good); prefixed['memory']['writes'][:0]=[[14,0],[15,0]]
    assert valid(prefixed,known[0])
    assert parse_log(fake_log(prefixed),100,1000,known[0])==prefixed['memory']
    for raw,start,finish,condition in (
        (f'range     : {RANGE}\n# 取りこぼし: 0件 / 総イベント数: 0件\n',100,1000,'イベント空'),
        (fake_log(good),100,300,'最終書込み不安定'),
        (fake_log(good).replace(f'総イベント数: {len(good["memory"]["writes"])}件','総イベント数: 999件'),100,1000,'件数不一致')):
        try: parse_log(raw,start,finish,known[0])
        except MeasurementFailure as exc:
            assert condition in str(exc) and '腕=cal-poke' in str(exc) and 'finish=' in str(exc)
        else: raise AssertionError('失敗条件を受理')
    for prefix in ([[14,1],[15,0]],[[15,0],[14,0]],[[14,0]],[[15,0]]):
        bad=copy.deepcopy(good); bad['memory']['writes'][:0]=prefix
        assert not valid(bad,known[0])
    bad=copy.deepcopy(prefixed); del bad['memory']['writes'][2]
    assert not valid(bad,known[0])
    bad=copy.deepcopy(good); bad['memory']['writes'][18:18]=[[14,0],[15,0]]
    assert not valid(bad,known[0])
    for mutate in ('missing','finish','noninteger','wrongstage','errorflag','unstable'):
        bad=copy.deepcopy(rs[1]['obs'][0])
        if mutate=='missing': bad['memory']['values'].pop('count')
        elif mutate=='finish': bad['memory']['writes'].pop()
        elif mutate=='noninteger': bad['memory']['values']['cal']=SECRET
        elif mutate=='wrongstage':
            for x in bad['memory']['writes']:
                if x[0] in (6,8): x[1]=60
            bad['memory']['values']['first_stage']=60; bad['memory']['values']['last_stage']=60
        elif mutate=='errorflag': bad['memory']['values']['ERROR_FLAG']=0
        else: bad['stable']=False
        assert not valid(bad,known[1])
    for raw in (fake_log(good).replace('取りこぼし: 0','取りこぼし: 1'),fake_log(good).replace(RANGE,'E600-E610'),fake_log(good).replace('1 100','2 100'),fake_log(good).replace(' E600 00',' E600 '+SECRET)):
        try: parse_log(raw,100,1000,known[0])
        except ValueError: pass
        else: raise AssertionError('壊れたログ受理')
    a=next(a for a in known if a['display']); raw=bytearray(b' '*3000); raw[24*120+5:24*120+10]=b't2abc'
    refs={'assigned':sig(b't2abc'),'contrast':sig(b't2abd')}
    d=display_field(bytes(raw),b' '*3000,refs,80,25)
    assert d['state']=='valid' and d['matches']['assigned']==[5]
    same=display_field(bytes(raw),b' '*3000,dict.fromkeys(refs,refs['assigned']),80,25)
    absent=display_field(bytes(raw),bytes(raw),refs,80,25)
    assert same['state']==absent['state']=='incomparable'
    # 表示外に非空白を置き、20行の実設定に反する25行の申告を拒否する。
    hidden=bytearray(b' '*3000); hidden[20*120:]=b'x'*(5*120)
    g20=geometry([206,147,0,0,19],35,True)
    positive=observation(good['memory'],bytes(hidden),g20,dict(state='excluded'))
    assert valid(positive,known[0]) and positive['bottom_row']==19 and positive['bottom_nonblank']==0
    assert positive['rows'][20:]==[dict(row=r,state='hidden') for r in range(20,25)]
    forged=copy.deepcopy(positive); forged['geometry']['rows']=25
    forged['rows']=row_metrics(bytes(hidden),geometry([206,152,0,0,19],35,True))
    forged['bottom_row']=24; forged['bottom_nonblank']=80
    assert not valid(forged,known[0])
    # 本文ではなくI/Oログで時点ごとの設定を確定する陽性・陰性。
    hp=work/'synthetic-hardware.txt'
    try:
        hp.write_text(fake_hardware(20))
        assert parse_geometry(hp,(100,400))==[g20,g20]
        later=fake_hardware(25).splitlines()[1:-1]
        hp.write_text(fake_hardware(20).split('# 取りこぼし:')[0]+''.join(' '.join([str(i+8),str(i+8),'100']+line.split()[3:])+'\n' for i,line in enumerate(later,1))+'# 取りこぼし: 0件 / 総イベント数: 16件\n')
        assert parse_geometry(hp,(100,101))==[g20,geometry([206,152,0,0,19],35,True)]
        hp.write_text(fake_hardware(20).split('# 取りこぼし:')[0]+'9 9 1 main OUT 0051 00 0000\n10 10 1 main OUT 0050 CE 0000\n11 11 1 main OUT 0051 20 0000\n# 取りこぼし: 0件 / 総イベント数: 11件\n')
        assert all(g['rows'] is None for g in parse_geometry(hp,(100,400)))
        hp.write_text(fake_hardware(20).replace('取りこぼし: 0','取りこぼし: 1'))
        assert parse_geometry(hp,(100,400))==[geometry(),geometry()]
    finally: hp.unlink(missing_ok=True)
    unknown=observation(good['memory'],bytes(hidden),geometry(),dict(state='excluded'))
    assert valid(unknown,known[0]) and unknown['bottom_nonblank'] is None
    with tempfile.TemporaryDirectory(dir=work,prefix='synthetic-') as td:
        td=Path(td); measured=td/'good.tsv'; exp=td/'expected.tsv'; badpath=td/'bad.tsv'
        assert emit(measured,rs); assert expected(exp,[measured])==len(known); assert check(exp,measured)==(len(known),[],[],['boot'])
        for mode in ('two-runs','calibration','gate','missing','plan','repeat','body'):
            broken=copy.deepcopy(rs)
            if mode=='two-runs': broken[2]['obs'][1]['rows'][0]['nonblank']=1
            elif mode=='calibration':
                for o in broken[0]['obs']:
                    o['memory']['values']['cal']=212
                    for x in o['memory']['writes']:
                        if x[0]==13: x[1]=212
            elif mode=='gate': broken[2]['gate']=False
            elif mode=='missing': broken.pop()
            elif mode=='body': broken[2]['obs'][0]['body']=SECRET
            emit(badpath,broken)
            if mode in ('plan','repeat'):
                text=badpath.read_text(); badpath.write_text(text.replace('key off','key on') if mode=='plan' else text.replace('\t2\t','\t1\t'))
            try: expected(td/'reject.tsv',[badpath])
            except ValueError: pass
            else: raise AssertionError('壊れたTSV受理')
            assert check(exp,badpath)[1]
        # 有効画面の欠落はNG。画面のみ比較不能でも数値は有効。
        target=next(r for r in rs if r['arm']['id']==a['id'])
        for o in target['obs']: o['display']=d
        assert emit(measured,rs); expected(exp,[measured])
        for o in target['obs']: o['display']=same
        assert emit(badpath,rs); assert check(exp,badpath)[1]==[a['id']]
        expected(exp,[badpath]); assert check(exp,badpath)==(len(known),[],[],['boot'])
        # 表示の関門だけ不通過でも数値の変化はNG。
        changed=copy.deepcopy(rs)
        target_numeric=changed[3]
        for o in target_numeric['obs']:
            o['memory']['values']['pos']=1
            for x in o['memory']['writes'][18:]:
                if x[0]==15: x[1]=1
        assert emit(measured,changed) and check(exp,measured)[1]==[target_numeric['arm']['id']]
        tampered=copy.deepcopy(rs)
        tr=next(r for r in tampered if r['arm']['id']==a['id'])
        for o in tr['obs']:
            o['display']=copy.deepcopy(d); o['display']['matches']['assigned']=[]
        assert not valid(tr['obs'][0],a)
        emit(measured,tampered)
        assert check(exp,measured)[1]
        # 秘密本文を含むTSVのCLI拒否時にも、本文・例外値を出さない。
        leak=measured.read_text().replace('incomparable',SECRET); measured.write_text(leak)
        cli=subprocess.run([sys.executable,str(Path(__file__).resolve()),'check','--expected',str(exp),'--measured',str(measured)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        assert cli.returncode==1 and SECRET.encode() not in cli.stdout+cli.stderr
        # 合成複数誤り：stmtとpostで段を保持。
        multi=arm('multi',['error 13'],post=['error 2']); mo=synth(multi)
        ws=mo['memory']['writes']; p=ws.index([0,40])+1; ws[p:p]=error_block(13,40,0)
        p=ws.index([0,60])+1; ws[p:p]=error_block(2,60,1)
        mo['memory']['values']={FIELDS[i]:v for i,v in ws}; assert valid(mo,multi)
        # 実行経路に秘密本文を注入し、成功・拒否とも出力と一時ファイルを監査。
        def fake(argv,**kwargs):
            start=int(argv[argv.index('--mem-write-from-frame')+1]); Path(argv[argv.index('--mem-write-log')+1]).write_text(fake_log(good,start))
            for j,x in enumerate(argv):
                if x=='--vram-dump':
                    base=Path(argv[j+1]); t=int(argv[j+3]); base.with_name(base.stem+f'.f{t:06d}'+base.suffix).write_bytes(b' '*3000)
            Path(argv[argv.index('--io-log')+1]).write_text(fake_hardware())
            return subprocess.CompletedProcess(argv,0,SECRET.encode(),SECRET.encode())
        sink=io.StringIO()
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=fake),redirect_stdout(sink),redirect_stderr(sink):
            assert capture(Path('synthetic'),False,known[0],td)[0]==good['memory']
        assert not sink.getvalue() and not list(td.glob('screen*')) and not (td/'memory.txt').exists() and not (td/'hardware.txt').exists()
        def rejected(argv,**kwargs): return subprocess.CompletedProcess(argv,1,SECRET.encode(),SECRET.encode())
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=rejected),redirect_stdout(sink),redirect_stderr(sink):
            try: capture(Path('synthetic'),False,known[0],td)
            except RuntimeError: pass
            else: raise AssertionError('実行拒否受理')
        def unsafe_exception(argv,**kwargs): raise ValueError(SECRET)
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=unsafe_exception),redirect_stdout(sink),redirect_stderr(sink):
            try: capture(Path('synthetic'),False,known[0],td)
            except MeasurementFailure as exc:
                assert SECRET not in str(exc) and '条件=検証' in str(exc) and '腕=cal-poke' in str(exc) and 'finish=' in str(exc)
            else: raise AssertionError('秘密例外受理')
        assert not sink.getvalue()
    print('OK 合成自己検査: 陽性・陰性・本文非出力・TSV拒否・2走・候補相異・表示欄限定関門・非表示25行偽装拒否',flush=True)


def candidates(rom,official,work):
    refs={}
    for tag,text in (('assigned','t2abc'),('contrast','t2abd')):
        a=arm('candidate-'+tag,[f'print "{text}";'],setup=['width 80,25','cls','locate 0,2'])
        dest=work/('candidate-'+tag); dest.mkdir(exist_ok=True)
        observations=[]
        for _ in (1,2):
            m,raw,g=capture(rom,official,a,dest)
            if g['rows'] is not None and (g['rows']!=25 or g['columns']!=80): raise ValueError('候補表示範囲')
            # 情報取得不能時も誤りなしの既知WIDTH候補は到達を検査する。
            if not valid_memory(m,a) or m['values']['ERROR_FLAG'] or raw[2*120:2*120+5]!=text.encode(): raise ValueError('候補到達')
            observations.append(sig(raw[2*120:2*120+5]))
        if observations[0]!=observations[1]: raise ValueError('候補2走')
        refs[tag]=observations[0]
    return refs


def measure(rom,official,work):
    safety_selftest(work)
    refs=candidates(rom,official,work); rs=[]
    for a in arms():
        obs=[]
        for repeat in (1,2):
            dest=work/(a['id']+'-'+str(repeat)); dest.mkdir(exist_ok=True)
            try: obs.append(run_arm(rom,official,a,dest,refs))
            except Exception as exc:
                if isinstance(exc,MeasurementFailure): print(str(exc),flush=True)
                else: print(f'腕={a["id"]} repeat={repeat} 条件={type(exc).__name__}（本文非出力）',flush=True)
                obs.append(dict(failure='capture-gate'))
        gate=all(valid(o,a) for o in obs) and obs[0]==obs[1]
        rs.append(dict(arm=a,obs=obs,gate=gate)); print(a['id']+': '+('pass' if gate else 'gate_failed'),flush=True)
    return rs


def selftest(work):
    safety_selftest(work); rom=work/'rom'
    p=subprocess.run([sys.executable,str(REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    if p.returncode: raise RuntimeError('自作ビルド拒否/失敗')
    rs=measure(rom,False,work); passed=emit(work/'selfrun.tsv',rs)
    rows=['# l4-t2 自作ROM試走', '2026-10-14。自作ROMの独立試走。src変更・commit・run_allなし。',
          f'{len(rs)}腕×2走、関門通過{sum(r["gate"] for r in rs)}/{len(rs)}、較正{calibrated(rs)}。候補2種も独立2走。',
          'ファンクションキー押下は現行APIでは文字打鍵と併用不可のため測らない。',
          '数値の仮説一致は関門にしない。表示比較不能はその欄だけ不明。生画面・生メモリログは削除。',
          '表示行数はCRTC RESETのP2下位6bit+1、桁数はポート0x30 bit0。非表示行は計数・署名化しない。',
          '', '| 腕 | 関門 | ERROR_FLAG/回数 | setup/stmt/post/diag ERR | 最初/最後 ERR@段 | CSRLIN/POS | 表示比較 | 表示行数 | 表示桁数 | 最下行番号（0起点） | 最下行非空白セル |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in rs:
        o=r['obs'][0] if r['gate'] else {}; v=(o.get('memory') or {}).get('values',{})
        g=lambda k:v.get(k,'不明')
        rows.append(f'| {r["arm"]["id"]} | {"pass" if r["gate"] else "gate_failed"} | {g("ERROR_FLAG")}/{g("count")} | '+ '/'.join(str(g(k)) for k in ('setup_err','statement_err','post_err','diagnostic_err'))+f' | {g("first_err")}@{g("first_stage")}/{g("last_err")}@{g("last_stage")} | {g("csrlin")}/{g("pos")} | {o.get("display",{}).get("state","不明")} | '+' | '.join(str(x) if x is not None else '不明' for x in ((o.get('geometry') or {}).get('rows'),(o.get('geometry') or {}).get('columns'),o.get('bottom_row'),o.get('bottom_nonblank')))+' |')
    ((work if any(work.resolve().is_relative_to(root.resolve()) for root in (REPO/'tmp/t2-impl-work', REPO/'tmp/c2-work')) else ROOT)/'selfrun.md').write_text('\n'.join(rows)+'\n')
    print('自作試走: '+('pass' if passed else 'gate_failed'),flush=True); return int(not passed)


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
        conformance_path=((name=='out' and args.command=='expected') or (name=='expected' and args.command=='check'))
        if conformance_path and path is not None and path.is_absolute() and path.resolve()==REPO/'tests/conformance/expected_l4_key.tsv': continue
        if path is not None and (not path.is_absolute() or not any(path.resolve().is_relative_to(root.resolve()) for root in (ROOT, REPO/"tmp/t2-impl-work", REPO/"tmp/c2-work"))): p.error('作業・結果先はtmp/t2-work、tmp/t2-impl-workまたはtmp/c2-work内の絶対パス必須')
    if hasattr(args,'paths') and any(not x.is_absolute() or not x.resolve().is_relative_to(ROOT.resolve()) for x in args.paths): p.error('入力もtmp/t2-work内')
    if hasattr(args,'work_dir'): args.work_dir.mkdir(parents=True,exist_ok=True)
    if args.command=='describe':
        for a in arms(): print(json.dumps(a,ensure_ascii=False,sort_keys=True))
        return 0
    if args.command=='expected': print(f'期待値{expected(args.out,args.paths)}腕'); return 0
    if args.command=='check':
        ok,bad,known,now_matches=check(args.expected,args.measured)
        print(f'一致{ok-len(known)}腕、KNOWN {len(known)}腕、KNOWN-NOW-MATCHES {len(now_matches)}腕、不一致{len(bad)}腕')
        for aid in known: print(f'KNOWN {aid}: {KNOWN_DIFFERENCES[aid]["reason"]}')
        for aid in now_matches: print(f'KNOWN-NOW-MATCHES {aid}')
        for aid in bad: print(f'NG {aid}')
        return int(bool(bad))
    if args.command=='selftest':
        if args.synthetic_only: safety_selftest(args.work_dir); check_selftest(args.work_dir); return 0
        return selftest(args.work_dir)
    rom=os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir): p.error('公式はPC88_REF_ROM_DIRのみ、自作は--rom-dir必須')
    rs=measure(rom,args.official,args.work_dir); return int(not emit(args.out,rs))


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        if isinstance(exc,MeasurementFailure): print(str(exc))
        tb=traceback.extract_tb(exc.__traceback__); print(f'NG 器具: {type(exc).__name__}、行{tb[-1].lineno}（本文非出力）'); raise SystemExit(1)
