#!/usr/bin/env python3
"""l4-t4 CALL・USR・VARPTR。自作コードと既知符号化だけを測る。"""
import argparse, copy, csv, hashlib, io, json, os, re, subprocess, sys, tempfile, traceback
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch
sys.dont_write_bytecode=True
import l4_listkw_measure as kw
REPO=Path(__file__).resolve().parents[1]
ROOT=REPO/'tmp/t4-work'
IMPL_ROOT=ROOT
T3B_IMPL_ROOT=ROOT
BASE=0xc300
FIELDS=('begin','stage','ready','finish','ERROR_FLAG','count','first_err','first_stage','last_err','last_stage',
        's1_first','s1_last','s2_first','s2_last','s3_first','s3_last','cal','result','returned1','returned2','returned3')+tuple('p'+str(i) for i in range(21,96))
RANGE='C300-C35F'
KNOWN_DIFFERENCES={} # 公式観測前に差を免除しない。
SECRET='synthetic-screen-secret'
MEASURE_NAME='mlcall'
PROGRAM_SHA='610e7f9103a263b35dbd962f42e141c206c312af7702b2b5437daafcb82e144b'
PLAN_SHA='549f8a96e24282b7df2f486001e4277c23f3542a0abfc68b90cbfc705c144794'

# 以下のバイトは当器具が作ったZ80コード。外部コード・ROM由来ではない。
CODE=0xc000
DATA=0xc100
RELOC=0xc200
PAY=0xc315
# A, BC, DE, HL, SPをフラグも変更せず保存し、実行印を付ける。
ENTRY=bytes.fromhex('32 15 c3 ed 43 16 c3 ed 53 18 c3 22 1a c3 ed 73 1c c3')
MARK=bytes.fromhex('f5 3e d5 32 1e c3 f1')
CLOBBER=bytes.fromhex('3e 33 01 44 55 11 66 77 21 88 99')
ENC={'int1':bytes.fromhex('01 00'),'single1':bytes.fromhex('00 00 00 81'),
     'double1':bytes.fromhex('00 00 00 00 00 00 00 81'),'text':b't4own'}

def put(addr,data):
    return [f'poke {addr+i},{b}' for i,b in enumerate(data)]

def result(slot,expr): return f'poke {BASE+slot},abs({expr})'

def match(addr,data,slot):
    # 読むのは既知候補との比較だけ。未一致バイトは記録しない。
    return f'@cmp({slot}|{addr}|{data.hex()})'

def pointer_checks():
    out=[]
    for reg,off in [('de',24),('hl',26)]:
        out += [f'p=peek({BASE+off})+256*peek({BASE+off+1})']
        for j,(name,data) in enumerate(ENC.items()):
            slot=32+(0 if reg=='de' else 16)+j
            out += [f'@scan({slot}|{data.hex()})']
    return out

def pointer_body(slot,data,first):
    # IFはPEEKを含むGOSUB全体を囲む。候補全体がRAM内のときだけ読む。
    compare=first+8
    return [f'if p<32768 or p>65535 then poke {BASE+slot},255:return',
            'm=0', 'for d=-8 to 8', 'q=p+d',
            f'if q>=32768 and q<={65536-len(data)} then gosub {compare}',
            'next d', f'poke {BASE+slot},m', 'return',
            'if m<>0 then return', 'z=1']+[
            f'z=z and (peek(q+{i})={b})' for i,b in enumerate(data)]+[
            'if z<>0 then m=d+9', 'return']

def first_arms():
    out=[]
    def add(i,commands,prediction='受理/復帰またはERR番号（未確定）',setup=None,post=None,code=None):
        out.append(dict(id=i,commands=commands,prediction=prediction,setup=setup or [],post=post or [],code=list(code or (ENTRY+MARK+b'\xc9'))))
    add('cal-poke',['poke &hc310,213'],'cal213・ERR0')
    add('cal-error',['error 13'],'ERR13、段1')
    for tag,expr in [('decimal','49152'),('hex','&hc000'),('variable','q')]:
        add('call-'+tag,[f'call {expr}'],'実行印213と復帰印',setup=['q=49152'],post=pointer_checks())
    add('call-clobber',['call &hc000'],'汎用レジスタ破壊後も復帰',code=ENTRY+MARK+CLOBBER+b'\xc9')
    for tag,arg in [('one','x'),('mixed','x%,y$')]:
        add('call-args-'+tag,[f'call &hc000({arg})'],setup=['x=1:x%=1:y$="t4own"'],post=pointer_checks())
    for tag,x in [('minus1','-1'),('65535','65535'),('65536','65536'),('fraction','49152.4'),('string','"a"'),('missing','')]:
        add('call-'+tag,['call '+x],'範囲/型/構文ERR。FFFF実行時は時間切れもあり得る')
    for n in range(10): add('def-usr'+str(n),[f'def usr{n}=&hc000',f'x=usr{n}(1)'],'定義・呼出・復帰',post=pointer_checks())
    add('def-omitted',['def usr=&hc000','x=usr(1)'],post=pointer_checks())
    add('def-range',['def usr10=&hc000','x=usr10(1)'],'番号範囲のERR')
    for tag,var,value in [('int','x%','1'),('single','x!','1!'),('double','x#','1#'),('string','x$','"t4own"')]:
        add('usr-'+tag,['def usr0=&hc000',f'y{var[-1]}=usr0({var})'],setup=[f'{var}={value}'],post=pointer_checks())
        # HLの内容が自作引数候補に一致した場合だけ、1→2/先頭t→uを書き換える。
        candidate=ENC[{'int':'int1','single':'single1','double':'double1','string':'text'}[tag]]
        mc=bytearray(ENTRY+MARK)
        # HLがRAM内か確認、既知の全候補を確認。HLはpush/popで保護。
        mc+=bytes.fromhex('f5 e5 7c fe 80 38 00 fe c0 30 00')
        jumps=[len(mc)-5,len(mc)-1]
        for b in candidate:
            mc+=bytes([0x7e,0xfe,b,0x20,0,0x23]); jumps.append(len(mc)-2)
        mc+=bytes([0xe1,0xe5])
        for i,b in enumerate(candidate):
            val=(b+1)&255 if (tag=='string' and i==0) or (tag=='int' and i==0) or (tag in ('single','double') and i==len(candidate)-1) else b
            mc+=bytes([0x36,val,0x23])
        target=len(mc)
        mc+=bytes.fromhex('e1 f1 c9')
        for j in jumps: mc[j]=(target-j-1)&255
        expected='"u4own"' if tag=='string' else '2'
        add('usr-mutate-'+tag,['def usr0=&hc000',f'y{var[-1]}=usr0({var})'],setup=[f'{var}={value}'],post=[result(65,f'y{var[-1]}={expected}')]+pointer_checks(),code=mc)
    add('varptr-result-type',['def usr0=&hc000','p=usr0(varptr(x%))'],'USR入口Aを整数・単・倍の対照と比較してVARPTRの型を判定',setup=['x%=1'])
    for n in (0,9): add('usr-undefined'+str(n),[f'x=usr{n}(1)'],'未定義ERR、暴走は不明')
    for tag,var,value,data in [('int','x%','1',ENC['int1']),('single','x!','1!',ENC['single1']),('double','x#','1#',ENC['double1']),('string','x$','"t4own"',None),('array','a(3)','1',ENC['single1'])]:
        setup=(['dim a(4)'] if tag=='array' else [])+[f'{var}={value}']
        post=['p=p+65536*(p<0)*(-1)','if p<32768 or p>49136 then 1800',result(67,'p>=32768 and p<=65535')]
        if data: post += [match('p',data,68)]
        else: post += [result(68,'peek(p)=5'),'q=peek(p+1)+256*peek(p+2)','if q>=32768 and q<=49146 then '+match('q',ENC['text'],69)]
        # 型判定は整数変数への代入と1/2加算の丸めを別に観測。
        add('varptr-'+tag,[f'p=varptr({var})',result(66,'p<0'), 'p%=p'],setup=setup,post=post)
    add('varptr-difference',['p=varptr(x%):q=varptr(y%)',':'.join([result(70,'q-p=2'),result(71,'q-p=4'),result(72,'q-p=8')]),'d=q-p'],setup=['x%=1:y%=2'],post=['d=d+65536*abs(d<0)',f'poke {BASE+74},d-256*int(d/256)',f'poke {BASE+75},int(d/256)'])
    for tag,expr in [('undefined','u'),('expression','x+1'),('constant','1'),('file','#1')]: add('varptr-'+tag,[f'p=varptr({expr})'],'未定義は作成の可能性、他はERR')
    for tag,cmd in [('call-extra','call &hc000,1'),('usr-noparen','x=usr0 1'),('usr-extra','x=usr0(1,2)'),('def-string','def usr0="a"'),('varptr-bare','p=varptr x'),('varptr-extra','p=varptr(x,y)')]: add('syntax-'+tag,[cmd],'構文ERR2/22または型ERR13')
    return out

# 第1回の腕・入力署名を保ち、追補は別集合として選ぶ。
ROUND='addendum1'
OFFICIAL=False
ADDENDUM_PLAN_SHA='706c17284c27f430831de0271ba0eae9fbd41373c35c23701933db3a079a1be1'
ADDENDUM_PROGRAM_SHA='10899cafb6fd0404ed967e0a34bb45934ff2bc862562b295722973cdf7bc3bc0'

def mbf_integer(value,size):
    """正の整数をMBFに符号化（隠れた先頭1、末尾に指数+129）。"""
    assert value>0 and size in (4,8)
    exponent=value.bit_length()-1
    fraction=(value-(1<<exponent)) << (8*(size-1)-1-exponent)
    return fraction.to_bytes(size-1,'little')+bytes([exponent+129])

ADD_ENC={'int12345':(12345).to_bytes(2,'little'),
         'single12345':mbf_integer(12345,4),'double12345':mbf_integer(12345,8),
         'text':b't4own','int23456':(23456).to_bytes(2,'little'), 'descriptor':b''}
ADD_SLOTS=set(range(32,50))

def add_pointer_checks():
    out=[]
    for r,off in enumerate((26,24,22)): # HL, DE, BC
        out.append(f'p=peek({BASE+off})+256*peek({BASE+off+1})')
        for j,data in enumerate(ADD_ENC.values()):
            out.append(f'@scan1({32+6*r+j}|{data.hex()})')
    return out

def add_pointer_body(slot,data,first):
    target=str(BASE+slot) if isinstance(slot,int) else f'{BASE}+{slot}'
    descriptor=not data
    size=3 if descriptor else len(data)
    body=[f'if p<32768 or p>65535 then poke {target},255:return',
          'm=0','for d=-32 to 32','q=p+d',
          f'if q>=32768 and q<={65536-size} then gosub {first+8}',
          'next d',f'poke {target},m','return','if m<>0 then return']
    if descriptor:
        body+=['if peek(q)<>5 then return','t=peek(q+1)+256*peek(q+2)',
               'if t<32768 or t>65531 then return','z=1']
        body += [f'z=z and (peek(t+{i})={b})' for i,b in enumerate(b't4own')]
    else:
        body+=['z=1']+[f'z=z and (peek(q+{i})={b})' for i,b in enumerate(data)]
    return body+['if z<>0 then m=d+33','return']

def addendum_arms():
    out=first_arms()[:2]
    def add(tag,commands,setup=None,code=None,prediction='ERR/入口/復帰を未確定として測る'):
        out.append(dict(id='a1-'+tag,commands=commands,setup=setup or [],
            post=add_pointer_checks(),code=list(code or ENTRY+MARK+b'\xc9'),prediction=prediction))
    add('call-variable',['call q'],['q=&hc000'],prediction='実行印213・正常復帰を再確認')
    add('call-clobber',['call q'],['q=&hc000'],ENTRY+MARK+CLOBBER+b'\xc9',prediction='レジスタ破壊後も正常復帰の仮説')
    add('call-args-one',['call q(x)'],['q=&hc000:x=12345!'])
    add('call-args-mixed',['call q(x%,y$)'],['q=&hc000:x%=12345:y$="t4own"'])
    for tag,value in [('minus1','-1'),('65535','65535'),('65536','65536'),('fraction','49152.4')]:
        add('call-'+tag,['call q'],['q='+value],prediction='範囲/丸め未確定。-1/65535の時間切れは不明')
    add('call-string',['call q$'],['q$="a"'],prediction='型ERR13を仮説')
    add('call-undefined',['call q'],prediction='未定義ERR5を仮説')
    for tag,var,value in [('int','x%','12345'),('single','x!','12345!'),('double','x#','12345#'),('string','x$','"t4own"'),('cross23456','x%','23456')]:
        add('usr-'+tag,['def usr0=&hc000',f'y{var[-1]}=usr0({var})'],[f'{var}={value}'],
            prediction='A型値02/04/08/03、候補位置は未確定。異値整数候補は不一致の仮説')
    return out

def arms(): return first_arms() if ROUND=='first' else addendum_arms()

def program(a):
    lines={1:'clear ,&hbfff',2:'poke &hc300,197',3:'for i=1 to 95:poke &hc300+i,0:next i',4:'on error goto 9000'}
    pokes=put(CODE,bytes(a['code']))
    setup=[':'.join(pokes[j:j+3]) for j in range(0,len(pokes),3)]+a['setup']
    for j,c in enumerate(setup): lines[200+j]=c
    lines[500]='poke &hc302,151:goto 1100'
    for j,cmd in enumerate(a['commands'],1):
        n=1000+100*j; lines[n]=f'poke &hc301,{j}'; lines[n+1]=cmd
        lines[n+2]=f'poke {BASE+17+j},77'
    # post比較は段3の誤りに含め、復帰先を終了へ。
    lines[1500]='f=1:poke &hc301,3'
    lines[1501]='if peek(&hc305)<>0 then 1800'
    for j,c in enumerate(a['post']): lines[1502+j]=c
    lines[1800]='poke &hc301,90'; lines[1801]='poke &hc303,163'; lines[1802]='goto 1802'
    lines.update({9000:'e=err:s=peek(&hc301)',9001:'poke &hc304,1',
        9002:'if peek(&hc305)<>0 then 9005',9003:'poke &hc306,e',9004:'poke &hc307,s',
        9005:'poke &hc308,e:poke &hc309,s',9006:'if peek(&hc300+8+s*2)<>0 then 9008',
        9007:'poke &hc300+8+s*2,e',9008:'poke &hc300+9+s*2,e',9009:'poke &hc305,peek(&hc305)+1',
        9010:'if s=1 then resume 1102',9011:'if s=2 then resume 1202',9012:'if f=0 then resume 1302',9013:'resume 1800'})
    sublines={}; subno=3000; shared_scans={}
    for n,cmd in list(lines.items()):
        def expand(x):
            nonlocal subno
            slot,addr,hexdata=int(x[1]),x[2],x[3]
            first=subno; body=['z=1']+[f'z=z and (peek({addr}+{i})={b})' for i,b in enumerate(bytes.fromhex(hexdata))]+[result(slot,'z<>0'),'return']
            for statement in body: sublines[subno]=statement;subno+=1
            return f'gosub {first}'
        def expand_scan(x):
            nonlocal subno
            first=subno; body=pointer_body(int(x[1]),bytes.fromhex(x[2]),first)
            for statement in body: sublines[subno]=statement;subno+=1
            return f'gosub {first}'
        def expand_scan1(x):
            nonlocal subno
            if x[2] not in shared_scans:
                first=subno; body=add_pointer_body('w',bytes.fromhex(x[2]),first)
                shared_scans[x[2]]=first
                for statement in body: sublines[subno]=statement; subno+=1
            return f'w={int(x[1])}:gosub {shared_scans[x[2]]}'
        cmd=re.sub(r'@scan1\((\d+)\|([0-9a-f]*)\)',expand_scan1,cmd)
        cmd=re.sub(r'@scan\((\d+)\|([0-9a-f]+)\)',expand_scan,cmd)
        lines[n]=re.sub(r'@cmp\((\d+)\|([^|]+)\|([0-9a-f]+)\)',expand,cmd)
    assert subno<9000
    lines.update(sublines)
    assert all(len(f'{n} {s}')<80 for n,s in lines.items()),'打鍵行長'
    return ['new']+[f'{n} {s}' for n,s in sorted(lines.items())]+['run']

def error_block(err,stage,count,seen):
    return [[4,1]]+([[6,err],[7,stage]] if count==0 else [])+[[8,err],[9,stage]]+(
        [] if stage in seen else [[8+stage*2,err]])+[[9+stage*2,err],[5,count+1]]

def memory_valid(o,a):
    if type(o) is not dict or set(o)!={'values','writes'}: return False
    v=o['values']; ws=o['writes']
    if type(v) is not dict or set(v)!=set(FIELDS) or any(type(n) is not int or not 0<=n<=255 for n in v.values()): return False
    if type(ws) is not list or any(type(x) is not list or len(x)!=2 or any(type(n) is not int for n in x) or not 0<=x[0]<96 or not 0<=x[1]<=255 for x in ws): return False
    init=[[0,197]]+[[i,0] for i in range(1,96)]+[[2,151]]
    if ws[:len(init)]!=init: return False
    pos=len(init); stage=0; stages=[]; count=0; seen=set(); returned=set(); results=set(); pointers=set()
    while pos<len(ws):
        i,n=ws[pos]
        if i==4:
            offset=3 if count==0 else 1
            if pos+offset>=len(ws) or stage not in set(range(1,len(a['commands'])+1))|{3}: return False
            err=ws[pos+offset][1]; block=error_block(err,stage,count,seen)
            if not err or ws[pos:pos+len(block)]!=block: return False
            count+=1; seen.add(stage); pos+=len(block); continue
        if i==1: stage=n; stages.append(n)
        elif 21<=i<=29 and stage in (1,2,3): pass # 保存レジスタ（許可された数値）
        elif i in (74,75) and stage==3: pass # 2変数の番地差だけ（16bit差）
        elif i==30 and n==213 and stage in (1,2,3): pass # 自作コードの実行印
        elif i in (ADD_SLOTS if a['id'].startswith('a1-') else set(range(32,36))|set(range(48,52))) and n in (*range(66 if a['id'].startswith('a1-') else 18),255) and stage==3:
            if i in pointers: return False
            pointers.add(i)
        elif i in set(range(65,74)) and n in (0,1) and stage in (1,2,3): pass
        elif i==16 and a['id']=='cal-poke' and stage==1:
            if stage in results: return False
            results.add(stage)
        elif i==17+stage and 1<=stage<=3 and n==77:
            if stage in returned: return False
            returned.add(stage)
        elif stage==90 and (i,n)==(3,163): pass
        else: return False
        pos+=1
    required={1} if a['id']=='cal-poke' and 1 not in seen else set()
    if results!=required: return False
    return stages==list(range(1,len(a['commands'])+1))+[3,90] and returned==set(range(1,len(a['commands'])+1)) and ws[-1]==[3,163] and sum(x==[3,163] for x in ws)==1 and {FIELDS[i]:n for i,n in ws}==v

def valid(o,a): return memory_valid(o,a)

class GateError(ValueError):
    def __init__(self,condition,events):
        super().__init__(condition)
        self.errors={FIELDS[i]:v for _,i,v in events if 4<=i<=15}

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
        if k!=seq+1 or t<last or not BASE<=addr<BASE+96: raise ValueError('連番/時点/番地')
        seq=k; last=t
        if t>=start: events.append((t,addr-BASE,val))
    if seq!=int(total[1]): raise ValueError('件数')
    # RUN前後の余分な書込みは初期化開始印より前だけ区切る。値列を残さない。
    begins=[j for j,(_,i,v) in enumerate(events) if (i,v)==(0,197)]
    if len(begins)!=1: raise ValueError('開始印')
    events=events[begins[0]:]
    if not events or events[-1][0]>finish-600: raise GateError('安定',events)
    ws=[[i,v] for _,i,v in events]; o=dict(values={FIELDS[i]:v for i,v in ws},writes=ws)
    if not memory_valid(o,a): raise GateError('論理印',events)
    return o

def schedule(a,official):
    at=1200 if official else 120; typed=[]
    if official: typed.append((300,'\n'))
    for cmd in program(a):
        typed.append((at,cmd+'\n')); at+=(len(cmd)+1)*(12 if official else 8)+(360 if official else 120)
    return typed,at+(18000 if official else 3600) # 公式の初期化・誤り復帰と実行を待つ。

def media_prepare(work,a): return [],lambda:None
def media_observe(work,a): return None

def capture(rom,official,a,work):
    typed,finish=schedule(a,official); start=typed[-1][0]; path=work/'memory.txt'
    argv=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom)]
    for frame,cmd in typed: argv+=['--type-at',str(frame),'--type',cmd]
    argv+=['--mem-write-log',str(path),'--mem-write-range',RANGE,'--mem-write-from-frame',str(start),'--frames',str(finish)]
    extra,cleanup=media_prepare(work,a)
    argv+=extra
    try:
        p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'),timeout=180)
        if p.returncode or b'untypable' in p.stderr.lower(): raise RuntimeError('実行/打鍵拒否')
        o=parse_log(path.read_text(),start,finish,a)
        media=media_observe(work,a)
        if media is not None: o['media']=media
        return o
    finally:
        path.unlink(missing_ok=True)
        cleanup()

def synth(a):
    ws=[[0,197]]+[[i,0] for i in range(1,96)]+[[2,151]]
    for j,_ in enumerate(a['commands'],1):
        ws.append([1,j])
        if a['id']=='cal-poke': ws.append([16,213])
        if a['id']=='cal-error': ws+=error_block(13,j,0,set())
        ws.append([17+j,77])
    ws+=[[1,3],[1,90],[3,163]]
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
    return {r['arm']['id']:dict(values=r['obs'][0]['values'],media=r['obs'][0].get('media')) for r in rs}

def expected(out,paths):
    if len(paths)!=1: raise ValueError('全腕TSV一つ')
    got=read_passed(paths[0]); write_tsv(out,['arm','values'],[[k,json.dumps(v)] for k,v in sorted(got.items())]); return len(got)

def expected_shape(v,a):
    if type(v) is not dict or set(v)!={'values','media'}: return False
    nums=v['values']
    if type(nums) is not dict or set(nums)!=set(FIELDS) or any(type(n) is not int or not 0<=n<=255 for n in nums.values()): return False
    if v['media'] is not None:
        o=synth(a);o['media']=v['media']
        if not valid(o,a): return False
    return True

def check(exp,measured):
    with exp.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
    want={r['arm']:json.loads(r['values']) for r in rows}
    if len(rows)!=len(want) or set(want)!={a['id'] for a in arms()} or any(not expected_shape(v,a) for a in arms() for k,v in want.items() if k==a['id']): raise ValueError('期待値形')
    for a in arms()[:2]:
        if want[a['id']]!=dict(values=synth(a)['values'],media=synth(a).get('media')): raise ValueError('期待値較正')
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

def code_selftest():
    # 自作コードの命令だけを実行する小さな合成対照。実ROMは入力しない。
    def execute(code,seed):
        ram=dict(seed); r=dict(a=7,f=0x41,bc=0x1234,de=0x9100,hl=0x9000,sp=0xd000); pc=0
        def word(k): return code[k]+256*code[k+1]
        def store(addr,val,n=2):
            for i in range(n): ram[addr+i]=(val>>(8*i))&255
        def push(v): r['sp']-=2;store(r['sp'],v)
        def pop():
            v=ram[r['sp']]+256*ram[r['sp']+1];r['sp']+=2;return v
        for _ in range(1000):
            op=code[pc];pc+=1
            if op==0xc9: return r,ram
            if op==0x32: store(word(pc),r['a'],1);pc+=2
            elif op==0xed:
                reg={0x43:'bc',0x53:'de',0x73:'sp'}[code[pc]];store(word(pc+1),r[reg]);pc+=3
            elif op==0x22: store(word(pc),r['hl']);pc+=2
            elif op==0xf5: push(r['a']*256+r['f'])
            elif op==0xf1:
                v=pop();r['a']=v>>8;r['f']=v&255
            elif op==0xe5: push(r['hl'])
            elif op==0xe1: r['hl']=pop()
            elif op==0x3e: r['a']=code[pc];pc+=1
            elif op in (0x01,0x11,0x21): r[{1:'bc',17:'de',33:'hl'}[op]]=word(pc);pc+=2
            elif op==0x7c: r['a']=r['hl']>>8
            elif op==0x7e: r['a']=ram.get(r['hl'],0)
            elif op==0x36: store(r['hl'],code[pc],1);pc+=1
            elif op==0x23: r['hl']=(r['hl']+1)&65535
            elif op==0xfe:
                b=code[pc];pc+=1;r['f']=(0x40 if r['a']==b else 0)|(1 if r['a']<b else 0)
            elif op in (0x20,0x30,0x38):
                d=code[pc];pc+=1
                take=(not r['f']&0x40) if op==0x20 else (not r['f']&1) if op==0x30 else (r['f']&1)
                if take: pc+=d if d<128 else d-256
            else: raise AssertionError('自作命令の合成器に未定義')
        raise AssertionError('自作コードがRETしない')
    for a in arms():
        code=bytes(a['code'])
        tag=a['id'].removeprefix('usr-mutate-')
        enc=ENC.get({'int':'int1','single':'single1','double':'double1','string':'text'}.get(tag,''),b'')
        seed={0x9000+i:b for i,b in enumerate(enc)}
        for matched in (True,False):
            mem=dict(seed)
            if not matched: mem[0x9000]=255
            r,ram=execute(code,mem)
            assert r['sp']==0xd000 and ram[BASE+30]==213
            if code.startswith(ENTRY):
                assert ram[BASE+21]==7 and ram[BASE+22]==0x34 and ram[BASE+28]==0
            if enc:
                assert r['a']==7 and r['hl']==0x9000 and r['f']==0x41
                if not matched: assert all(ram.get(k)==v for k,v in mem.items())
                else:
                    delta=0 if tag in ('int','string') else len(enc)-1
                    assert ram[0x9000+delta]==(enc[delta]+1)&255
    print('OK 自作Z80: 保存・RET・スタック平衡・候補一致時だけ書換',flush=True)

def pointer_selftest():
    # 実際に生成するBASICサブルーチンを合成RAM上で実行する。読出し番地も検査。
    def execute(p,data,seed):
        body=pointer_body(32,data,3000); v={'p':p}; reads=[]; writes=[]
        pc=0; stack=[]; loop=None
        def peek(addr):
            assert 32768<=addr<=65535, 'ROM/16bit範囲外のPEEK'
            reads.append(addr); return seed.get(addr,255)
        def expr(s):
            s=s.replace('<>','!='); s=re.sub(r'(?<![<>!])=(?!=)','==',s)
            return int(eval(s,{'__builtins__':{},'peek':peek},v))
        for _ in range(1000):
            statement=body[pc]; pc+=1
            if statement.startswith('if '):
                cond,statement=statement[3:].split(' then ')
                if not expr(cond): continue
            for c in statement.split(':'):
                if c.startswith('for '):
                    v['d']=-8; loop=pc
                elif c=='next d':
                    v['d']+=1
                    if v['d']<=8: pc=loop
                elif c.startswith('gosub '): stack.append(pc); pc=int(c[6:])-3000
                elif c=='return':
                    if not stack: return writes,reads
                    pc=stack.pop()
                elif c.startswith('poke '):
                    addr,value=c[5:].split(','); writes.append((int(addr),expr(value)))
                else:
                    name,value=c.split('=',1);v[name]=expr(value)
        raise AssertionError('合成BASIC未復帰')
    for data in ENC.values():
        cases=[(0xe610,0,9),(0xc100,-8,1),(0xc100,-3,6),
               (0xc100,8,17),(0xffff,-len(data)+1,10-len(data)),
               (0x8000,0,9)]
        for p,delta,want in cases:
            seed={p+delta+i:b for i,b in enumerate(data)}
            writes,reads=execute(p,data,seed)
            assert writes==[(BASE+32,want)] and reads
            seed[p+delta]=254
            assert execute(p,data,seed)[0]==[(BASE+32,0)]
        for p in (0,0x7fff,0x10000):
            # 範囲外は近傍に既知値があっても読まない。
            seed={0x8000+i:b for i,b in enumerate(data)}
            assert execute(p,data,seed)==([(BASE+32,255)],[])
        assert execute(0x8000,data,{0x7fff+i:b for i,b in enumerate(data)})[0]==[(BASE+32,0)]
        assert execute(0xffff,data,{0xffff+i:b for i,b in enumerate(data)})[0]==[(BASE+32,0)]
        # 複数一致でも最初のずれだけ。
        seed={0xc100+d+i:b for d in (-8,3) for i,b in enumerate(data)}
        assert execute(0xc100,data,seed)[0]==[(BASE+32,1)]
    a=first_arms()[2]
    for slot in (32,48):
        for n in (*range(18),255,18,254):
            o=synth(a); o['writes'].insert(-2,[slot,n])
            o['values']={FIELDS[i]:v for i,v in o['writes']}
            assert valid(o,a)==(n in (*range(18),255))
    o=synth(a); o['writes'][-2:-2]=[[32,0],[32,1]]
    o['values']={FIELDS[i]:v for i,v in o['writes']}; assert not valid(o,a)
    for slot in (36,39,52,55):
        o=synth(a); o['writes'].insert(-2,[slot,1])
        o['values']={FIELDS[i]:v for i,v in o['writes']}; assert not valid(o,a)
    print('OK pointer: C000以上・負ずれ・境界・範囲外255・不一致0・最初一致・印の陰性',flush=True)

def first_safety_selftest(work):
    work.mkdir(parents=True,exist_ok=True)
    assert hashlib.sha256(json.dumps(arms(),sort_keys=True,separators=(',',':')).encode()).hexdigest()==PLAN_SHA,'事前登録の腕定義'
    assert hashlib.sha256(json.dumps([program(a) for a in arms()],separators=(',',':')).encode()).hexdigest()==PROGRAM_SHA,'事前登録の全入力'
    code_selftest()
    pointer_selftest()
    aa=arms(); assert len({a['id'] for a in aa})==len(aa)
    rs=[dict(arm=a,obs=[synth(a),synth(a)],gate=True) for a in aa]
    assert all(valid(r['obs'][0],r['arm']) for r in rs)
    good=synth(aa[0])
    assert parse_log(fake_log(good,[[18,0],[19,0]]),100,2000,aa[0])==good
    for mode in ('finish','stage','values','init','begin','payload'):
        bad=copy.deepcopy(good)
        if mode=='finish': bad['writes'].pop()
        elif mode=='stage': bad['writes'][97]=[1,2]
        elif mode=='values': bad['values']['count']=1
        elif mode=='init': bad['writes'].pop(1)
        elif mode=='begin': bad['writes'].insert(97,[0,197])
        else:
            bad['writes'].insert(98,[66,2]);bad['values']['p66']=2
        assert not valid(bad,aa[0]),mode
    # 陰性対照が狙いのERR整合判定へ届くことを陽性から一箇所だけ変更して確認。
    a=aa[1]; err=synth(a); assert valid(err,a)
    bad=copy.deepcopy(err); ix=bad['writes'].index([7,1]); bad['writes'][ix]=[7,2]
    bad['values']={FIELDS[i]:v for i,v in bad['writes']}; assert not valid(bad,a)
    with tempfile.TemporaryDirectory(dir=work,prefix='synthetic-') as td:
        td=Path(td); m=td/'m.tsv'; e=td/'e.tsv'; b=td/'b.tsv'
        assert emit(m,rs); assert expected(e,[m])==len(aa); assert check(e,m)==(len(aa),[])
        for mode in ('gate','repeat','plan','body','two-runs','missing','calibration'):
            br=copy.deepcopy(rs)
            if mode=='gate': br[2]['gate']=False
            elif mode=='body': br[2]['obs'][0]['body']=SECRET
            elif mode=='two-runs': br[2]['obs'][1]['values']['p21']=1
            elif mode=='missing': br.pop()
            elif mode=='calibration': br[0]['obs']=[synth(aa[1])]*2
            emit(b,br)
            if mode=='repeat': b.write_text(b.read_text().replace('\t2\t','\t1\t'))
            if mode=='plan': b.write_text(b.read_text().replace('new','wrong'))
            try: expected(td/'reject.tsv',[b])
            except (ValueError,KeyError,TypeError): pass
            else: raise AssertionError(mode)
            assert check(e,b)[1],mode
        changed=copy.deepcopy(rs); a=aa[2]
        for o in changed[2]['obs']:
            ix=o['writes'].index([1,1])+1;o['writes'].insert(ix,[66,1]);o['values']['p66']=1
        assert emit(b,changed) and check(e,b)[1]==[a['id']]
        original=dict(values=rs[2]['obs'][0]['values'],media=rs[2]['obs'][0].get('media'))
        measured=dict(values=changed[2]['obs'][0]['values'],media=changed[2]['obs'][0].get('media'))
        rule=dict(expected=original,measured=measured,reason='合成の完全条件差')
        with patch.dict(KNOWN_DIFFERENCES,{a['id']:rule}),redirect_stdout(io.StringIO()):
            assert check(e,b)==(len(aa),[])
            # 条件の一部だけ変えた差は免除しない。
            rule['measured']=dict(values=original['values'],media=original['media'])
            assert check(e,b)[1]==[a['id']]
    with tempfile.TemporaryDirectory(dir=work,prefix='frontend-') as td:
        td=Path(td); sink=io.StringIO(); frontend_good=good
        def fake(argv,**kwargs):
            start=int(argv[argv.index('--mem-write-from-frame')+1]); raw=fake_log(frontend_good)
            raw=re.sub(r'^(\d+) (\d+) ',lambda x:f'{x[1]} {start+int(x[1])} ',raw,flags=re.M)
            Path(argv[argv.index('--mem-write-log')+1]).write_text(raw)
            return subprocess.CompletedProcess(argv,0,SECRET.encode(),SECRET.encode())
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=fake),redirect_stdout(sink),redirect_stderr(sink):
            assert capture(Path('synthetic'),False,aa[0],td)==good
            frontend_good=synth(aa[2])
            assert capture(Path('synthetic'),False,aa[2],td)==frontend_good
            frontend_good=good
        assert not sink.getvalue() and not (td/'memory.txt').exists()
        assert not list(td.glob('*.d88'))
        def denied(argv,**kwargs): return subprocess.CompletedProcess(argv,1,SECRET.encode(),SECRET.encode())
        with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',side_effect=denied),redirect_stdout(sink),redirect_stderr(sink):
            try: capture(Path('synthetic'),False,aa[0],td)
            except RuntimeError: pass
            else: raise AssertionError('実行拒否を受理')
        assert not sink.getvalue() and not (td/'memory.txt').exists() and not list(td.glob('*.d88'))

    # 正常なログを一箇所ずつ壊し、各関門の陰性が実際に拒否されること。
    normal=fake_log(good)
    for raw in (normal.replace(RANGE,'C301-C35F'),
                normal.replace('総イベント数: '+str(len(good['writes'])),'総イベント数: 999'),
                normal.replace('1 100 ','2 100 '),normal.replace('2 101 ','2 99 ')):
        try: parse_log(raw,100,2000,aa[0])
        except ValueError: pass
        else: raise AssertionError('ログ関門の陰性')
    try: parse_log(normal,100,200,aa[0])
    except GateError: pass
    else: raise AssertionError('安定関門の陰性')
    # ERROR_FLAGと段別最初/最後を保持する陽性。途中の追加誤りも検証。
    a=aa[-1]; o=synth(a); j=o['writes'].index([1,1])+1
    o['writes'][j:j]=error_block(13,1,0,set())+error_block(2,1,1,{1})
    o['values']={FIELDS[i]:v for i,v in o['writes']}; assert valid(o,a)
    assert o['values']['first_err']==13 and o['values']['s1_last']==2
    try: parse_log(fake_log(o),100,200,a)
    except GateError as exc: assert exc.errors['first_err']==13 and exc.errors['last_err']==2
    else: raise AssertionError('関門失敗でERR保持')
    raw=fake_log(o); raw=raw.replace('取りこぼし: 0','取りこぼし: 1')
    try: parse_log(raw,100,2000,a)
    except ValueError: pass
    else: raise AssertionError('取りこぼし陰性')
    print('OK 合成: 開始前分離・印順・ERR段・較正・2走・plan・陰性対照',flush=True)

def safety_selftest(work):
    global ROUND
    selected=ROUND
    try:
        ROUND='first'
        first_safety_selftest(work)
    finally: ROUND=selected
    assert hashlib.sha256(json.dumps(addendum_arms(),sort_keys=True,separators=(',',':')).encode()).hexdigest()==ADDENDUM_PLAN_SHA,'追補腕署名'
    assert hashlib.sha256(json.dumps([program(a) for a in addendum_arms()],separators=(',',':')).encode()).hexdigest()==ADDENDUM_PROGRAM_SHA,'追補入力署名'
    for a in addendum_arms():
        assert valid(synth(a),a)
        assert sum(len(c)+1 for c in program(a))+1<=8192,'打鍵総数'
    add_pointer_selftest()

def add_pointer_selftest():
    # 生成BASICそのものを合成RAMで評価。境界・記述子・クロス対照。
    def execute(p,data,seed):
        body=add_pointer_body('w',data,3000); v={'p':p,'w':32}; reads=[]; writes=[]
        pc=0; stack=[]; loop=0
        def peek(addr):
            assert 32768<=addr<=65535
            reads.append(addr); return seed.get(addr,255)
        def expr(s):
            s=s.replace('<>','!=');s=re.sub(r'(?<![<>!])=(?!=)','==',s)
            return int(eval(s,{'__builtins__':{},'peek':peek},v))
        for _ in range(10000):
            statement=body[pc];pc+=1
            if statement.startswith('if '):
                cond,statement=statement[3:].split(' then ')
                if not expr(cond): continue
            for c in statement.split(':'):
                if c.startswith('for '): v['d']=-32;loop=pc
                elif c=='next d':
                    v['d']+=1
                    if v['d']<=32: pc=loop
                elif c.startswith('gosub '): stack.append(pc);pc=int(c[6:])-3000
                elif c=='return':
                    if not stack: return writes,reads
                    pc=stack.pop()
                elif c.startswith('poke '):
                    addr,value=c[5:].split(',');writes.append((expr(addr),expr(value)))
                else:
                    name,value=c.split('=',1);v[name]=expr(value)
        raise AssertionError('追補照合未復帰')
    assert mbf_integer(1,4)==ENC['single1'] and mbf_integer(1,8)==ENC['double1']
    assert ADD_ENC['single12345'].hex()=='00e4408e'
    for data in list(ADD_ENC.values())[:-1]:
        for p,d in ((0xe610,-32),(0xc100,32),(0x8000,0),(0xffff,1-len(data))):
            seed={p+d+i:b for i,b in enumerate(data)}
            assert execute(p,data,seed)[0]==[(BASE+32,d+33)]
            seed[p+d]=254; assert execute(p,data,seed)[0]==[(BASE+32,0)]
        for p in (0x7fff,65536): assert execute(p,data,{})==([(BASE+32,255)],[])
        seed={0xc100+d+i:b for d in (-32,16) for i,b in enumerate(data)}
        assert execute(0xc100,data,seed)[0]==[(BASE+32,1)]
    for x,y in ((12345,23456),(23456,12345)):
        assert execute(0xc100,x.to_bytes(2,'little'),dict(enumerate(y.to_bytes(2,'little'),0xc100)))[0]==[(BASE+32,0)]
    seed={0xc100:5,0xc101:0,0xc102:0xe6,**dict(enumerate(b't4own',0xe600))}
    assert execute(0xc100,b'',seed)[0]==[(BASE+32,33)]
    for addr in (0x7fff,65532):
        bad=dict(seed);bad[0xc101]=addr&255;bad[0xc102]=addr>>8
        assert execute(0xc100,b'',bad)[0]==[(BASE+32,0)]
    bad=dict(seed);bad[0xe600]=254;assert execute(0xc100,b'',bad)[0]==[(BASE+32,0)]
    a=dict(first_arms()[0],id='a1-synthetic')
    for n in (0,1,65,255,66,254):
        o=synth(a);o['writes'].insert(-2,[49,n]);o['values']={FIELDS[i]:v for i,v in o['writes']}
        assert valid(o,a)==(n in (0,1,65,255))
    print('OK 追補照合: ±32・3レジスタ・MBF・クロス・記述子・RAM境界・陰性',flush=True)

def measure(rom,official,work):
    global OFFICIAL
    OFFICIAL=official
    safety_selftest(work)
    def run_arm(a):
        obs=[]
        for repeat in (1,2):
            dest=work/(a['id']+'-'+str(repeat)); dest.mkdir(exist_ok=True)
            try: obs.append(capture(rom,official,a,dest))
            except PermissionError:
                raise # 本筋の書込み・実行拒否は継続しない
            except Exception as exc:
                print(f'腕={a["id"]} 走={repeat} 条件={type(exc).__name__}（本文非出力）',flush=True)
                obs.append(dict(failure='capture-gate',errors=getattr(exc,'errors',{}),result='不明',screen_comparison=None))
        gate=all(valid(o,a) for o in obs) and obs[0]==obs[1]
        print(a['id']+': '+('pass' if gate else 'gate_failed'),flush=True)
        return dict(arm=a,obs=obs,gate=gate)
    if official: return [run_arm(a) for a in arms()]
    # 自作試走だけ、作業ディレクトリと起動を分けた4プロセスで並行測定。
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool: return list(pool.map(run_arm,arms()))

def summary(rs,work=None):
    path=ROOT/('selfrun-addendum1.md' if ROUND=='addendum1' else 'selfrun.md')
    rows=[f'## {MEASURE_NAME}: {len(rs)}腕×2独立走、関門{sum(r["gate"] for r in rs)}/{len(rs)}',
          '公式ROM未実行。未実装のERRは値一致と区別。画面比較は採らない。',
          '|腕|関門|最初ERR@段|最後ERR@段|','|---|---|---|---|']
    for r in rs:
        v=r['obs'][0].get('values',r['obs'][0].get('errors',{})); g=lambda k:v.get(k,'不明')
        rows.append(f'|{r["arm"]["id"]}|{r["gate"]}|{g("first_err")}@{g("first_stage")}|{g("last_err")}@{g("last_stage")}|')
    with path.open('a') as f: f.write('\n'.join(rows)+'\n')

def selftest(work):
    safety_selftest(work); rom=work/'rom'
    p=subprocess.run([sys.executable,str(REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    if p.returncode: raise RuntimeError('自作ビルド失敗')
    rs=measure(rom,False,work); passed=emit(work/'selfrun.tsv',rs)
    summary(rs,work if work.resolve().is_relative_to(T3B_IMPL_ROOT.resolve()) else None)
    if passed: expected(work/'self-expected.tsv',[work/'selfrun.tsv']); assert check(work/'self-expected.tsv',work/'selfrun.tsv')==(len(rs),[])
    return int(not passed)

def main():
    global ROUND,OFFICIAL
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('measure'); m.add_argument('--official',action='store_true'); m.add_argument('--rom-dir',type=Path); m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True)
    s=sub.add_parser('selftest'); s.add_argument('--work-dir',type=Path,default=ROOT/'selftest'); s.add_argument('--synthetic-only',action='store_true')
    sub.add_parser('describe')
    e=sub.add_parser('expected'); e.add_argument('--out',type=Path,required=True); e.add_argument('paths',type=Path,nargs='+')
    c=sub.add_parser('check'); c.add_argument('--expected',type=Path,required=True); c.add_argument('--measured',type=Path,required=True)

    for parser in (m,s): parser.add_argument('--round',choices=('first','addendum1'),default='addendum1')
    args=p.parse_args()
    ROUND=getattr(args,'round','addendum1')
    OFFICIAL=getattr(args,'official',False)
    for name in ('work_dir','out','expected','measured'):
        path=getattr(args,name,None)
        if path is not None and (not path.is_absolute() or not any(path.resolve().is_relative_to(root.resolve()) for root in (ROOT,IMPL_ROOT,T3B_IMPL_ROOT))): p.error('作業・結果はtmp/t4-work内の絶対パス必須')
    if hasattr(args,'paths') and any(not x.is_absolute() or not any(x.resolve().is_relative_to(root.resolve()) for root in (ROOT,IMPL_ROOT,T3B_IMPL_ROOT)) for x in args.paths): p.error('入力もtmp/t4-work内')
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
