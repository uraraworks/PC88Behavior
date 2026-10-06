#!/usr/bin/env python3
"""l4-s9m: DEFINT・DEFSNG・DEFDBL・DEFSTR（型宣言文）の事前予測と測定器具。画面本文は非出力。"""
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

WORK = kw.REPO.parent / 'tmp/s9m-work'
ARITY = {x: 2 for x in ('s9mp', 's9mo', 's9mb', 's9mv', 's9mz')}
ARITY['s9me'] = 3
NUMBER = r'(?: +\d+| *-\d+)'
MARK = re.compile(r'^(s9m[a-z])((?:'+NUMBER+r')+) *$', re.I)


def value(n):
    return ['s9mv', 1, n]


def arm(aid, body, rows, **extra):
    return dict(id=aid, body=body, rows=rows, **extra)


def controls():
    return [
        arm('control-values', ['print "s9mv";1;17', 'print "s9mv";1;-1'], [value(17),value(-1)]),
        arm('control-goto', {20:'goto 40',30:'print "s9mv";1;99',40:'print "s9mv";1;7'}, [value(7)]),
        arm('control-gosub', {20:'gosub 100:print "s9mv";1;8:goto 790',100:'print "s9mv";1;7:return'}, [value(7),value(8)]),
        arm('control-for', ['k=0:for i=1 to 3','k=k+1','next i','print "s9mv";1;k'], [value(3)]),
        arm('control-if', ['if 1 then print "s9mv";1;9'], [value(9)]),
        arm('control-dim', ['dim a(3):a(2)=7','print "s9mv";1;a(2)'], [value(7)]),
        arm('control-trap', ['p=4:error 5'], [['s9me',1,5,4]]),
        arm('control-syntax', ['p=1:let'], [['s9me',1,2,1]]),
        arm('control-direct-5', ['error 5'], [], direct=True,error=5),
        arm('control-direct-8', ['goto 777'], [], direct=True,error=8),
        arm('control-direct-17', ['cont'], [], direct=True,error=17),
    ]


def arms():
    out = []

    def V(e):
        return f'print "s9mv";1;{e}'

    def prog(aid, body, vals):
        out.append(arm(aid, body, None if vals is None else [value(n) for n in vals]))

    def bad(aid, body, n):
        out.append(arm(aid, body, [['s9me', 1, n, 1]]))

    def direct(aid, lines, vals, error=None):
        out.append(arm(aid, lines, [value(n) for n in vals], direct=True, error=error))

    # 1 基本: DEFINT（CINT と同じ丸め・範囲）。GW は DEFTBL の1文字目の型を変数参照のたびに引く。
    for aid, init, n in (('int-round', '2.6', 3), ('int-half-pos', '2.5', 3), ('int-half-neg', '-2.5', -3),
                         ('int-low', '2.4', 2), ('int-third', '1/3', 0), ('int-edge', '32767.4', 32767)):
        direct(aid, ['defint a', f'a={init}', V('a')], [n])
    direct('int-over', ['defint a', 'a=40000', V('a')], [0], error=6)
    direct('int-over-half', ['defint a', 'a=32767.5', V('a')], [0], error=6)
    direct('int-mul-promote', ['defint a', 'a=300', V('a*300')], [90000])
    direct('int-add-promote', ['defint a', 'a=20000', V('a+a')], [40000])
    direct('int-divide', ['defint a', 'a=3', V('a/2*10')], [15])
    # 2 単精度・倍精度（比較の真偽で精度を判定）
    direct('sng-default', ['a=2.6', V('a*10')], [26])
    direct('sng-explicit', ['defsng a', 'a=2.6', V('a*10')], [26])
    direct('sng-after-int', ['defint a', 'defsng a', 'a=2.6', V('a*10')], [26])
    direct('dbl-third', ['defdbl a', 'a=1/3#', V('a=1/3#')], [-1])
    direct('sng-third', ['defsng a', 'a=1/3#', V('a=1/3#')], [0])
    direct('dbl-from-single', ['defdbl a', 'a=1/3', V('a=1/3#')], [0])
    direct('dbl-big', ['defdbl a', 'a=123456789', V('a-123456780')], [9])
    direct('sng-big', ['defsng a', 'a=123456789', V('a-123456780')], [12])
    # 3 DEFSTR
    direct('str-len', ['defstr a', 'a="hi"', V('len(a)')], [2])
    direct('str-dollar-same', ['defstr a', 'a="hi"', V('len(a$)')], [2])
    direct('str-prior-dollar', ['a$="xyz"', 'defstr a', V('len(a)')], [3])
    direct('str-numeric', ['defstr a', 'a=1', V('len(a)')], [0], error=13)
    direct('str-concat', ['defstr a-b', 'a="x":b=a+"yz"', V('len(b)')], [3])
    direct('str-int-suffix', ['defstr a', 'a%=2.6', V('a%')], [3])
    direct('str-long-name', ['defstr a', 'abc="hey"', V('len(abc)')], [3])
    # 4 範囲・列挙・書式
    direct('range-a-c', ['defint a-c', 'a=2.6:b=2.6:c=2.6', V('a+b+c'), 'd=2.6', V('d*10')], [9, 26])
    direct('range-before', ['defint b-c', 'a=2.6', V('a*10')], [26])
    direct('range-after', ['defint b-c', 'd=2.6', V('d*10')], [26])
    direct('list-a-c-e', ['defint a,c,e', 'a=2.6:c=2.6:e=2.6', V('a+c+e'), 'b=2.6', V('b*10')], [9, 26])
    direct('two-ranges', ['defint a-b,x-z', 'a=2.6:y=2.6', V('a+y'), 'm=2.6', V('m*10')], [6, 26])
    direct('range-whole', ['defint a-z', 'q=2.6', V('q')], [3])
    direct('range-spaces', ['defint a - c , e', 'a=2.6:e=2.6', V('a+e')], [6])
    direct('later-wins-str', ['defint a', 'defstr a', 'a="hi"', V('len(a)')], [2])
    # 5 誤り（GW は先に検査し、範囲の逆順・文字でない・空は構文の誤りで何も変えない。
    #   カンマの後の失敗と余分な文字は、そこまでの範囲を設定したあとで誤りになる）
    direct('err-reverse', ['defint c-a', 'a=2.6', V('a*10')], [26], error=2)
    direct('err-dash-open', ['defint a-', 'a=2.6', V('a*10')], [26], error=2)
    direct('err-digit', ['defint 1', 'a=2.6', V('a*10')], [26], error=2)
    direct('err-empty', ['defint', 'a=2.6', V('a*10')], [26], error=2)
    direct('err-comma-end', ['defint a,', 'a=2.6', V('a')], [3], error=2)
    direct('err-comma-digit', ['defint a,1', 'a=2.6', V('a')], [3], error=2)
    direct('err-second-reverse', ['defint a,d-c', 'a=2.6', V('a')], [3], error=2)
    direct('err-two-letters', ['defint ab', 'a=2.6', V('a')], [3], error=2)
    bad('prog-reverse', ['p=1:defint c-a'], 2)
    bad('prog-empty', ['p=1:defint'], 2)
    # 6 接尾辞が既定に優先する
    direct('suffix-single', ['defint a', 'a!=2.6', V('a!*10')], [26])
    direct('suffix-double', ['defint a', 'a#=1/3#', V('a#=1/3#')], [-1])
    direct('suffix-string', ['defint a', 'a$="hi"', V('len(a$)')], [2])
    direct('suffix-int-under-single', ['defsng a', 'a%=2.6', V('a%')], [3])
    direct('suffix-coexist', ['defint a', 'a=7:a!=2.6', V('a'), V('a!*10')], [7, 26])
    # 7 すでにある変数との関係（型ごとに別の変数）
    direct('exist-before', ['a=2.6', 'defint a', V('a'), V('a!*10')], [0, 26])
    direct('exist-return', ['a=2.6', 'defint a', 'a=5', 'defsng a', V('a*10')], [26])
    direct('exist-int-return-s', ['defint a:a=2.6:defsng a', V('a'), 'defint a', V('a')], [0, 3])
    direct('first-letter-only', ['defint a', 'ba=2.6', V('ba*10'), 'abc=2.6', V('abc')], [26, 3])
    # 8 何が宣言を戻すか（直接モード）
    direct('keep-none', ['defint a', 'a=2.6', V('a*10')], [30])
    direct('keep-assign', ['defint a', 'b=5', 'a=2.6', V('a*10')], [30])
    direct('keep-list', ['10 end', 'defint a', 'list', 'a=2.6', V('a*10')], [30])
    direct('keep-missing-line', ['defint a', '20', 'a=2.6', V('a*10')], [30], error=8)
    direct('reset-insert', ['defint a', '10 end', 'a=2.6', V('a*10')], [26])
    direct('reset-delete', ['10 end', 'defint a', '10', 'a=2.6', V('a*10')], [26])
    direct('reset-replace', ['10 end', 'defint a', '10 rem', 'a=2.6', V('a*10')], [26])
    direct('reset-clear', ['defint a', 'clear', 'a=2.6', V('a*10')], [26])
    direct('reset-new', ['defint a', 'new', 'a=2.6', V('a*10')], [26])
    direct('reset-run', ['10 end', 'defint a', 'run', 'a=2.6', V('a*10')], [26])
    direct('reset-run-program', ['10 a=2.6:' + V('a*10'), 'defint a', 'run'], [26])
    direct('program-persists', ['10 defint a', 'run', 'a=2.6', V('a*10')], [30])
    direct('stop-cont', ['10 defint a:stop', '20 a=2.6:' + V('a*10'), 'run', 'cont'], [30])
    direct('stop-edit', ['10 defint a:stop', 'run', '20 end', 'a=2.6', V('a*10')], [26])
    # 9 プログラム中（実行のたびに型を引く）
    prog('prog-clear', ['defint a:clear:a=2.6:' + V('a*10')], [26])
    prog('prog-run-line', {20: 'defint a:run 40', 40: 'a=2.6:' + V('a*10') + ':goto 790'}, [26])
    prog('prog-runtime-type', [ 'a=2.6:' + V('a*10'), 'defint a:' + V('a*10'), 'a=2.6:' + V('a*10')], [26, 0, 30])
    prog('prog-loop', ['for k=1 to 2:a=2.6:' + V('a*10') + ':defint a:next'], [26, 30])
    prog('prog-if-true', ['if 1 then defint a', 'a=2.6:' + V('a*10')], [30])
    prog('prog-if-false', ['if 0 then defint a', 'a=2.6:' + V('a*10')], [26])
    # 10 配列
    direct('array-int', ['defint a', 'dim a(3)', 'a(1)=2.6', V('a(1)')], [3])
    direct('array-before-def-s', ['dim a(3):a(1)=2.6:defint a:a(1)=5', V('a(1)'), 'defsng a', V('a(1)*10')], [5, 26])
    direct('array-redim-int', ['dim a%(3)', 'defint a', 'dim a(3)', 'a(1)=4', V('a(1)')], [4], error=10)
    direct('array-over', ['defint a', 'dim a(3)', 'a(1)=40000', V('a(1)')], [0], error=6)
    direct('array-str', ['defstr a', 'dim a(2)', 'a(1)="xy"', V('len(a(1))')], [2])
    direct('array-str-numeric', ['defstr a', 'dim a(2)', 'a(1)=1', V('len(a(1))')], [0], error=13)
    direct('array-erase-s', ['dim a(3):defint a', 'erase a', 'defsng a:erase a:dim a(5)', 'a(5)=1:' + V('a(5)')], [1], error=5)
    # 11 FOR・DEF FN・READ・SWAP
    prog('for-int', ['defint i:k=0:for i=1 to 3:k=k+i:next', V('k')], [6])
    prog('for-int-limit', ['defint i:k=0:for i=1 to 2.6:k=k+1:next', V('k')], None)
    prog('for-int-step', ['defint i:k=0:for i=1 to 2 step .5:k=k+1:next', V('k')], None)
    prog('for-int-edge', ['p=1:defint i:k=0:for i=32766 to 32767:k=k+1:next', V('k')], None)
    prog('for-dbl-step', ['defdbl i:k=0:for i=1 to 2 step .5:k=k+1:next', V('k')], [3])
    bad('for-str', ['p=1:defstr i:for i=1 to 2:next'], 13)
    prog('fn-def-a', ['defint a:def fna(x)=x/3', V('fna(7.5)*2')], [6])
    prog('fn-def-f', ['defint f:def fna(x)=x/3', V('fna(7.5)*2')], [5])
    prog('fn-def-none', ['def fna(x)=x/3', V('fna(7.5)*2')], [5])
    prog('fn-param-int', ['defint x:def fna(x)=x', V('fna(2.6)*10')], [30])
    prog('fn-str', ['defstr a:def fna(x)="hi"', V('len(fna(1))')], [2])
    prog('read-int', {20: 'defint a:read a:' + V('a') + ':goto 790', 30: 'data 2.6'}, [3])
    bad('read-text-into-int', {20: 'p=1:defint a:read a:' + V('a'), 30: 'data hi'}, 2)
    prog('read-num-into-str', {20: 'p=1:defstr a:read a:' + V('len(a)') + ':goto 790', 30: 'data 12'}, [2])
    prog('read-dbl', {20: 'defdbl a:read a:' + V('a=2.6#') + ':goto 790', 30: 'data 2.6'}, None)
    direct('swap-int-int', ['defint a,b', 'a=3:b=7', 'swap a,b', V('a')], [7])
    direct('swap-int-single', ['defint a', 'a=3:b=7', 'swap a,b', V('a')], [3], error=13)
    direct('swap-int-suffix', ['defint a', 'a=3:b%=7', 'swap a,b%', V('a')], [7])
    direct('swap-str', ['defstr a,b', 'a="ab":b="xyz"', 'swap a,b', V('len(a)')], [3])
    direct('swap-str-num', ['defstr a', 'a="x":b=7', 'swap a,b', V('len(a)')], [1], error=13)
    return out



def stage(rows=(), error=None, exact=False):
    return dict(rows=copy.deepcopy(list(rows)),
                errors=[] if error is None else [[error,True,exact]])


def prepare_rows(a):
    return [['s9mp',1,1]]


def prediction(a):
    # G_GW。数値変換の未分離点は観測後に埋めない。
    if a['rows'] is None:
        return None
    return dict(prepare=stage(prepare_rows(a)),operation=stage([['s9mo',1,1]]),
                result=stage([['s9mb',1,1]]+a['rows']+[['s9mz',1,1]],a.get('error')))


def optional_terminal(a):
    # 全program腕はRUN内に終端印を置く。直接DEFの予測はERR 12。
    return False


def terminal_present(value):
    """有無は比較とは別に保存し、不正・欠損の観測は空欄とする。"""
    if not isinstance(value, dict) or not isinstance(value.get('result'), dict):
        return ''
    rows = value['result'].get('rows')
    return int(['s9mz', 1, 1] in rows) if isinstance(rows, list) else ''


def program(a):
    out=['new']
    direct=a.get('direct',False)
    if not direct:
        body=a['body'] if isinstance(a['body'],dict) else {20+i*10:s for i,s in enumerate(a['body'])}
        body={10:'print "s9mb";1;1:'+('p=0' if a.get('untrapped') else 'on error goto 800:p=0'),
              **body,790:'print "s9mz";1;1:end',
              800:'print "s9me";1;err;p:print "s9mz";1;1:end'}
        out += [f'{n} {s}' for n,s in sorted(body.items())]
    out += ['cls','print "s9mp";1;1',('capture','prepare'),
            'cls','print "s9mo";1;1',('capture','operation'),'cls']
    out += ['print "s9mb";1;1',*a['body']] if direct else ['run']
    if direct:
        out += ['print "s9mz";1;1']
    out += [('capture','result')]
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
        elif text.lower().startswith('s9m'):
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
    if value['prepare']!=stage(prepare_rows(a)) or value['operation']!=stage([['s9mo',1,1]]):
        return False
    rows=value['result']['rows']
    has_terminal = bool(rows) and rows[-1] == ['s9mz',1,1]
    body = rows[1:-1] if has_terminal else rows[1:]
    return (bool(rows) and rows[0]==['s9mb',1,1]
            and (has_terminal or optional_terminal(a))
            and rows.count(['s9mb',1,1])==1
            and rows.count(['s9mz',1,1])==int(has_terminal)
            and all(r[0] in ('s9mv','s9me') for r in body)
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
                    and comparable(obs[0], a) == comparable(obs[1], a))
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


def comparable(value, a=None):
    """exactと対象腕の終端印を比較・2走一致から除く。観測は保持する。"""
    if value is None:
        return None
    omit_terminal = a is not None and optional_terminal(a)
    return {name: dict(rows=[r for r in v['rows']
                            if not (omit_terminal and name == 'result' and r[0] == 's9mz')],
                       errors=[e[:2] for e in v['errors']])
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
                     and comparable(r['obs'][0], r['arm']) == comparable(r['obs'][1], r['arm'])
                     and len(r['others']) == 2 and all(valid_counts(c) for c in r['others']))
    cs = [r for r in records if r['arm']['id'].startswith('control-')]
    calibrated = (len(cs) == len(controls())
                  and {r['arm']['id'] for r in cs} == {a['id'] for a in controls()}
                  and all(r['gate'] and comparable(r['obs'][0], r['arm']) ==
                          comparable(prediction(r['arm']), r['arm']) for r in cs))
    write(path, ['arm', 'repeat', 'typed_lines', 'observation', 'other_line_counts',
                 'gate', 'G_GW', 'typing_or_capture_failed', 's9mz_present'],
          [(r['arm']['id'], i+1, json.dumps(program(r['arm']), ensure_ascii=False),
            json.dumps(r['obs'][i]), json.dumps(r['others'][i]),
            'pass' if calibrated and r['gate'] else 'gate_failed',
            'gate_failed' if not calibrated or not r['gate'] else
            'unpredicted' if prediction(r['arm']) is None else
            'agree' if comparable(r['obs'][0], r['arm']) == comparable(prediction(r['arm']), r['arm']) else 'differ',
            int(r['failed'][i]), terminal_present(r['obs'][i])) for r in records for i in range(2)])
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


def merge(base, patch, retire, out):
    """追補1: 基の記録から退けた腕の行を除き、基に無い腕の行を補う。対照は基を採る。"""
    if len({base.resolve(), patch.resolve(), out.resolve()}) != 3:
        raise ValueError('入力2つと出力は別ファイルにする')
    def rows(path):
        with path.open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream, delimiter='\t')
            return list(reader.fieldnames), list(reader)
    head, base_rows = rows(base)
    head2, patch_rows = rows(patch)
    if head != head2:
        raise ValueError('列が一致しない')
    kept = [r for r in base_rows if r['arm'] not in retire]
    have = {r['arm'] for r in kept}
    added = [r for r in patch_rows if r['arm'] not in have and r['arm'] not in retire]
    write(out, head, [[r[h] for h in head] for r in kept+added])
    return len(kept), len(added)


def check(expected, measured, predicted_only=False):
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
            if predicted_only and value is None and aid in known and prediction(known[aid]) is None:
                continue
            if aid not in known or prediction(known[aid]) is None or not valid(value, known[aid]):
                return False
            if aid in targets and comparable(targets[aid], known[aid]) != comparable(value, known[aid]):
                return False
            targets[aid] = value
        grouped = {}
        for r in actual:
            grouped.setdefault(r['arm'], []).append(r)
        if not targets or (predicted_only and not set(targets).issubset(grouped)) or (
                not predicted_only and set(targets) != set(grouped)):
            return False
        cs = {aid for aid in targets if aid.startswith('control-')}
        if cs != {a['id'] for a in controls()}:
            return False
        if any(comparable(targets[aid], known[aid]) != comparable(prediction(known[aid]), known[aid]) for aid in cs):
            return False
        for aid, value in targets.items():
            runs = grouped[aid]
            if len(runs) != 2 or {r['repeat'] for r in runs} != {'1', '2'}:
                return False
            if comparable(json.loads(runs[0]['observation']), known[aid]) != comparable(json.loads(runs[1]['observation']), known[aid]):
                return False
            if any(json.loads(r['typed_lines']) != json.loads(json.dumps(program(known[aid])))
                   or not valid_counts(json.loads(r['other_line_counts']))
                   or r['G_GW'] not in ('agree', 'differ')
                   or r['gate'] != 'pass' or r['typing_or_capture_failed'] != '0'
                   or not valid(json.loads(r['observation']), known[aid])
                   or comparable(json.loads(r['observation']), known[aid]) != comparable(value, known[aid]) for r in runs):
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
    assert len(by_id)==len(known) and len(controls())==11
    assert sum(prediction(a) is None for a in known)==4
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
    fixed={'int-round':[value(3)],'int-half-neg':[value(-3)],'int-third':[value(0)],
           'dbl-third':[value(-1)],'sng-third':[value(0)],'dbl-big':[value(9)],'sng-big':[value(12)],
           'str-len':[value(2)],'str-concat':[value(3)],'range-a-c':[value(9),value(26)],
           'err-comma-end':[value(3)],'exist-before':[value(0),value(26)],
           'exist-int-return-s':[value(0),value(3)],'keep-none':[value(30)],'reset-insert':[value(26)],
           'prog-runtime-type':[value(26),value(0),value(30)],'fn-def-a':[value(6)],'fn-def-f':[value(5)],
           'prog-reverse':[['s9me',1,2,1]],'prog-empty':[['s9me',1,2,1]],'for-str':[['s9me',1,13,1]]}
    for aid,rows in fixed.items():
        assert prediction(by_id[aid])['result']['rows']==[['s9mb',1,1]]+rows+[['s9mz',1,1]]
    for aid in ('for-int-limit','for-int-step','for-int-edge','read-dbl'):
        assert prediction(by_id[aid]) is None
    assert prediction(by_id['int-over'])['result']['errors']==[[6,True,False]]
    assert prediction(by_id['err-reverse'])['result']['errors']==[[2,True,False]]
    for a in known:
        plan=program(a)
        if not a.get('direct'):
            assert 'print "s9mz";1;1' not in plan
            assert '790 print "s9mz";1;1:end' in plan
            assert '800 print "s9me";1;err;p:print "s9mz";1;1:end' in plan
    assert extract(screen_of([value(-1),value(17)]))[0]==stage([value(-1),value(17)])
    assert extract(b' '*3000)[0]==stage()
    assert extract(screen_of([['s9mv',1]]))[0]['rows']==[['invalid']]
    assert not valid_stage(stage([['s9mv',1,1,2]]))
    assert extract(screen_of([value(17)]).replace(b's9mv',b'z9kv',1))[0]['rows']==[]
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
    with tempfile.TemporaryDirectory(prefix='l4s9m-selftest-',dir=work) as temp:
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
        # 値違いは採取形の関門を通ってdifferに届く。
        bad=copy.deepcopy(records)
        target=next(r for r in bad if r['arm']['id']=='int-round')
        for o in target['obs']: o['result']['rows'][1][2]=99
        assert valid(target['obs'][0],target['arm']) and emit(measured,bad)
        assert not check(expected,measured)
        with measured.open() as stream:
            assert all(r['gate']=='pass' and r['G_GW']=='differ'
                       for r in csv.DictReader(stream,delimiter='\t') if r['arm']=='int-round')
        # 誤り番号違いも本文やexactの検査に遮られず比較に届く。
        bad=copy.deepcopy(records)
        target=next(r for r in bad if r['arm']['id']=='prog-reverse')
        for o in target['obs']: o['result']['rows'][1][2]=13
        assert valid(target['obs'][0],target['arm']) and emit(measured,bad)
        assert not check(expected,measured)
        for index,replacement in ((2,6),(3,2)):
            bad=copy.deepcopy(records)
            target=next(r for r in bad if r['arm']['id']=='prog-empty')
            for o in target['obs']: o['result']['rows'][1][index]=replacement
            assert valid(target['obs'][0],target['arm']) and emit(measured,bad)
            assert not check(expected,measured)
            with measured.open() as stream:
                assert all(r['gate']=='pass' and r['G_GW']=='differ'
                           for r in csv.DictReader(stream,delimiter='\t') if r['arm']=='prog-empty')
        bad=copy.deepcopy(records)
        target=next(r for r in bad if r['arm']['id']=='prog-empty')
        for o in target['obs']: o['result']['rows'].pop()
        assert not valid(target['obs'][0],target['arm'])
        assert not emit(measured,bad)
        for mutation in ('repeat','capture','control','end','duplicate-mark'):
            bad=copy.deepcopy(records)
            if mutation=='repeat': bad[-1]['obs'][1]['result']['rows'][1][2]=99
            elif mutation=='capture': bad[-1]['failed'][1]=True
            elif mutation=='control':
                for o in bad[0]['obs']: o['result']['rows'][1][2]=99
            elif mutation=='end':
                for o in bad[-1]['obs']: o['result']['rows'].pop()
            else:
                for o in bad[-1]['obs']: o['result']['rows'].insert(0,['s9mb',1,1])
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
        # 追補1: merge は退けた腕の行を捨て、基に無い腕だけ補い、同一ファイル指定を拒否する。
        assert emit(measured,records)
        with measured.open() as stream:
            rows0=list(csv.DictReader(stream,delimiter='\t'))
        extra=[dict(r,arm='retired-arm') for r in rows0[:2]]
        new=[dict(r,arm='new-arm') for r in rows0[:2]]
        write(root/'base.tsv',list(rows0[0]),[list(r.values()) for r in rows0+extra])
        write(root/'patch.tsv',list(rows0[0]),[list(r.values()) for r in new+rows0[2:4]])
        assert merge(root/'base.tsv',root/'patch.tsv',{'retired-arm'},root/'merged.tsv')==(len(rows0),2)
        merged_arms={r['arm'] for r in csv.DictReader((root/'merged.tsv').open(),delimiter='\t')}
        assert 'retired-arm' not in merged_arms and 'new-arm' in merged_arms
        try:
            merge(root/'base.tsv',root/'base.tsv',set(),root/'merged.tsv')
            raise AssertionError('同一入力を受理')
        except ValueError:
            pass
        unknown=by_id['for-int-limit']
        obs=prediction(by_id['int-round'])
        unknown_record=dict(arm=unknown,obs=[obs,copy.deepcopy(obs)],others=[counts,counts],failed=[False,False],gate=True)
        assert emit(measured,records+[unknown_record])
        freeze(selected)
        assert not check(expected,measured)
        assert check(expected,measured,predicted_only=True)
        assert rejudge(measured,out) and check(expected,out,predicted_only=True)
        # 期待値にある腕の欠落はsubset照合でも不合格。
        with measured.open() as stream:
            subset_rows=list(csv.DictReader(stream,delimiter='\t'))
        missing=[r for r in subset_rows if r['arm']!='int-round']
        write(out,list(missing[0]),[list(r.values()) for r in missing])
        assert not check(expected,out,predicted_only=True)
        freeze(selected+[unknown])
        assert check(expected,measured,predicted_only=True)

        assert not check(expected,measured)
        write(expected,['arm','observation'],[(a['id'],json.dumps(obs if a['id']==unknown['id'] else prediction(a))) for a in selected+[unknown]])
        assert not check(expected,measured)
        assert not check(expected,measured,predicted_only=True)
        with measured.open() as stream:
            assert all(r['G_GW']=='unpredicted' for r in csv.DictReader(stream,delimiter='\t') if r['arm']==unknown['id'])
        print('OK 固定予測・取り出し陽性陰性・本文非出力・exact除外・2走・破損拒否・予測なし拒否',flush=True)
        rom=root/'rom'
        built=subprocess.run([os.sys.executable,str(kw.REPO/'src/build_main_rom.py'),str(rom),
                              '--work-dir',str(root/'asm')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert built.returncode==0,'自作ROM一時ビルド失敗'
        own=controls()
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
        assert check(expected,measured,predicted_only=True)
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
    m.add_argument('--only', help='追補1: 指定した本体腕（コンマ区切り）と対照だけを測る')
    c = sub.add_parser('check'); c.add_argument('--expected', type=Path, required=True)
    c.add_argument('--measured', type=Path, required=True)
    c.add_argument('--predicted-only', action='store_true')
    r = sub.add_parser('rejudge'); r.add_argument('--measured', type=Path, required=True)
    r.add_argument('--out', type=Path, required=True)
    g = sub.add_parser('merge'); g.add_argument('--base', type=Path, required=True)
    g.add_argument('--patch', type=Path, required=True); g.add_argument('--out', type=Path, required=True)
    g.add_argument('--retire', action='append', default=[])
    s = sub.add_parser('selftest'); s.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'check':
        ok = check(args.expected, args.measured, args.predicted_only)
        print('照合一致' if ok else '照合不一致'); return 0 if ok else 1
    if args.command == 'merge':
        kept, added = merge(args.base, args.patch, set(args.retire), args.out)
        print(f'統合: 基{kept}行＋補{added}行'); return 0
    if args.command == 'rejudge':
        ok = rejudge(args.measured, args.out)
        print('再判定完了: 関門'+('通過' if ok else '失敗'))
        return 0 if ok else 1
    selected = controls()+arms()
    if args.command == 'measure' and args.only:
        wanted = set(args.only.split(','))
        if not wanted <= {a['id'] for a in arms()}:
            parser.error('--only は本体腕の名前だけ')
        selected = controls()+[a for a in arms() if a['id'] in wanted]
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
