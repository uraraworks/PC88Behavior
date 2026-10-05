#!/usr/bin/env python3
"""l4-s9j: ON・LET・WHILEの事前予測と測定器具。画面本文は非出力。"""
import argparse
import contextlib
import copy
import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import traceback
from unittest.mock import patch
import l4_listkw_measure as kw
import l4_listnum_measure as num

WORK = kw.REPO.parent / 'tmp/l4s9j-work'
ARITY = {x: 2 for x in ('s9jp', 's9jo', 's9jb', 's9jv', 's9jz')}
ARITY['s9je'] = 3
NUMBER = r'(?: +\d+| *-\d+)'
MARK = re.compile(r'^(s9j[a-z])((?:'+NUMBER+r')+) *$', re.I)


def value(n):
    return ['s9jv', 1, n]


def arm(aid, body, rows, **extra):
    return dict(id=aid, body=body, rows=rows, **extra)


def controls():
    out = [arm('control-values', ['print "s9jv";1;17',
                                'print "s9jv";1;-1'], [value(17), value(-1)]),
           arm('control-goto', ['goto 40', 'print "s9jv";1;99',
                               'print "s9jv";1;7'], [value(7)]),
           arm('control-gosub', {20:'gosub 100:print "s9jv";1;8',
                                30:'end',100:'print "s9jv";1;7:return'},
               [value(7),value(8)]),
           arm('control-for', ['k=0:for i=1 to 3', 'k=k+1',
                              'next i', 'print "s9jv";1;k'], [value(3)]),
           arm('control-if', ['if 1 then print "s9jv";1;9'], [value(9)]),
           arm('control-trap', ['p=4:error 5'], [['s9je',1,5,4]])]
    for n, statement in [(5,'error 5'),(8,'goto 777'),(17,'cont')]:
        out.append(arm(f'control-direct-{n}', [statement], [], direct=True,
                       error=n))
    for n, statement in [(1,'next i'),(3,'return'),(5,'error 5')]:
        out.append(arm(f'control-program-{n}', [statement], [],
                       untrapped=True, error=n))
    return out


def arms():
    out = []
    choices = [('one','1',1),('two','2',2),('three','3',3),
               ('zero','0',0),('beyond','4',0),('negative','-1',5),
               ('byte-over','256',5),('large','1000000000',None),
               ('f14','1.4',None),('f15','1.5',None),('f25','2.5',None),
               ('fm05','-0.5',None),('f05','0.5',None),
               ('expr','a+1',2),('string','"x"',13)]
    for kind in ('goto','gosub'):
        for name, expr, selected in choices:
            body={20:'a=1:p=1',30:f'on {expr} {kind} 100,200,300',
                  40:'print "s9jv";1;0:end'}
            for j in (1,2,3):
                body[j*100]=f'print "s9jv";1;{j}:'+('return' if kind=='gosub' else 'end')
            rows = None if selected is None else (
                [['s9je',1,selected,1]] if selected in (5,13) else
                ([value(selected)] if selected else []) +
                ([value(0)] if kind=='gosub' or selected==0 else []))
            out.append(arm(f'on-{kind}-{name}',body,rows))
        for name, expr, targets, colon, selected, err in [
            ('unselected-missing','1','100,777',True,1,None),
            ('selected-missing','2','100,777',True,0,8),
            ('duplicate','2','100,100,100',True,1,None),
            ('single','1','100',False,1,None),
            ('single-zero-colon','0','100',True,0,None),
            ('single-over','2','100',False,0,None),
            ('colon-return','1','100',True,1,None)]:
            body={20:'p=1',30:f'on {expr} {kind} {targets}'+
                  (':print "s9jv";1;8' if colon else ''),
                  40:'print "s9jv";1;9:end',
                  100:'print "s9jv";1;1:'+('return' if kind=='gosub' else 'end')}
            rows = [['s9je',1,err,1]] if err else (
                ([value(1)] if selected else [])+
                ([value(8)] if colon and (kind=='gosub' or not selected) else [])+
                ([value(9)] if kind=='gosub' or not selected else []))
            out.append(arm(f'on-{kind}-{name}',body,rows))
    assignments=[('number','a=1','a',1),('string','a$="x"','len(a$)',1),
                 ('array','b(2)=3','b(2)',3),('integer','a%=2.6','a%',None)]
    for mode in ('program','direct'):
        for name, assignment, expression, n in assignments:
            for explicit in (True,False):
                body=['dim b(3)',('let ' if explicit else '')+assignment,
                      f'print "s9jv";1;{expression}']
                out.append(arm(f'let-{mode}-{name}-'+('let' if explicit else 'plain'),
                               body,None if n is None else [value(n)],direct=mode=='direct'))
        for name, statement in [('empty','let'),('equals','let =1'),
                                ('missing-equals','let a'),('type','let a="x"')]:
            n=13 if name=='type' else 2
            out.append(arm(f'let-{mode}-bad-{name}', ['p=1',statement],
                           [] if mode=='direct' else [['s9je',1,n,1]],
                           direct=mode=='direct',error=n if mode=='direct' else None))
    specs=[
      ('normal',['i=0','while i<3','i=i+1:print "s9jv";1;i','wend'],[value(1),value(2),value(3)]),
      ('false',['while 0','print "s9jv";1;99','wend','print "s9jv";1;7'],[value(7)]),
      ('false-nested',['while 0','while 1','print "s9jv";1;99','wend','wend','print "s9jv";1;7'],[value(7)]),
      ('false-rem',['while 0','rem wend:while 1','print "s9jv";1;99','wend','print "s9jv";1;7'],[value(7)]),
      ('false-string',['while 0','a$="wend:while"','print "s9jv";1;99','wend','print "s9jv";1;7'],[value(7)]),
      ('nested',['i=0','while i<2','j=0','while j<2','j=j+1:print "s9jv";1;i*10+j','wend','i=i+1','wend'],[value(1),value(2),value(11),value(12)]),
      ('for-outer',['for i=1 to 2','j=0','while j<2','j=j+1:print "s9jv";1;i*10+j','wend','next i'],[value(11),value(12),value(21),value(22)]),
      ('while-outer',['i=0','while i<2','for j=1 to 2','print "s9jv";1;i*10+j','next j','i=i+1','wend'],[value(1),value(2),value(11),value(12)]),
      ('reenter',{20:'i=0',30:'while i<2',40:'i=i+1:print "s9jv";1;i',50:'goto 100',60:'wend',70:'print "s9jv";1;7:end',100:'goto 30'},[value(1),value(2),value(7)]),
      ('orphan-wend',['p=1:wend','print "s9jv";1;99'],[['s9je',1,30,1]]),
      ('missing-true',['p=1:while 1','p=2:print "s9jv";1;99'],[['s9je',1,29,1]]),
      ('missing-false',['p=1:while 0','p=2:print "s9jv";1;99'],[['s9je',1,29,1]]),
      ('string',['p=1:while "x"','p=2:print "s9jv";1;99','wend'],[['s9je',1,13,1]]),
      ('one-line',['i=0:while i<3:i=i+1:print "s9jv";1;i:wend', 'print "s9jv";1;7'],[value(1),value(2),value(3),value(7)]),
    ]
    for name,expr in [('neg','-1'),('one','1'),('two','2'),('half','0.5'),('neg-half','-0.5'),('zero','0')]:
        specs.append(('condition-'+name,['a='+expr,'while a','print "s9jv";1;1:a=0','wend','print "s9jv";1;7'],
                      ([] if expr=='0' else [value(1)])+[value(7)]))
    out += [arm('while-'+name,body,rows) for name,body,rows in specs]
    return out


def stage(rows=(), error=None, exact=False):
    return dict(rows=copy.deepcopy(list(rows)),
                errors=[] if error is None else [[error,True,exact]])


def prepare_rows(a):
    return [['s9jp',1,1]]


def prediction(a):
    # G_GW。数値変換の未分離点は観測後に埋めない。
    if a['rows'] is None:
        return None
    return dict(prepare=stage(prepare_rows(a)),operation=stage([['s9jo',1,1]]),
                result=stage([['s9jb',1,1]]+a['rows']+[['s9jz',1,1]],a.get('error')))


def program(a):
    out=['new']
    direct=a.get('direct',False)
    if not direct:
        body=a['body'] if isinstance(a['body'],dict) else {20+i*10:s for i,s in enumerate(a['body'])}
        body={10:'print "s9jb";1;1:'+('p=0' if a.get('untrapped') else 'on error goto 800:p=0'),
              **body,790:'end',800:'print "s9je";1;err;p:end'}
        out += [f'{n} {s}' for n,s in sorted(body.items())]
    out += ['cls','print "s9jp";1;1',('capture','prepare'),
            'cls','print "s9jo";1;1',('capture','operation'),'cls']
    out += ['print "s9jb";1;1',*a['body']] if direct else ['run']
    out += ['print "s9jz";1;1',('capture','result')]
    assert all(not isinstance(x,str) or (x.isascii() and x==x.lower() and
               len(x)<80 and '@' not in x and '\n' not in x and '\r' not in x) for x in out)
    return out

def error_numbers():
    return [int(line.split('\t')[0]) for line in
            (kw.REPO/'src/l4_basic/errors.tsv').read_text(encoding='utf-8').splitlines()
            if line and not line.startswith('#')]


def extract(data):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    rows, other = [], 0
    for r in range(25):
        raw = data[r*120:r*120+80].rstrip(b' ')
        if not raw:
            continue
        text = raw.decode('ascii', errors='replace')
        match = MARK.fullmatch(text)
        if match and match[1].lower() in ARITY:
            values = [int(n) for n in match[2].split()]
            row = [match[1].lower(), *values]
            rows.append(row if len(values) == ARITY[row[0]] else ['invalid'])
        elif text.lower().startswith('s9j'):
            rows.append(['invalid'])
        else:
            other += 1
    errors = []
    for n in error_numbers():
        contains, exact = num.entry_message_status(data, n)
        if contains:
            errors.append([n, contains, exact])
    return dict(rows=rows, errors=errors), other


def valid_stage(value):
    if not isinstance(value, dict) or set(value) != {'rows', 'errors'}:
        return False
    rows, errors = value['rows'], value['errors']
    if not isinstance(rows, list) or not isinstance(errors, list):
        return False
    for row in rows:
        if (not isinstance(row, list) or not row or row[0] not in ARITY
                or len(row) != ARITY[row[0]]+1 or row[1] != 1
                or any(type(n) is not int for n in row[1:])):
            return False
    numbers = []
    for e in errors:
        if (not isinstance(e, list) or len(e) != 3 or type(e[0]) is not int
                or e[0] not in error_numbers() or e[1] is not True
                or type(e[2]) is not bool):
            return False
        numbers.append(e[0])
    return numbers == sorted(set(numbers))


def valid(value, a):
    if not isinstance(value,dict) or set(value)!={'prepare','operation','result'}:
        return False
    if not all(valid_stage(v) for v in value.values()):
        return False
    if value['prepare']!=stage(prepare_rows(a)) or value['operation']!=stage([['s9jo',1,1]]):
        return False
    rows=value['result']['rows']
    return (len(rows)>=2 and rows[0]==['s9jb',1,1] and rows[-1]==['s9jz',1,1]
            and rows.count(['s9jb',1,1])==rows.count(['s9jz',1,1])==1
            and all(r[0] in ('s9jv','s9je') for r in rows[1:-1])
            and len(rows)<=16)


def dump_path(path, frame, multiple):
    return path.with_name(path.stem+f'.f{frame:06d}'+path.suffix) if multiple else path


def run_arm(rom, official, a, work):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    captures = []
    for step in program(a):
        if isinstance(step, str):
            args += ['--type-at', str(at), '--type', step+'\n']
            at += (len(step)+1)*8+240+(15000 if step == 'run' else 0)
        else:
            path, frame = work/(step[1]+'.bin'), at+200
            args += ['--vram-dump', str(path), '--vram-dump-at', str(frame)]
            captures.append((step[1], path, frame))
            at = frame+100
    args += ['--frames', str(at+100)]
    paths = [(name, dump_path(path, frame, len(captures) > 1))
             for name, path, frame in captures]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if (proc.returncode or b'untypable' in proc.stderr.lower()
                or '打てない'.encode() in proc.stderr):
            raise RuntimeError('測定器の実行または打鍵に失敗')
        obs, others = {}, {}
        for name, path in paths:
            obs[name], others[name] = extract(path.read_bytes())
        return obs, others
    finally:
        for _, path in paths:
            path.unlink(missing_ok=True)
        for _, path, _ in captures:
            path.unlink(missing_ok=True)


def measure(rom, official, selected, work):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as temp:
        for a in selected:
            obs, others, failed = [], [], []
            for _ in range(2):
                try:
                    value, count = run_arm(rom, official, a, Path(temp))
                    obs.append(value); others.append(count); failed.append(False)
                except Exception:
                    obs.append({}); others.append({}); failed.append(True)
            gate = (not any(failed) and all(valid(o, a) for o in obs)
                    and comparable(obs[0]) == comparable(obs[1]))
            records.append(dict(arm=a, obs=obs, others=others, failed=failed, gate=gate))
    return records


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(header); writer.writerows(rows)


def valid_counts(value):
    return (isinstance(value, dict) and set(value) == {'prepare', 'operation', 'result'}
            and all(type(n) is int and n >= 0 for n in value.values()))


def comparable(value):
    """比較と2走一致からexactを除く。保存観測は変更しない。"""
    if value is None:
        return None
    return {name: dict(rows=v['rows'], errors=[e[:2] for e in v['errors']])
            for name, v in value.items()}


def emit(path, records):
    # 保存された gate を信用せず、2走と既知の採取形を再評価する。
    known = {a['id']: a for a in controls()+arms()}
    unique = len({r['arm']['id'] for r in records}) == len(records)
    for r in records:
        r['gate'] = (r['gate'] and unique and r['arm'] == known.get(r['arm']['id'])
                     and len(r['obs']) == 2 and len(r['failed']) == 2
                     and all(type(f) is bool for f in r['failed']) and not any(r['failed'])
                     and all(valid(o, r['arm']) for o in r['obs'])
                     and comparable(r['obs'][0]) == comparable(r['obs'][1])
                     and len(r['others']) == 2 and all(valid_counts(c) for c in r['others']))
    cs = [r for r in records if r['arm']['id'].startswith('control-')]
    calibrated = (len(cs) == len(controls())
                  and {r['arm']['id'] for r in cs} == {a['id'] for a in controls()}
                  and all(r['gate'] and comparable(r['obs'][0]) ==
                          comparable(prediction(r['arm'])) for r in cs))
    write(path, ['arm', 'repeat', 'typed_lines', 'observation', 'other_line_counts',
                 'gate', 'G_GW', 'typing_or_capture_failed'],
          [(r['arm']['id'], i+1, json.dumps(program(r['arm']), ensure_ascii=False),
            json.dumps(r['obs'][i]), json.dumps(r['others'][i]),
            'pass' if calibrated and r['gate'] else 'gate_failed',
            'gate_failed' if not calibrated or not r['gate'] else
            'unpredicted' if prediction(r['arm']) is None else
            'agree' if comparable(r['obs'][0]) == comparable(prediction(r['arm'])) else 'differ',
            int(r['failed'][i])) for r in records for i in range(2)])
    return calibrated and bool(records) and all(r['gate'] for r in records)


def rejudge(measured, out):
    """保存TSVの観測からmeasureと同じemitを使う。旧判定列は参照しない。"""
    if measured.resolve() == out.resolve():
        raise ValueError('再判定の入力と出力は別ファイルにする')
    known = {a['id']: a for a in controls()+arms()}
    grouped = {}
    with measured.open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream, delimiter='\t'):
            aid, repeat = row['arm'], row['repeat']
            if aid not in known or repeat not in ('1', '2'):
                raise ValueError('腕または走番号が不正')
            runs = grouped.setdefault(aid, {})
            if repeat in runs or json.loads(row['typed_lines']) != json.loads(
                    json.dumps(program(known[aid]))):
                raise ValueError('走の重複または打鍵計画の不一致')
            if row['typing_or_capture_failed'] not in ('0', '1'):
                raise ValueError('採取失敗フラグが不正')
            runs[repeat] = row
    records = []
    for aid, runs in grouped.items():
        if set(runs) != {'1', '2'}:
            raise ValueError('2走の記録が不足')
        rows = [runs[str(i)] for i in (1, 2)]
        records.append(dict(arm=known[aid], gate=True,
                            obs=[json.loads(r['observation']) for r in rows],
                            others=[json.loads(r['other_line_counts']) for r in rows],
                            failed=[r['typing_or_capture_failed'] == '1' for r in rows]))
    return emit(out, records)


def check(expected, measured):
    try:
        with expected.open(encoding='utf-8') as s:
            wanted = list(csv.DictReader(s, delimiter='\t'))
        with measured.open(encoding='utf-8') as s:
            actual = list(csv.DictReader(s, delimiter='\t'))
        known = {a['id']: a for a in controls()+arms()}
        targets = {}
        for r in wanted:
            value = json.loads(r.get('prediction') or r['observation'])
            aid = r['arm']
            if aid not in known or prediction(known[aid]) is None or not valid(value, known[aid]):
                return False
            if aid in targets and comparable(targets[aid]) != comparable(value):
                return False
            targets[aid] = value
        grouped = {}
        for r in actual:
            grouped.setdefault(r['arm'], []).append(r)
        if not targets or set(targets) != set(grouped):
            return False
        cs = {aid for aid in targets if aid.startswith('control-')}
        if cs != {a['id'] for a in controls()}:
            return False
        if any(comparable(targets[aid]) != comparable(prediction(known[aid])) for aid in cs):
            return False
        for aid, value in targets.items():
            runs = grouped[aid]
            if len(runs) != 2 or {r['repeat'] for r in runs} != {'1', '2'}:
                return False
            if comparable(json.loads(runs[0]['observation'])) != comparable(json.loads(runs[1]['observation'])):
                return False
            if any(json.loads(r['typed_lines']) != json.loads(json.dumps(program(known[aid])))
                   or not valid_counts(json.loads(r['other_line_counts']))
                   or r['G_GW'] not in ('agree', 'differ')
                   or r['gate'] != 'pass' or r['typing_or_capture_failed'] != '0'
                   or not valid(json.loads(r['observation']), known[aid])
                   or comparable(json.loads(r['observation'])) != comparable(value) for r in runs):
                return False
        return True
    except (ValueError, KeyError, TypeError, OSError):
        return False


def screen_of(rows, error=None, exact=True):
    data = bytearray(b' '*3000)
    texts = [row[0]+''.join((' ' if n >= 0 else '')+str(n)+' ' for n in row[1:])
             for row in rows]
    if error is not None:
        messages = dict(line.split('\t') for line in
                        (kw.REPO/'src/l4_basic/errors.tsv').read_text().splitlines()
                        if line and not line.startswith('#'))
        texts += [messages[str(error)]+('' if exact else ' in 110')]
    for i, text in enumerate(texts):
        raw = text.encode('ascii')
        assert i < 25 and len(raw) < 80
        data[i*120:i*120+len(raw)] = raw
    return bytes(data)



def selftest(work=None):
    if work is not None:
        work.mkdir(parents=True,exist_ok=True)
    known=controls()+arms()
    by_id={a['id']:a for a in known}
    assert len(arms())==88 and len(controls())==12 and len(by_id)==100
    assert sum(prediction(a) is None for a in known)==16
    for a in known:
        program(a)
        p=prediction(a)
        if p is not None:
            assert valid(p,a)
            for v in p.values():
                e=v['errors']
                assert extract(screen_of(v['rows'],e[0][0] if e else None,
                                         e[0][2] if e else True))[0]==v
    # 手順から独立に固定した値。予測関数の再利用だけで検査を済ませない。
    fixed={'on-goto-one':[value(1)],'on-goto-two':[value(2)],
           'on-goto-three':[value(3)],'on-goto-zero':[value(0)],
           'on-gosub-two':[value(2),value(0)],
           'on-gosub-colon-return':[value(1),value(8),value(9)],
           'on-goto-selected-missing':[['s9je',1,8,1]],
           'on-goto-unselected-missing':[value(1)],
           'on-goto-negative':[['s9je',1,5,1]],
           'on-goto-byte-over':[['s9je',1,5,1]],
           'on-goto-string':[['s9je',1,13,1]],
           'let-program-array-let':[value(3)],
           'let-program-bad-empty':[['s9je',1,2,1]],
           'while-normal':[value(1),value(2),value(3)],
           'while-false-nested':[value(7)],
           'while-false-rem':[value(7)],'while-false-string':[value(7)],
           'while-missing-true':[['s9je',1,29,1]],
           'while-missing-false':[['s9je',1,29,1]],
           'while-orphan-wend':[['s9je',1,30,1]],
           'while-condition-half':[value(1),value(7)],
           'while-condition-neg-half':[value(1),value(7)],
           'while-condition-zero':[value(7)]}
    for aid,rows in fixed.items():
        assert prediction(by_id[aid])['result']['rows']==[['s9jb',1,1]]+rows+[['s9jz',1,1]]
    for aid in ('on-goto-f15','on-gosub-large','let-direct-integer-let'):
        assert prediction(by_id[aid]) is None
    assert extract(screen_of([value(-1),value(17)]))[0]==stage([value(-1),value(17)])
    assert extract(b' '*3000)[0]==stage()
    assert extract(screen_of([value(17)]).replace(b's9jv',b'z9jv',1))[0]['rows']==[]
    assert extract(screen_of([value(17)]).replace(b' 17',b' xx',1))[0]['rows']==[['invalid']]
    for exact in (True,False):
        assert extract(screen_of([],5,exact))[0]['errors']==[[5,True,exact]]
    try:
        extract(b' ')
        raise AssertionError('短い写しを受理')
    except ValueError:
        pass
    assert dump_path(Path('x.bin'),123,True).name=='x.f000123.bin'
    assert dump_path(Path('x.bin'),123,False).name=='x.bin'
    with tempfile.TemporaryDirectory(prefix='l4s9j-selftest-',dir=work) as temp:
        root=Path(temp)
        probe=by_id['control-values']; planned=prediction(probe)
        def frontend(argv,**kwargs):
            times=[]; typed=[]; dumps=[]
            for i,arg in enumerate(argv):
                if arg=='--type-at': times.append(int(argv[i+1]))
                if arg=='--type': typed.append(argv[i+1])
                if arg=='--vram-dump': dumps.append((Path(argv[i+1]),int(argv[i+3])))
            assert times==sorted(set(times)) and typed[0]=='\n'
            assert typed[1:]==[x+'\n' for x in program(probe) if isinstance(x,str)]
            assert len(dumps)==3 and int(argv[-1])>dumps[-1][1]
            for name,(path,frame) in zip(('prepare','operation','result'),dumps):
                dump_path(path,frame,True).write_bytes(screen_of(planned[name]['rows']))
            return subprocess.CompletedProcess(argv,0,b'unknown-screen-body',b'unknown-screen-body')
        captured=io.StringIO()
        with patch.object(kw,'find_core',return_value=Path('synthetic-core')), \
             patch.object(subprocess,'run',side_effect=frontend), \
             contextlib.redirect_stdout(captured),contextlib.redirect_stderr(captured):
            got,_=run_arm('synthetic-rom',True,probe,root)
        assert got==planned and captured.getvalue()=='' and not list(root.glob('*.bin'))
        with patch.object(kw,'find_core',return_value=Path('synthetic-core')), \
             patch.object(subprocess,'run',return_value=subprocess.CompletedProcess(
                 [],1,b'unknown-screen-body',b'unknown-screen-body')):
            try:
                run_arm('synthetic-rom',False,probe,root)
                raise AssertionError('実行失敗を受理')
            except RuntimeError as e:
                assert 'unknown-screen-body' not in str(e)
        selected=[a for a in known if prediction(a) is not None]
        counts={name:0 for name in ('prepare','operation','result')}
        with patch(__name__+'.run_arm',side_effect=lambda rom,official,a,wd:(prediction(a),counts)):
            records=measure('',False,selected,root)
        expected=root/'expected.tsv'; measured=root/'measured.tsv'; out=root/'rejudged.tsv'
        def freeze(chosen):
            write(expected,['arm','prediction'],[(a['id'],json.dumps(prediction(a))) for a in chosen])
        freeze(selected)
        assert emit(measured,records) and check(expected,measured)
        with measured.open() as stream:
            skip_rows=list(csv.DictReader(stream,delimiter='\t'))
        skip_rows[-1]['G_GW']='SKIP'
        write(measured,list(skip_rows[0]),[list(r.values()) for r in skip_rows])
        assert not check(expected,measured)
        # exactは期待値比較にも2走の関門にも使わない。
        changed=copy.deepcopy(records)
        for r in changed:
            for v in r['obs'][1].values():
                for e in v['errors']: e[2]=not e[2]
        assert emit(measured,changed) and check(expected,measured)
        assert rejudge(measured,out) and check(expected,out)
        with measured.open() as stream:
            saved=list(csv.DictReader(stream,delimiter='\t'))
        for r in saved: r['gate']=r['G_GW']='gate_failed'
        write(measured,list(saved[0]),[list(r.values()) for r in saved])
        assert rejudge(measured,out) and check(expected,out)
        # 値違いは採取形と校正を通してからdifferまで到達する。
        bad=copy.deepcopy(records)
        target=next(r for r in bad if r['arm']['id']=='on-goto-one')
        for o in target['obs']: o['result']['rows'][1][2]=2
        assert valid(target['obs'][0],target['arm']) and emit(measured,bad)
        assert not check(expected,measured)
        with measured.open() as stream:
            assert all(r['gate']=='pass' and r['G_GW']=='differ' for r in csv.DictReader(stream,delimiter='\t') if r['arm']=='on-goto-one')
        # 誤り番号違いも本文やexactの検査に遮られず比較に届く。
        bad=copy.deepcopy(records)
        target=next(r for r in bad if r['arm']['id']=='on-goto-negative')
        for o in target['obs']: o['result']['rows'][1][2]=13
        assert valid(target['obs'][0],target['arm']) and emit(measured,bad)
        assert not check(expected,measured)
        for mutation in ('repeat','capture','control','end','duplicate-mark'):
            bad=copy.deepcopy(records)
            if mutation=='repeat': bad[-1]['obs'][1]['result']['rows'][1][2]=99
            elif mutation=='capture': bad[-1]['failed'][1]=True
            elif mutation=='control':
                for o in bad[0]['obs']: o['result']['rows'][1][2]=99
            elif mutation=='end':
                for o in bad[-1]['obs']: o['result']['rows'].pop()
            else:
                for o in bad[-1]['obs']: o['result']['rows'].insert(0,['s9jb',1,1])
            assert not emit(measured,bad) and not check(expected,measured)
        assert not emit(measured,records[1:]) and not emit(root/'empty.tsv',[])
        for mutation in ('missing','duplicate','unknown','flag','typing','counts'):
            rows=copy.deepcopy(saved)
            if mutation=='missing': rows.pop()
            elif mutation=='duplicate': rows.append(copy.deepcopy(rows[0]))
            elif mutation=='unknown': rows[0]['arm']='unknown'
            elif mutation=='flag': rows[0]['typing_or_capture_failed']='2'
            elif mutation=='counts':
                rows[0]['other_line_counts']='{}'
                write(measured,list(rows[0]),[list(r.values()) for r in rows])
                assert not rejudge(measured,out)
                continue
            else: rows[0]['typed_lines']='[]'
            write(measured,list(rows[0]),[list(r.values()) for r in rows])
            try:
                rejudge(measured,out)
                raise AssertionError('保存TSVの破損を受理')
            except ValueError:
                pass
        unknown=by_id['on-goto-f15']
        obs=prediction(by_id['on-goto-one'])
        unknown_record=dict(arm=unknown,obs=[obs,copy.deepcopy(obs)],others=[counts,counts],failed=[False,False],gate=True)
        assert emit(measured,records+[unknown_record])
        freeze(selected+[unknown])
        assert not check(expected,measured)
        write(expected,['arm','observation'],[(a['id'],json.dumps(obs if a['id']==unknown['id'] else prediction(a))) for a in selected+[unknown]])
        assert not check(expected,measured)
        with measured.open() as stream:
            assert all(r['G_GW']=='unpredicted' for r in csv.DictReader(stream,delimiter='\t') if r['arm']==unknown['id'])
        print('OK 固定予測・取り出し陽性陰性・本文非出力・exact除外・2走・破損拒否・予測なし拒否',flush=True)
        rom=root/'rom'
        built=subprocess.run([os.sys.executable,str(kw.REPO/'src/build_main_rom.py'),str(rom),
                              '--work-dir',str(root/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert built.returncode==0,'自作ROM一時ビルド失敗'
        own=controls()+[a for a in arms() if a['id'].startswith('let-') and a['id'].endswith('-plain') and prediction(a) is not None]
        observed=measure(rom,False,own,root)
        bad_ids=[r['arm']['id'] for r in observed if not r['gate'] or comparable(r['obs'][0])!=comparable(prediction(r['arm']))]
        if bad_ids:
            print('NG 自作ROMの既知値対照: '+','.join(bad_ids))
            for r in observed:
                if r['arm']['id'] in bad_ids:
                    print(json.dumps(dict(arm=r['arm']['id'],observation=r['obs'],failed=r['failed'])))
        assert not bad_ids
        freeze(own)
        assert emit(measured,observed) and check(expected,measured)
        wrong=prediction(own[0]); wrong['result']['rows'][1][2]=999
        write(expected,['arm','prediction'],[(a['id'],json.dumps(wrong if i==0 else prediction(a))) for i,a in enumerate(own)])
        assert not check(expected,measured)
        print(f'OK 自作ROM一時ビルド・既知値対照{len(own)}腕×2走・期待値改変拒否')
    return 0



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('predict'); p.add_argument('--out', type=Path, required=True)
    m = sub.add_parser('measure'); m.add_argument('--rom-dir')
    m.add_argument('--official', action='store_true'); m.add_argument('--out', type=Path, required=True)
    m.add_argument('--work-dir', type=Path, default=WORK)
    c = sub.add_parser('check'); c.add_argument('--expected', type=Path, required=True)
    c.add_argument('--measured', type=Path, required=True)
    r = sub.add_parser('rejudge'); r.add_argument('--measured', type=Path, required=True)
    r.add_argument('--out', type=Path, required=True)
    s = sub.add_parser('selftest'); s.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'check':
        ok = check(args.expected, args.measured)
        print('照合一致' if ok else '照合不一致'); return 0 if ok else 1
    if args.command == 'rejudge':
        ok = rejudge(args.measured, args.out)
        print('再判定完了: 関門'+('通過' if ok else '失敗'))
        return 0 if ok else 1
    selected = controls()+arms()
    if args.command == 'predict':
        write(args.out, ['arm', 'candidate', 'prediction', 'typed_lines'],
              [(a['id'], 'G_GW', json.dumps(prediction(a)), json.dumps(program(a), ensure_ascii=False))
               for a in selected])
        print(f'予測記録: {len(selected)}腕'); return 0
    rom = os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir):
        parser.error('公式ROMはPC88_REF_ROM_DIRだけ、自作ROMは--rom-dirで指定する')
    records = measure(rom, args.official, selected, args.work_dir)
    ok = emit(args.out, records)
    print(f'記録完了: {len(records)}腕×2走、関門'+('通過' if ok else '失敗'))
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # 例外のreprやフロントエンドの出力を本文漏えいの経路にしない。
        frames = traceback.extract_tb(error.__traceback__)
        print(f'NG 器具の検査または実行に失敗 ({type(error).__name__}, '
              f'行{frames[-1].lineno}、画面本文は非出力)')
        raise SystemExit(1)
