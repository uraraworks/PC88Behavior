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

# 追補2専用。コード・候補・印はすべて自作予約域内。
ADDENDUM2_PLAN_SHA='c6d300c6b49ec54d5debf4e562b20a304da16b5a9747d9a9012dc76ae549c15a'
ADDENDUM2_PROGRAM_SHA='a0b3c495d8875647d8711c7d3154a11545ce5c55612904ab0fee30c67e22b914'
A2_CAND=0xc280
A2_PTR=0xc2a0
A2_PROBE=0xc2e0

def scan_code(candidates, mutate=False):
    """候補ごとにRAMを入口で走査。全レジスタを復元し、単一一致だけ介入。"""
    code=bytearray(ENTRY+MARK+bytes.fromhex('f5 c5 d5 e5'))
    labels={}; fix=[]
    def emit(*bs): code.extend(bs)
    def word(op,n): emit(op,n&255,n>>8)
    def label(n): labels[n]=len(code)
    def jump(op,n): emit(op,0,0); fix.append((len(code)-2,n))
    for k,data in enumerate(candidates):
        prefix=str(k); count=BASE+32+9*k; addresses=count+1
        word(0x21,addresses); emit(0x22,A2_PTR&255,A2_PTR>>8)
        word(0x21,0x8000)
        label(prefix+'loop')
        # 候補全体が予約域に重なる最初の位置からC35Fまで飛ばす。
        emit(0x7c,0xfe,0xbf); jump(0xc2,prefix+'c0')
        emit(0x7d,0xfe,257-len(data)); jump(0xd2,prefix+'skip')
        label(prefix+'c0'); emit(0x7c,0xfe,0xc0); jump(0xc2,prefix+'compare')
        label(prefix+'skip'); word(0x21,0xc360)
        label(prefix+'compare')
        emit(0xe5); word(0x11,A2_CAND+16*k); emit(0x06,len(data) or 3)
        label(prefix+'bytes')
        emit(0x1a,0xbe); jump(0xc2,prefix+'miss')
        emit(0x23,0x13,0x05); jump(0xc2,prefix+'bytes')
        emit(0xe1)
        word(0x3a,count); emit(0xfe,255); jump(0xca,prefix+'next')
        emit(0x3c); word(0x32,count); emit(0xfe,5); jump(0xd2,prefix+'next')
        emit(0xed,0x5b,A2_PTR&255,A2_PTR>>8,0x7d,0x12,0x13,0x7c,0x12,0x13,
             0xed,0x53,A2_PTR&255,A2_PTR>>8)
        jump(0xc3,prefix+'next')
        label(prefix+'miss'); emit(0xe1)
        label(prefix+'next')
        # 最後の開始番地を処理したら終了（FFFF跨ぎを読まない）。
        last=65536-len(data)
        emit(0x7c,0xfe,last>>8); jump(0xc2,prefix+'inc')
        emit(0x7d,0xfe,last&255); jump(0xca,prefix+'end')
        label(prefix+'inc'); emit(0x23); jump(0xc3,prefix+'loop')
        label(prefix+'end')
    if mutate:
        word(0x3a,BASE+32); emit(0xfe,1); jump(0xc2,'restore')
        emit(0x2a,(BASE+33)&255,(BASE+33)>>8)
        for b in a2_encoding(1234,len(candidates[0])): emit(0x36,b,0x23)
        emit(0x3e,1); word(0x32,BASE+68)
    label('restore'); emit(0x3e,219); word(0x32,BASE+31); emit(0xe1,0xd1,0xc1,0xf1,0xc9)
    for at,name in fix:
        dest=CODE+labels[name]; code[at:at+2]=dest.to_bytes(2,'little')
    assert CODE+len(code)<A2_CAND
    return bytes(code)

def a2_encoding(value,size):
    return value.to_bytes(2,'little') if size==2 else mbf_integer(value,size)

def descriptor_code():
    # 共通走査の比較部分を、動的ポインタ付き記述子照合に差し替える。
    # ラベル再配置を避けるため、記述子専用の別生成器を用いる。
    return a2_descriptor_scan()

def a2_descriptor_scan():
    c=bytearray(ENTRY+MARK+bytes.fromhex('f5 c5 d5 e5'))
    labels={}; fix=[]
    def e(*b): c.extend(b)
    def w(op,n): e(op,n&255,n>>8)
    def lab(n): labels[n]=len(c)
    def j(op,n): e(op,0,0);fix.append((len(c)-2,n))
    w(0x21,BASE+33);w(0x22,A2_PTR);w(0x21,0x8000)
    lab('loop');e(0x7c,0xfe,0xbf);j(0xc2,'c0');e(0x7d,0xfe,254);j(0xd2,'skip')
    lab('c0');e(0x7c,0xfe,0xc0);j(0xc2,'cmp')
    lab('skip');w(0x21,0xc360)
    lab('cmp');e(0xe5,0x7e,0xfe,5);j(0xc2,'miss')
    e(0x23,0x5e,0x23,0x56,0xeb,0x7c,0xfe,0x80);j(0xda,'miss')
    # ポインタの全5BがRAM内、かつ予約域と重ならない。
    e(0x7c,0xfe,0xff);j(0xc2,'reserved');e(0x7d,0xfe,0xfc);j(0xd2,'miss')
    lab('reserved');e(0x7c,0xfe,0xbf);j(0xda,'text')
    e(0x7c,0xfe,0xc4);j(0xd2,'text')
    # BFxx末尾とC3xx先頭も候補全体の重なりを除外。
    e(0x7c,0xfe,0xbf);j(0xc2,'c3');e(0x7d,0xfe,0xfc);j(0xda,'text');j(0xc3,'miss')
    lab('c3');e(0x7c,0xfe,0xc3);j(0xc2,'miss');e(0x7d,0xfe,0x60);j(0xda,'miss')
    lab('text')
    for b in b't4own': e(0x7e,0xfe,b);j(0xc2,'miss');e(0x23)
    e(0xe1);w(0x3a,BASE+32);e(0xfe,255);j(0xca,'next')
    e(0x3c);w(0x32,BASE+32);e(0xfe,5);j(0xd2,'next')
    e(0xed,0x5b,A2_PTR&255,A2_PTR>>8,0x7d,0x12,0x13,0x7c,0x12,0x13,
      0xed,0x53,A2_PTR&255,A2_PTR>>8);j(0xc3,'next')
    lab('miss');e(0xe1)
    lab('next');e(0x7c,0xfe,255);j(0xc2,'inc');e(0x7d,0xfe,253);j(0xca,'end')
    lab('inc');e(0x23);j(0xc3,'loop')
    lab('end');e(0x3e,219);w(0x32,BASE+31);e(0xe1,0xd1,0xc1,0xf1,0xc9)
    for at,name in fix: c[at:at+2]=(CODE+labels[name]).to_bytes(2,'little')
    assert CODE+len(c)<A2_CAND
    return bytes(c)

def addendum2_arms():
    out=first_arms()[:2]
    for tag,size,suffix in [('int',2,''),('single',4,'!'),('double',8,'#')]:
        for mode,value in [('expr12345',12345),('expr23456',23456),('variable',12345),('mutate',12345)]:
            other=23456 if value==12345 else 12345
            enc=[a2_encoding(value,size),a2_encoding(other,size)]
            expr=f'{12000 if value==12345 else 23000}{suffix}+{345 if value==12345 else 456}{suffix}'
            var='x'+('%' if size==2 else suffix)
            setup=[]
            if mode=='variable': setup=[f'{var}=12345{suffix}'];expr=var
            for k,data in enumerate(enc): setup+=put(A2_CAND+16*k,data)
            setup+=put(A2_PROBE,bytes([0x32,(BASE+70)&255,(BASE+70)>>8,0xc9]))
            post=[result(65,'y=1234'),result(66,f'y=({expr})')]
            # first-HLとfirst-DEを16bitの差として保存。生バイトは読まない。
            for k in (0,1):
                off=33+9*k
                post += [f'p=peek({BASE+off})+256*peek({BASE+off+1})',
                         f'q=peek({BASE+26})+256*peek({BASE+27})',
                         'd=p-q:if d<0 then d=d+65536',
                         f'poke {BASE+52+2*k},d-256*int(d/256)',f'poke {BASE+53+2*k},int(d/256)']
            out.append(dict(id=f'a2-{tag}-{mode}',commands=['def usr0=&hc000:def usr1=&hc2e0',f'y=usr1(usr0({expr}))'],
                setup=setup,post=post,code=list(scan_code(enc,mode=='mutate')),
                prediction='A=02/04/08、異値0件、値対照で共通番地。単一一致書換で1234・型維持を仮説'))
    out.append(dict(id='a2-string-expr',commands=['def usr0=&hc000','y$=usr0("t4"+"own")'],
        setup=[],post=[f'p=peek({BASE+33})+256*peek({BASE+34})',
        f'q=peek({BASE+24})+256*peek({BASE+25})','d=p-q:if d<0 then d=d+65536',
        f'poke {BASE+52},d-256*int(d/256)',f'poke {BASE+53},int(d/256)'],
        code=list(descriptor_code()),prediction='A=03、記述子の最初番地とDE差0を仮説'))
    return out

# 追補3は追補2と同じ走査・予約域・返却型採取を使う。
ADDENDUM3_PLAN_SHA='21e7a8e12b589fff0589f72576208aee06e60f8bdd6cb6f36bef364a33fa33f0'
ADDENDUM3_PROGRAM_SHA='27bf93e4a0c4cdfe5d2960b6724cd92bb12355bc7cc035e2143fe5bfee2a86a3'

def addendum3_arms():
    out=first_arms()[:2]
    for mode,value,other,expr in [('expr25000',25000,23456,'24000+1000'),
                                 ('expr23456',23456,25000,'23000+456'),
                                 ('mutate',25000,23456,'24000+1000')]:
        enc=[a2_encoding(value,2),a2_encoding(other,2)]
        setup=[]
        for k,data in enumerate(enc): setup+=put(A2_CAND+16*k,data)
        setup+=put(A2_PROBE,bytes([0x32,(BASE+70)&255,(BASE+70)>>8,0xc9]))
        post=[result(65,'y%=1234'),result(66,f'y%=({expr})')]
        for k in (0,1):
            off=33+9*k
            post += [f'p=peek({BASE+off})+256*peek({BASE+off+1})',
                     f'q=peek({BASE+26})+256*peek({BASE+27})',
                     'd=p-q:if d<0 then d=d+65536',
                     f'poke {BASE+52+2*k},d-256*int(d/256)',f'poke {BASE+53+2*k},int(d/256)']
        out.append(dict(id=f'a3-int-{mode}',
            commands=['def usr0=&hc000:def usr1=&hc2e0',f'y%=usr1(usr0({expr}))'],
            setup=setup,post=post,code=list(scan_code(enc,mode=='mutate')),
            prediction='入口A=02、主候補HL+0に1件・異値0件。書換でy%=1234・返却型02を仮説'))
    return out

def a2_write_allowed(i,n,stage):
    return (stage==2 and (32<=i<=49 or (i==31 and n==219) or (i==68 and n==1) or (i==70 and n in (2,3,4,8)))) or (stage==3 and 52<=i<=55)

def a2_valid(o,a):
    if not a['id'].startswith(('a2-','a3-')): return True
    v=o['values']; ws=o['writes']; executed=v['p30']==213
    payload=[(i,n) for i,n in ws[97:] if i in {31,68,70}|set(range(32,50))|set(range(52,56))]
    if not executed: return not payload
    active=0
    for i,n in ws[97:]:
        if i==1: active=n
        if i in {31,68,70}|set(range(32,50))|set(range(52,56)) and not a2_write_allowed(i,n,active): return False
    if 'string' in a['id'] and any(41<=i<=49 or i in (54,55,68,70) for i,n in payload): return False
    if v['p31']!=219 or sum(i==31 for i,n in payload)!=1: return False
    if v['s2_first']!=0: return True # 呼出途中のERRは残し、成功とは解釈しない。
    for k in range(1 if 'string' in a['id'] else 2):
        count=v['p'+str(32+9*k)]
        for j in range(4):
            lo=33+9*k+2*j; addr=v['p'+str(lo)]+256*v['p'+str(lo+1)]
            if j<min(count,4):
                if not 0x8000<=addr<=0xffff or 0xc000<=addr<0xc360: return False
            elif addr: return False
        # 件数は1から単調増加し255で飽和。全番地は一度だけ書かれる。
        changes=[n for i,n in payload if i==32+9*k]
        if changes!=list(range(1,count+1)): return False
        for j in range(8):
            if sum(i==33+9*k+j for i,n in payload)!=(1 if j<2*min(count,4) else 0): return False
    if v['p68'] and ('mutate' not in a['id'] or v['p32']!=1): return False
    return True

def a2_execute(code,candidates,seed):
    """生成したZ80バイトを実行する合成器。公式ROMもsrcも入力にしない。"""
    ram=bytearray(65536)
    ram[CODE:CODE+len(code)]=code
    for k,data in enumerate(candidates): ram[A2_CAND+16*k:A2_CAND+16*k+len(data)]=data
    for addr,data in seed.items(): ram[addr:addr+len(data)]=data
    r=dict(a=2,f=0x41,b=0x12,c=0x34,d=0x91,e=0,h=0x90,l=0,sp=0xdf00)
    original=dict(r);pc=CODE; writes=[];steps=0
    def pair(name): return r[name[0]]*256+r[name[1]]
    def setpair(name,v): r[name[0]]=v>>8;r[name[1]]=v&255
    def read(addr):
        assert 0x8000<=addr<=0xffff,'合成Z80のROM読出し'
        return ram[addr]
    def store(addr,v):
        ram[addr]=v&255
        if BASE<=addr<BASE+96: writes.append([addr-BASE,v&255])
    def pop():
        v=read(r['sp'])+256*read(r['sp']+1);r['sp']+=2;return v
    def push(v):
        r['sp']-=2;store(r['sp'],v);store(r['sp']+1,v>>8)
    def fetch():
        nonlocal pc
        v=ram[pc];pc+=1;return v
    def word(): return fetch()+256*fetch()
    for steps in range(12000000):
        op=fetch()
        if op==0xc9:
            assert r==original,'レジスタ/フラグ/スタック復元'
            return ram,writes,steps
        if op==0x32: store(word(),r['a'])
        elif op==0x3a: r['a']=read(word())
        elif op in (0x21,0x11): setpair('hl' if op==0x21 else 'de',word())
        elif op==0x22:
            addr=word();store(addr,r['l']);store(addr+1,r['h'])
        elif op==0x2a:
            addr=word();setpair('hl',read(addr)+256*read(addr+1))
        elif op==0xed:
            sub=fetch();addr=word()
            if sub==0x5b: setpair('de',read(addr)+256*read(addr+1))
            else:
                v=r['sp'] if sub==0x73 else pair({0x43:'bc',0x53:'de'}[sub])
                store(addr,v);store(addr+1,v>>8)
        elif op in (0xf5,0xc5,0xd5,0xe5): push(pair({0xf5:'af',0xc5:'bc',0xd5:'de',0xe5:'hl'}[op]))
        elif op in (0xf1,0xc1,0xd1,0xe1): setpair({0xf1:'af',0xc1:'bc',0xd1:'de',0xe1:'hl'}[op],pop())
        elif op==0x3e: r['a']=fetch()
        elif op==0x06: r['b']=fetch()
        elif op in (0x7c,0x7d): r['a']=r['h' if op==0x7c else 'l']
        elif op==0x7e: r['a']=read(pair('hl'))
        elif op==0x1a: r['a']=read(pair('de'))
        elif op in (0x5e,0x56): r['e' if op==0x5e else 'd']=read(pair('hl'))
        elif op in (0xfe,0xbe):
            v=fetch() if op==0xfe else read(pair('hl'))
            r['f']=(0x40 if r['a']==v else 0)|(1 if r['a']<v else 0)
        elif op in (0x3c,0x05):
            key='a' if op==0x3c else 'b';r[key]=(r[key]+(1 if key=='a' else -1))&255
            r['f']=(r['f']&1)|(0x40 if r[key]==0 else 0)
        elif op in (0x23,0x13):
            key='hl' if op==0x23 else 'de';setpair(key,(pair(key)+1)&65535)
        elif op==0x12: store(pair('de'),r['a'])
        elif op==0x36: store(pair('hl'),fetch())
        elif op==0xeb:
            de=pair('de');setpair('de',pair('hl'));setpair('hl',de)
        elif op in (0xc3,0xc2,0xca,0xd2,0xda):
            addr=word()
            if op==0xc3 or (op==0xc2 and not r['f']&0x40) or (op==0xca and r['f']&0x40) or (op==0xd2 and not r['f']&1) or (op==0xda and r['f']&1): pc=addr
        else: raise AssertionError(f'合成Z80未定義命令 {op:02x}')
    raise AssertionError('走査ステップ上限')

@patch(__name__+'.ROUND','addendum2')
@patch(__name__+'.OFFICIAL',False)
def addendum2_selftest():
    # 媒体器具による差し替えから独立した、メモリだけの合成対照。
    synth=_memory_synth; valid=memory_valid
    assert hashlib.sha256(json.dumps(addendum2_arms(),sort_keys=True,separators=(',',':')).encode()).hexdigest()==ADDENDUM2_PLAN_SHA
    assert hashlib.sha256(json.dumps([program(a) for a in addendum2_arms()],separators=(',',':')).encode()).hexdigest()==ADDENDUM2_PROGRAM_SHA
    empty_writes={}
    for size in (2,4,8):
        data=a2_encoding(12345,size);cross=a2_encoding(23456,size)
        code=scan_code([data,cross])
        for seed,expected_count in [({},0),({0x9003:data,0xfff8:data},2),
              ({0x9000+size*i:data for i in range(270)},255)]:
            ram,ws,steps=a2_execute(code,[data,cross],seed)
            if not seed: empty_writes[size]=ws
            assert ram[BASE+32]==expected_count and ram[BASE+41]==0 and ram[BASE+31]==219
            if expected_count:
                assert [int.from_bytes(ram[BASE+33+2*j:BASE+35+2*j],'little') for j in range(min(expected_count,4))]==sorted(seed)[:4]
        ram,_,_=a2_execute(scan_code([data,cross],True),[data,cross],{0x9876:data})
        assert ram[0x9876:0x9876+size]==a2_encoding(1234,size) and ram[BASE+68]==1
        for seed in ({},{0x9000:data,0x9100:data}):
            ram,_,_=a2_execute(scan_code([data,cross],True),[data,cross],seed)
            assert ram[BASE+68]==0
        # 予約域を跨ぐ候補も除外。末尾ちょうどの候補は採る。
        ram,_,_=a2_execute(code,[data,cross],{0xc360-size+1:data,0x10000-size:data})
        assert ram[BASE+32]==1 and int.from_bytes(ram[BASE+33:BASE+35],'little')==0x10000-size
    ram,_,_=a2_execute(bytes([0x32,(BASE+70)&255,(BASE+70)>>8,0xc9]),[],{})
    assert ram[BASE+70]==2
    code=descriptor_code()
    for seed,want in [({},0),({0x9000:bytes([5,0,0x98]),0x9800:b't4own'},1),
                      ({0x9000:bytes([5,0xff,0x7f])},0),
                      ({0x9000:bytes([5,0xfc,0xff])},0),
                      ({0x9000:bytes([5,0,0x98]),0x9800:b't4owx'},0),
                      ({0x9000:bytes([5,0x80,0xc2]),0xc280:b't4own'},0)]:
        ram,ws,_=a2_execute(code,[],seed);assert ram[BASE+32]==want
        if not seed: empty_writes[3]=ws
    for a in addendum2_arms():
        assert valid(synth(a),a)
        assert sum(len(c)+1 for c in program(a))+1<=8192
        if not a['id'].startswith(('a2-','a3-')): continue
        size=3 if 'string' in a['id'] else 2 if '-int-' in a['id'] else 4 if '-single-' in a['id'] else 8
        # 上で実生成命令を実行して得た型別0件の印を段2へ差し込む。
        ws=empty_writes[size]
        good=synth(a);ix=good['writes'].index([1,2])+1;good['writes'][ix:ix]=ws
        good['values']={FIELDS[i]:v for i,v in good['writes']};assert valid(good,a)
        bad=copy.deepcopy(good);bad['writes'].remove([31,219]);bad['values']={FIELDS[i]:v for i,v in bad['writes']}
        assert memory_valid(good,a) and not memory_valid(bad,a),'完了印判定の陰性'
        bad=copy.deepcopy(good);ix=bad['writes'].index([31,219]);bad['writes'][ix:ix]=[[32,1],[33,0],[34,0]]
        bad['values']={FIELDS[i]:v for i,v in bad['writes']};assert not valid(bad,a),'番地判定の陰性'
    print('OK 追補2: 実生成Z80の全RAM走査・陽性/0件・255飽和・境界/予約域・単一一致介入・復元・関門陰性',flush=True)

@patch(__name__+'.ROUND','addendum3')
@patch(__name__+'.OFFICIAL',False)
def addendum3_selftest():
    synth=_memory_synth; valid=memory_valid
    assert hashlib.sha256(json.dumps(addendum3_arms(),sort_keys=True,separators=(',',':')).encode()).hexdigest()==ADDENDUM3_PLAN_SHA
    assert hashlib.sha256(json.dumps([program(a) for a in addendum3_arms()],separators=(',',':')).encode()).hexdigest()==ADDENDUM3_PROGRAM_SHA
    data=a2_encoding(25000,2);cross=a2_encoding(23456,2)
    assert data==bytes.fromhex('a8 61') and a2_encoding(1234,2)==bytes.fromhex('d2 04')
    for a in addendum3_arms():
        assert valid(synth(a),a)
        assert sum(len(c)+1 for c in program(a))+1<=8192
        if not a['id'].startswith('a3-'): continue
        candidates=[cross,data] if a['id'].endswith('expr23456') else [data,cross]
        target=candidates[0];mutate=a['id'].endswith('mutate')
        # 腕そのもののZ80を実行。既知HL=9000の陽性と0/複数件の陰性。
        for seed,count in [({0x9000:target},1),({},0),({0x9000:target,0x9100:target},2)]:
            ram,ws,_=a2_execute(bytes(a['code']),candidates,seed)
            assert ram[BASE+32]==count and ram[BASE+41]==0 and ram[BASE+31]==219
            assert ram[BASE+68]==int(mutate and count==1)
            if count:
                assert int.from_bytes(ram[BASE+33:BASE+35],'little')==0x9000
            for addr,original in seed.items():
                assert ram[addr:addr+2]==(a2_encoding(1234,2) if mutate and count==1 else original)
            good=synth(a);ix=good['writes'].index([1,2])+1
            probe_ram,probe_ws,_=a2_execute(bytes([0x32,(BASE+70)&255,(BASE+70)>>8,0xc9]),[],{})
            assert probe_ram[BASE+70]==2
            good['writes'][ix:ix]=ws+probe_ws
            good['values']={FIELDS[i]:v for i,v in good['writes']}
            assert valid(good,a)
            bad=copy.deepcopy(good);bad['writes'].remove([31,219])
            bad['values']={FIELDS[i]:v for i,v in bad['writes']};assert not valid(bad,a)
            bad=copy.deepcopy(good);ix=bad['writes'].index([31,219])
            bad['writes'][ix:ix]=[[32,1],[33,0],[34,0]]
            bad['values']={FIELDS[i]:v for i,v in bad['writes']};assert not valid(bad,a)
    print('OK 追補3: 実生成Z80・25000/23456・HL+0単一一致・1234全長書換・0/複数件不介入・返却型・関門陰性',flush=True)

def arms(): return first_arms() if ROUND=='first' else addendum3_arms() if ROUND=='addendum3' else addendum2_arms() if ROUND=='addendum2' else addendum_arms()

def program(a):
    lines={1:'clear ,&hbfff',2:'poke &hc300,197',3:'for i=1 to 95:poke &hc300+i,0:next i',4:'on error goto 9000'}
    pokes=put(CODE,bytes(a['code']))
    if a['id'].startswith(('a2-','a3-')):
        data=bytes(a['code'])
        for j in range(0,len(data),12): lines[5000+j]='data '+','.join(map(str,data[j:j+12]))
        pokes=[f'for i=0 to {len(data)-1}:read b:poke {CODE}+i,b:next i']
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
        elif a['id'].startswith(('a2-','a3-')) and a2_write_allowed(i,n,stage): pass
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
    return stages==list(range(1,len(a['commands'])+1))+[3,90] and returned==set(range(1,len(a['commands'])+1)) and ws[-1]==[3,163] and sum(x==[3,163] for x in ws)==1 and {FIELDS[i]:n for i,n in ws}==v and a2_valid(o,a)

def valid(o,a): return memory_valid(o,a)

class ExecutionDenied(RuntimeError): pass

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

def extra_wait_frames(a,official):
    # 自作は公式より遅く、追補1のBASIC候補照合に時間を要するため自作走だけ
    # 終了待ちを12000フレーム延長する。経過時間は要求ではない。
    return 12000 if MEASURE_NAME=='mlcall' and not official and a['id'].startswith('a1-') else 0

def capture_timeout(a,official):
    # 追加フレームを60fpsで実行する200秒も自作走の上限に加える。
    return 180+extra_wait_frames(a,official)/60

def schedule(a,official):
    at=1200 if official else 120; typed=[]
    if official: typed.append((300,'\n'))
    for cmd in program(a):
        typed.append((at,cmd+'\n')); at+=(len(cmd)+1)*(12 if official else 8)+(360 if official else 120)
    return typed,at+((36000 if official else 7200) if a['id'].startswith(('a2-','a3-')) else (18000 if official else 3600))+extra_wait_frames(a,official) # 公式の初期化・誤り復帰と実行を待つ。

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
        p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,M6FH_LONG_TYPING='1'),timeout=capture_timeout(a,official))
        if p.returncode: raise ExecutionDenied('実行拒否')
        if b'untypable' in p.stderr.lower(): raise RuntimeError('打鍵拒否')
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

_memory_synth=synth # 合成検査用に、媒体器具の差し替え前の生成器を保持。

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


# 結果ノート用の限定除外。通常の全欄自己照合と混ぜず、明示 --results で使う。
RESULT_ARM_EXCLUSIONS={
    'usr-mutate-int':'HL介入位置未確定。追補2で再測定',
    'usr-mutate-single':'HL介入位置未確定。追補2で再測定',
    'usr-mutate-double':'HL介入位置未確定。追補2で再測定',
    'usr-mutate-string':'HL介入位置未確定。追補2で再測定',
    'a1-call-minus1':'完了関門不成立。時間切れは不明であり期待値にしない',
    'a1-call-65535':'完了関門不成立。時間切れは不明であり期待値にしない',
    'a1-call-undefined':'完了関門不成立。時間切れは不明であり期待値にしない',
}

def result_exclusions(round_name,aid):
    rules={'values.p'+str(i):'入口BC/DE/HL/SPの生番地は公式配置に依存' for i in range(22,30)}
    if MEASURE_NAME=='mlcall' and round_name=='first' and (aid.startswith('usr-') or aid.startswith('def-')):
        rules.update({'values.p'+str(i):'引数1の候補照合は偶然一致。識別値の追補1で判定' for i in range(32,65)})
    if MEASURE_NAME=='mlcall' and round_name in ('addendum2','addendum3') and aid.startswith(('a2-','a3-')):
        rules.update({'values.p'+str(i):'一致番地の生値は公式メモリ配置に依存' for i in (*range(33,41),*range(42,50))})
        rules.update({'values.p'+str(i):'異値候補は0件か否かのみ比較。初期番地由来の差や偶然一致位置は比較しない' for i in (54,55)})
        if aid in ('a2-int-expr12345','a2-int-variable','a2-int-mutate'):
            rules.update({'values.p'+str(i):'整数12345はASCIIとの偶然一致により場所・件数・介入有無・値判定が不定。型・誤り・完了印・戻り型のみ採る' for i in (32,41,52,53,65,66,68)})
    if MEASURE_NAME=='mlcall':
        if round_name=='first' and aid=='varptr-array':
            rules['values.p68']='配列要素の単精度1符号化との不一致は原因未解決。公式の不一致を要求にせず原因は追補で測る'
        if round_name=='addendum1' and aid=='a1-usr-string':
            rules.update({'values.p'+str(i):'BCからの候補照合は公式作業域の並びに依存。BCの指す関係は要求せずDE+0の記述子は比較する' for i in range(44,50)})
        if round_name=='addendum2' and aid=='a2-string-expr':
            rules.update({'values.p'+str(i):'文字列記述子の写しの数は一時領域の作り方に依存。件数真偽は要求せず最初一致とDEの差は比較する' for i in (32,41)})
        if round_name=='first' and aid=='varptr-difference':
            rules.update({'values.p'+str(i):'変数領域の配置に依存する番地差。要求はVARPTRの指す先の形式であり変数間隔ではない' for i in (74,75)})
        if round_name=='addendum1' and aid=='a1-call-args-mixed':
            rules.update({'values.p'+str(i):'変数領域の配置に依存する隣接変数の候補位置。要求はHL+0が第1引数・DE+0が第2引数を指す関係' for i in (37,38)})
        if round_name=='addendum2' and aid in ('a2-int-variable','a2-single-variable','a2-double-variable'):
            # 整数12345の既存の偶然一致除外は保持し、未除外の差欄だけ追加する。
            for i in (52,53):
                rules.setdefault('values.p'+str(i),'変数領域の配置に依存する最初候補とHLの差。要求は引数を指す関係と指す先の形式であり変数領域と作業域の距離ではない')
    if MEASURE_NAME=='bsave':
        rules.update({f'media.{part}.sha256':'末尾以後のバッファ由来バイトを再現対象にしない' for part in ('header','payload')})
        if aid=='a1-cal-disk': rules['media.payload.matches']='0x00候補は空き領域にも一致する弱いパターン'
    return rules

def result_project(value,rules):
    value=copy.deepcopy(value)
    for path in rules:
        node=value
        parts=path.split('.')
        for part in parts[:-1]:
            if not isinstance(node,dict) or part not in node: break
            node=node[part]
        else:
            if isinstance(node,dict): node.pop(parts[-1],None)
    return value

def result_normalize(value,rnd,aid):
    value=copy.deepcopy(value)
    if MEASURE_NAME=='mlcall' and rnd in ('addendum2','addendum3') and aid.startswith(('a2-','a3-')):
        value['values']['p32']=int(value['values']['p32']==1) # 主候補がちょうど1件
        value['values']['p41']=int(value['values']['p41']==0) # クロス候補が0件
    return value

def result_rounds(rounds):
    if MEASURE_NAME=='bsave' and rounds=={'addendum1'}: return 'addendum1'
    if MEASURE_NAME=='mlcall':
        if rounds=={'first','addendum1'}: return 'first'
        if rounds=={'addendum2','addendum3'}: return 'addendum2'
    raise ValueError('結果ラウンド不足/混在')


def result_definitions():
    global ROUND
    selected=ROUND
    try:
        out={}
        for rnd in (('first','addendum1') if MEASURE_NAME=='bsave' else ('first','addendum1','addendum2','addendum3')):
            ROUND=rnd;out[rnd]={a['id']:a for a in arms()}
        return out
    finally: ROUND=selected

def result_read(paths,official=False):
    global ROUND,OFFICIAL
    definitions=result_definitions(); combined={}; rounds=set()
    for path in paths:
        with path.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
        groups={}
        for row in rows: groups.setdefault(row['arm'],[]).append(row)
        candidates=[rnd for rnd,aa in definitions.items() if set(groups)==set(aa)]
        if len(candidates)!=1: raise ValueError('結果TSV全腕集合')
        rnd=candidates[0]
        if rnd in rounds: raise ValueError('結果TSVラウンド重複')
        rounds.add(rnd)
        if MEASURE_NAME=='bsave' and rnd=='first':
            print('EXCLUDE first/*: 第1回BSAVE全腕は媒体構成誤りで無効')
            raise ValueError('第1回BSAVEは期待値に使えない')
        rs=[]; selected=ROUND; selected_official=OFFICIAL
        try:
            ROUND=rnd; OFFICIAL=official
            for aid,rr in groups.items():
                a=definitions[rnd][aid]
                if len(rr)!=2 or {r['repeat'] for r in rr}!={'1','2'}: raise ValueError('結果反復')
                if any(json.loads(r['plan'])!=program(a) for r in rr): raise ValueError('結果予定')
                if MEASURE_NAME=='mlcall' and aid in RESULT_ARM_EXCLUSIONS:
                    print(f'EXCLUDE {rnd}/{aid}: {RESULT_ARM_EXCLUSIONS[aid]}')
                    continue
                obs=[json.loads(r['observation']) for r in rr]
                if any(r['gate']!='pass' for r in rr) or not all(valid(o,a) for o in obs) or obs[0]!=obs[1]: raise ValueError('結果関門/観測/2走')
                rs.append(dict(arm=a,obs=obs,gate=True))
                value=dict(values=obs[0]['values'],media=obs[0].get('media'))
                rules=result_exclusions(rnd,aid)
                item=dict(round=rnd,values=result_project(result_normalize(value,rnd,aid),rules),exclusions=rules)
                if aid in combined:
                    # 較正のみ共通。両ラウンドの厳密一致を確認し、先行回へ一本化。
                    if not aid.startswith('cal-') or combined[aid]['values']!=item['values']: raise ValueError('結果重複')
                    if rnd in ('first','addendum2'): combined[aid]=item
                    continue
                combined[aid]=item
            if not calibrated(rs): raise ValueError('結果較正/媒体関門')
        finally: ROUND=selected; OFFICIAL=selected_official
    result_rounds(rounds)
    return combined

def results_expected(out,paths):
    got=result_read(paths,official=True)
    write_tsv(out,['arm','round','values','exclusions'],[[k,v['round'],json.dumps(v['values']),json.dumps(v['exclusions'],ensure_ascii=False)] for k,v in sorted(got.items())])
    return len(got)

def results_check(exp,paths):
    definitions=result_definitions()
    with exp.open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
    want={r['arm']:dict(round=r['round'],values=json.loads(r['values']),exclusions=json.loads(r['exclusions'])) for r in rows}
    selected_rounds={item['round'] for item in want.values()}
    calibration_round=result_rounds(selected_rounds)
    required={aid for rnd,aa in definitions.items() if rnd in selected_rounds for aid in aa if (MEASURE_NAME!='bsave' or rnd=='addendum1') and (MEASURE_NAME!='mlcall' or aid not in RESULT_ARM_EXCLUSIONS)}
    if len(rows)!=len(want) or set(want)!=required: raise ValueError('結果期待値全腕')
    for aid,item in want.items():
        rnd=item['round']
        if rnd not in definitions or aid not in definitions[rnd] or (aid.startswith('cal-') and rnd!=calibration_round): raise ValueError('結果期待値ラウンド')
        rules=result_exclusions(rnd,aid)
        if item['exclusions']!=rules: raise ValueError('結果除外の改変')
        value=item['values']
        # 除外欄以外の欠落・追加は許さない。媒体値は元の形へ戻して検証。
        restored=copy.deepcopy(value)
        if type(restored) is not dict or set(restored)!={'values','media'}: raise ValueError('結果期待値形')
        for path in rules:
            if path.startswith('values.'): restored['values'][path.split('.')[1]]=0
        if MEASURE_NAME=='mlcall' and rnd=='first' and (aid.startswith('usr-') or aid.startswith('def-')):
            for i in range(32,65): restored['values']['p'+str(i)]=0
        media=restored['media']
        if isinstance(media,dict) and media.get('found'):
            for part in ('header','payload'): media[part]['sha256']='0'*64
            if aid=='a1-cal-disk': media['payload']['matches']=[]
        if rnd in ('addendum2','addendum3') and aid.startswith(('a2-','a3-')) and any(value['values'].get('p'+str(i),0) not in (0,1) for i in (32,41)): raise ValueError('結果期待値の件数真偽')
        if result_project(restored,rules)!=value or not expected_shape(restored,definitions[rnd][aid]): raise ValueError('結果期待値欄')
        if aid.startswith('cal-') and restored!=dict(values=synth(definitions[rnd][aid])['values'],media=None): raise ValueError('結果期待値較正')
    try: got=result_read(paths)
    except (ValueError,KeyError,TypeError): got={}
    bad=[k for k,v in want.items() if got.get(k)!=v]
    for k in bad: print(f'DIFF {k}')
    return len(want)-len(bad),bad

def results_safety_selftest(work,rounds=None):
    # 除外による弱体化を検査。入力の順序、除外改変、対象欄の差、関門落ち。
    global ROUND,OFFICIAL
    selected=ROUND; selected_official=OFFICIAL
    try:
        with tempfile.TemporaryDirectory(dir=work,prefix='results-') as td:
            td=Path(td); paths=[]
            for rnd in (rounds or (('addendum1',) if MEASURE_NAME=='bsave' else ('first','addendum1'))):
                ROUND=rnd; OFFICIAL=False
                rs=[dict(arm=a,obs=[synth(a),synth(a)],gate=True) for a in arms()]
                if MEASURE_NAME=='bsave':
                    # ディスク較正は陽性、他腕に一つ誤りを置いて非一様にする。
                    for o in rs[2]['obs']:
                        o['media']=dict(found=True,drive='synthetic',name_match=True,type01=True,
                            header=dict(matches=[],length=16,sha256='0'*64),
                            payload=dict(matches=[],length=256,sha256='0'*64))
                    for o in rs[-1]['obs']:
                        ix=o['writes'].index([1,1])+1
                        o['writes'][ix:ix]=error_block(2,1,0,set())
                        o['values']={FIELDS[i]:v for i,v in o['writes']}
                path=td/(rnd+'.tsv'); emit(path,rs); paths.append(path)
            exp=td/'expected.tsv'
            with redirect_stdout(io.StringIO()):
                count=results_expected(exp,paths)
                assert results_check(exp,paths)==(count,[])
                if len(paths)==2:
                    assert results_expected(td/'reverse.tsv',paths[::-1])==count
                    assert exp.read_bytes()==(td/'reverse.tsv').read_bytes()
                rows=list(csv.DictReader(exp.open(),delimiter='\t'))
                original=exp.read_text()
                rules=json.loads(rows[0]['exclusions']); rules['values.first_err']='偽の除外'
                rows[0]['exclusions']=json.dumps(rules)
                write_tsv(exp,rows[0].keys(),[r.values() for r in rows])
                try: results_check(exp,paths)
                except ValueError: pass
                else: raise AssertionError('除外範囲拡大')
                exp.write_text(original)
                # 非較正の実行印（追補は入口A）の差は一腕不一致。生番地だけなら一致。
                path=paths[-1]; original=path.read_text()
                rows=list(csv.DictReader(path.open(),delimiter='\t')); aid=rows[4]['arm']
                for slot,value in ((22,123),((21,4) if rounds else (30,213))):
                    changed=copy.deepcopy(rows)
                    for row in changed[4:6]:
                        o=json.loads(row['observation']); ix=o['writes'].index([1,1])+1
                        o['writes'].insert(ix,[slot,value]); o['values']['p'+str(slot)]=value
                        row['observation']=json.dumps(o)
                    write_tsv(path,changed[0].keys(),[r.values() for r in changed])
                    ok,bad=results_check(exp,paths)
                    assert (ok,bad)==((count,[]) if slot==22 else (count-1,[aid]))
                path.write_text(original)
                rows[4]['gate']='gate_failed'
                write_tsv(path,rows[0].keys(),[r.values() for r in rows])
                assert results_check(exp,paths)[1]
    finally: ROUND=selected; OFFICIAL=selected_official
    print('OK 結果除外: 理由固定・番地のみ許容・実行印差/関門失敗を拒否',flush=True)

    if MEASURE_NAME=='mlcall' and rounds is None:
        # 配置差だけを許し、各腕の形式・参照関係・印の差は検出する。
        cases=[('first','varptr-difference',(74,75),(21,30,66,67,68)),
               ('first','varptr-array',(68,),(21,30,66,67)),
               ('addendum1','a1-usr-string',tuple(range(44,50)),(21,30,43)),
               ('addendum2','a2-string-expr',(32,41),(21,30,31,52,53)),
               ('addendum1','a1-call-args-mixed',(37,38),(21,30,32,43)),
               ('addendum2','a2-single-variable',(52,53),(21,30,31,32,41,65,66,68,70)),
               ('addendum2','a2-double-variable',(52,53),(21,30,31,32,41,65,66,68,70)),
               ('addendum2','a2-int-variable',(52,53),(21,30,31,70))]
        definitions=result_definitions()
        for rnd,aid,excluded,retained in cases:
            rules=result_exclusions(rnd,aid)
            value=dict(values=synth(definitions[rnd][aid])['values'],media=None)
            base=result_project(result_normalize(value,rnd,aid),rules)
            for slot in (*excluded,*retained):
                changed=copy.deepcopy(value)
                changed['values']['p'+str(slot)]^=1
                projected=result_project(result_normalize(changed,rnd,aid),rules)
                assert (projected==base)==(slot in excluded),(aid,slot)
            changed=copy.deepcopy(value)
            changed['values']['first_err']^=1
            assert result_project(result_normalize(changed,rnd,aid),rules)!=base
        print('OK 限定除外: 指定欄のみ許容・非除外の形式/引数参照/件数真偽/A/印/誤りの差を検出',flush=True)
        results_safety_selftest(work,('addendum2','addendum3'))
        def projected(aid,count,cross=0,**changes):
            value=dict(values=dict(synth(addendum2_arms()[2])['values'],p32=count,p41=cross,**changes),media=None)
            return result_project(result_normalize(value,'addendum2',aid),result_exclusions('addendum2',aid))
        aid='a2-single-variable'
        assert projected(aid,2)==projected(aid,19)
        assert projected(aid,1)!=projected(aid,2)
        assert projected(aid,2,1)==projected(aid,2,18)
        assert projected(aid,2,0)!=projected(aid,2,1)
        for slot in ('p33','p42','p54','p52','p53'):
            assert projected(aid,2)==projected(aid,2,**{slot:123})
        for slot in ('p21','p30','p31','p65','p66','p68','p70'):
            assert projected(aid,2)!=projected(aid,2,**{slot:1})
        aid='a2-int-mutate'
        assert projected(aid,19)==projected(aid,1,18,p52=123,p65=1,p66=1,p68=1)
        assert projected(aid,19)!=projected(aid,19,p70=2)
        print('OK 追補結果除外: 件数真偽・ASCII衝突・比較対象の差を検出',flush=True)


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

def wait_selftest(work):
    # 合成だけで公式の従来待ち・打鍵と、自作追補1だけの延長を確認する。
    aa=first_arms()+addendum_arms()+addendum2_arms()+addendum3_arms()
    with tempfile.TemporaryDirectory(dir=work,prefix='wait-') as td:
        for a in aa:
            for official in (False,True):
                at=1200 if official else 120
                expected_typed=[(300,'\n')] if official else []
                for cmd in program(a):
                    expected_typed.append((at,cmd+'\n'))
                    at+=(len(cmd)+1)*(12 if official else 8)+(360 if official else 120)
                wait=((36000 if official else 7200) if a['id'].startswith(('a2-','a3-')) else (18000 if official else 3600))
                extra=12000 if MEASURE_NAME=='mlcall' and not official and a['id'].startswith('a1-') else 0
                typed,finish=schedule(a,official)
                assert typed==expected_typed and finish==at+wait+extra
                # captureが実際に渡すフレーム数とtimeoutも検査。公式ROMは起動しない。
                with patch.object(kw,'find_core',return_value=Path('synthetic')),patch.object(subprocess,'run',return_value=subprocess.CompletedProcess([],1,b'',b'')) as run:
                    try: capture(Path('synthetic'),official,a,Path(td))
                    except ExecutionDenied: pass
                    else: raise AssertionError('合成実行拒否')
                argv=run.call_args.args[0]
                assert int(argv[argv.index('--frames')+1])==finish
                assert run.call_args.kwargs['timeout']==180+extra/60
    print('OK 合成: 自作追補1のみ待ち+12000フレーム・上限+200秒、公式は維持',flush=True)

def safety_selftest(work):
    global ROUND
    selected=ROUND
    try:
        ROUND='first'
        first_safety_selftest(work)
    finally: ROUND=selected
    wait_selftest(work)
    assert hashlib.sha256(json.dumps(addendum_arms(),sort_keys=True,separators=(',',':')).encode()).hexdigest()==ADDENDUM_PLAN_SHA,'追補腕署名'
    assert hashlib.sha256(json.dumps([program(a) for a in addendum_arms()],separators=(',',':')).encode()).hexdigest()==ADDENDUM_PROGRAM_SHA,'追補入力署名'
    for a in addendum_arms():
        assert valid(synth(a),a)
        assert sum(len(c)+1 for c in program(a))+1<=8192,'打鍵総数'
    add_pointer_selftest()
    addendum2_selftest()
    addendum3_selftest()

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
            except (PermissionError,ExecutionDenied):
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
    path=(ROOT if work is None else work)/('selfrun-addendum3.md' if ROUND=='addendum3' else 'selfrun-addendum2.md' if ROUND=='addendum2' else 'selfrun-addendum1.md' if ROUND=='addendum1' else 'selfrun.md')
    rows=[f'## {MEASURE_NAME}: {len(rs)}腕×2独立走、関門{sum(r["gate"] for r in rs)}/{len(rs)}',
          '公式ROM未実行。未実装のERRは値一致と区別。画面比較は採らない。',
          '|腕|関門|最初ERR@段|最後ERR@段|','|---|---|---|---|']
    for r in rs:
        v=r['obs'][0].get('values',r['obs'][0].get('errors',{})); g=lambda k:v.get(k,'不明')
        rows.append(f'|{r["arm"]["id"]}|{r["gate"]}|{g("first_err")}@{g("first_stage")}|{g("last_err")}@{g("last_stage")}|')
    with path.open('a') as f: f.write('\n'.join(rows)+'\n')

def selftest(work):
    results_safety_selftest(work)
    safety_selftest(work); rom=work/'rom'
    p=subprocess.run([sys.executable,str(REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(work/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    if p.returncode: raise RuntimeError('自作ビルド失敗')
    rs=measure(rom,False,work); passed=emit(work/'selfrun.tsv',rs)
    summary(rs,work if any(work.resolve().is_relative_to(root.resolve()) for root in (T3B_IMPL_ROOT,REPO/'tmp/c2-work')) else None)
    if passed: expected(work/'self-expected.tsv',[work/'selfrun.tsv']); assert check(work/'self-expected.tsv',work/'selfrun.tsv')==(len(rs),[])
    return int(not passed)

def main():
    global ROUND,OFFICIAL
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='command',required=True)
    m=sub.add_parser('measure'); m.add_argument('--official',action='store_true'); m.add_argument('--rom-dir',type=Path); m.add_argument('--work-dir',type=Path,required=True); m.add_argument('--out',type=Path,required=True)
    s=sub.add_parser('selftest'); s.add_argument('--work-dir',type=Path,default=ROOT/'selftest'); s.add_argument('--synthetic-only',action='store_true')
    sub.add_parser('describe')
    e=sub.add_parser('expected'); e.add_argument('--out',type=Path,required=True); e.add_argument('paths',type=Path,nargs='+')
    c=sub.add_parser('check'); c.add_argument('--expected',type=Path,required=True); c.add_argument('--measured',type=Path,nargs='+',required=True)

    for parser in (e,c): parser.add_argument('--results',action='store_true')
    for parser in (m,s): parser.add_argument('--round',choices=('first','addendum1','addendum2','addendum3'),default='addendum1')
    args=p.parse_args()
    ROUND=getattr(args,'round','addendum1')
    OFFICIAL=getattr(args,'official',False)
    for name in ('work_dir','out','expected','measured'):
        path=getattr(args,name,None)
        if isinstance(path,list):
            if any(not x.is_absolute() or not x.resolve().is_relative_to(ROOT.resolve()) for x in path): p.error('入力もtmp/t4-work内')
            continue
        if path is not None and (not path.is_absolute() or not any(path.resolve().is_relative_to(root.resolve()) for root in (ROOT,IMPL_ROOT,T3B_IMPL_ROOT,REPO/'tmp/c2-work'))): p.error('作業・結果はtmp/t4-workまたはtmp/c2-work内の絶対パス必須')
    if hasattr(args,'paths') and any(not x.is_absolute() or not any(x.resolve().is_relative_to(root.resolve()) for root in (ROOT,IMPL_ROOT,T3B_IMPL_ROOT,REPO/'tmp/c2-work')) for x in args.paths): p.error('入力もtmp/t4-work内')
    if hasattr(args,'work_dir'): args.work_dir.mkdir(parents=True,exist_ok=True)
    if args.command=='describe':
        for a in arms(): print(json.dumps(a,ensure_ascii=False))
        return 0
    if args.command=='expected': print(f'期待値{(results_expected if args.results else expected)(args.out,args.paths)}腕'); return 0
    if args.command=='check':
        if not args.results and len(args.measured)!=1: p.error('通常照合の入力は一つ')
        ok,bad=results_check(args.expected,args.measured) if args.results else check(args.expected,args.measured[0]); print(f'一致{ok}腕、不一致{len(bad)}腕'); return int(bool(bad))
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
