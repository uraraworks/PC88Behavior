#!/usr/bin/env python3
"""l4-f2 ランダムファイル。比較印と自作対象ファイルの候補署名だけを記録。"""
import sys
sys.dont_write_bytecode = True
import argparse, copy, csv, gzip, hashlib, json, os, re, shutil, struct, subprocess, time
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
import l4_seqfile_measure as seq

REPO = seq.REPO
ROOT = Path(os.environ.get('PC88_L4_RANDFILE_WORK', REPO/'tmp/f2-work')).resolve()
mem, blank, BASE, FIELDS = seq.mem, seq.blank, seq.BASE, seq.FIELDS
boolean, number, program = seq.boolean, seq.number, seq.program
PLAN_SHA = 'c5b23debb67cd48f1578a2c865fd4de544e72de82a133ade03832ae7104fbb68'
PROGRAM_SHA = 'aad12fbae8b2fa83a6d64bf4d5bdc448a233a44ca506537b8d8bc3d3ba1bcde3'
NAME = b'f2own'
CONDITIONS = ('stable','logical_marks','memory_no_loss','io_no_loss','prefix_no_loss','prefix_marks_absent','replay_equal','media_known')
KNOWN_DIFFERENCES = {}
PROTECTED = seq.PROTECTED
COMMON_SYNTH = seq.synth
COMMON_GATES = seq.gates
OP = 'open "2:f2own" as #1'
FIELD = 'field #1,128 as a$'

def arms():
    aa=[]
    def add(aid, setup, target, prediction, cleanup=None, bodies=None):
        aa.append(dict(id=aid,stages=[setup,target,['close'] if cleanup is None else cleanup],
                       commands=['stage1','stage2','stage3'],prediction=prediction,
                       bodies=bodies or {},fixture=None,lifecycle=None))
    add('cal-poke',['poke &hc310,213'],['rem calibration'],'cal213・ERR0',['rem calibration'])
    add('cal-error',[],['error 13'],'ERR13@段2',['rem calibration'])
    add('disk-positive',[],['open "2:f2own" for output as #1','print #1,"ok"','close',
        'open "2:f2own" for input as #1','input #1,a$',boolean(65,'a$="ok"'),'close'],
        'ERR0・印1・種別00・ok-crlf-sub',['rem done'],{'ok-crlf-sub':b'ok\r\n\x1a'+bytes(251)})
    add('open-default',[],[OP],'ERR0・既定128')
    for n in (128,256,1,0,257):
        add('open-len-'+str(n),[],[OP+' len='+str(n)],'1..256受理、0/257はERR5を仮説')
    for n in (128,256,1):
        add('open-short-'+str(n),[],[f'open "r",#1,"2:f2own",{n}'],'ERR2を仮説')
    for n in (0,1,2,3,15,16,255,256):
        add('open-number-'+str(n),[],[f'open "2:f2own" as #{n}'],'1/2受理、0/3..255はERR52、256はERR5')
    add('open-nohash',[],['open "2:f2own" as 1'],'ERR0')
    add('open-double-number',[OP],[OP],'ERR54')
    add('open-double-name',[OP],['open "2:f2own" as #2'],'ERR54')
    for width in (127,128,129):
        add('field-width-'+str(width),[OP],[f'field #1,{width} as a$',boolean(65,f'len(a$)={width}')],
            '128以下ERR0・長さ印1、129はERR50')
    add('field-sum-exact',[OP],['field #1,64 as a$,64 as b$',boolean(65,'len(a$)=64 and len(b$)=64')],'ERR0・印1')
    add('field-sum-over',[OP],['field #1,64 as a$,65 as b$'],'ERR50')
    add('field-multiple',[OP,FIELD],['field #1,4 as b$','lset b$="ab"',boolean(65,'left$(a$,4)=b$')],'ERR0・先頭を共有、印1')
    add('field-let',[OP,'field #1,4 as a$'],['a$="z"','put #1,1','field #1,4 as b$',
        'lset b$="xxxx"','get #1,1',boolean(65,'a$="z"'),boolean(66,'b$="z   "')],
        'LETで結合解除、a$保持印1・媒体z印0を仮説')
    add('field-closed',[],[FIELD],'ERR60')
    add('field-after-close',[OP,'close'],[FIELD],'ERR60')
    for verb in ('lset','rset'):
        for tag,value in (('short','ab'),('equal','abcd'),('long','abcdef'),('empty','')):
            want=(value[:4].ljust(4) if verb=='lset' else value[:4].rjust(4))
            add(verb+'-'+tag,[OP,'field #1,4 as a$'],[f'{verb} a$="{value}"',boolean(65,f'a$="{want}"'),'put #1,1'],
                'ERR0・長さ4、LSET右空白/RSET左空白、超過は先頭4・印1',bodies={tag:want.encode()+bytes(124)})
        add(verb+'-ordinary',['a$="xxxx"'],[f'{verb} a$="ab"',boolean(65,'len(a$)=4')],'ERR0・元長保持・印1')
    for verb in ('put','get'):
        for tag,n in (('omit',None),('one',1),('two',2),('large',33),('zero',0),('negative',-1)):
            target=[verb+' #1'+('' if n is None else ','+str(n))]+number(21,'loc(1)')+number(23,'lof(1)')
            add(verb+'-'+tag,[OP,FIELD,'lset a$="ab"'],target,
                ('正番号/省略はERR0、LOC=対象番号・LOF=256Bセクタ数、0/負はERR63を仮説' if verb=='put' else
                 '未書込GETはERR55、0/負はERR63を仮説'),bodies=record_candidates(128,[(n or 1,b'ab'+b' '*126)]) if verb=='put' and (n is None or n>0) else None)
    add('put-next',[OP,FIELD,'lset a$="ab"'],['put #1','put #1']+number(21,'loc(1)')+number(23,'lof(1)'),
        'ERR0・LOC2・LOF1・128Bを2個詰める',bodies=record_candidates(128,[(1,b'ab'+b' '*126),(2,b'ab'+b' '*126)]))
    add('get-next',[OP,FIELD,'rset a$="ab"','put #1,1','rset a$="cd"','put #1,2','close',OP,FIELD],
        ['lset a$="xx"','get #1',boolean(65,'right$(a$,2)="ab"'),'lset a$="yy"','get #1',boolean(66,'right$(a$,2)="cd"')]+number(21,'loc(1)'),
        'ERR0・2読戻印1・LOC2')
    for size in (1,128,256):
        payload=b'a'*size
        add('record-size-'+str(size),[OP+f' len={size}',f'field #1,{size} as a$',f'lset a$=string$({size},97)'],
            ['put #1,1','put #1,2']+number(21,'loc(1)')+number(23,'lof(1)'),
            'ERR0・LOC2・LOF=ceil(2*LEN/256)、packed候補',bodies=record_candidates(size,[(1,payload),(2,payload)]))
    add('roundtrip-two',[OP,FIELD,'rset a$="ab"','put #1,1','rset a$="cd"','put #1,2','close',OP,FIELD],
        ['lset a$="xxxx"',boolean(67,'right$(a$,2)<>"ab"'),'get #1,1',boolean(65,'right$(a$,2)="ab"'),
         'lset a$="yyyy"',boolean(68,'right$(a$,2)<>"cd"'),'get #1,2',boolean(66,'right$(a$,2)="cd"')],
        'ERR0・破壊2印と読戻2印がすべて1',bodies=record_candidates(128,[(1,b' '*126+b'ab'),(2,b' '*126+b'cd')]))
    add('overwrite',[OP,FIELD,'lset a$="ab"','put #1,1'],['lset a$="cd"','put #1,1']+number(23,'lof(1)'),
        'ERR0・LOF1維持・cdに置換',bodies=record_candidates(128,[(1,b'cd'+b' '*126)]))
    add('loc-before',[OP],number(21,'loc(1)')+number(23,'lof(1)'),'ERR0・LOC0・LOF0')
    add('loc-after-get',[OP,FIELD,'rset a$="ab"','put #1,2'],['get #1,2']+number(21,'loc(1)')+number(23,'lof(1)'), 'ERR0・LOC2・LOF1')
    for mk,cv,size in (('mki$','cvi',2),('mks$','cvs',4),('mkd$','cvd',8)):
        for value in (0,1,-1,12345):
            encoded=encoding(value,size)
            add(mk[:-1]+'-'+str(value).replace('-','minus'),[],[f'b$={mk}({value})',boolean(65,f'len(b$)={size}'),
                boolean(66,f'{cv}(b$)={value}'),OP,f'field #1,{size} as a$','lset a$=b$','put #1,1'],
                f'ERR0・長さ{size}印1・往復印1・整数LE/MBF候補',bodies=record_candidates(size,[(1,encoded)]))
        for length in (0,size-1,size+1):
            add(cv+'-length-'+str(length),[],[f'x={cv}(string$({length},97))'],
                '短すぎる文字列ERR5、長い文字列は先頭の規定長を使用してERR0を仮説')
    add('mixed-seq-random',[],['open "2:f2own" for output as #1','print #1,"ab";','close',OP,
        'field #1,2 as a$','lset a$="xx"','get #1,1',boolean(65,'a$="ab"')],'ERR0・印1')
    return aa

def encoding(value,size):
    if size==2: return value.to_bytes(2,'little',signed=True)
    if not value: return bytes(size)
    data=bytearray(mem.mbf_integer(abs(value),size))
    if value<0: data[-2]|=128
    return bytes(data)

def record_candidates(size,records):
    result={}
    for layout,stride in [('packed',size),('sector',((size+255)//256)*256)]:
        end=max(n for n,_ in records)*stride
        length=((end+255)//256)*256
        for pad in (0,32,26):
            data=bytearray([pad])*length
            for n,body in records: data[(n-1)*stride:(n-1)*stride+len(body)]=body
            result[f'{layout}-pad{pad}']=bytes(data)
    return result

def serial_plan():
    return [{**a,'bodies':{k:hashlib.sha256(v).hexdigest() for k,v in a['bodies'].items()}} for a in arms()]

def signatures():
    return (hashlib.sha256(json.dumps(serial_plan(),sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            hashlib.sha256(json.dumps([program(a) for a in arms()],separators=(',',':')).encode()).hexdigest())

def inspect(image,a):
    # ヘッダ、ディレクトリ、FATは案内。本体は対象名の当該鎖だけ。SUBでも切らない。
    entry=None
    for r in range(1,13):
        directory=seq.sector(image,18,1,r)
        for j in range(0,256,16):
            if directory[j]==255: break
            if directory[j:j+9]==NAME.ljust(9,b' '): entry=directory[j:j+11];break
        if entry is not None or 255 in directory[::16]: break
    if entry is None: return {'found':False}
    fat=seq.sector(image,18,1,14)[:160]; unit=entry[10];seen=set();data=bytearray()
    while True:
        if unit>=160 or unit in seen or unit in (74,75): raise ValueError('chain')
        seen.add(unit);t=fat[unit];n=8 if t<160 else t-192
        if not 0<=n<=8: raise ValueError('end')
        for k in range(n):
            track,rr=divmod(unit*8+k,16);c,h=divmod(track,2)
            data+=seq.sector(image,c,h,rr+1)
        if t>=160: break
        unit=t
    return dict(found=True,type00=entry[9]==0,length=len(data),sha256=hashlib.sha256(data).hexdigest(),
                matches=sorted(k for k,b in a['bodies'].items() if b==data))

def valid(o,a):
    if type(o) is not dict or set(o)!={'values','writes','media','conditions','io_counts'}: return False
    if set(o['conditions'])!=set(CONDITIONS) or not all(v is True for v in o['conditions'].values()): return False
    if not mem.memory_valid({k:o[k] for k in ('values','writes')},a): return False
    d=o['media']
    if d=={'found':False}: return True
    return (type(d) is dict and set(d)=={'found','type00','length','sha256','matches'} and d['found'] is True
        and type(d['type00']) is bool and type(d['length']) is int and 0<=d['length']<=327680
        and d['length']%256==0 and type(d['sha256']) is str and re.fullmatch('[0-9a-f]{64}',d['sha256']) is not None
        and type(d['matches']) is list and d['matches']==sorted(set(d['matches'])) and all(k in a['bodies'] for k in d['matches']))

def comparable(o): return seq.comparable(o)

def synth(a,err=0):
    o=COMMON_SYNTH(a,err)
    o.update(conditions={k:True for k in CONDITIONS},io_counts={})
    return o

def gates(rs,exclude=()):
    projected=[dict(r,obs=[{k:v for k,v in o.items() if k not in ('conditions','io_counts')} for o in r['obs']]) for r in rs]
    # expected/checkの束縛中も、較正は共通器具の素の合成観測と照合する。
    with patch.object(seq,'synth',COMMON_SYNTH): return COMMON_GATES(projected,exclude)

def schedule(a,official): return seq.schedule(a,official)

def windows(a,official):
    typed,finish=schedule(a,official);run=next(t for t,c in typed if c=='run\n')
    return typed,finish,[(typed[0][0],run-1),(run-1,finish)]

def diagnostic(memory_raw,io_raw,start,finish,a):
    o,c=seq.memory_conditions(memory_raw,start,finish,a)
    drops=re.findall(r'^# 取りこぼし: (\d+)件 / 総イベント数: \d+件$',io_raw,re.M)
    c['io_no_loss']=len(drops)==2 and all(n=='0' for n in drops)
    return o,c

def redact(path):
    if not path.exists(): return
    p=subprocess.run([sys.executable,str(REPO/'tools/redact_iolog.py'),'--in-place',str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.returncode: path.unlink(missing_ok=True);raise RuntimeError('redaction')
    with path.open('rb') as src,gzip.open(str(path)+'.redacted.gz','wb',compresslevel=1) as dest: shutil.copyfileobj(src,dest)
    path.unlink()

def capture(rom,official,a,work):
    typed,finish,intervals=windows(a,official);start=typed[0][0]
    prefix=None; counts={};o=None;c={k:None for k in CONDITIONS}
    for ix,(io_from,end) in enumerate(intervals):
        part=work/('prefix' if ix==0 else 'run');part.mkdir(exist_ok=True)
        memory_path=part/'memory.txt';io_path=part/'io.txt'
        argv=[str(mem.kw.FRONT),'--core',str(mem.kw.find_core()),'--rom-dir',str(rom)]
        for frame,cmd in typed:
            if frame<end: argv+=['--type-at',str(frame),'--type',cmd]
        argv+=['--mem-write-log',str(memory_path),'--mem-write-range',mem.RANGE,'--mem-write-from-frame',str(start),
               '--io-log',str(io_path),'--io-log-from-frame',str(io_from),'--frames',str(end)]
        try:
            argv+=seq.prepare(part,{'fixture':None},official)
            p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'),timeout=240)
            if p.returncode: raise mem.ExecutionDenied('execution denied')
            if b'untypable' in p.stderr.lower(): raise RuntimeError('typing')
            mraw=memory_path.read_text();iraw=io_path.read_text();counts[str(ix)]=seq.io_counts(iraw,mraw)
            if ix==0:
                drops=re.findall(r'^# 取りこぼし: (\d+)件 / 総イベント数: \d+件$',iraw,re.M)
                c['prefix_no_loss']=len(drops)==2 and all(n=='0' for n in drops) and bool(re.search(r'^# 取りこぼし: 0件 / 総イベント数: 0件$',mraw,re.M))
                c['prefix_marks_absent']=not any(re.match(r'^\s*\d+\s',row) for row in mraw.splitlines())
                prefix=(part/'b.d88').read_bytes()
            else:
                o,tail=diagnostic(mraw,iraw,start,end,a);c.update(tail)
                # 別起動の同じ前半が同じか。打鍵/RUN境界まで印0、媒体は初期空媒体のまま。
                before=[row for row in mraw.splitlines() if re.match(r'^\s*\d+\s',row) and int(row.split()[1])<io_from]
                c['replay_equal']=not before and prefix==seq.fixture_image(None)
                try: media=inspect((part/'b.d88').read_bytes(),a);c['media_known']=True
                except (ValueError,IndexError,struct.error): media={'unknown':True};c['media_known']=False
        except (PermissionError,mem.ExecutionDenied):
            raise
        except Exception as exc:
            exc.conditions=copy.deepcopy(c);exc.io_counts=copy.deepcopy(counts)
            raise
        finally:
            try: redact(io_path)
            finally:
                for name in ('memory.txt','io.txt','a.d88','b.d88'): (part/name).unlink(missing_ok=True)
    if o is None or not all(v is True for v in c.values()): return dict(failure='GateError',conditions=c,io_counts=counts)
    return dict(**o,media=media,conditions=c,io_counts=counts)

def measure(rom,official,work):
    safety(work)
    if official and seq.reference_disk() is None: raise ValueError('PC88_REF_DISK_DIR_missing')
    def run(a):
        obs=[]
        for j in (1,2):
            dest=work/(a['id']+'-'+str(j));dest.mkdir(exist_ok=True)
            try: obs.append(capture(rom,official,a,dest))
            except (PermissionError,mem.ExecutionDenied): raise
            except Exception as exc: obs.append(dict(failure=type(exc).__name__,conditions=getattr(exc,'conditions',{k:None for k in CONDITIONS}),io_counts=getattr(exc,'io_counts',{})))
        gate=all(valid(o,a) for o in obs) and comparable(obs[0])==comparable(obs[1])
        print(a['id']+': '+('pass' if gate else 'gate_failed'),flush=True)
        return dict(arm=a,obs=obs,gate=gate)
    if official: return [run(a) for a in arms()]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool: return list(pool.map(run,arms()))

def emit(path,rs):
    g=gates(rs)
    mem.write_tsv(path,['arm','repeat','plan_sha','program_sha','observation','gate'],
        [[r['arm']['id'],j+1,PLAN_SHA,PROGRAM_SHA,json.dumps(o,sort_keys=True),'pass' if r['gate'] and g['passed'] else 'gate_failed'] for r in rs for j,o in enumerate(r['obs'])])
    return g['passed']

def read_passed(path,exclude=(),strict_excluded=True):
    ex=set(exclude);known={a['id']:a for a in arms()};groups={}
    if not ex<=set(known) or ex&set(PROTECTED): raise ValueError('exclude')
    with path.open() as f:
        for row in csv.DictReader(f,delimiter='\t'): groups.setdefault(row['arm'],[]).append(row)
    if set(groups)!=set(known): raise ValueError('arms')
    rs=[]
    for aid,rows in groups.items():
        if len(rows)!=2 or {r['repeat'] for r in rows}!={'1','2'}: raise ValueError('repeat')
        if any((r['plan_sha'],r['program_sha'])!=(PLAN_SHA,PROGRAM_SHA) or r['gate'] not in ('pass','gate_failed') for r in rows): raise ValueError('signature')
        if not ex and any(r['gate']!='pass' for r in rows): raise ValueError('gate')
        obs=[json.loads(r['observation']) for r in rows];a=known[aid]
        ok=all(valid(o,a) for o in obs) and comparable(obs[0])==comparable(obs[1])
        if aid in ex:
            if ok and strict_excluded: raise ValueError('excluded arm passed')
        elif not ok: raise ValueError('observations')
        rs.append(dict(arm=a,obs=obs,gate=ok))
    if not gates(rs,ex)['passed']: raise ValueError('global gate')
    return {r['arm']['id']:{k:r['obs'][0][k] for k in ('values','media')} for r in rs if r['arm']['id'] not in ex}

@contextmanager
def common_expected():
    # 順次器具の汎用expected/checkを、呼出し中だけ本測定の定義に束縛。実走とは並行しない。
    with patch.multiple(seq,arms=arms,valid=valid,synth=synth,read_passed=read_passed,
                        PLAN_SHA=PLAN_SHA,PROGRAM_SHA=PROGRAM_SHA,KNOWN_DIFFERENCES=KNOWN_DIFFERENCES): yield

def expected(out,paths,exclude):
    with common_expected(): return seq.first_expected(out,paths,exclude)

def check(exp,path,exclude):
    with common_expected(): return seq.first_check(exp,path,exclude)

def safety(work):
    work.mkdir(parents=True,exist_ok=True)
    assert signatures()==(PLAN_SHA,PROGRAM_SHA),'signature'
    aa=arms();assert 60<=len(aa)<=90 and len({a['id'] for a in aa})==len(aa)
    assert all(a['lifecycle'] is None and a['fixture'] is None and a['prediction'] for a in aa)
    for a in aa:
        assert all('load ' not in cmd for stage in a['stages'] for cmd in stage)
        for official in (False,True):
            typed,end,intervals=windows(a,official)
            assert intervals[0][0]==typed[0][0] and intervals[0][1]==intervals[1][0] and intervals[1][1]==end


def synthetic(work):
    safety(work);aa=arms()
    rs=[dict(arm=a,obs=[synth(a),synth(a)],gate=True) for a in aa]
    image=bytearray(blank.build())
    seq.write_sector(image,18,1,1,NAME.ljust(9,b' ')+bytes([0,72])+bytes([255])*5)
    for r in (14,15,16):
        fat=bytearray(seq.sector(image,18,1,r));fat[72]=193;seq.write_sector(image,18,1,r,fat)
    seq.write_sector(image,18,0,1,aa[2]['bodies']['ok-crlf-sub'])
    for o in rs[2]['obs']: o['media']=inspect(image,aa[2])
    rs[-1]['obs']=[synth(aa[-1],5) for _ in (1,2)]
    assert all(valid(o,r['arm']) for r in rs for o in r['obs']) and gates(rs)['passed']
    good=inspect(image,aa[2]);seq.write_sector(image,18,0,1,b'pk\r\n\x1a'+bytes(251));bad=inspect(image,aa[2])
    assert good['matches']==['ok-crlf-sub'] and not bad['matches'] and good['sha256']!=bad['sha256']
    # SUB後のバイトも照合対象。別ファイルの本体は読まない。
    seq.write_sector(image,18,0,1,b'ok\r\n\x1a'+bytes(250)+b'x');assert not inspect(image,aa[2])['matches']
    empty=blank.build();assert inspect(empty,aa[2])=={'found':False}
    # 訪問する本体は当該鎖のみ。別エントリとその本体を加えても観測不変。
    tracked=[];original_sector=seq.sector
    def tracked_sector(img,c,h,r):
        tracked.append((c,h,r));return original_sector(img,c,h,r)
    before=inspect(image,aa[2])
    seq.write_sector(image,18,1,1,NAME.ljust(9,b' ')+bytes([0,72])+bytes([255])*5+b'other'.ljust(9,b' ')+bytes([0,71])+bytes([255])*5)
    with patch.object(seq,'sector',side_effect=tracked_sector): assert inspect(image,aa[2])==before
    assert all((c,h,r)==(18,0,1) or (c,h)==(18,1) for c,h,r in tracked)
    for terminal in (72,255,201):
        corrupt=bytearray(image);fat=bytearray(seq.sector(corrupt,18,1,14));fat[72]=terminal;seq.write_sector(corrupt,18,1,14,fat)
        try: inspect(corrupt,aa[2])
        except ValueError: pass
        else: raise AssertionError('corrupt chain accepted')
    raw=mem.fake_log(synth(aa[0]));iraw='# main\n# 取りこぼし: 0件 / 総イベント数: 0件\n# sub\n# 取りこぼし: 0件 / 総イベント数: 0件\n'
    o,c=diagnostic(raw,iraw,100,2000,aa[0]);assert all(c.values())
    for key,m,i,end in [('stable',raw,iraw,200),('logical_marks',raw.replace('C303 A3','C303 A2'),iraw,2000),
                        ('memory_no_loss',raw.replace('取りこぼし: 0','取りこぼし: 1'),iraw,2000),
                        ('io_no_loss',raw,iraw.replace('取りこぼし: 0','取りこぼし: 1',1),2000)]:
        _,c=diagnostic(m,i,100,end,aa[0]);assert c[key] is False
    for err in (0,2,33):
        bad=copy.deepcopy(rs)
        for r in bad[3:]: r['obs']=[synth(r['arm'],err) for _ in (1,2)]
        assert not gates(bad)['nonuniform'] and not gates(bad)['passed']
    bad=copy.deepcopy(rs);bad[2]['obs'][0]['media']={'found':False};assert not gates(bad)['positive']
    for key in CONDITIONS:
        bad=copy.deepcopy(rs);bad[-2]['obs'][0]['conditions'][key]=False
        assert not valid(bad[-2]['obs'][0],bad[-2]['arm'])
    path=work/'synthetic.tsv';exp=work/'expected.tsv';emit(path,rs)
    assert expected(exp,[path],{})==len(aa) and check(exp,path,{})==(len(aa),[])
    bad=copy.deepcopy(rs);bad[-2]['obs'][1]['values']['p65']=1;bad[-2]['gate']=False;emit(path,bad)
    try: expected(exp,[path],{})
    except ValueError: pass
    else: raise AssertionError('mismatch accepted')
    ex={aa[-2]['id']:'合成2走不一致'}
    assert expected(exp,[path],ex)==len(aa)-1 and check(exp,path,ex)==(len(aa)-1,[])
    emit(path,rs)
    for ex in ({'cal-poke':'禁止'},{'absent':'不明'},{aa[4]['id']:'通過腕'}):
        try: expected(exp,[path],ex)
        except ValueError: pass
        else: raise AssertionError('exclude accepted')
    for items in (['x='],['x=a','x=b'],['x']):
        try: seq.parse_exclude(items)
        except ValueError: pass
        else: raise AssertionError('exclude reason accepted')
    # 準備は自作媒体だけで検査し、参照媒体は開かない。
    with patch.dict(os.environ,{},clear=True):
        part=work/'media';part.mkdir(exist_ok=True);seq.prepare(part,{'fixture':None},False)
        assert seq.sector((part/'a.d88').read_bytes(),18,1,13)==bytes([16])*256
        assert (part/'b.d88').read_bytes()==blank.build()
        for p in part.iterdir(): p.unlink()
    print(f'OK 合成自己検査 {len(aa)}腕・陰性対照・候補変異・関門・exclude',flush=True)

def capture_selftest(work):
    a=arms()[0];typed,finish,intervals=windows(a,False)
    raw=mem.fake_log(synth(a))
    raw='\n'.join(' '.join([row.split()[0],str(intervals[1][0]+100+int(row.split()[0]))]+row.split()[2:]) if re.match(r'^\d+ ',row) else row for row in raw.splitlines())+'\n'
    empty_raw=f'range     : {mem.RANGE}\n# 取りこぼし: 0件 / 総イベント数: 0件\n'
    io_raw='# main\n# 取りこぼし: 0件 / 総イベント数: 0件\n# sub\n# 取りこぼし: 0件 / 総イベント数: 0件\n'
    mode={'failure':None};calls=[]
    def fake(argv,**kwargs):
        if '--in-place' in argv: return subprocess.CompletedProcess(argv,0,b'',b'')
        get=lambda k:argv[argv.index(k)+1]
        end=int(get('--frames'));prefix=end==intervals[0][1]
        calls.append((int(get('--io-log-from-frame')),end))
        m=empty_raw if prefix else raw
        i=io_raw
        if mode['failure']=='prefix_no_loss' and prefix: i=i.replace('取りこぼし: 0','取りこぼし: 1',1)
        if mode['failure']=='prefix_marks_absent' and prefix: m=m.replace('# 取りこぼし:',f'1 {intervals[0][0]} 0000 C301 01\n# 取りこぼし:')
        if mode['failure']=='logical_marks' and not prefix: m=m.replace('C303 A3','C303 A2')
        if mode['failure']=='io_no_loss' and not prefix: i=i.replace('取りこぼし: 0','取りこぼし: 1',1)
        Path(get('--mem-write-log')).write_text(m);Path(get('--io-log')).write_text(i)
        assert '--vram-dump' not in argv and '--screenshot' not in argv
        assert kwargs['stdout']==subprocess.PIPE and kwargs['stderr']==subprocess.PIPE
        return subprocess.CompletedProcess(argv,0,b'synthetic-screen-secret',b'synthetic-screen-secret')
    def prepare(part,arm,official):
        (part/'b.d88').write_bytes(blank.build());return []
    dest=work/'capture-synthetic';dest.mkdir(exist_ok=True)
    with patch.object(subprocess,'run',side_effect=fake),patch.object(seq,'prepare',side_effect=prepare),patch.object(mem.kw,'find_core',return_value=Path('synthetic-core')):
        good=capture(Path('synthetic-rom'),False,a,dest)
        assert valid(good,a) and calls==intervals
        assert 'synthetic-screen-secret' not in json.dumps(good)
        for key in ('prefix_no_loss','prefix_marks_absent','logical_marks','io_no_loss'):
            mode['failure']=key
            bad=capture(Path('synthetic-rom'),False,a,dest)
            assert bad['failure']=='GateError' and bad['conditions'][key] is False
            assert not any(k in bad for k in ('values','writes','media'))
    assert not list(dest.rglob('io.txt')) and not list(dest.rglob('*.d88')) and not list(dest.rglob('memory.txt'))
    print('OK 区間接続・打鍵開始採取・失敗条件保存・本文非出力・後始末',flush=True)

def report(rs,seconds,status='完了'):
    from collections import Counter
    counts=Counter(str(o.get('values',{}).get('first_err','不明')) for r in rs for o in r['obs'])
    frames=sum(sum(end for _,end in windows(a,True)[2])*2 for a in arms())
    ownframes=sum(sum(end for _,end in windows(a,False)[2])*2 for a in arms())
    lines=['# l4-f2 第1回報告',f'状態: {status}',f'腕数: {len(arms())}。各2走、各走は打鍵前半とRUN以降の2起動で分割。',
        'CLAUDE.mdを最初に読んだ。公式ROM未実行・バイト列未読・画面未取得。src変更・commit・run_allなし。',
        '取得範囲の逸脱: 仕様探索の初期rgで指定節外の見出し・種別/鎖の該当断片も表示。全文は読んでいない。事前登録へ記録し、当該断片を追加の仕様根拠にしない。',
        '自己検査: 合成較正・陽性/陰性・一様ERR0/2/33・媒体候補変異・各関門失敗・2走不一致・expected/check・excludeを検査。',
        f'自作ROMの試走一式: {len(rs)}腕×2走。器具関門 {sum(r["gate"] for r in rs)}/{len(rs)}。壁時計 {seconds:.1f}秒。',
        '最初ERR集計（走単位）: '+json.dumps(dict(counts),ensure_ascii=False),
        '全体関門: '+json.dumps(gates(rs)),
        'PC88_REF_*なし。drive1は自作の書込禁止印媒体。未実装差と器具関門を区別し、全体関門失敗でも自己検査自体は通せる。',
        f'公式予定: {len(arms())*4}起動、計{frames}フレーム、60fps換算{frames/3600:.1f}分。各起動240秒上限の合計{len(arms())*4*240/3600:.1f}時間。',
        f'自作4並列実測から逐次へ比例換算: 約{seconds*4*frames/ownframes/60:.1f}分（ホスト依存）。',
        '|腕|2走器具関門|初回ERR|失敗条件|','|---|---|---|---|']
    for r in rs:
        o=r['obs'][0];lines.append('|'+r['arm']['id']+'|'+str(r['gate'])+'|'+str(o.get('values',{}).get('first_err','不明'))+'|'+json.dumps({k:v for k,v in o.get('conditions',{}).items() if v is not True})+'|')
    ROOT.mkdir(parents=True,exist_ok=True);(ROOT/'p1-report.md').write_text('\n'.join(lines)+'\n')

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('selftest');s.add_argument('--synthetic-only',action='store_true');s.add_argument('--work-dir',type=Path,default=ROOT/'selftest')
    m=sub.add_parser('measure');m.add_argument('--official',action='store_true');m.add_argument('--rom-dir',type=Path);m.add_argument('--work-dir',type=Path,required=True);m.add_argument('--out',type=Path,required=True)
    sub.add_parser('describe')
    e=sub.add_parser('expected');e.add_argument('--out',type=Path,required=True);e.add_argument('--exclude',action='append',default=[]);e.add_argument('paths',type=Path,nargs='+')
    c=sub.add_parser('check');c.add_argument('--expected',type=Path,required=True);c.add_argument('--measured',type=Path,required=True);c.add_argument('--exclude',action='append',default=[])
    args=p.parse_args()
    assert signatures()==(PLAN_SHA,PROGRAM_SHA),'signature'
    for key in ('work_dir','out','paths','expected','measured'):
        value=getattr(args,key,None)
        for path in value if isinstance(value,list) else [value] if value else []:
            if not path.is_absolute() or not path.resolve().is_relative_to(ROOT): p.error('作業root内の絶対パス必須')
    if args.command=='describe':
        for a in serial_plan(): print(json.dumps(a,ensure_ascii=False))
        return 0
    if args.command=='expected': print('期待値'+str(expected(args.out,args.paths,seq.parse_exclude(args.exclude)))+'腕');return 0
    if args.command=='check':
        ex=seq.parse_exclude(args.exclude)
        if not args.exclude:
            with args.expected.open() as f: ex=json.loads(next(csv.DictReader(f,delimiter='\t')).get('exclusions') or '{}')
        ok,bad=check(args.expected,args.measured,ex);print(f'一致{ok}腕・不一致{len(bad)}腕');return int(bool(bad))
    args.work_dir.mkdir(parents=True,exist_ok=True)
    if args.command=='selftest':
        synthetic(args.work_dir);capture_selftest(args.work_dir)
        if args.synthetic_only: return 0
        rom=args.work_dir/'rom'
        build=subprocess.run([sys.executable,str(REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(args.work_dir/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        if build.returncode: report([],0,'自作ビルド拒否または失敗');raise RuntimeError('自作ビルド失敗')
        start=time.monotonic()
        try: rs=measure(rom,False,args.work_dir)
        except (PermissionError,mem.ExecutionDenied): report([],time.monotonic()-start,'エミュレータ実行拒否');raise
        emit(args.work_dir/'selfrun.tsv',rs);report(rs,time.monotonic()-start)
        return int(not all(r['gate'] for r in rs))
    rom=os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir): p.error('公式はPC88_REF_ROM_DIR、自作は--rom-dir')
    return int(not emit(args.out,measure(rom,args.official,args.work_dir)))

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        import traceback
        tb=traceback.extract_tb(exc.__traceback__)
        print(f'NG 器具: {type(exc).__name__}、行{tb[-1].lineno}（本文非出力）');raise SystemExit(1)
