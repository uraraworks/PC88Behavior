#!/usr/bin/env python3
"""l4-s9a の文字列関数予測・整数PRINT採取。画面の他の本文は残さない。"""
import argparse
import csv
from fractions import Fraction
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from unittest.mock import patch
import l4_listkw_measure as kw

WORK = kw.REPO.parent / 'tmp/l4s9a-work'
ENCODER = [
    '900 l=len(x$):if l>8 then goto 920',
    '905 print "s9";n;l;',
    '906 if l=0 then goto 915',
    '910 for i=1 to l:print asc(mid$(x$,i,1));:next',
    '915 print:return',
    '920 t=0:for i=1 to l:t=t+asc(mid$(x$,i,1)):next',
    '925 print "s9s";n;l;t;',
    '930 print asc(mid$(x$,1,1));asc(mid$(x$,int(l/4),1));',
    '935 print asc(mid$(x$,int(l/2),1));',
    '940 print asc(mid$(x$,int(l*3/4),1));asc(mid$(x$,l,1)):return',
    '950 print "s9e";n;err:f=1:resume next',
]

class BasicError(Exception):
    def __init__(self, number):
        self.number = number


def integer(x):
    if isinstance(x, str):
        raise BasicError(13)
    x = Fraction(x)
    n = (abs(x) + Fraction(1, 2)).numerator // (abs(x) + Fraction(1, 2)).denominator
    n *= -1 if x < 0 else 1
    if not -32768 <= n <= 32767:
        raise BasicError(6)
    return n


def byte(x):
    n = integer(x)
    if not 0 <= n <= 255:
        raise BasicError(5)
    return n


def gw(fn, args):
    if fn == 'chr':
        return bytes([byte(args[0])])
    if fn == 'space':
        return b' ' * byte(args[0])
    if fn == 'string':
        count = byte(args[0])
        char = args[1]
        if isinstance(char, str):
            if not char:
                raise BasicError(5)
            code = ord(char[0])
        else:
            code = byte(char)
        return bytes([code]) * count
    if fn in ('hex', 'oct'):
        x = args[0]
        if isinstance(x, str):
            raise BasicError(13)
        # FRQINT は正数で指数が16のとき65536を引いてFRCINTへ渡す。
        x = Fraction(x)
        n = integer(x - 65536 if 32768 <= x < 65536 else x)
        return format(n & 65535, 'X' if fn == 'hex' else 'o').encode('ascii')
    if fn == 'instr':
        start, hay, needle = (1, *args) if len(args) == 2 else args
        start = byte(start)
        if not start:
            raise BasicError(5)
        if not isinstance(hay, str) or not isinstance(needle, str):
            raise BasicError(13)
        if start > len(hay):
            return 0
        if not needle:
            return start
        return hay.find(needle, start-1) + 1
    if fn == 'long':
        raise BasicError(15)
    if fn == 'error':
        raise BasicError(args[0])
    raise ValueError('関数名が不正')


def string_row(value):
    length = len(value)
    if length <= 8:
        return ['s9', 1, length, *value]
    indices = [1, length//4, length//2, length*3//4, length]
    return ['s9s', 1, length, sum(value), *(value[i-1] for i in indices)]


def prediction(arm):
    try:
        value = arm['constant'] if 'constant' in arm else gw(arm['fn'], arm['args'])
        row = string_row(value) if isinstance(value, bytes) else ['s9v', 1, value]
    except BasicError as error:
        row = ['s9e', 1, error.number]
    return [row, ['s9d', 1, 1]]


def controls():
    return [dict(id='control-ab', expr='"ab"', constant=b'ab'),
            dict(id='control-empty', expr='""', constant=b''),
            dict(id='control-mid', expr='mid$("hello",2,3)', constant=b'ell'),
            dict(id='control-error', expr='error 5', fn='error', args=[5])]


def literal(x):
    return '"'+x+'"' if isinstance(x, str) and not re.fullmatch(r'-?\d+(?:\.\d+)?', x) else str(x)


def arms():
    result = []
    def add(fn, args, expr=None):
        result.append(dict(id=f'{fn}-{sum(a["fn"] == fn for a in result)+1:02d}',
                           fn=fn, args=args, expr=expr or fn+'$('+','.join(literal(a) for a in args)+')'))
    for x in [0,1,7,13,31,32,65,127,128,160,223,255,'65.4','65.5','66.5','-0.4',256,-1,'-0.6',32768]:
        add('chr', [Fraction(x)])
    for x in [0,1,5,255,'2.5','3.5',256,-1]:
        add('space', [Fraction(x)])
    for count, char in [(3,65),(3,'ab'),(0,65),(255,42),(3,0),(3,255),(3,''),(256,65),(3,256),(-1,65),('2.5',65),(3,'65.5')]:
        add('string', [Fraction(count), Fraction(char) if char == '65.5' else char])
    for fn in ('hex','oct'):
        for x in [0,1,10,255,32767,-1,-32768,32768,65535,65536,-32769,'2.5','3.5','-0.5']:
            add(fn, [Fraction(x)])
    for args in [('abcabc','c'),(4,'abcabc','c'),(1,'abc',''),(3,'abc',''),(4,'abc',''),(5,'abc',''),('','a'),('',''),('abc','abcd'),(0,'abc','a'),(256,'abc','a'),(255,'abc','a'),(-1,'abc','a'),(Fraction('2.5'),'abcabc','b')]:
        add('instr', list(args), 'instr('+','.join(literal(a) for a in args)+')')
    add('long', [], 'string$(255,65)+chr$(66)')
    add('long', [], 'space$(200)+space$(56)')
    add('chr', ['a'])
    add('hex', ['1'], 'hex$("1")')
    add('instr', [1,2,3], 'instr(1,2,3)')
    return result


def program(arm, trap=True):
    expr = arm['expr']
    lines = ['new', *ENCODER, '10 n=1:f=0']
    if trap:
        lines += ['15 on error goto 950']
    if arm.get('fn') == 'error':
        body = expr
    elif arm.get('fn') == 'instr':
        body = 'v='+expr
    else:
        body = 'x$='+expr
    lines += ['20 '+body]
    if arm.get('fn') == 'instr':
        lines += ['30 if f=0 then print "s9v";n;v']
    elif arm.get('fn') != 'error':
        lines += ['30 if f=0 then gosub 900']
    lines += ['40 print "s9d";n;1', '50 end', 'cls', 'run']
    assert all(len(line)<80 and line==line.lower() for line in lines)
    return lines


MARK = re.compile(r'^(s9s|s9v|s9e|s9d|s9)((?: +\d+| *-\d+)+) *$', re.I)
TOKEN = re.compile(r' +\d+| *-\d+')


def extract(data):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    rows, other = [], 0
    for r in range(25):
        raw = data[r*120:r*120+80]
        if raw == b' '*80:
            continue
        match = MARK.fullmatch(raw.decode('ascii', errors='replace').rstrip(' '))
        if match:
            rows.append([match[1].lower(), *(int(t) for t in TOKEN.findall(match[2]))])
        else:
            other += 1
    return rows, other


def valid(rows):
    if len(rows)!=2 or rows[1]!=['s9d',1,1]:
        return False
    row = rows[0]
    if len(row)<3 or row[1]!=1:
        return False
    tag = row[0]
    if tag=='s9':
        return 0<=row[2]<=8 and len(row)==3+row[2] and all(0<=x<=255 for x in row[3:])
    if tag=='s9s':
        return len(row)==9 and 9<=row[2]<=255 and 0<=row[3]<=255*row[2] and all(0<=x<=255 for x in row[4:])
    if tag=='s9v':
        return len(row)==3 and 0<=row[2]<=255
    if tag=='s9e':
        return len(row)==3 and 1<=row[2]<=255
    return False


def run_arm(rom, official, arm, work, trap=True):
    args = [str(kw.FRONT),'--core',str(kw.find_core()),'--rom-dir',str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at','300','--type','\n']
    for line in program(arm, trap):
        args += ['--type-at',str(at),'--type',line+'\n']
        at += (len(line)+1)*8+240+(15000 if line=='run' else 0)
    screen = work/'screen.bin'
    args += ['--vram-dump',str(screen),'--vram-dump-at',str(at+200),'--frames',str(at+300)]
    try:
        proc = subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              env=dict(os.environ,M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
            raise RuntimeError('測定器の実行または打鍵に失敗')
        return extract(screen.read_bytes())
    finally:
        screen.unlink(missing_ok=True)


def measure(rom, official, selected, work, trap=True):
    work.mkdir(parents=True,exist_ok=True)
    records=[]
    with tempfile.TemporaryDirectory(prefix='measure-',dir=work) as temp:
        for arm in selected:
            obs,others,failed=[],[],[]
            for _ in range(2):
                try:
                    rows,count=run_arm(rom,official,arm,Path(temp),trap)
                    obs.append(rows);others.append(count);failed.append(False)
                except Exception:
                    obs.append([]);others.append(0);failed.append(True)
            gate=not any(failed) and obs[0]==obs[1] and valid(obs[0])
            records.append(dict(arm=arm,obs=obs,others=others,gate=gate,failed=failed))
    return records


def write(path, header, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream,delimiter='\t');writer.writerow(header);writer.writerows(rows)


def emit(path, records, trap=True):
    calibration=all(r['gate'] and r['obs'][0]==prediction(r['arm']) for r in records if r['arm']['id'].startswith('control-'))
    write(path,['arm','repeat','typed_lines','print_values','other_line_counts','gate','S_GW','typing_or_capture_failed'],
          [(r['arm']['id'],i+1,json.dumps(program(r['arm'],trap),ensure_ascii=False),json.dumps(r['obs'][i]),r['others'][i],
            'pass' if calibration and r['gate'] else 'gate_failed',
            'gate_failed' if not calibration or not r['gate'] else 'agree' if r['obs'][0]==prediction(r['arm']) else 'differ',
            int(r['failed'][i])) for r in records for i in range(2)])
    return calibration and all(r['gate'] for r in records)


def check(expected, measured):
    with expected.open(encoding='utf-8') as stream:
        wanted=list(csv.DictReader(stream,delimiter='\t'))
    with measured.open(encoding='utf-8') as stream:
        actual=list(csv.DictReader(stream,delimiter='\t'))
    targets={}
    for r in wanted:
        key=r['arm']
        values=json.loads(r.get('prediction') or r['print_values'])
        if key in targets and targets[key]!=values:
            return False
        targets[key]=values
    grouped={}
    for r in actual:
        grouped.setdefault(r['arm'],[]).append(r)
    if not targets or set(targets)!=set(grouped):
        return False
    for aid, value in targets.items():
        runs=grouped[aid]
        if len(runs)!=2 or {r['repeat'] for r in runs}!={'1','2'}:
            return False
        if any(r['gate']!='pass' or not valid(json.loads(r['print_values'])) or json.loads(r['print_values'])!=value for r in runs):
            return False
    return True


def screen_of(rows):
    data=bytearray(b' '*3000)
    for i,row in enumerate(rows):
        text=(row[0]+''.join(' '+str(x)+' ' for x in row[1:])).encode('ascii')
        data[i*120:i*120+len(text)]=text
    return bytes(data)


def selftest(work):
    work.mkdir(parents=True,exist_ok=True)
    assert gw('chr',[Fraction('65.5')])==b'B'
    assert gw('chr',[Fraction('-0.4')])==b'\0'
    assert gw('space',[Fraction('2.5')])==b'   '
    assert gw('string',[3,'ab'])==b'aaa'
    assert gw('hex',[-1])==b'FFFF' and gw('oct',[-32768])==b'100000'
    assert gw('hex',[32768])==b'8000' and gw('hex',[65535])==b'FFFF'
    assert gw('instr',[3,'abc',''])==3 and gw('instr',[4,'abc',''])==0
    assert gw('instr',['',''])==0 and gw('instr',[Fraction('2.5'),'abcabc','b'])==5
    for fn,args,num in [('chr',[256],5),('chr',[32768],6),('string',[3,''],5),('hex',[65536],6),('hex',['1'],13),('long',[],15)]:
        try:
            gw(fn,args)
            raise AssertionError('予測器が誤りを拒否しなかった')
        except BasicError as error:
            assert error.number==num
    selected=controls()+arms()
    for arm in selected:
        good=prediction(arm)
        assert valid(good) and extract(screen_of(good))[0]==good
        program(arm)
    good=prediction(controls()[0]); data=screen_of(good)
    assert not valid(extract(data.replace(b's9 ',b'z9 ',1))[0])
    bad=[['s9',1,3,97,98],['s9d',1,1]]
    assert not valid(extract(screen_of(bad))[0])
    bad=[['s9',1,2,97,99],['s9d',1,1]]
    assert valid(bad) and extract(screen_of(bad))[0]!=good
    err=prediction(controls()[-1]);bad=[['s9e',1,6],['s9d',1,1]]
    assert valid(bad) and extract(screen_of(bad))[0]!=err
    # 全腕の2走・完了印と、片走改変・定数ERR改変の伝播を検査する。
    with tempfile.TemporaryDirectory(prefix='replay-',dir=work) as temp:
        root=Path(temp)
        def replay(rom,official,arm,directory,trap=True):
            return prediction(arm), 2
        with patch(__name__+'.run_arm',replay):
            records=measure('',False,selected,root)
        assert emit(root/'good.tsv',records)
        assert all(r['gate'] for r in records)
        first=records[4]
        first['obs'][1]=[['s9',1,1,99],['s9d',1,1]]
        # 本物のmeasureを通して片走だけ改変する。
        calls=0
        def changed(rom,official,arm,directory,trap=True):
            nonlocal calls
            calls+=1
            return (first['obs'][1] if calls==2 else prediction(arm)), 2
        with patch(__name__+'.run_arm',changed):
            broken=measure('',False,[selected[4]],root)
        assert not broken[0]['gate']
        def error_changed(rom,official,arm,directory,trap=True):
            rows=prediction(arm)
            if arm['id']=='control-error':
                rows[0][2]=6
            return rows, 0
        with patch(__name__+'.run_arm',error_changed):
            broken=measure('',False,selected,root)
        assert not emit(root/'broken.tsv',broken)
        with (root/'broken.tsv').open() as stream:
            assert all(r['gate']=='gate_failed' for r in csv.DictReader(stream,delimiter='\t'))
        def failed(rom,official,arm,directory,trap=True):
            raise RuntimeError('合成の打鍵失敗')
        with patch(__name__+'.run_arm',failed):
            broken=measure('',False,[selected[0]],root)
        assert not broken[0]['gate'] and all(broken[0]['failed'])
    print('OK 合成採取の陽性・陰性対照、GW規則の固定値')
    with tempfile.TemporaryDirectory(prefix='selftest-',dir=work) as temp:
        root=Path(temp);rom=root/'rom'
        proc=subprocess.run([os.sys.executable,str(kw.REPO/'src/build_main_rom.py'),str(rom),'--work-dir',str(root/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert proc.returncode==0,'自作ROMの一時ビルド失敗'
        # 自作ROMのERROR/ON ERRORは測定済みでない。値採取の定数だけを検証する。
        constants=controls()[:3]
        records=measure(rom,False,constants,root,trap=False)
        assert all(r['gate'] and r['obs'][0]==prediction(r['arm']) for r in records),'自作ROMの定数採取関門失敗: '+json.dumps([(r['arm']['id'],r['gate'],r['obs'],r['others']) for r in records])
        observed=root/'measured.tsv';expected=root/'expected.tsv'
        assert emit(observed,records,trap=False)
        write(expected,['arm','prediction'],[(a['id'],json.dumps(prediction(a))) for a in constants])
        assert check(expected,observed)
        wrong=prediction(constants[0]);wrong[0][-1]=99
        write(expected,['arm','prediction'],[(a['id'],json.dumps(wrong if i==0 else prediction(a))) for i,a in enumerate(constants)])
        assert not check(expected,observed)
        # 定数関門の不一致と2走不一致が全体へ伝わることも合成で確認する。
        records[0]['obs']=[wrong,wrong]
        assert not emit(observed,records,trap=False)
        with observed.open() as stream:
            assert all(r['gate']=='gate_failed' for r in csv.DictReader(stream,delimiter='\t'))
    print('OK 自作ROM一時ビルド、定数3腕×2走、期待値改変の陰性対照')
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('predict');p.add_argument('--out',type=Path,required=True)
    m=sub.add_parser('measure');m.add_argument('--rom-dir',required=True);m.add_argument('--out',type=Path,required=True);m.add_argument('--official',action='store_true');m.add_argument('--work-dir',type=Path,default=WORK)
    c=sub.add_parser('check');c.add_argument('--expected',type=Path,required=True);c.add_argument('--measured',type=Path,required=True)
    s=sub.add_parser('selftest');s.add_argument('--work-dir',type=Path,default=WORK)
    args=parser.parse_args()
    if args.command=='selftest':
        return selftest(args.work_dir)
    if args.command=='check':
        passed=check(args.expected,args.measured);print('照合一致' if passed else '照合不一致');return 0 if passed else 1
    selected=controls()+arms()
    if args.command=='predict':
        write(args.out,['arm','candidate','prediction','typed_lines'],[(a['id'],'S_GW',json.dumps(prediction(a)),json.dumps(program(a),ensure_ascii=False)) for a in selected]);return 0
    records=measure(args.rom_dir,args.official,selected,args.work_dir)
    passed=emit(args.out,records)
    print(f'記録完了: {len(records)}腕×2走、全体関門 '+('通過' if passed else '失敗'))
    return 0 if passed else 1

if __name__=='__main__':
    raise SystemExit(main())
