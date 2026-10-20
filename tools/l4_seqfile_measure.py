#!/usr/bin/env python3
"""l4-f1 順次ファイル。自作値の比較印と対象ファイルの候補署名だけを採る。"""
import sys
sys.dont_write_bytecode = True
import argparse, copy, csv, hashlib, io, json, os, re, shutil, struct, subprocess, tempfile, time
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch
import l4_mlcall_measure as mem
import build_blank_data_disk as blank

REPO = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('PC88_L4_SEQFILE_WORK', REPO / 'tmp/f1-work')).resolve()
BASE = mem.BASE
FIELDS = mem.FIELDS
KNOWN_DIFFERENCES = {}  # 期待値全体と観測全体が一致する理由付き規則だけ。事前免除なし。
PLAN_SHA = 'e9531797224d19bdae81978a4cc4091c92036014c8ea1fdccd69d9655a048816'
PROGRAM_SHA = '8ee7416ce43f7e7fe4a2ff8aa0d1250f6a446217877168e822759a86bd5c9d0a'
ADDENDUM_PLAN_SHA = '4c2c9968e41e9ed23ead9bbeb002eaccf9f43e57a22d2e5dc8532cb5f5158671'
ADDENDUM_PROGRAM_SHA = 'e0f7492a5478b7fcfb6f5503a5f327d925929044766cd418f086cbfa5243120e'
OFFICIAL = False
NAME = b'f1own'

def boolean(slot, expr): return f'poke {BASE+slot},abs({expr})'
def number(slot, expr):
    return [f'v={expr}', f'if v<0 then v=v+65536',
            f'poke {BASE+slot},v-256*int(v/256)', f'poke {BASE+slot+1},int(v/256)']
def candidates(text):
    """入力した文字だけから生成。生値はdescribe/ノート/結果に出さない。"""
    result = {}
    for label, value in text.items():
        for eol, suffix in [('crlf', b'\r\n'), ('cr', b'\r'), ('lf', b'\n'), ('none', b'')]:
            for eof, end in [('sub', b'\x1a'), ('none', b'')]:
                result[f'{label}-{eol}-{eof}'] = value + suffix + end
    return result

def arms():
    aa = []
    def add(aid, setup, target, cleanup=None, prediction='ERR0、比較印1を予測（仮説）', bodies=None, fixture=None, lifecycle=None):
        aa.append(dict(id=aid, stages=[setup, target, cleanup or ['close']],
                       commands=['stage1','stage2','stage3'], prediction=prediction,
                       bodies=bodies or {}, fixture=fixture, lifecycle=lifecycle))
    op = 'open "2:f1own" for output as #1'
    ip = 'open "2:f1own" for input as #1'
    add('cal-poke', ['poke &hc310,213'], ['rem calibration'], ['rem calibration'], 'cal213・ERR0')
    add('cal-error', [], ['error 13'], ['rem calibration'], 'ERR13@段2')
    add('disk-positive', [], [op, 'print #1,"ok"', 'close #1', ip, 'input #1,a$', boolean(65,'a$="ok"'), 'close #1'], ['rem done'], 'ERR0・比較印1・種別00・ok-crlf-sub', {'ok':b'ok'})
    for n in list(range(17))+[256]:
        add('open-number-'+str(n).replace('-','minus'), [], [f'open "2:f1own" for output as #{n}'], prediction='1..15受理、他ERR52を予測。最大は連続受理域と次番号で判定', bodies={'empty':b''})
    add('open-range-sweep', [], ['for n=1 to 255', 'q=0', 'open "2:f1own" for output as #n', f'if q=0 then poke {BASE+21},n:close #n', f'if q<>0 and peek({BASE+22})=0 then poke {BASE+22},n', 'next n'], ['rem sweep closed individually'], prediction='最大15・最初拒否16を予測。1..255全走査、256腕と合わせ最大を測る', bodies={'empty':b''})
    for tag, cmd, fixture, pred in [
        ('output',op,None,'ERR0'),('input',ip,'alpha','ERR0'),
        ('append','open "2:f1own" for append as #1','alpha','ERR0'),
        ('nohash','open "2:f1own" for output as 1',None,'ERR0'),
        ('short-o','open "o",#1,"2:f1own"',None,'ERR0またはERR2'),
        ('short-i','open "i",#1,"2:f1own"','alpha','ERR0またはERR2'),
        ('short-a','open "a",#1,"2:f1own"','alpha','ERR0またはERR2'),
        ('bad-mode','open "2:f1own" for banana as #1',None,'ERR2'),
        ('short-bad','open "x",#1,"2:f1own"',None,'ERR5またはERR2'),
        ('omit-drive','open "f1own" for output as #1',None,'既定drive1、ERR0。drive2非生成を予測'),
        ('double-number',op,None,'ERR54'),
        ('double-name','open "2:f1own" for output as #2',None,'ERR54'),
        ('wrong-type',ip,'binary','ERR59またはERR64'),
        ('missing',ip,None,'ERR53')]:
        add('open-'+tag,[op] if tag.startswith('double') else [],[cmd],prediction=pred,fixture=fixture,bodies={'empty':b'','alpha':b'alpha'})
    writes = [
        ('string','print #1,"alpha"',{'plain':b'alpha'}),
        ('empty','print #1,""',{'empty':b''}),
        ('positive','print #1,12',{'both':b' 12 ','right':b'12 ','none':b'12'}),
        ('negative','print #1,-12',{'right':b'-12 ','none':b'-12'}),
        ('semi','print #1,"a";"b"',{'joined':b'ab','space':b'a b'}),
        ('comma','print #1,"a","b"',{f'zone{n}':b'a'+b' '*n+b'b' for n in (0,1,12,13,14,15)}),
        ('trailing-semi','print #1,"a";',{'single':b'a'}),
        ('trailing-comma','print #1,"a",:print #1,"b"',{f'zone{n}':b'a'+b' '*n+b'b' for n in (0,1,12,13,14,15)}),
        ('blank','print #1,',{'empty':b''}),
        ('mixed','print #1,12;"a";-3',{'spaces':b' 12 a-3 ','compact':b'12a-3'}),
        ('write-string','write #1,"alpha"',{'quoted':b'"alpha"','plain':b'alpha'}),
        ('write-mixed','write #1,"a",12,-3,""',{'quoted':b'"a",12,-3,""','spaces':b'"a", 12 ,-3 ,""'}),
        ('write-quote','write #1,chr$(34)+"a"',{'raw':b'""a"','double':b'"""a"'}),
        ('using','print #1,using "###";12',{'field':b' 12','right':b'12 ','both':b' 12 '})]
    for tag,cmd,bs in writes:
        add('write-'+tag,[op],[cmd],['close #1'], 'ERR0・CRLF+SUB、数値前後空白、WRITE引用符/カンマを仮説。USINGはERR2も対立候補',bs)
    reads = [
        ('string','alpha',['input #1,a$',boolean(65,'a$="alpha"')],'ERR0・印1'),
        ('number','number',['input #1,a',boolean(65,'a=12')],'ERR0・印1'),
        ('negative','negative',['input #1,a',boolean(65,'a=-12')],'ERR0・印1'),
        ('comma','comma',['input #1,a$,b$',boolean(65,'a$="a" and b$="b"')],'ERR0・カンマで2値'),
        ('quote','quote',['input #1,a$',boolean(65,'a$="a,b"')],'ERR0・引用符内カンマ保持'),
        ('line-comma','comma',['line input #1,a$',boolean(65,'a$="a,b"')],'ERR0・カンマ保持'),
        ('line-quote','quote',['line input #1,a$',boolean(65,'a$=chr$(34)+"a,b"+chr$(34)')],'ERR0・引用符保持'),
        ('empty-line','empty',['line input #1,a$',boolean(65,'a$=""')],'ERR0・空文字'),
        ('two-lines','two',['line input #1,a$','line input #1,b$',boolean(65,'a$="a" and b$="b"')],'ERR0・CRLF除去'),
        ('bad-number','alpha',['input #1,a'],'ERR13を予測'),
        ('number-string','number',['input #1,a$',boolean(65,'a$="12"')],'ERR0・文字列12'),
        ('past-end','alpha',['input #1,a$','input #1,b$'],'ERR55'),
        ('line-past-end','alpha',['line input #1,a$','line input #1,b$'],'ERR55'),
        ('input-output',None,['input #1,a$'],'ERR54またはERR60'),
        ('print-input','alpha',['print #1,"x"'],'ERR54またはERR60')]
    for tag,fix,cmd,pred in reads:
        add('read-'+tag,[ip if fix else op],cmd,prediction=pred,fixture=fix)
    for func in ('eof','loc','lof'):
        for tag,fix,read in [('before','two',[]),('middle','two',['line input #1,a$']),('last','two',['line input #1,a$','line input #1,b$']),('long','long',['line input #1,a$','line input #1,b$'])]:
            add(func+'-'+tag,[ip],read+number(21,func+'(1)'),prediction=('EOF before/middle=0、last/long=-1' if func=='eof' else 'LOCは128B単位、LOFはセクタ割当量を仮説。実値16bitと候補比較で単位判定'),fixture=fix)
    for tag,cmd in [('hash','close #1'),('all','close'),('list','close 1,2')]:
        setup=[op,'print #1,"alpha"']
        if tag=='list': setup+=['open "2:f1two" for output as #2','print #2,"b"']
        add('close-'+tag,setup,[cmd],[ip,'input #1,a$',boolean(65,'a$="alpha"'),'close'],bodies={'alpha':b'alpha'})
    for tag,event in [('end','end'),('run','run'),('new','new'),('load','load "2:f1prog"')]:
        add('finish-'+tag,[op,'print #1,"alpha"'],[event],[ip,'input #1,a$',boolean(65,'a$="alpha"'),'close'],prediction='転送成立・再読印1・alpha-crlf-subを仮説',bodies={'alpha':b'alpha'},lifecycle=tag)
    for tag,event in [('end','end'),('run','run'),('new','new'),('load','load "2:f1prog"')]:
        add('flush-'+tag,[op,'print #1,"alpha"'],[event],['rem no close before media observation'],prediction='イベント直後の媒体がalpha-crlf-subに一致を予測。再読はfinish系列で独立観測',bodies={'alpha':b'alpha'},lifecycle=tag)
    add('kill-open',[op,'print #1,"alpha"'],['kill "2:f1own"'],prediction='ERR54を仮説',bodies={'alpha':b'alpha'})
    add('append-existing',['open "2:f1own" for append as #1'],['print #1,"beta"'],['close #1',ip,'line input #1,a$','line input #1,b$',boolean(65,'a$="alpha" and b$="beta"'),'close'],fixture='alpha',bodies={'joined':b'alpha\r\nbeta'},prediction='ERR0・既存SUBを置換して末尾追加・読戻印1')
    return aa

def addendum_arms():
    selected = []
    for a in arms():
        if a['id'] not in ('finish-run','flush-run','finish-load','flush-load'): continue
        a=copy.deepcopy(a);a['id']+='-a1'
        a.update(io_start='initial-run-minus-one', load_wait=36000, self_load_wait=7200)
        selected.append(a)
    control=copy.deepcopy(next(a for a in selected if a['id']=='flush-load-a1'))
    control.update(id='flush-load-control-a1', stages=[[], ['load "2:f1prog"'], ['rem no close before media observation']],
                   prediction='順次OPEN/PRINTなしのLOAD後最小経路で段2/3復帰・終了・600フレーム安定・取りこぼし0を予測。対象ファイル非生成')
    selected.append(control)
    return selected

def is_addendum(a): return a['id'].endswith('-a1')
def selected_arms(round_name): return addendum_arms() if round_name=='addendum1' else arms()
def round_signatures(round_name):
    return (ADDENDUM_PLAN_SHA,ADDENDUM_PROGRAM_SHA) if round_name=='addendum1' else (PLAN_SHA,PROGRAM_SHA)
def addendum_signatures():
    aa=addendum_arms()
    plan=[{**a,'bodies':{n:hashlib.sha256(b).hexdigest() for n,b in a['bodies'].items()}} for a in aa]
    return (hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            hashlib.sha256(json.dumps([program(a) for a in aa],separators=(',',':')).encode()).hexdigest())

FIXTURES = {'alpha':b'alpha\r\n\x1a','number':b'12\r\n\x1a','negative':b'-12\r\n\x1a',
            'comma':b'a,b\r\n\x1a','quote':b'"a,b"\r\n\x1a','empty':b'\r\n\x1a',
            'two':b'a\r\nb\r\n\x1a','long':(b'x'*100+b'\r\n')*3+b'\x1a','binary':b'own\x1a'}

def error_lines():
    return {9000:'q=1:e=err:s=peek(&hc301)',9001:'poke &hc304,1',
        9002:'if peek(&hc305)<>0 then 9005',9003:'poke &hc306,e',9004:'poke &hc307,s',
        9005:'poke &hc308,e:poke &hc309,s',9006:'if peek(&hc300+8+s*2)<>0 then 9008',
        9007:'poke &hc300+8+s*2,e',9008:'poke &hc300+9+s*2,e',
        9009:'poke &hc305,peek(&hc305)+1',9010:'resume next'}

def program(a):
    lines = {1:'clear ,&hbfff',2:'poke &hc300,197',3:'for i=1 to 95:poke &hc300+i,0:next i',4:'on error goto 9000',5:'poke &hc302,151'}
    if a['lifecycle']=='run':
        # 初回CLEARをON ERRORより前に置く。再RUN時は診断履歴を保つ。
        lines={n+1:cmd for n,cmd in lines.items()}
        lines[1]='if peek(&hc300)=197 and peek(&hc301)=2 then 7000'
    if a['lifecycle']=='load':
        # LOADの対象も自作。プログラム保存は順次出力を開く前に実施。
        lines[7]='save "2:f1prog",a'
    for stage, cmds in enumerate(a['stages'],1):
        n=1000*stage
        lines[n]=f'poke &hc301,{stage}'
        for j,cmd in enumerate(cmds): lines[n+1+j]=cmd
        lines[n+100]=f'poke {BASE+17+stage},77'
    lines.update({4000:'poke &hc301,3',4001:'poke &hc301,90',4002:'poke &hc303,163',4003:'goto 4003'})
    lines.update(error_lines())
    continuation=[]
    if a['lifecycle']:
        # 転送前の段2復帰印以降は実行させない。別の打鍵で復帰経路を作る。
        lines[2100]='end'
        del lines[3000]
        for k in list(lines):
            if 3000<k<4000: del lines[k]
        probe={7000:'on error goto 9000',7001:f'poke {BASE+19},77',7002:'poke &hc301,3'}
        for j,cmd in enumerate(a['stages'][2]): probe[7010+j]=cmd
        probe.update({7100:f'poke {BASE+20},77',7101:'poke &hc301,3',7102:'poke &hc301,90',7103:'poke &hc303,163',7104:'goto 7104'})
        probe.update(error_lines())
        continuation=[f'{n} {s}' for n,s in sorted(probe.items())]+['goto 7000']
        if a['id'].startswith('flush-'):
            # BASICを再RUN/END/CLOSEせず、転送後は直打ちPOKEだけで印を完了。
            continuation=[f'poke {BASE+19},77','poke &hc301,3',f'poke {BASE+20},77',
                          'poke &hc301,3','poke &hc301,90','poke &hc303,163']
        if a['lifecycle']=='run':
            # 再RUN後はプログラム内で印を完了。実行中の直打ちを待たない。
            if a['id'].startswith('flush-'):
                probe={7000:f'poke {BASE+19},77',7001:'poke &hc301,3',
                       7002:f'poke {BASE+20},77',7003:'poke &hc301,3',
                       7004:'poke &hc301,90',7005:'poke &hc303,163',7006:'goto 7006'}
            lines.update(probe)
            continuation=[]
    result=['new']+[f'{n} {s}' for n,s in sorted(lines.items())]+['run']+continuation
    assert all(len(c)<80 for c in result),a['id']
    assert sum(len(c)+1 for c in result)<8192,a['id']
    return result

# D88ヘッダはセクタ位置の案内のみ。本体は自作名の鎖に限定。
def sector(image,c,h,r):
    pos=struct.unpack_from('<I',image,32+(c*2+h)*4)[0]
    if not pos: raise ValueError('track')
    count=struct.unpack_from('<H',image,pos+4)[0]
    for _ in range(count):
        size=struct.unpack_from('<H',image,pos+14)[0]
        if tuple(image[pos:pos+3])==(c,h,r): return image[pos+16:pos+16+size]
        pos+=16+size
    raise ValueError('sector')

def write_sector(image,c,h,r,data):
    pos=struct.unpack_from('<I',image,32+(c*2+h)*4)[0]
    for _ in range(16):
        if tuple(image[pos:pos+3])==(c,h,r):
            image[pos+16:pos+16+len(data)]=data; return
        pos+=272
    raise ValueError('sector')

def fixture_image(fixture):
    image=bytearray(blank.build())
    if fixture:
        body=FIXTURES[fixture]; count=(len(body)+255)//256
        entry=NAME.ljust(9,b' ')+bytes([1 if fixture=='binary' else 0,72])+bytes([255])*5
        write_sector(image,18,1,1,entry)
        for r in (14,15,16):
            fat=bytearray(sector(image,18,1,r));fat[72]=0xc0+count;write_sector(image,18,1,r,fat)
        for k in range(count): write_sector(image,18,0,k+1,body[k*256:(k+1)*256])
    return bytes(image)

def inspect(image,a):
    entry=None
    for r in range(1,13):
        directory=sector(image,18,1,r)
        for j in range(0,256,16):
            if directory[j]==255: break
            if directory[j:j+9]==NAME.ljust(9,b' '): entry=directory[j:j+11];break
        if entry is not None or 255 in directory[::16]: break
    if entry is None: return dict(found=False)
    fat=sector(image,18,1,14)[:160]; unit=entry[10]; seen=set();data=bytearray()
    while True:
        if unit>=160 or unit in seen or unit in (74,75): raise ValueError('chain')
        seen.add(unit); t=fat[unit]
        n=8 if t<160 else t-0xc0
        if not 0<=n<=8: raise ValueError('end')
        for k in range(n):
            track,rr=divmod(unit*8+k,16);c,h=divmod(track,2)
            data+=sector(image,c,h,rr+1)
            # ASCIIの論理終端より後ろは照合・ハッシュに使わない。
            if 26 in data: break
        if 26 in data or t>=160: break
        unit=t
    end=data.find(26)
    logical=bytes(data[:end+1] if end>=0 else data)
    cc=candidates(a['bodies'])
    # fixtureを読む腕は既知fixture自体も候補に含める。
    if a['fixture']: cc['fixture-'+a['fixture']]=FIXTURES[a['fixture']]
    return dict(found=True,type00=entry[9]==0,length=len(logical),sha256=hashlib.sha256(logical).hexdigest(),
                matches=sorted(n for n,b in cc.items() if b==logical),terminated=end>=0)

def reference_disk():
    root=os.environ.get('PC88_REF_DISK_DIR')
    if not root: return None
    config=Path(os.environ.get('M6FF_FROZEN_CONFIG',REPO/'tools/m6ff_frozen.tsv'))
    with config.open() as f: rows=list(csv.reader(f,delimiter='\t'))
    names=[r[1] for r in rows if len(r)>=2 and r[0]=='reference_disk']
    if len(names)!=1 or Path(names[0]).name!=names[0]: raise ValueError('reference config')
    source=Path(root)/names[0]
    if not source.is_file(): raise ValueError('reference missing')
    return source

def prepare(work,a,official):
    source=reference_disk()
    if official and source is None: raise ValueError('PC88_REF_DISK_DIR_missing')
    try:
        if source: shutil.copyfile(source,work/'a.d88')
        else:
            # 第24.1節の起動構成: 既定ドライブ1は書込禁止。自作媒体で同じ条件を作る。
            substitute=bytearray(blank.build())
            write_sector(substitute,18,1,13,bytes([0x10])*256)
            (work/'a.d88').write_bytes(substitute)
        (work/'a.d88').chmod(0o600)
        (work/'b.d88').write_bytes(fixture_image(a['fixture']))
    except BaseException:
        for name in ('a.d88','b.d88'): (work/name).unlink(missing_ok=True)
        raise
    return ['--disk',str(work/'a.d88'),'--disk2',str(work/'b.d88'),'--save-to-disk-image']

def valid(o,a):
    if type(o) is not dict: return False
    if is_addendum(a):
        if set(o)!={'values','writes','media','conditions','io_counts'}: return False
        c=o['conditions']
        if type(c) is not dict or set(c)!={'stable','logical_marks','memory_no_loss','io_no_loss','pre_io_marks_absent'} or not all(v is True for v in c.values()): return False
    elif set(o)!={'values','writes','media'}: return False
    base={k:o[k] for k in ('values','writes')}
    # 自作の比較印は65..73、関数数値は21..29に限定。
    if not mem.memory_valid(base,a): return False
    d=o['media']
    if d in ({'found':False},{'unknown':True}): return True
    if type(d) is not dict or set(d)!={'found','type00','length','sha256','matches','terminated'}: return False
    return d['found'] is True and type(d['type00']) is bool and type(d['terminated']) is bool and type(d['length']) is int and 0<=d['length']<=327680 and bool(re.fullmatch('[0-9a-f]{64}',d['sha256'])) and type(d['matches']) is list and all(n in set(candidates(a['bodies']))|{'fixture-'+str(a['fixture'])} for n in d['matches'])

def schedule(a,official):
    at=1200 if official else 120; typed=[(300,'\n')] if official else []
    for cmd in program(a):
        typed.append((at,cmd+'\n'))
        at+=(len(cmd)+1)*(12 if official else 8)+(360 if official else 120)
        if cmd=='run' and a['lifecycle']:
            at+=(a['load_wait'] if official else a['self_load_wait']) if is_addendum(a) and a['lifecycle']=='load' else (18000 if official else 6000)
    return typed,at+(24000 if official else 6000)

def io_start(a,typed):
    # 印ログは打鍵開始から。入出力だけ、最初のRUNの打鍵直前から採る。
    return next(t for t,c in typed if c=='run\n')-1 if is_addendum(a) else typed[0][0]

def memory_conditions(raw,start,finish,a):
    conditions=dict(stable=None,logical_marks=None,memory_no_loss=False)
    totals=re.findall(r'^# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件$',raw,re.M)
    conditions['memory_no_loss']=len(totals)==1 and totals[0][0]=='0'
    # 取りこぼしがあっても安定/論理印を独立に診断する。採用判定には元のloss条件を必須とする。
    diagnostic=re.sub(r'(# 取りこぼし: )\d+',r'\g<1>0',raw)
    o=None
    try:
        o=mem.parse_log(diagnostic,start,finish,a)
        conditions.update(stable=True,logical_marks=True)
    except mem.GateError as exc:
        conditions['stable']=str(exc)!='安定'
        if conditions['stable']: conditions['logical_marks']=False
        else:
            try: mem.parse_log(diagnostic,start,10**15,a);conditions['logical_marks']=True
            except ValueError: conditions['logical_marks']=False
    except ValueError:
        conditions['logical_marks']=False
    return o,conditions

def io_counts(raw,memory_raw):
    # 値/PC列は参照せず、CPU別・段別の件数とポート番号の種類だけを残す。
    from bisect import bisect_right
    marks=[]
    for line in memory_raw.splitlines():
        parts=line.split()
        if len(parts)==5 and parts[0].isdigit() and parts[3]=='C301':
            marks.append((int(parts[1]),int(parts[4],16)))
    marks.sort();frames=[t for t,_ in marks]
    result={};cpu=None
    for line in raw.splitlines():
        if line in ('# main','# sub'):
            cpu=line[2:];result[cpu]=dict(stages={},ports={},recorded=0,dropped=None)
        parts=line.split()
        if cpu and len(parts)==8 and parts[0].isdigit():
            frame=int(parts[2]);port=parts[5];ix=bisect_right(frames,frame)-1
            stage=str(marks[ix][1]) if ix>=0 else 'before-stage1'
            d=result[cpu];d['stages'][stage]=d['stages'].get(stage,0)+1
            d['ports'][port]=d['ports'].get(port,0)+1
        m=re.fullmatch(r'# 取りこぼし: (\d+)件 / 総イベント数: (\d+)件',line)
        if m and cpu: result[cpu].update(dropped=int(m[1]),recorded=int(m[2]))
    return result

def addendum_observation(memory_raw,io_raw,start,finish,a,io_from):
    o,conditions=memory_conditions(memory_raw,start,finish,a)
    drops=re.findall(r'^# 取りこぼし: (\d+)件 / 総イベント数: \d+件$',io_raw,re.M)
    conditions['io_no_loss']=len(drops)==2 and all(int(n)==0 for n in drops)
    # 記録を省く区間には診断域の書込（段印を含む）が一つも無いことを確認。
    conditions['pre_io_marks_absent']=not any(len(p)==5 and p[0].isdigit() and int(p[1])<io_from
                                              for p in (line.split() for line in memory_raw.splitlines()))
    counts=io_counts(io_raw,memory_raw)
    if o is None or not all(v is True for v in conditions.values()):
        return dict(failure='GateError',conditions=conditions,io_counts=counts)
    return dict(**o,conditions=conditions,io_counts=counts)

def capture(rom,official,a,work):
    typed,finish=schedule(a,official); start=typed[0][0];io_from=io_start(a,typed)
    path=work/'memory.txt'; io_path=work/'io.txt'; safe_io=work/'io.redacted.txt'
    argv=[str(mem.kw.FRONT),'--core',str(mem.kw.find_core()),'--rom-dir',str(rom)]
    for frame,cmd in typed: argv+=['--type-at',str(frame),'--type',cmd]
    argv+=['--mem-write-log',str(path),'--mem-write-range',mem.RANGE,'--mem-write-from-frame',str(start),
           '--io-log',str(io_path),'--io-log-from-frame',str(io_from),'--frames',str(finish)]
    try:
        argv+=prepare(work,a,official)
        p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'),timeout=240)
        if p.returncode: raise mem.ExecutionDenied('execution denied')
        if b'untypable' in p.stderr.lower(): raise RuntimeError('typing')
        memory_raw=path.read_text();io_text=io_path.read_text()
        if is_addendum(a):
            o=addendum_observation(memory_raw,io_text,start,finish,a,io_from)
            if 'failure' in o: return o
        else: o=mem.parse_log(memory_raw,start,finish,a)
        drops=re.findall(r'^# 取りこぼし: (\d+)件 / 総イベント数: \d+件$',io_text,re.M)
        if len(drops)!=2 or any(int(n) for n in drops):
            raise mem.GateError('io log loss',[(0,i,v) for i,v in o['writes']])
        try: o['media']=inspect((work/'b.d88').read_bytes(),a)
        except (ValueError,IndexError,struct.error): o['media']={'unknown':True}
        return o
    finally:
        # データポートの生値を残さず、既存伏字器を通す。画面は取得しない。
        try:
            if io_path.exists():
                p=subprocess.run([sys.executable,str(REPO/'tools/redact_iolog.py'),'--in-place',str(io_path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                if p.returncode==0:
                    import gzip
                    with io_path.open('rb') as src, gzip.open(str(safe_io)+'.gz','wb',compresslevel=1) as dest:
                        shutil.copyfileobj(src,dest)
                else: raise RuntimeError('io redaction failed')
        finally:
            for name in ('memory.txt','io.txt','a.d88','b.d88'): (work/name).unlink(missing_ok=True)

def synth(a,err=0):
    ws=[[0,197]]+[[i,0] for i in range(1,96)]+[[2,151]]
    for j in range(1,4):
        ws.append([1,j])
        if a['id']=='cal-poke' and j==1: ws.append([16,213])
        e=13 if a['id']=='cal-error' and j==2 else err if j==2 else 0
        if e: ws+=mem.error_block(e,j,0,set())
        if a['id']=='disk-positive' and j==2 and not e: ws.append([65,1])
        ws.append([17+j,77])
    ws += [[1,3],[1,90],[3,163]]
    return dict(values={FIELDS[i]:v for i,v in ws},writes=ws,media={'found':False})

def gates(rs,exclude=()):
    # excludeは腕IDの明示だけ。除外腕は非一様判定と全体passedから外れる。較正・陽性の条件は緩めない。
    exclude=set(exclude)
    by={r['arm']['id']:r for r in rs}
    calibration=all(k in by and by[k]['gate'] and all(o==synth(by[k]['arm']) for o in by[k]['obs']) for k in ('cal-poke','cal-error'))
    c=by.get('disk-positive'); positive=bool(c and c['gate'] and all(o.get('values',{}).get('count')==0 and o['values'].get('p65')==1 and o.get('media',{}).get('type00') and 'ok-crlf-sub' in o['media'].get('matches',[]) for o in c['obs']))
    ee=[o.get('values',{}).get('first_err',o.get('errors',{}).get('first_err')) for r in rs if r['arm']['id'] not in ('cal-poke','cal-error','disk-positive') and r['arm']['id'] not in exclude for o in r['obs']]
    nonuniform=bool(ee) and None not in ee and len(set(ee))>1
    return dict(calibration=calibration,positive=positive,nonuniform=nonuniform,passed=calibration and positive and nonuniform and all(r['gate'] for r in rs if r['arm']['id'] not in exclude))

def measure(rom,official,work,round_name="first"):
    safety(work)
    if official and reference_disk() is None: raise ValueError('PC88_REF_DISK_DIR_missing')
    def run(a):
        obs=[]
        for j in (1,2):
            dest=work/(a['id']+'-'+str(j));dest.mkdir(exist_ok=True)
            try: obs.append(capture(rom,official,a,dest))
            except (PermissionError,mem.ExecutionDenied): raise
            except Exception as exc:
                obs.append(dict(failure=type(exc).__name__,conditions=dict(stable=None,logical_marks=None,memory_no_loss=None,io_no_loss=None,pre_io_marks_absent=None)) if is_addendum(a) else dict(failure=type(exc).__name__,errors=getattr(exc,'errors',{})))
        gate=all(valid(o,a) for o in obs) and comparable(obs[0])==comparable(obs[1])
        print(a['id']+': '+('pass' if gate else 'gate_failed'),flush=True)
        return dict(arm=a,obs=obs,gate=gate)
    if official: return [run(a) for a in selected_arms(round_name)]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool: return list(pool.map(run,selected_arms(round_name)))

def comparable(o): return {k:v for k,v in o.items() if k not in ("conditions","io_counts")}

def emit(path,rs,round_name="first"):
    g=gates(rs)
    plan_sha,program_sha=round_signatures(round_name)
    mem.write_tsv(path,['arm','repeat','plan_sha','program_sha','observation','gate'],
        [[r['arm']['id'],j+1,plan_sha,program_sha,json.dumps(o,sort_keys=True),'pass' if r['gate'] and g['passed'] else 'gate_failed'] for r in rs for j,o in enumerate(r['obs'])])
    return g['passed'] and all(r['gate'] for r in rs)

PROTECTED=('cal-poke','cal-error','disk-positive')
def read_passed(path,exclude=(),strict_excluded=True):
    """exclude: 器具関門を通らなかった腕IDの明示。指定が無ければ従来どおり全腕の関門成立を要求する。"""
    exclude=set(exclude)
    known={a['id']:a for a in arms()}; groups={}
    if not exclude<=set(known) or exclude&set(PROTECTED): raise ValueError('exclude')
    with path.open() as f:
        for row in csv.DictReader(f,delimiter='\t'): groups.setdefault(row['arm'],[]).append(row)
    if set(groups)!=set(known): raise ValueError('arms')
    rs=[]
    for aid,rows in groups.items():
        if len(rows)!=2 or {r['repeat'] for r in rows}!={'1','2'}: raise ValueError('repeat')
        if any(r['plan_sha']!=PLAN_SHA or r['program_sha']!=PROGRAM_SHA for r in rows): raise ValueError('signature/gate')
        # 除外指定が無いときは従来どおり行の関門欄がpassであること。除外指定時は全体関門が
        # 除外腕の失敗で落ちた記録をそのまま使うため、関門欄はpass/gate_failedのいずれかとし、
        # 各腕の成立は観測から再計算する（緩和ではなく再検算）。
        if any(r['gate']!='pass' for r in rows) and (not exclude or any(r['gate'] not in ('pass','gate_failed') for r in rows)): raise ValueError('signature/gate')
        obs=[json.loads(r['observation']) for r in rows];a=known[aid]
        ok=all(valid(o,a) for o in obs) and obs[0]==obs[1]
        if aid in exclude:
            if ok and strict_excluded: raise ValueError('excluded arm passed')  # 関門を通った腕は除外できない
        elif not ok: raise ValueError('observations')
        rs.append(dict(arm=a,obs=obs,gate=ok))
    if not gates(rs,exclude)['passed']: raise ValueError('global gate')
    return {r['arm']['id']:dict(values=r['obs'][0]['values'],media=r['obs'][0]['media']) for r in rs if r['arm']['id'] not in exclude}

def parse_exclude(items):
    """ARM=理由 の列を {腕ID: 理由} にする。理由が空なら拒否。"""
    out={}
    for item in items or []:
        aid,sep,reason=item.partition('=')
        if not sep or not aid or not reason.strip() or aid in out: raise ValueError('exclude')
        out[aid]=reason.strip()
    return out

def expected(out,paths,exclude=None):
    if len(paths)!=1: raise ValueError('one complete measurement')
    exclude=exclude or {}
    got=read_passed(paths[0],exclude)
    if exclude:
        note=json.dumps(exclude,sort_keys=True,ensure_ascii=False)
        mem.write_tsv(out,['arm','plan_sha','values','exclusions'],[[k,PLAN_SHA,json.dumps(v,sort_keys=True),note] for k,v in sorted(got.items())])
    else: mem.write_tsv(out,['arm','plan_sha','values'],[[k,PLAN_SHA,json.dumps(v,sort_keys=True)] for k,v in sorted(got.items())])
    return len(got)

def check(exp,path,exclude=None):
    exclude=exclude or {}
    with exp.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
    want={r['arm']:json.loads(r['values']) for r in rows}
    if len(want)!=len(rows) or set(want)!={a['id'] for a in arms()}-set(exclude) or any(r['plan_sha']!=PLAN_SHA for r in rows): raise ValueError('expected shape')
    # 除外は期待値ファイル自身が理由つきで持ち、呼び出し側の指定と完全一致していること。
    note=json.dumps(exclude,sort_keys=True,ensure_ascii=False) if exclude else None
    if any(r.get('exclusions')!=note for r in rows): raise ValueError('expected exclusions')
    for a in arms():
        if a['id'] in exclude: continue
        value=want[a['id']]
        if set(value)!={'values','media'}: raise ValueError('expected fields')
        o=synth(a);o['media']=value['media']
        if not valid(o,a) or set(value['values'])!=set(FIELDS) or any(type(n) is not int or not 0<=n<=255 for n in value['values'].values()): raise ValueError('expected content')
        if a['id'] in ('cal-poke','cal-error') and value!=dict(values=synth(a)['values'],media=synth(a)['media']): raise ValueError('expected calibration')
    try: got=read_passed(path,exclude,strict_excluded=False)
    except (ValueError,KeyError,TypeError): got={}
    bad=[]
    for k,v in want.items():
        if v==got.get(k): continue
        rule=KNOWN_DIFFERENCES.get(k)
        if not (rule and rule.get('reason') and rule.get('expected')==v and rule.get('measured')==got.get(k)): bad.append(k)
    return len(want)-len(bad),bad

def serial_plan(round_name="first"):
    return [{**a,'bodies':{n:hashlib.sha256(b).hexdigest() for n,b in a['bodies'].items()}} for a in selected_arms(round_name)]

def signatures():
    return (hashlib.sha256(json.dumps(serial_plan(),sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            hashlib.sha256(json.dumps([program(a) for a in arms()],separators=(',',':')).encode()).hexdigest())

def safety(work):
    work.mkdir(parents=True,exist_ok=True)
    assert signatures()==(PLAN_SHA,PROGRAM_SHA),'preregistration signature'
    aa=arms();assert 60<=len(aa)<=90 and len({a['id'] for a in aa})==len(aa)
    for a in aa:
        if a['lifecycle']=='run':
            commands=program(a)
            assert commands[-1]=='run'
            assert commands.index('2 clear ,&hbfff')<commands.index('5 on error goto 9000')
            assert '1 if peek(&hc300)=197 and peek(&hc301)=2 then 7000' in commands
            assert any(c.startswith('7000 ') for c in commands)
    rs=[dict(arm=a,obs=[synth(a),synth(a)],gate=True) for a in aa]
    # cal-pokeの位置は既存memory validatorに合わせて段1を使う。
    assert all(valid(o,r['arm']) for r in rs for o in r['obs'])
    cal=rs[2]
    img=bytearray(fixture_image('alpha'));write_sector(img,18,0,1,b'ok\r\n\x1a')
    for o in cal['obs']: o['media']=inspect(img,cal['arm'])
    # 非一様の陽性。ERRを使う対立腕を1つだけ変更。
    rs[-2]['obs']=[synth(rs[-2]['arm'],54) for _ in (1,2)]
    assert gates(rs)['passed']
    bad=copy.deepcopy(rs);bad[-1]['gate']=False
    assert not gates(bad)['passed']
    bad=copy.deepcopy(rs)
    for o in bad[2]['obs']: o['media']=inspect(blank.build(),bad[2]['arm'])
    assert gates(bad)['calibration'] and gates(bad)['nonuniform'] and not gates(bad)['positive']
    # 起動媒体誤り→ディスクBASIC不成立の観測を較正正常のまま模擬。
    bad[2]['obs']=[synth(bad[2]['arm'],33) for _ in (1,2)]
    assert not gates(bad)['passed']
    for err in (0,2,33):
        bad=copy.deepcopy(rs)
        for r in bad[3:]: r['obs']=[synth(r['arm'],err) for _ in (1,2)]
        assert gates(bad)['positive'] and not gates(bad)['nonuniform'] and not gates(bad)['passed']
    body=inspect(img,cal['arm']);assert body['matches']==['ok-crlf-sub']
    write_sector(img,18,0,1,b'pk\r\n\x1a');changed=inspect(img,cal['arm'])
    assert changed['matches']==[] and changed['length']==body['length'] and changed['sha256']!=body['sha256']
    assert not any(k in json.dumps(changed) for k in ('raw','payload'))
    # 生値余り・他ファイルを変えても当該対象の署名は変えない。
    write_sector(img,18,0,1,b'ok\r\n\x1aSECRET');assert inspect(img,cal['arm'])==body
    with tempfile.TemporaryDirectory(dir=work,prefix='synthetic-') as td:
        td=Path(td);out=td/'measurement.tsv';exp=td/'expected.tsv'
        assert emit(out,rs) and expected(exp,[out])==len(aa) and check(exp,out)==(len(aa),[])
        bad=copy.deepcopy(rs);bad[-1]['obs'][1]['values']['p21']=1
        assert not all(valid(o,bad[-1]['arm']) for o in bad[-1]['obs'])
        emit(out,bad)
        try: expected(exp,[out])
        except ValueError: pass
        else: raise AssertionError('repeat negative')
        assert check(exp,out)[1]
        # 腕IDを明示した除外: 関門を通らない腕があるときだけ、理由つきで除外できる。
        def rejects(f):
            try: f()
            except ValueError: return True
            return False
        bad=copy.deepcopy(rs);victim=bad[-1]['arm']['id'];other=bad[-2]['arm']['id']
        bad[-1]['obs']=[dict(failure='GateError',errors={}) for _ in (1,2)];bad[-1]['gate']=False
        emit(out,bad)
        ex={victim:'合成の関門落ち'}
        assert rejects(lambda:expected(exp,[out]))                       # 除外指定なしは従来どおり拒否
        assert rejects(lambda:expected(exp,[out],{other:'x'}))           # 別の腕の除外では落ちた腕が残り拒否
        assert rejects(lambda:expected(exp,[out],{other:'x',victim:'y'})) # 関門を通った腕は除外できない
        assert rejects(lambda:expected(exp,[out],{'cal-poke':'x',victim:'y'})) # 較正・陽性は除外できない
        assert rejects(lambda:expected(exp,[out],{'no-such-arm':'x',victim:'y'}))
        assert rejects(lambda:parse_exclude([victim+'=']))               # 理由なしは拒否
        assert rejects(lambda:parse_exclude([victim]))
        assert expected(exp,[out],ex)==len(aa)-1
        assert check(exp,out,ex)==(len(aa)-1,[])
        # 公式で除外された腕が自作で成立しても、比較対象の集合は変えない。
        emit(out,rs)
        assert rejects(lambda:expected(exp,[out],ex))
        assert check(exp,out,ex)==(len(aa)-1,[])
        emit(out,bad)
        assert rejects(lambda:check(exp,out))                            # 除外つき期待値は除外指定なしで検査できない
        assert rejects(lambda:check(exp,out,{victim:'別の理由'}))        # 理由が期待値の記録と違えば拒否
        two=copy.deepcopy(bad);two[-3]['obs']=[dict(failure='GateError',errors={}) for _ in (1,2)];two[-3]['gate']=False
        emit(out,two)
        assert rejects(lambda:expected(exp,[out],ex))                    # 2腕目の失敗は除外指定が無い限り拒否
        two=copy.deepcopy(bad);two[-3]['obs'][1]['values']['p21']=1       # 除外外の腕の2走不一致
        emit(out,two)
        assert rejects(lambda:expected(exp,[out],ex))
        emit(out,rs);expected(exp,[out])
        assert check(exp,out)==(len(aa),[]) and rejects(lambda:check(exp,out,ex))
    # 複数誤りの最初/最後と段履歴を保持し、矛盾を拒否する。
    a=aa[3];o=synth(a);ix=o['writes'].index([1,2])+1
    o['writes'][ix:ix]=mem.error_block(13,2,0,set())+mem.error_block(2,2,1,{2})
    o['values']={FIELDS[i]:n for i,n in o['writes']}
    assert valid(o,a) and o['values']['first_err']==13 and o['values']['s2_last']==2
    bad=copy.deepcopy(o);bad['values']['s2_first']=2;assert not valid(bad,a)
    try: mem.parse_log(mem.fake_log(o),100,200,a)
    except mem.GateError as exc: assert exc.errors['first_err']==13 and exc.errors['last_err']==2
    else: raise AssertionError('failed gate error retention')
    # 継承した開始/終了/段/初期化/安定/取りこぼしの検査を本器具の生成印で確認。
    a=aa[3];o=synth(a);raw=mem.fake_log({k:o[k] for k in ('values','writes')})
    assert mem.parse_log(raw,100,2000,a)=={k:o[k] for k in ('values','writes')}
    for text in (raw.replace('取りこぼし: 0','取りこぼし: 1'),raw.replace(mem.RANGE,'C301-C35F')):
        try: mem.parse_log(text,100,2000,a)
        except ValueError: pass
        else: raise AssertionError('log negative')
    try: mem.parse_log(raw,100,200,a)
    except mem.GateError: pass
    else: raise AssertionError('stability')
    with tempfile.TemporaryDirectory(dir=work,prefix='frontend-') as td:
        td=Path(td);source=td/'own-source.d88'
        boot=bytearray(blank.build());pos=struct.unpack_from('<I',boot,32)[0]
        boot[pos+8]=0;source.write_bytes(boot)
        real_run=subprocess.run; sink=io.StringIO()
        def fake(argv,**kwargs):
            if argv[0]!=str(mem.kw.FRONT): return real_run(argv,**kwargs)
            start=int(argv[argv.index('--mem-write-from-frame')+1])
            assert start==int(argv[argv.index('--io-log-from-frame')+1])==schedule(cal['arm'],True)[0][0][0]
            drive1=Path(argv[argv.index('--disk')+1]);drive2=Path(argv[argv.index('--disk2')+1])
            image=drive1.read_bytes();p=struct.unpack_from('<I',image,32)[0]
            disk_basic=image[p+8]==0
            obs=synth(cal['arm'],0 if disk_basic else 33)
            if disk_basic:
                image=bytearray(fixture_image('alpha'));write_sector(image,18,0,1,b'ok\r\n\x1a');drive2.write_bytes(image)
            raw=mem.fake_log(obs)
            raw=re.sub(r'^(\d+) (\d+) ',lambda x:f'{x[1]} {int(x[2])+start} ',raw,flags=re.M)
            Path(argv[argv.index('--mem-write-log')+1]).write_text(raw)
            Path(argv[argv.index('--io-log')+1]).write_text('# 取りこぼし: 0件 / 総イベント数: 0件\n'*2)
            return subprocess.CompletedProcess(argv,0,b'synthetic-screen-secret',b'synthetic-screen-secret')
        dest=td/'run';dest.mkdir()
        with patch.object(mem.kw,'find_core',return_value=Path('synthetic-core')),patch.object(subprocess,'run',side_effect=fake),redirect_stdout(sink),redirect_stderr(sink):
            with patch(__name__+'.reference_disk',return_value=source):
                positive=capture(Path('synthetic-rom'),True,cal['arm'],dest)
            source.write_bytes(blank.build())
            with patch(__name__+'.reference_disk',return_value=source):
                negative=capture(Path('synthetic-rom'),True,cal['arm'],dest)
        assert valid(positive,cal['arm']) and valid(negative,cal['arm'])
        front=copy.deepcopy(rs);front[2]['obs']=[positive,positive]
        assert gates(front)['passed']
        front[2]['obs']=[negative,negative]
        assert gates(front)['calibration'] and gates(front)['nonuniform'] and not gates(front)['positive']
        assert not sink.getvalue() and not list(dest.glob('*.d88')) and not (dest/'memory.txt').exists() and not (dest/'io.txt').exists()
    addendum_selftest(work)
    print(f'OK 合成自己検査 {len(aa)}腕: 媒体構成陰性・1B変異・一様ERR0/2/33・2走・署名・ログ関門',flush=True)

def addendum_selftest(work):
    assert signatures()==(PLAN_SHA,PROGRAM_SHA)
    assert addendum_signatures()==(ADDENDUM_PLAN_SHA,ADDENDUM_PROGRAM_SHA)
    aa=addendum_arms(); assert len(aa)==5
    original={a['id']:a for a in arms()}
    for a in aa[:4]:
        assert a['prediction']==original[a['id'][:-3]]['prediction']
        typed,finish=schedule(a,True)
        assert io_start(a,typed)==next(t for t,c in typed if c=='run\n')-1
        if a['lifecycle']=='load':
            at=next(i for i,(_,c) in enumerate(typed) if c=='run\n')
            assert typed[at+1][0]-typed[at][0]==(len('run')+1)*12+360+36000
    a=aa[0];raw=mem.fake_log(synth(a));io_raw='# main\n1 1 101 main IN 0040 SECRET SECRET\n# 取りこぼし: 0件 / 総イベント数: 1件\n# sub\n# 取りこぼし: 0件 / 総イベント数: 0件\n'
    good=addendum_observation(raw,io_raw,100,2000,a,99)
    assert all(good['conditions'].values()) and 'SECRET' not in json.dumps(good)
    assert good['io_counts']['main']['ports']=={'0040':1}
    cases=[('stable',raw,io_raw,200),
           ('logical_marks',raw.replace('C303 A3','C303 A2'),io_raw,2000),
           ('memory_no_loss',raw.replace('取りこぼし: 0','取りこぼし: 1'),io_raw,2000),
           ('io_no_loss',raw,io_raw.replace('取りこぼし: 0','取りこぼし: 1',1),2000)]
    for key,mraw,iraw,end in cases:
        failed=addendum_observation(mraw,iraw,100,end,a,99)
        assert failed.get('failure')=='GateError' and failed['conditions'][key] is False
        assert all(v is True for k,v in failed['conditions'].items() if k!=key),(key,failed['conditions'])
        assert not any(k in failed for k in ('values','writes','errors','media'))
    both=addendum_observation(raw.replace('C303 A3','C303 A2'),io_raw,100,200,a,99)
    assert both['conditions']['stable'] is False and both['conditions']['logical_marks'] is False
    pre=addendum_observation(raw,io_raw,100,2000,a,101)
    assert pre['conditions']['pre_io_marks_absent'] is False
    # 凍結期待値に対する合成記録の照合結果を、追補集合生成の前後で固定する。
    # 旧公式は四腕の関門確認以外に読まない。
    frozen=REPO/'tests/conformance/expected_l4_seqfile.tsv'
    before=hashlib.sha256(frozen.read_bytes()).hexdigest()
    with frozen.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
    assert len(rows)==86
    ex=json.loads(rows[0]['exclusions'])
    rs=[dict(arm=a,obs=[synth(a),synth(a)],gate=True) for a in arms()]
    image=bytearray(fixture_image('alpha'));write_sector(image,18,0,1,b'ok\r\n\x1a')
    for o in rs[2]['obs']: o['media']=inspect(image,rs[2]['arm'])
    rs[-2]['obs']=[synth(rs[-2]['arm'],54) for _ in (1,2)]
    for r in rs:
        if r['arm']['id'] in ex:
            r['obs']=[dict(failure='GateError',errors={}) for _ in (1,2)];r['gate']=False
    with tempfile.TemporaryDirectory(dir=work,prefix='frozen86-') as td:
        path=Path(td)/'synthetic.tsv';emit(path,rs)
        baseline=check(frozen,path,ex)
        assert len(selected_arms('addendum1'))==5 and len(arms())==90
        assert signatures()==(PLAN_SHA,PROGRAM_SHA) and check(frozen,path,ex)==baseline
        assert baseline[0]+len(baseline[1])==86
    assert hashlib.sha256(frozen.read_bytes()).hexdigest()==before
    print('OK 追補5腕: 条件別陰性対照・複合失敗・開始前印・凍結86腕の合成照合結果不変・期待値不変',flush=True)

def addendum_report(rs,work,seconds):
    frames=sum(schedule(a,True)[1]*2 for a in addendum_arms())
    own_frames=sum(schedule(a,False)[1]*2 for a in addendum_arms())
    rows=['# l4-f1 追補1 第1回報告',
          'CLAUDE.mdを先に読み適用。公式ROM未実行・バイト列未読・画面未取得。src変更、commit、run_allなし。',
          '事前登録: docs/notes/l4-f1-addendum1-preregistration.md。第1回の署名・腕定義・凍結期待値は維持。',
          '自己検査: 合成陽性/陰性対照、失敗条件の独立記録、凍結86腕に対する合成記録の照合結果不変を検査（旧公式の全腕再照合ではない）。',
          '作業逸脱: 初版の自己検査が旧official.tsvの全180行を2回内部照合し、指定された4腕の読取範囲を超えた。値・画面本文は出力していない。該当処理は撤去し、以後は凍結期待値と合成記録のみで不変性を検査。srcは読まず変更していない。',
          f'自作試走: 追補5腕、各2独立起動の一式を1回。器具関門 {sum(r["gate"] for r in rs)}/5。壁時計 {seconds:.1f}秒。',
          'PC88_REF_*未指定。自作のdrive1は自作書込禁止媒体で代用。公式の起動条件成立は主張しない。',
          '追補だけでは較正・陽性・非一様の全体関門を証明しない。公式結果から期待値を作る際も既存の全体関門を免除しない。',
          f'公式予定: 10起動、計{frames}フレーム。60fps換算 {frames/3600:.1f}分、各起動240秒上限の合計40分。',
          f'自作の並列実測からの単純比例は約{seconds*4*frames/own_frames/60:.1f}分（4並列相当を逐次へ換算、ホスト速度依存）。',
          '旧公式のRUN先頭区間: finish-runは記録8388608/欠落502323、flush-runは記録8388608/欠落434825（各2走同数、結果ノートから）。',
          '旧公式の段別内訳・ポート種類は不明。許可されたofficial.tsvに件数列がなく、他のtmpを開かない制約のため復元不能。',
          '以下は件数・ポート番号・関門真偽のみ。失敗した観測には誤り値を入れない。',
          '|腕|走|器具関門|条件|','|---|---|---|---|']
    table=rows[-2:];rows=rows[:-2]
    details=[]
    for r in rs:
        for j,o in enumerate(r['obs'],1):
            table.append('|'+r['arm']['id']+'|'+str(j)+'|'+str(r['gate'])+'|'+json.dumps(o.get('conditions',{}),sort_keys=True)+'|')
            details.append(r['arm']['id']+' 走'+str(j)+' 段別入出力件数: `'+json.dumps(o.get('io_counts',{}),sort_keys=True)+'`')
    rows.append('\n'.join(table));rows.extend(details)
    (ROOT/'a1-report.md').write_text('\n\n'.join(rows)+'\n')

def report(rs,work,seconds):
    from collections import Counter
    counts=Counter(str(o.get('values',o.get('errors',{})).get('first_err','不明')) for r in rs for o in r['obs'])
    rows=['# l4-f1 第1回報告',f'腕数: {len(rs)}、各2走（自作ROMのみ、計{2*len(rs)}起動）。',
          '本器具は公式ROMの実行・srcの変更・commit・run_allを行わない。',
          '自己検査: 合成陽性、媒体構成誤り、1バイト変異、一様ERR0/2/33、2走不一致、ログ関門を通過。',
          f'自作試走の器具関門: {sum(r["gate"] for r in rs)}/{len(rs)}。',
          '最初ERR集計（走単位）: '+json.dumps(dict(counts),ensure_ascii=False),
          '全体関門: '+json.dumps(gates(rs),ensure_ascii=False),
          'PC88_REF_*未指定の自作試走はdrive1に自作の書込禁止媒体を代用。追補1構成の公式測定ではない。陽性・一様誤り関門の免除なし。',
          f'実測壁時計: {seconds:.1f}秒。公式は逐次{len(rs)*2}起動、各240秒上限。',
          f'公式予定フレーム合計: {sum(schedule(a,True)[1]*2 for a in arms())}。ホスト実行速度依存。上限見積{len(rs)*2*240/3600:.1f}時間。',
          '|腕|器具関門|最初ERR@段|最後ERR@段|','|---|---|---|---|']
    for r in rs:
        v=r['obs'][0].get('values',r['obs'][0].get('errors',{}))
        rows.append(f'|{r["arm"]["id"]}|{r["gate"]}|{v.get("first_err","不明")}@{v.get("first_stage","不明")}|{v.get("last_err","不明")}@{v.get("last_stage","不明")}|')
    (ROOT/'p1-report.md').write_text('\n'.join(rows)+'\n')

def main():
    global OFFICIAL
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('selftest');s.add_argument('--round',choices=['first','addendum1'],default='first');s.add_argument('--synthetic-only',action='store_true');s.add_argument('--work-dir',type=Path,default=ROOT/'selftest')
    m=sub.add_parser('measure');m.add_argument('--round',choices=['first','addendum1'],default='first');m.add_argument('--official',action='store_true');m.add_argument('--rom-dir',type=Path);m.add_argument('--work-dir',type=Path,required=True);m.add_argument('--out',type=Path,required=True)
    d=sub.add_parser('describe');d.add_argument('--round',choices=['first','addendum1'],default='first')
    e=sub.add_parser('expected');e.add_argument('--out',type=Path,required=True);e.add_argument('--exclude',action='append',default=[],metavar='ARM=理由',help='器具関門を通らなかった腕IDを理由つきで除外（繰り返し可）');e.add_argument('paths',nargs='+',type=Path)
    c=sub.add_parser('check');c.add_argument('--expected',type=Path,required=True);c.add_argument('--measured',type=Path,required=True);c.add_argument('--exclude',action='append',default=[],metavar='ARM=理由',help='期待値ファイルに記録された除外と同じ指定');
    args=p.parse_args();OFFICIAL=getattr(args,'official',False)
    if addendum_signatures()!=(ADDENDUM_PLAN_SHA,ADDENDUM_PROGRAM_SHA): raise ValueError('addendum signatures')
    if signatures()!=(PLAN_SHA,PROGRAM_SHA): raise ValueError('frozen signatures')
    for key in ('work_dir','out','paths','expected','measured'):
        value=getattr(args,key,None)
        for path in value if isinstance(value,list) else [value] if value else []:
            if key == 'expected' and path.resolve() == (REPO/'tests/conformance/expected_l4_seqfile.tsv').resolve(): continue
            if not path.is_absolute() or not path.resolve().is_relative_to(ROOT.resolve()): p.error('作業・入出力は指定された作業root内の絶対パス必須')
    if args.command=='describe':
        for a in serial_plan(args.round): print(json.dumps(a,ensure_ascii=False))
        return 0
    if args.command=='expected': print(f'期待値{expected(args.out,args.paths,parse_exclude(args.exclude))}腕、除外{len(args.exclude)}腕');return 0
    if args.command=='check':
        exclusions=parse_exclude(args.exclude)
        if not args.exclude:
            with args.expected.open() as f: first=next(csv.DictReader(f,delimiter='\t'))
            exclusions=json.loads(first.get('exclusions') or '{}')
        ok,bad=check(args.expected,args.measured,exclusions)
        print(f'一致{ok}腕、不一致{len(bad)}腕')
        for aid in bad: print(aid+': false')
        return int(bool(bad))
    args.work_dir.mkdir(parents=True,exist_ok=True)
    if args.command=='selftest':
        safety(args.work_dir)
        if args.synthetic_only: return 0
        rom=args.work_dir/'rom'
        p1=subprocess.run([sys.executable,str(REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(args.work_dir/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
        if p1.returncode: raise RuntimeError('自作ビルド失敗')
        start=time.monotonic();rs=measure(rom,False,args.work_dir,args.round);emit(args.work_dir/'selfrun.tsv',rs,args.round)
        if args.round=='addendum1': addendum_report(rs,args.work_dir,time.monotonic()-start)
        else: report(rs,args.work_dir,time.monotonic()-start)
        # 未実装差と媒体代替による全体測定無効は自己検査成功と区別して報告。
        return int(not all(r['gate'] for r in rs))
    rom=os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir): p.error('公式はPC88_REF_ROM_DIR、自作は--rom-dir')
    return int(not emit(args.out,measure(rom,args.official,args.work_dir,args.round),args.round))

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        import traceback
        tb=traceback.extract_tb(exc.__traceback__)
        print(f'NG 器具: {type(exc).__name__}、行{tb[-1].lineno}（本文非出力）')
        raise SystemExit(1)
