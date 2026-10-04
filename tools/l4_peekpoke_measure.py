#!/usr/bin/env python3
"""l4-s9b の事前予測・安全な PEEK/POKE 採取・照合・自己検査。"""
import argparse
import ast
import contextlib
import csv
from fractions import Fraction
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch
import l4_strfunc_measure as common

kw = common.kw
WORK = kw.REPO.parent / 'tmp/l4s9b-work'
LIMIT, ADDRESS = 49151, 49152  # マニュアルのCLEARによって確保する利用者領域。
DONE = ['s9bd', 1, 1]


def address(x):
    x = Fraction(x)
    return common.integer(x-65536 if 32768 <= x < 65536 else x) & 65535


def controls():
    return [dict(id='control-clear', kind='clear', expected=1),
            dict(id='control-roundtrip', kind='roundtrip', value='73'),
            dict(id='control-error', kind='error', error=5)]


def arms():
    out = []
    for i,v in enumerate(['0','1','127','128','255','327/5','131/2','133/2',
                          '-2/5','1277/5','511/2','256','-1','32768','-32769','"x"'],1):
        out.append(dict(id=f'value-{i:02d}', kind='roundtrip', value=v))
    for name,p in [('decimal',str(ADDRESS)),('hex','&hc000'),('negative','-16384')]:
        out.append(dict(id='address-'+name, kind='roundtrip', value='73', poke=p))
    for name,p in [('plus04','49152+2/5'),('plus05','49152+1/2')]:
        out.append(dict(id='address-poke-'+name,kind='adjacent',fraction=p))
        out.append(dict(id='address-peek-'+name,kind='fraction-read',fraction=p))
    for p in ['65536','-32769']:
        out.append(dict(id='address-out-'+p,kind='out',poke=p))
    out += [dict(id='type-print',kind='print'),dict(id='type-integer',kind='integer')]
    return out


def number(expr):
    """番地は定数の四則式だけ。変数・関数・指数・文字列は拒否する。"""
    expr = re.sub(r'&h([0-9a-f]+)', lambda m:str(int(m[1],16)),expr.lower())
    def visit(n):
        if isinstance(n,ast.Constant) and type(n.value) is int:
            return Fraction(n.value)
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
            return visit(n.operand)*(1 if isinstance(n.op,ast.UAdd) else -1)
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a,b=visit(n.left),visit(n.right)
            if isinstance(n.op,ast.Add): return a+b
            if isinstance(n.op,ast.Sub): return a-b
            if isinstance(n.op,ast.Mult): return a*b
            return a/b
        raise ValueError('番地は定数式に限定する')
    return visit(ast.parse(expr,mode='eval').body)


def possible(expr):
    """小数番地の丸め候補は隣接両方を確保する。ROM・画面領域は許さない。"""
    x=number(expr)
    if not -32768 <= x < 65536:
        raise ValueError('範囲外番地は読み出さない')
    x=x+65536 if x<0 else x
    lo=x.numerator//x.denominator
    return {lo} if x.denominator==1 else {lo,lo+1}


def static_check(lines):
    written=set(); cleared=False
    # 登録順でなく、RUNで実行される行番号順に検査する。
    statements=sorted((int(m[1]),m[2]) for s in lines
                      if (m:=re.fullmatch(r'(\d+) (.*)',s)))
    for _,s in statements:
        if re.search(r'\bclear\b',s):
            if s!=f'clear ,{LIMIT}': raise ValueError('CLEAR指定が不正')
            cleared=True;written.clear()
        tokens=list(re.finditer(r'\bpoke +([^,:]+),|\bpeek\(([^()]*)\)',s))
        if len(tokens)!=len(re.findall(r'\b(?:poke|peek)\b',s)):
            raise ValueError('静的に解析できないメモリアクセスを拒否')
        for token in tokens:
            expr=token[1] or token[2]
            try: targets=possible(expr)
            except ValueError:
                if token[1] and number(expr) in (65536,-32769): continue
                raise
            if not cleared or not targets <= {ADDRESS,ADDRESS+1}:
                raise ValueError('確保した利用者番地以外へのアクセス')
            if token[1]:
                # 小数POKEは一方だけを書くため、保証できるのは整数POKEだけ。
                if len(targets)==1: written.update(targets)
            elif not targets <= written:
                raise ValueError('先行POKEのないPEEKを拒否')
    return True


def prediction(a):
    kind=a['kind']
    if kind=='error': return [['s9be',1,a['error']],DONE.copy()]
    if kind=='out': return [['s9be',1,6],DONE.copy()]
    if kind=='roundtrip':
        try:
            value=a['value']
            v=common.byte('x' if value=='"x"' else number(value))
            return [['s9bv',1,v],DONE.copy()]
        except common.BasicError as e: return [['s9be',1,e.number],DONE.copy()]
    if kind=='adjacent':
        return [['s9bv',1,77 if address(number(a['fraction']))==ADDRESS else 17],
                ['s9bv',2,77 if address(number(a['fraction']))==ADDRESS+1 else 29],DONE.copy()]
    if kind=='fraction-read':
        return [['s9bv',1,17 if address(number(a['fraction']))==ADDRESS else 29],DONE.copy()]
    return [['s9bv',1,a.get('expected',73)],DONE.copy()]


def allowed_values(a):
    # 隣接番地の両値は、その腕で自分が書いた値だけなので記録できる。
    if a['kind']=='adjacent': return {1:{17,77},2:{29,77}}
    if a['kind']=='fraction-read': return {1:{17,29}}
    return {r[1]:{r[2]} for r in prediction(a) if r[0]=='s9bv'}


def program(a,trap=True):
    k=a['kind']; lines=['new']
    if k!='constant': lines.append(f'5 clear ,{LIMIT}')
    lines += ['10 n=1:f=0']
    if trap: lines.append('15 on error goto 950')
    body=[]
    def read(expr,expected,idx=1,integer=False,direct=False):
        var='x%' if integer else 'x'
        body.append(f'if f=0 then {var}=peek({expr})')
        values=sorted(allowed_values(a)[idx])
        mismatch=' and '.join(f'{var}<>{v}' for v in values)
        body.append(f'if f=0 and {mismatch} then print "s9bm";{idx};1')
        shown=f'peek({expr})' if direct else var
        for v in values:
            body.append(f'if f=0 and {var}={v} then print "s9bv";{idx};{shown}')
    if k=='clear': body=['print "s9bv";1;1']
    elif k=='constant': body=[f'print "s9bv";1;{a["expr"]}']
    elif k=='error': body=[f'error {a["error"]}']
    elif k=='out': body=[f'poke {a["poke"]},73','if f=0 then print "s9bn";1;1']
    elif k=='roundtrip':
        body=[f'poke {a.get("poke",str(ADDRESS))},{a["value"]}']
        p=prediction(a)[0]
        if p[0]=='s9bv': read(str(ADDRESS),p[2])
        else: body.append('if f=0 then print "s9bn";1;1')
    elif k in ('adjacent','fraction-read'):
        body=[f'poke {ADDRESS},17',f'if f=0 then poke {ADDRESS+1},29']
        if k=='adjacent':
            body.append(f'if f=0 then poke {a["fraction"]},77')
            for r in prediction(a)[:-1]: read(str(ADDRESS+r[1]-1),r[2],r[1])
        else: read(a['fraction'],prediction(a)[0][2])
    else:
        body=[f'poke {ADDRESS},73']
        read(str(ADDRESS),73,integer=k=='integer',direct=k=='print')
    lines += [f'{20+i*10} {s}' for i,s in enumerate(body)]
    lines += ['800 print "s9bd";1;1','810 end']
    if trap: lines += ['950 print "s9be";n;err:f=1:resume next']
    lines += ['cls','run']
    assert all(len(s)<80 and s==s.lower() and '@' not in s for s in lines)
    static_check(lines)
    return lines


MARK=re.compile(r'^(s9b[vemnd])((?: +\d+| *-\d+)+) *$',re.I)


def extract(data,arm):
    if len(data)!=3000: raise ValueError('画面写しの長さが不正')
    rows=[]; other=0
    # 自分で書いた候補値以外は、差ありという印へ縮約する。
    expected=allowed_values(arm)
    for i in range(25):
        raw=data[i*120:i*120+80]
        if raw==b' '*80: continue
        m=MARK.fullmatch(raw.decode('ascii',errors='replace').rstrip(' '))
        if not m: other+=1;continue
        row=[m[1].lower(),*(int(x) for x in common.TOKEN.findall(m[2]))]
        if row[0]=='s9bv' and (len(row)!=3 or row[2] not in expected.get(row[1],set())):
            row=['s9bm',row[1] if len(row)>1 and row[1] in (1,2) else 1,1]
        # ERRや完了印の異常な数値も既存内容を持ち出す経路にしない。
        if row[0]=='s9be' and (len(row)!=3 or row[1]!=1 or not 1<=row[2]<=255):
            other+=1;continue
        if row[0] in ('s9bm','s9bn','s9bd') and row not in ([row[0],1,1],[row[0],2,1]):
            other+=1;continue
        rows.append(row)
    return rows,other


def valid(rows):
    if len(rows) not in (2,3) or rows[-1]!=DONE: return False
    for i,r in enumerate(rows[:-1],1):
        if len(r)!=3 or r[1]!=i: return False
        if r[0]=='s9bv' and not 0<=r[2]<=255: return False
        if r[0]=='s9be' and (i!=1 or len(rows)!=2 or not 1<=r[2]<=255): return False
        if r[0] in ('s9bm','s9bn') and r[2]!=1: return False
        if r[0] not in ('s9bv','s9be','s9bm','s9bn'): return False
    return True


def run_arm(rom,official,arm,work,trap=True):
    args=[str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom)]
    at=700 if official else 100
    if official: args += ['--type-at','300','--type','\n']
    for line in program(arm,trap):
        args += ['--type-at',str(at),'--type',line+'\n']
        at+=(len(line)+1)*8+240+(15000 if line=='run' else 0)
    screen=work/'screen.bin'
    args += ['--vram-dump',str(screen),'--vram-dump-at',str(at+200),'--frames',str(at+300)]
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if p.returncode or b'untypable' in p.stderr.lower() or '打てない'.encode() in p.stderr:
            raise RuntimeError('打鍵または採取に失敗')
        return extract(screen.read_bytes(),arm)
    finally: screen.unlink(missing_ok=True)


def measure(rom,official,selected,work,trap=True):
    work.mkdir(parents=True,exist_ok=True);records=[]
    with tempfile.TemporaryDirectory(prefix='measure-',dir=work) as t:
        calibration=True
        for a in selected:
            r=dict(arm=a,obs=[],others=[],failed=[],gate=False)
            if not calibration:
                r.update(obs=[[],[]],others=[0,0],failed=[False,False],skipped=True)
            else:
                for _ in range(2):
                    try:
                        rows,count=run_arm(rom,official,a,Path(t),trap)
                        # 合成の入口も同じ縮約器を必ず通す。
                        rows,_=extract(common.screen_of(rows),a)
                        r['obs'].append(rows);r['others'].append(count);r['failed'].append(False)
                    except Exception:
                        r['obs'].append([]);r['others'].append(0);r['failed'].append(True)
                r['gate']=not any(r['failed']) and r['obs'][0]==r['obs'][1] and valid(r['obs'][0])
                if a['id'].startswith('control-'):
                    calibration &= r['gate'] and r['obs'][0]==prediction(a)
            records.append(r)
    return records


def emit(path,records,trap=True):
    ids={r['arm']['id'] for r in records}
    required={a['id'] for a in controls()}
    own=all(r['arm']['kind']=='constant' for r in records)
    calibration=(own or required<=ids) and all(r['gate'] and r['obs'][0]==prediction(r['arm'])
                 for r in records if own or r['arm']['id'].startswith('control-'))
    output=[]
    for r in records:
        for i in range(2):
            # emitへ不一致の生値を直接渡された場合も排除する。
            rows,_=extract(common.screen_of(r['obs'][i]),r['arm'])
            gate=calibration and r['gate']
            state='gate_failed' if not gate else 'agree' if rows==prediction(r['arm']) else 'differ'
            output.append([r['arm']['id'],i+1,json.dumps(program(r['arm'],trap),ensure_ascii=False),
                           json.dumps(rows),r['others'][i],'pass' if gate else 'gate_failed',state,
                           int(r['failed'][i]),int(r.get('skipped',False))])
    common.write(path,['arm','repeat','typed_lines','print_values','other_line_counts','gate',
                       'P_GW','typing_or_capture_failed','skipped'],output)
    return calibration and all(r['gate'] for r in records)


def check(expected,measured):
    # 前段の厳密な腕集合・2走チェックを、今回の妥当性判定で流用する。
    with patch.object(common,'valid',valid): return common.check(expected,measured)


def selftest(work):
    try:
        work.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="write-probe-",dir=work): pass
    except PermissionError:
        # 器具既定は維持し、自己検査だけ許可された一時領域へ移す。
        work=Path(tempfile.mkdtemp(prefix='l4s9b-work-'))
        print('自己検査の作業先を許可された一時領域へ変更')
    selected=controls()+arms()
    assert address(Fraction('49152.4'))==ADDRESS
    assert address(Fraction('49152.5'))==ADDRESS
    assert [prediction(a)[0][2] for a in arms()[:11]]==[0,1,127,128,255,65,66,67,0,255,5]
    assert [prediction(a)[0][2] for a in arms()[11:16]]==[5,5,6,6,13]
    for a in selected:
        program(a);p=prediction(a)
        assert valid(p) and extract(common.screen_of(p),a)[0]==p
    def rejects(lines):
        try: static_check(lines)
        except (ValueError,SyntaxError): return True
        return False
    assert rejects(['5 clear ,49151','10 x=peek(49152)'])
    assert rejects(['5 clear ,49151','10 poke 49152,73','20 x=peek(49153)'])
    assert rejects(['5 clear ,49151','10 poke 0,73','20 x=peek(0)'])
    assert rejects(['5 clear ,49151','10 poke 49152,73','20 x=peek(a)'])
    assert rejects(['10 poke 49152,73','20 x=peek(49152)'])
    assert rejects(['5 clear ,49151','10 x=peek(65536)'])
    assert rejects(['5 clear ,49151','10 x=peek((49152))'])
    assert rejects(['5 clear ,49151','10 poke a,73'])
    frac=next(a for a in selected if a['kind']=='fraction-read')
    assert extract(common.screen_of([['s9bv',1,29],DONE]),frac)[0]==[['s9bv',1,29],DONE]
    a=controls()[1];p=prediction(a)
    assert not valid(extract(common.screen_of(p).replace(b's9bv',b'z9bv',1),a)[0])
    assert extract(common.screen_of([['s9bv',1,219],DONE]),a)[0]==[['s9bm',1,1],DONE]
    assert not valid(extract(common.screen_of([['s9bv',1,73],['s9bd',1,2]]),a)[0])
    with tempfile.TemporaryDirectory(prefix='replay-',dir=work) as t:
        root=Path(t)
        def replay(rom,official,a,work,trap=True): return prediction(a),0
        with patch(__name__+'.run_arm',replay): records=measure('',False,selected,root)
        assert emit(root/'good.tsv',records)
        common.write(root/'expected.tsv',['arm','prediction'],[(a['id'],json.dumps(prediction(a))) for a in selected])
        assert check(root/'expected.tsv',root/'good.tsv')
        records[3]['obs'][1]=[['s9bm',1,1],DONE]
        assert emit(root/'different.tsv',records)
        assert not check(root/'expected.tsv',root/'different.tsv')
        count=0
        def badgate(rom,official,a,work,trap=True):
            nonlocal count
            count+=1
            return ([['s9bv',1,219],DONE] if a['id']=='control-roundtrip' else prediction(a)),0
        captured=io.StringIO()
        with contextlib.redirect_stdout(captured),patch(__name__+'.run_arm',badgate):
            broken=measure('',False,selected,root)
            assert not emit(root/'broken.tsv',broken)
        assert count==4 and '219' not in captured.getvalue()
        assert '219' not in (root/'broken.tsv').read_text()
        with (root/'broken.tsv').open() as f:
            assert all(r['gate']=='gate_failed' for r in csv.DictReader(f,delimiter='\t'))
        def errors(rom,official,a,work,trap=True):
            return ([['s9be',1,6],DONE] if a['id']=='control-error' else prediction(a)),0
        with patch(__name__+'.run_arm',errors): broken=measure('',False,selected,root)
        assert not emit(root/'error.tsv',broken)
        # 非対照の生値もTSVと標準出力のどちらにも漏らさない。
        with patch(__name__+'.run_arm',replay): records=measure('',False,selected,root)
        records[3]['obs']=[[['s9bv',1,219],DONE]]*2
        with contextlib.redirect_stdout(captured): emit(root/'leak.tsv',records)
        assert '219' not in captured.getvalue() and '219' not in (root/'leak.tsv').read_text()
        calls=0
        def unstable(rom,official,a,work,trap=True):
            nonlocal calls
            calls+=1
            return (prediction(a) if calls==1 else [['s9bm',1,1],DONE]),0
        with patch(__name__+'.run_arm',unstable): broken=measure('',False,[selected[3]],root)
        assert not broken[0]['gate']
        def failed(*args): raise RuntimeError('合成の打鍵失敗')
        with patch(__name__+'.run_arm',failed): broken=measure('',False,selected,root)
        assert not emit(root/'failed.tsv',broken)
    print(f'OK 合成採取・静的安全検査・漏出防止・関門・照合、{len(selected)}腕×2走')
    with tempfile.TemporaryDirectory(prefix='own-rom-',dir=work) as t:
        root=Path(t);rom=root/'rom'
        proc=subprocess.run([os.sys.executable,str(kw.REPO/'src/build_main_rom.py'),str(rom),
                             '--work-dir',str(root/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert proc.returncode==0,'自作ROMの一時ビルド失敗'
        constants=[dict(id='own-len',kind='constant',expr='len("ab")',expected=2),
                   dict(id='own-asc',kind='constant',expr='asc("a")',expected=97),
                   dict(id='own-mid',kind='constant',expr='len(mid$("hello",2,3))',expected=3)]
        records=measure(rom,False,constants,root,trap=False)
        assert emit(root/'own.tsv',records,trap=False),'自作ROMの定数対照失敗'
        common.write(root/'expected.tsv',['arm','prediction'],[(a['id'],json.dumps(prediction(a))) for a in constants])
        assert check(root/'expected.tsv',root/'own.tsv')
        bad=prediction(constants[0]);bad[0][2]=3
        common.write(root/'wrong.tsv',['arm','prediction'],[(a['id'],json.dumps(bad if i==0 else prediction(a))) for i,a in enumerate(constants)])
        assert not check(root/'wrong.tsv',root/'own.tsv')
    print('OK 自作ROM一時ビルド・既存関数の定数3腕×2走・期待値改変拒否')
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('predict');p.add_argument('--out',type=Path,required=True)
    m=sub.add_parser('measure');m.add_argument('--rom-dir',required=True);m.add_argument('--out',type=Path,required=True);m.add_argument('--official',action='store_true');m.add_argument('--work-dir',type=Path,default=WORK)
    c=sub.add_parser('check');c.add_argument('--expected',type=Path,required=True);c.add_argument('--measured',type=Path,required=True)
    s=sub.add_parser('selftest');s.add_argument('--work-dir',type=Path,default=WORK)
    args=parser.parse_args()
    if args.command=='selftest': return selftest(args.work_dir)
    if args.command=='check':
        ok=check(args.expected,args.measured);print('照合一致' if ok else '照合不一致');return 0 if ok else 1
    selected=controls()+arms()
    if args.command=='predict':
        common.write(args.out,['arm','candidate','prediction','typed_lines'],[(a['id'],'P_GW',json.dumps(prediction(a)),json.dumps(program(a),ensure_ascii=False)) for a in selected]);return 0
    if args.official:
        ref=os.environ.get('PC88_REF_ROM_DIR')
        if not ref or Path(ref).resolve()!=Path(args.rom_dir).resolve():
            parser.error('公式ROMの置き場はPC88_REF_ROM_DIR経由で指定してください')
    records=measure(args.rom_dir,args.official,selected,args.work_dir)
    ok=emit(args.out,records)
    print(f'記録完了: {len(records)}腕×2走、全体関門'+('通過' if ok else '失敗'))
    return 0 if ok else 1

if __name__=='__main__': raise SystemExit(main())
