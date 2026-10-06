#!/usr/bin/env python3
"""l4-s9n: 括弧なしの比較式・WIDTH・BEEP の事前予測と測定器具。画面本文は非出力。

採取は印（s9n?）と整数、誤り番号の包含だけ。WIDTH は画面の桁数・行数を変えテキストVRAMの
並びが80桁のときと違うので、**印を出す前に必ず width 80,25 へ戻す**設計にする（直接モードの
腕は戻す文を B の前に置き、プログラムの腕は 790・800 行が戻してから B を出す）。戻し忘れは
selftest の静的検査（腕ごとに width 文を畳んで最終状態が 80,25 であること）が落とす。
BEEP は I/O ポート 0x40 の OUT の各ビットの立ち上がり・立ち下がりの有無（値列は出さない）で観測する。
"""
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

WORK = kw.REPO.parent / 'tmp/s9n-work'
ARITY = {x: 2 for x in ('s9np', 's9no', 's9nb', 's9nv', 's9nz', 's9nq')}
ARITY['s9ne'] = 3
NUMBER = r'(?: +\d+| *-\d+)'
MARK = re.compile(r'^(s9n[a-z])((?:'+NUMBER+r')+) *$', re.I)
P, O = 'print "s9np";1;1', 'print "s9no";1;1'
B, Z = 'print "s9nb";1;1', 'print "s9nz";1;1'
PORT_LINE = re.compile(r'^\s*\d+\s+\d+\s+(\d+)\s+main\s+OUT\s+0040\s+([0-9A-Fa-f]{2})\s')
PORT_FROM = 1  # 追補1: 第1フレームから記録して、窓の最初の書き込みの比較相手（起動時の書き込み）を持つ


def value(n):
    return ['s9nv', 1, n]


def V(e):
    return f'print "s9nv";1;{e}'


def arm(aid, kind, **extra):
    return dict(id=aid, kind=kind, **extra)


def controls():
    def prog(aid, body, vals):
        return arm(aid, 'prog', body=body, rows=[value(n) for n in vals])

    def direct(aid, line, error):
        return arm(aid, 'direct', pre=[], post=[line], rows=[], error=error)
    return [
        prog('control-values', ['print "s9nv";1;17', 'print "s9nv";1;-1'], [17, -1]),
        prog('control-goto', {20: 'goto 40', 30: 'print "s9nv";1;99', 40: 'print "s9nv";1;7'}, [7]),
        prog('control-gosub', {20: 'gosub 100:print "s9nv";1;8:goto 790', 100: 'print "s9nv";1;7:return'}, [7, 8]),
        prog('control-for', ['k=0:for i=1 to 3', 'k=k+1', 'next i', 'print "s9nv";1;k'], [3]),
        prog('control-if', ['if 1 then print "s9nv";1;9'], [9]),
        prog('control-dim', ['dim a(3):a(2)=7', 'print "s9nv";1;a(2)'], [7]),
        arm('control-trap', 'prog', body=['p=4:error 5'], rows=[['s9ne', 1, 5, 4]]),
        arm('control-syntax', 'prog', body=['p=1:let'], rows=[['s9ne', 1, 2, 1]]),
        direct('control-direct-5', 'error 5', 5),
        direct('control-direct-8', 'goto 777', 8),
        direct('control-direct-17', 'cont', 17),
        # I/Oポートの採取が偽の変化を作らないことの対照（何も鳴らさない行）
        arm('control-port-silent', 'direct', pre=['rem'], post=[V('7')], rows=[value(7)], error=None,
            port='none'),
    ]


def arms():
    out = []

    def D(aid, post, vals, error=None, pre=(), **extra):
        out.append(arm(aid, 'direct', pre=list(pre), post=list(post),
                       rows=None if vals is None else [value(n) for n in vals], error=error, **extra))

    def PR(aid, body, vals, err=None):
        rows = ([['s9ne', 1, err[0], err[1]]] if err else []) + [value(n) for n in vals]
        out.append(arm(aid, 'prog', body=body, rows=rows))

    def W(aid, body, show, vals, err=None, **extra):
        rows = None if vals is None else ([['s9ne', 1, err[0], err[1]]] if err else []) + [value(n) for n in vals]
        out.append(arm(aid, 'wprog', body=body, show=show, rows=rows, **extra))

    # ---- 1 括弧なしの比較式（PRINT の項目として、代入の右辺として）。GW は関係演算子を同じ段で左結合に畳む。
    for aid, e, n in (
            ('cmp-num-eq-t', '1=1', -1), ('cmp-num-eq-f', '1=2', 0), ('cmp-num-lt', '1<2', -1),
            ('cmp-num-ne', '1<>2', -1),
            ('cmp-str-eq-t', '"a"="a"', -1), ('cmp-str-eq-f', '"a"="b"', 0), ('cmp-str-lt', '"a"<"b"', -1),
            ('cmp-str-gt', '"a">"b"', 0), ('cmp-str-ne', '"a"<>"b"', -1), ('cmp-str-le', '"a"<="a"', -1),
            ('cmp-str-ge', '"a">="b"', 0),
            ('cmp-and', '1<2 and 2<3', -1), ('cmp-or', '1>2 or 2<3', -1),
            ('cmp-add', '2+3=5', -1), ('cmp-add-before-lt', '1+1<2', 0), ('cmp-mul', '2*3<7', -1),
            ('cmp-concat', '"a"+"b"="ab"', -1),
            ('cmp-not', 'not 1=2', -1), ('cmp-negconst', '-1=1', 0),
            ('cmp-chain-lt', '1<2<3', -1), ('cmp-chain-eq', '1=1=1', 0), ('cmp-chain-eq-m1', '1=1=-1', -1),
            ('cmp-rel-le-rev', '1=<2', -1), ('cmp-rel-ge-rev', '2=>1', -1), ('cmp-rel-ne-rev', '1><2', -1),
            ('cmp-mixed-and-or', '1=1 and 2=3 or 4=4', -1),
            ('cmp-float', '1.5=1.5', -1), ('cmp-sd-third', '1/3=1/3#', 0)):
        D(aid, [V(e)], [n])
    D('cmp-asg-num', ['a=1=1', V('a')], [-1])
    D('cmp-asg-num-f', ['a=1=2', V('a')], [0])
    D('cmp-asg-str', ['a="b"="b"', V('a')], [-1])
    D('cmp-asg-int', ['a%=2>1', V('a%')], [-1])
    D('cmp-asg-strvar-err', ['a$=1=1', V('len(a$)')], [0], error=13)
    D('cmp-vars', ['a=3:b=3', V('a=b')], [-1])
    D('cmp-chain-str-err', ['a="a"<"b"<"c"', V('a')], [0], error=13)
    D('cmp-mixed-err1', ['a="a"=1', V('a')], [0], error=13)
    D('cmp-mixed-err2', ['a=1="a"', V('a')], [0], error=13)
    D('cmp-print-mixed', ['print "a"=1', V('7')], [7], error=13)
    D('cmp-print-mixed2', ['print 1="a"', V('7')], [7], error=13)
    # 関係演算子の記号は集めた印の集合（<=1, =2, >=4 のビット）。同じ記号を2回は構文の誤り、3種そろえると常に真。
    D('cmp-dup-eq', ['a=1==1', V('a')], [0], error=2)
    D('cmp-dup-lt-print', ['print 1<<2', V('7')], [7], error=2)
    D('cmp-rel-triple', [V('1<=>2')], [-1])

    # ---- 2 WIDTH の値の受理（プログラム中。p=1 を立ててから width、通れば a=1）
    for aid, stmt in (('w-ok-40', 'width 40'), ('w-ok-80', 'width 80'), ('w-ok-40-20', 'width 40,20'),
                      ('w-ok-80-20', 'width 80,20'), ('w-ok-80-25', 'width 80,25'), ('w-ok-40-25', 'width 40,25'),
                      ('w-ok-rows-only', 'width ,20'), ('w-ok-cols-trailing', 'width 40,'),
                      ('w-ok-noargs', 'width'), ('w-ok-expr', 'width 20*2'), ('w-ok-lprint', 'width lprint 40')):
        W(aid, [f'p=1:{stmt}:a=1'], ['a'], [1])
    for aid, stmt, code in (('w-err-0', 'width 0', 5), ('w-err-39', 'width 39', 5), ('w-err-41', 'width 41', 5),
                            ('w-err-81', 'width 81', 5), ('w-err-256', 'width 256', 5),
                            ('w-err-rows-19', 'width 80,19', 5), ('w-err-rows-24', 'width 80,24', 5),
                            ('w-err-rows-26', 'width 80,26', 5),
                            ('w-err-extra', 'width 80,25,3', 2), ('w-err-lprint-0', 'width lprint 0', 5),
                            ('w-err-str', 'width "a"', 56)):
        W(aid, [f'p=1:{stmt}:a=1'], ['a'], [0], err=(code, 1))
    W('w-frac-404', ['p=1:width 40.4:a=1'], ['a'], None)
    W('w-frac-796', ['p=1:width 79.6:a=1'], ['a'], None)

    # ---- 3 幅40・80での折り返し・項目の前改行・コンマ・TAB・SPC（位置は pos(0) と csrlin の差）
    def geo(aid, width, stmt, vals, rows_stmt=None):
        W(aid, [f'width {width}:c=csrlin', stmt, 'a=pos(0):b=csrlin-c'], ['a', 'b'], vals)

    for n, vals in ((39, [39, 0]), (40, [0, 1]), (41, [1, 1]), (45, [5, 1]), (85, [5, 2])):
        geo(f'w40-wrap-{n}', 40, f'print string$({n},"a");', vals)
    geo('w80-wrap-80', 80, 'print string$(80,"a");', [0, 1])
    geo('w80-wrap-85', 80, 'print string$(85,"a");', [5, 1])
    W('w80-after-40', ['width 40', 'width 80:c=csrlin', 'print string$(85,"a");', 'a=pos(0):b=csrlin-c'],
      ['a', 'b'], [5, 1])
    geo('w40-item-wrap', 40, 'print string$(30,"a");string$(15,"b");', [15, 1])
    geo('w40-item-exact', 40, 'print string$(30,"a");string$(10,"b");', [0, 1])
    geo('w40-num-wrap', 40, 'print string$(37,"a");12345;', [7, 1])
    geo('w40-comma-1', 40, 'print "a",', [14, 0])
    geo('w40-comma-2', 40, 'print "a","b",', [0, 1])
    geo('w40-comma-13', 40, 'print string$(13,"a"),', [14, 0])
    geo('w40-comma-14', 40, 'print string$(14,"a"),', [0, 1])
    geo('w40-tab-10', 40, 'print tab(10);', [10, 0])
    geo('w40-tab-39', 40, 'print tab(39);', [39, 0])
    geo('w40-tab-45', 40, 'print tab(45);', [5, 0])
    geo('w40-tab-back', 40, 'print "xxxxxx";tab(5);', [5, 1])
    geo('w40-spc-45', 40, 'print spc(45);', [5, 0])
    geo('w40-spc-39', 40, 'print spc(39);', [39, 0])
    W('w40-locate-pos', ['width 40:c=csrlin', 'locate 5,2', 'a=pos(0):b=csrlin-c'], ['a', 'b'], [5, 2])
    # width は画面を消してカーソルを先頭へ戻す、とマニュアルは書く（GW の「変化なしは何もしない」とは別の予測）
    W('w-home-80', ['cls:c=csrlin', 'locate 5,10:width 80,25:a=pos(0):b=csrlin-c'], ['a', 'b'], [0, 0])
    W('w-home-40', ['cls:c=csrlin', 'locate 5,10:width 40:a=pos(0):b=csrlin-c'], ['a', 'b'], [0, 0])

    # ---- 4 行数・桁の上限（予測なし。起点が分からない）
    for aid, setup, stmt in (('w8025-loc-y23', None, 'locate 0,23'), ('w8025-loc-y24', None, 'locate 0,24'),
                             ('w8025-loc-y25', None, 'locate 0,25'),
                             ('w8020-loc-y19', 'width 80,20', 'locate 0,19'),
                             ('w8020-loc-y20', 'width 80,20', 'locate 0,20'),
                             ('w4025-loc-x39', 'width 40', 'locate 39,0'), ('w4025-loc-x40', 'width 40', 'locate 40,0')):
        W(aid, ([setup] if setup else []) + [f'p=1:{stmt}:a=1'], ['a'], None)
    for aid, wd in (('w8025-scroll', 'width 80,25'), ('w8020-scroll', 'width 80,20'),
                    ('w4025-scroll', 'width 40,25'), ('w4020-scroll', 'width 40,20')):
        W(aid, [f'{wd}:c=csrlin', 'for i=1 to 30:print:next', 'a=csrlin-c'], ['a'], None)

    # ---- 5 width が画面を消すか（q印が残るかで見る。残る=消さない）
    def Q(aid, stmt, survive, vals=(7,), error=None, **extra):
        D(aid, [V('7')], None if survive is None else list(vals), error=error,
          pre=[f'print "s9nq";1;5:{stmt}'], q=True, qs=survive, **extra)

    Q('w-q-same', 'width 80,25', False)
    Q('w-q-40', 'width 40:width 80,25', False)
    Q('w-q-err', 'width 39', True, error=5, width_error=True)
    Q('w-q-noarg', 'width', None)
    Q('w-q-rows', 'width ,25', False)
    Q('w-q-lprint', 'width lprint 40', True)

    # ---- 6 直接モードの width（行の中で戻す）
    D('w-d-wrap40', [V('a'), V('b')], [5, 1],
      pre=['width 40:c=csrlin:print string$(45,"a");:a=pos(0):b=csrlin-c:width 80,25'])
    D('w-d-home', [V('a'), V('b')], [0, 0],
      pre=['cls:c=csrlin:locate 5,10:width 40,20:a=pos(0):b=csrlin-c:width 80,25'])
    D('w-d-roundtrip-40', [V('7')], [7], pre=['width 40,20:width 80,25'])
    D('w-d-roundtrip-80', [V('7')], [7], pre=['width 80,20:width 80,25'])

    # ---- 7 BEEP（誤り番号と、ポート0x40の各ビットの立ち上がり・立ち下がり）
    def Bp(aid, pre, port, vals=(7,), error=None, predicted=True):
        D(aid, [V('7')], list(vals) if predicted else None, error=error, pre=pre,
          port=port if predicted else 'free')

    Bp('beep-plain', ['beep'], 'both')
    Bp('beep-0', ['beep 0'], 'none')
    Bp('beep-1-0', ['beep 1', 'beep 0'], 'both')
    Bp('beep-1-only', ['beep 1', 'rem'], 'rise')
    Bp('beep-2', ['beep 2', 'beep 0'], None, predicted=False)
    Bp('beep-neg', ['beep -1', 'beep 0'], None, predicted=False)
    Bp('beep-256', ['beep 256', 'beep 0'], None, predicted=False)
    Bp('beep-str', ['beep "a"'], 'none', error=13)
    Bp('beep-extra', ['beep 0,1'], 'none', error=2)
    Bp('beep-two', ['beep:beep'], 'both')
    Bp('beep-if', ['if 1 then beep'], 'both')
    Bp('beep-expr', ['a=1:beep a:beep a-1'], 'both')
    Bp('beep-chr7', ['print chr$(7);'], 'both')
    PR('beep-prog', ['p=1:beep:beep 0', V('9')], [9])
    PR('beep-prog-str', ['p=1:beep "a"'], [], err=(13, 1))
    return out


def port_flags(spec):
    """予測の書き方（none/both/rise）を、ビットごとの有無（立ち上がり・立ち下がり）に直す。"""
    rise = [0]*8
    fall = [0]*8
    if spec in ('both', 'rise'):
        rise[5] = 1
    if spec == 'both':
        fall[5] = 1
    return dict(rise=rise, fall=fall)


def stage(rows=(), error=None, exact=False):
    return dict(rows=copy.deepcopy(list(rows)),
                errors=[] if error is None else [[error, True, exact]])


def prediction(a):
    if a['rows'] is None:
        return None
    q = [['s9nq', 1, 5]] if a.get('qs') else []
    out = dict(prepare=stage([['s9np', 1, 1]]), operation=stage([['s9no', 1, 1]]),
               result=stage(q+[['s9nb', 1, 1]]+a['rows']+[['s9nz', 1, 1]], a.get('error')))
    if a.get('port') in ('none', 'both', 'rise'):
        out['port'] = port_flags(a['port'])
    return out


def has_port(a):
    return a.get('port') is not None


def frame_dict(a):
    body = a['body'] if isinstance(a['body'], dict) else {20+i*10: s for i, s in enumerate(a['body'])}
    if a['kind'] == 'wprog':
        return {10: 'on error goto 800:p=0', **body,
                790: 'width 80,25:'+B, 791: ':'.join(V(x) for x in a['show']), 792: Z+':end',
                800: 'width 80,25:'+B+':print "s9ne";1;err;p:goto 791'}
    return {10: B+':on error goto 800:p=0', **body, 790: Z+':end',
            800: 'print "s9ne";1;err;p:'+Z+':end'}


def program(a):
    out = ['new']
    if a['kind'] in ('prog', 'wprog'):
        out += [f'{n} {s}' for n, s in sorted(frame_dict(a).items())]
    out += ['cls', P, ('capture', 'prepare'), 'cls', O, ('capture', 'operation'), 'cls']
    if a['kind'] == 'direct':
        if has_port(a):
            out += [('window',)]
        out += [*a['pre'], B, *a['post'], Z]
    else:
        out += ['run']
    out += [('capture', 'result')]
    assert all(not isinstance(x, str) or (x.isascii() and x == x.lower() and
               len(x) < 80 and '@' not in x and '\n' not in x and '\r' not in x) for x in out)
    return out


def final_width_state(a):
    """直接モードの腕の width 文を畳んで、印（B）を出す時点の画面の桁数・行数を返す。"""
    cols, rows = 80, 25
    if a['kind'] != 'direct' or a.get('width_error'):
        return cols, rows
    for line in a['pre']:
        for st in line.split(':'):
            m = re.fullmatch(r'width(?: +(\d*)(?: *, *(\d*))?)?', st.strip())
            if not m or st.strip().startswith('width lprint'):
                continue
            if m[1]:
                cols = int(m[1])
            if m[2]:
                rows = int(m[2])
    return cols, rows


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
        elif text.lower().startswith('s9n'):
            rows.append(['invalid'])
        else:
            other += 1
    errors = []
    for n in error_numbers():
        contains, exact = num.entry_message_status(data, n)
        if contains:
            errors.append([n, contains, exact])
    return dict(rows=rows, errors=errors), other


def valid_stage(value_):
    if not isinstance(value_, dict) or set(value_) != {'rows', 'errors'}:
        return False
    rows, errors = value_['rows'], value_['errors']
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


def valid_port(p):
    return (isinstance(p, dict) and set(p) >= {'rise', 'fall'} and
            all(isinstance(p[k], list) and len(p[k]) == 8 and all(type(n) is int and n >= 0 for n in p[k])
                for k in ('rise', 'fall')) and (p.get('outs') is None or type(p['outs']) is int))


def valid(value_, a):
    keys = {'prepare', 'operation', 'result'} | ({'port'} if has_port(a) else set())
    if not isinstance(value_, dict) or set(value_) != keys:
        return False
    if not all(valid_stage(value_[k]) for k in ('prepare', 'operation', 'result')):
        return False
    if has_port(a) and not valid_port(value_['port']):
        return False
    if value_['prepare'] != stage([['s9np', 1, 1]]) or value_['operation'] != stage([['s9no', 1, 1]]):
        return False
    rows = value_['result']['rows']
    qs = [r for r in rows if r[0] == 's9nq']
    rest = [r for r in rows if r[0] != 's9nq']
    if qs and (not a.get('q') or qs != [['s9nq', 1, 5]]):
        return False
    has_terminal = bool(rest) and rest[-1] == ['s9nz', 1, 1]
    body = rest[1:-1] if has_terminal else rest[1:]
    return (bool(rest) and rest[0] == ['s9nb', 1, 1] and has_terminal
            and rows.count(['s9nb', 1, 1]) == 1 and rows.count(['s9nz', 1, 1]) == 1
            and (not qs or rows.index(qs[0]) < rows.index(['s9nb', 1, 1]))
            and all(r[0] in ('s9nv', 's9ne') for r in body)
            and len(rows) <= 16)


def dump_path(path, frame, multiple):
    return path.with_name(path.stem+f'.f{frame:06d}'+path.suffix) if multiple else path


def port_summary(text, window):
    """ポート0x40のメインCPUのOUTだけから、窓の中のビットごとの立ち上がり・立ち下がりを数える。
    値列は返さない。窓の手前の最後の値を比較相手にする。"""
    prev, rise, fall, outs, prior = None, [0]*8, [0]*8, 0, 0
    for line in text.splitlines():
        m = PORT_LINE.match(line)
        if not m:
            continue
        frame, val = int(m[1]), int(m[2], 16)
        if frame >= window:
            outs += 1
            if prev is not None:
                for b in range(8):
                    x, y = (prev >> b) & 1, (val >> b) & 1
                    rise[b] += int(x == 0 and y == 1)
                    fall[b] += int(x == 1 and y == 0)
        else:
            prior = 1
        prev = val
    return dict(rise=rise, fall=fall, outs=outs, prior=prior)


def run_arm(rom, official, a, work):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    captures, window = [], None
    for step in program(a):
        if isinstance(step, str):
            args += ['--type-at', str(at), '--type', step+'\n']
            at += (len(step)+1)*8+240+(15000 if step == 'run' else 0)
        elif step[0] == 'window':
            window = at
        else:
            path, frame = work/(step[1]+'.bin'), at+200
            args += ['--vram-dump', str(path), '--vram-dump-at', str(frame)]
            captures.append((step[1], path, frame))
            at = frame+100
    iolog = work/'port.txt'
    if has_port(a):
        args += ['--io-log', str(iolog), '--io-log-from-frame', str(PORT_FROM)]
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
        if has_port(a):
            obs['port'] = port_summary(iolog.read_text(encoding='utf-8', errors='replace'), window)
        return obs, others
    finally:
        for _, path in paths:
            path.unlink(missing_ok=True)
        for _, path, _ in captures:
            path.unlink(missing_ok=True)
        iolog.unlink(missing_ok=True)


def comparable(value_, a=None):
    """exact と窓の回数を比較から除く。ポートは各ビットの変化の有無だけ。"""
    if value_ is None:
        return None
    out = {name: dict(rows=list(v['rows']), errors=[e[:2] for e in v['errors']])
           for name, v in value_.items() if name != 'port'}
    if 'port' in value_:
        p = value_['port']
        out['port'] = dict(rise=[int(n > 0) for n in p['rise']], fall=[int(n > 0) for n in p['fall']])
    return out


def measure(rom, official, selected, work):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as temp:
        for a in selected:
            obs, others, failed = [], [], []
            for _ in range(2):
                try:
                    value_, count = run_arm(rom, official, a, Path(temp))
                    obs.append(value_); others.append(count); failed.append(False)
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


def valid_counts(value_):
    return (isinstance(value_, dict) and set(value_) == {'prepare', 'operation', 'result'}
            and all(type(n) is int and n >= 0 for n in value_.values()))


def terminal_present(value_):
    if not isinstance(value_, dict) or not isinstance(value_.get('result'), dict):
        return ''
    rows = value_['result'].get('rows')
    return int(['s9nz', 1, 1] in rows) if isinstance(rows, list) else ''


def emit(path, records):
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
                 'gate', 'G_GW', 'typing_or_capture_failed', 's9nz_present'],
          [(r['arm']['id'], i+1, json.dumps(program(r['arm']), ensure_ascii=False),
            json.dumps(r['obs'][i]), json.dumps(r['others'][i]),
            'pass' if calibrated and r['gate'] else 'gate_failed',
            'gate_failed' if not calibrated or not r['gate'] else
            'unpredicted' if prediction(r['arm']) is None else
            'agree' if comparable(r['obs'][0], r['arm']) == comparable(prediction(r['arm']), r['arm']) else 'differ',
            int(r['failed'][i]), terminal_present(r['obs'][i])) for r in records for i in range(2)])
    return calibrated and bool(records) and all(r['gate'] for r in records)


def rejudge(measured, out):
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
    """追補: 基の記録から退けた腕の行を除き、基に無い腕の行を補う。"""
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
            value_ = json.loads(r.get('prediction') or r['observation'])
            aid = r['arm']
            if predicted_only and value_ is None and aid in known and prediction(known[aid]) is None:
                continue
            if aid not in known or prediction(known[aid]) is None or not valid(value_, known[aid]):
                return False
            if aid in targets and comparable(targets[aid], known[aid]) != comparable(value_, known[aid]):
                return False
            targets[aid] = value_
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
        for aid, value_ in targets.items():
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
                   or comparable(json.loads(r['observation']), known[aid]) != comparable(value_, known[aid]) for r in runs):
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


def synthetic_iolog(window_from, events):
    """合成のI/O記録。events は (frame相対, cpu, kind, port, value)。"""
    lines = ['# main', '# seq    clock   frame  cpu   kind  port  value  pc']
    for i, (df, cpu, kind, port, val) in enumerate(events):
        lines.append(f'{i:6d} {i*10:7d} {window_from+df:6d}  {cpu:<4s}  {kind:<4s}  {port:04X}   {val:02X}   0000')
    return '\n'.join(lines)+'\n'


def selftest(work=None):
    if work is not None:
        work.mkdir(parents=True, exist_ok=True)
    known = controls()+arms()
    by_id = {a['id']: a for a in known}
    assert len(by_id) == len(known) and len(controls()) == 12
    unpredicted = [a['id'] for a in known if prediction(a) is None]
    assert len(unpredicted) == 17, unpredicted
    for a in known:
        program(a)
        p = prediction(a)
        if p is not None:
            assert valid(p, a)
            for k in ('prepare', 'operation', 'result'):
                v = p[k]
                e = v['errors']
                assert extract(screen_of(v['rows'], e[0][0] if e else None,
                                         e[0][2] if e else True))[0] == v
    # 手順から独立に固定した値。予測関数の再利用だけで検査を済ませない。
    fixed = {'cmp-num-eq-t': [value(-1)], 'cmp-num-eq-f': [value(0)], 'cmp-str-eq-f': [value(0)],
             'cmp-str-lt': [value(-1)], 'cmp-add': [value(-1)], 'cmp-chain-lt': [value(-1)],
             'cmp-chain-eq': [value(0)], 'cmp-sd-third': [value(0)], 'cmp-chain-str-err': [value(0)],
             'w40-wrap-40': [value(0), value(1)], 'w40-wrap-45': [value(5), value(1)],
             'w40-comma-2': [value(0), value(1)], 'w-ok-40': [value(1)],
             'w-err-39': [['s9ne', 1, 5, 1], value(0)], 'w-err-str': [['s9ne', 1, 56, 1], value(0)],
             'beep-prog-str': [['s9ne', 1, 13, 1]]}
    for aid, rows in fixed.items():
        assert prediction(by_id[aid])['result']['rows'] == [['s9nb', 1, 1]]+rows+[['s9nz', 1, 1]]
    assert prediction(by_id['w-q-same'])['result']['rows'][0] == ['s9nb', 1, 1]
    assert prediction(by_id['w-q-err'])['result']['rows'][0] == ['s9nq', 1, 5]
    assert prediction(by_id['w-q-err'])['result']['errors'] == [[5, True, False]]
    assert prediction(by_id['beep-plain'])['port'] == dict(rise=[0, 0, 0, 0, 0, 1, 0, 0], fall=[0, 0, 0, 0, 0, 1, 0, 0])
    assert prediction(by_id['beep-1-only'])['port'] == dict(rise=[0, 0, 0, 0, 0, 1, 0, 0], fall=[0]*8)
    assert prediction(by_id['beep-0'])['port'] == dict(rise=[0]*8, fall=[0]*8)
    for aid in ('beep-2', 'beep-neg', 'beep-256', 'w-q-noarg', 'w-frac-404', 'w8025-scroll', 'w4025-loc-x40'):
        assert prediction(by_id[aid]) is None
    # WIDTH の戻し忘れの静的検査: 印を出す時点で画面は 80,25 でなければならない。
    for a in known:
        plan = program(a)
        assert final_width_state(a) == (80, 25), a['id']
        if a['kind'] == 'wprog':
            fd = frame_dict(a)
            assert fd[790].startswith('width 80,25:print "s9nb"') and fd[800].startswith('width 80,25:print "s9nb"')
            assert 's9nb' not in ''.join(s for n, s in fd.items() if n not in (790, 800))
            assert all(len(f'{n} {s}') < 80 for n, s in fd.items())
        elif a['kind'] == 'direct':
            assert plan.index(B) > max([i for i, s in enumerate(plan) if isinstance(s, str) and 'width' in s] or [-1])
    # 検査の検出力: 戻し忘れた腕を作ると静的検査が落ちる。
    broken = dict(by_id['w-d-roundtrip-40'], pre=['width 40,20'])
    assert final_width_state(broken) == (40, 20)
    assert final_width_state(dict(by_id['w-q-err'], pre=['width 39'])) == (80, 25)
    assert final_width_state(dict(by_id['w-q-err'], width_error=False, pre=['width 39'])) == (39, 25)
    assert final_width_state(dict(by_id['w-q-lprint'])) == (80, 25)
    assert final_width_state(dict(by_id['w-q-rows'], pre=['width ,20'])) == (80, 20)
    # 印の取り出し
    assert extract(screen_of([value(-1), value(17)]))[0] == stage([value(-1), value(17)])
    assert extract(b' '*3000)[0] == stage()
    assert extract(screen_of([['s9nv', 1]]))[0]['rows'] == [['invalid']]
    assert extract(screen_of([['s9nq', 1, 5]]))[0]['rows'] == [['s9nq', 1, 5]]
    assert extract(screen_of([value(17)]).replace(b's9nv', b'z9kv', 1))[0]['rows'] == []
    assert extract(screen_of([value(17)]).replace(b' 17', b' xx', 1))[0]['rows'] == [['invalid']]
    for exact in (True, False):
        assert extract(screen_of([], 5, exact))[0]['errors'] == [[5, True, exact]]
    try:
        extract(b' ')
        raise AssertionError('短い写しを受理')
    except ValueError:
        pass
    # 採取の検査: q 印は q を出す腕でだけ許す。順序（q が B の前）。
    qa = by_id['w-q-err']
    good = prediction(qa)
    assert valid(good, qa)
    noq = copy.deepcopy(good); noq['result']['rows'].pop(0)
    assert valid(noq, qa)
    assert not valid(good, by_id['cmp-num-eq-t'])
    late = copy.deepcopy(good); late['result']['rows'] = [late['result']['rows'][1], late['result']['rows'][0]]+late['result']['rows'][2:]
    assert not valid(late, qa)
    # ポート集計の陽性・陰性: 窓の手前の変化・他ポート・サブCPU・読み出しは数えない。
    events = [(1, 'main', 'OUT', 0x40, 0x00), (5, 'main', 'OUT', 0x40, 0x20),      # 窓の手前で立ち上がり
              (650, 'main', 'OUT', 0x40, 0x00),                                       # 窓の中の立ち下がり
              (700, 'main', 'OUT', 0x41, 0x20), (710, 'sub', 'OUT', 0x40, 0x20),      # 他ポート・サブ
              (720, 'main', 'IN', 0x40, 0x20),                                        # IN
              (800, 'main', 'OUT', 0x40, 0x20)]                                       # 窓の中の立ち上がり
    got = port_summary(synthetic_iolog(100, events), 700)
    assert got == dict(rise=[0, 0, 0, 0, 0, 1, 0, 0], fall=[0, 0, 0, 0, 0, 1, 0, 0], outs=2, prior=1), got
    assert port_summary(synthetic_iolog(100, events[:2]), 700) == dict(rise=[0]*8, fall=[0]*8, outs=0, prior=1)
    assert port_summary('', 1) == dict(rise=[0]*8, fall=[0]*8, outs=0, prior=0)
    assert port_summary(synthetic_iolog(100, [(500, 'main', 'OUT', 0x40, 0x21)]), 700)['outs'] == 0
    # 最初の書き込みは比較相手が無い（窓の手前に書き込みが無い）ので変化に数えない。
    one = port_summary(synthetic_iolog(100, [(650, 'main', 'OUT', 0x40, 0x20)]), 700)
    assert one['rise'] == [0]*8 and one['prior'] == 0 and one['outs'] == 1
    # 追補1: 窓の手前に書き込みがあれば、窓の最初の書き込みの立ち上がりが数えられる。
    first = port_summary(synthetic_iolog(0, [(5, 'main', 'OUT', 0x40, 0x00), (800, 'main', 'OUT', 0x40, 0x20)]), 700)
    assert first['rise'] == [0, 0, 0, 0, 0, 1, 0, 0] and first['fall'] == [0]*8 and first['prior'] == 1
    assert dump_path(Path('x.bin'), 123, True).name == 'x.f000123.bin'
    assert dump_path(Path('x.bin'), 123, False).name == 'x.bin'
    with tempfile.TemporaryDirectory(prefix='l4s9n-selftest-', dir=work) as temp:
        root = Path(temp)
        probe = by_id['control-values']; planned = prediction(probe)
        pprobe = by_id['beep-plain']; pplanned = prediction(pprobe)

        def frontend(argv, **kwargs):
            times, typed, dumps, iolog, io_from = [], [], [], None, None
            for i, arg in enumerate(argv):
                if arg == '--type-at': times.append(int(argv[i+1]))
                if arg == '--type': typed.append(argv[i+1])
                if arg == '--vram-dump': dumps.append((Path(argv[i+1]), int(argv[i+3])))
                if arg == '--io-log': iolog = Path(argv[i+1])
                if arg == '--io-log-from-frame': io_from = int(argv[i+1])
            assert times == sorted(set(times)) and typed[0] == '\n'
            plan = pprobe if iolog else probe
            assert typed[1:] == [x+'\n' for x in program(plan) if isinstance(x, str)]
            assert len(dumps) == 3 and int(argv[-1]) > dumps[-1][1]
            planned_now = pplanned if iolog else planned
            for name, (path, frame) in zip(('prepare', 'operation', 'result'), dumps):
                dump_path(path, frame, True).write_bytes(screen_of(planned_now[name]['rows']))
            if iolog:
                # 窓は最初の本体行を打つフレーム = io_from + PORT_LEAD
                assert io_from == PORT_FROM
                w = times[typed.index(plan['pre'][0]+'\n')]
                iolog.write_text(synthetic_iolog(0, [(5, 'main', 'OUT', 0x40, 0x00),
                                                      (w+50, 'main', 'OUT', 0x40, 0x20),
                                                      (w+300, 'main', 'OUT', 0x40, 0x00)]), encoding='utf-8')
            return subprocess.CompletedProcess(argv, 0, b'unknown-screen-body', b'unknown-screen-body')
        captured = io.StringIO()
        with patch.object(kw, 'find_core', return_value=Path('synthetic-core')), \
             patch.object(subprocess, 'run', side_effect=frontend), \
             contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            got, _ = run_arm('synthetic-rom', True, probe, root)
            pgot, _ = run_arm('synthetic-rom', True, pprobe, root)
        assert got == planned and captured.getvalue() == '' and not list(root.glob('*.bin'))
        assert comparable(pgot, pprobe) == comparable(pplanned, pprobe) and valid(pgot, pprobe)
        assert not (root/'port.txt').exists()
        with patch.object(kw, 'find_core', return_value=Path('synthetic-core')), \
             patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess(
                 [], 1, b'unknown-screen-body', b'unknown-screen-body')):
            try:
                run_arm('synthetic-rom', False, probe, root)
                raise AssertionError('実行失敗を受理')
            except RuntimeError as e:
                assert 'unknown-screen-body' not in str(e)
        selected = [a for a in known if prediction(a) is not None]
        counts = {name: 0 for name in ('prepare', 'operation', 'result')}

        def fake(rom, official, a, wd):
            p = copy.deepcopy(prediction(a))
            if 'port' in p:
                p['port'] = dict(rise=[n*2 for n in p['port']['rise']], fall=p['port']['fall'], outs=3)
            return p, counts
        with patch(__name__+'.run_arm', side_effect=fake):
            records = measure('', False, selected, root)
        expected = root/'expected.tsv'; measured = root/'measured.tsv'; out = root/'rejudged.tsv'

        def freeze(chosen):
            write(expected, ['arm', 'prediction'], [(a['id'], json.dumps(prediction(a))) for a in chosen])
        freeze(selected)
        assert emit(measured, records) and check(expected, measured)
        with measured.open() as stream:
            skip_rows = list(csv.DictReader(stream, delimiter='\t'))
        skip_rows[-1]['G_GW'] = 'SKIP'
        write(measured, list(skip_rows[0]), [list(r.values()) for r in skip_rows])
        assert not check(expected, measured)
        # exact と回数は期待値比較にも2走の関門にも使わない。
        changed = copy.deepcopy(records)
        for r in changed:
            for k, v in r['obs'][1].items():
                if k == 'port':
                    v['rise'] = [n+3 if n else 0 for n in v['rise']]; v['outs'] += 1
                else:
                    for e in v['errors']: e[2] = not e[2]
        assert emit(measured, changed) and check(expected, measured)
        assert rejudge(measured, out) and check(expected, out)
        with measured.open() as stream:
            saved = list(csv.DictReader(stream, delimiter='\t'))
        for r in saved: r['gate'] = r['G_GW'] = 'gate_failed'
        write(measured, list(saved[0]), [list(r.values()) for r in saved])
        assert rejudge(measured, out) and check(expected, out)
        # 値違いは採取形の関門を通って differ に届く。
        bad = copy.deepcopy(records)
        target = next(r for r in bad if r['arm']['id'] == 'cmp-num-eq-t')
        for o in target['obs']: o['result']['rows'][1][2] = 99
        assert valid(target['obs'][0], target['arm']) and emit(measured, bad)
        assert not check(expected, measured)
        with measured.open() as stream:
            assert all(r['gate'] == 'pass' and r['G_GW'] == 'differ'
                       for r in csv.DictReader(stream, delimiter='\t') if r['arm'] == 'cmp-num-eq-t')
        # ポートの食い違い（立ち下がりが出ない・別ビットが動く）も differ に届く。
        for mutate in ('no-fall', 'other-bit'):
            bad = copy.deepcopy(records)
            target = next(r for r in bad if r['arm']['id'] == 'beep-plain')
            for o in target['obs']:
                if mutate == 'no-fall': o['port']['fall'] = [0]*8
                else: o['port']['rise'][3] = 1
            assert valid(target['obs'][0], target['arm']) and emit(measured, bad)
            assert not check(expected, measured)
            with measured.open() as stream:
                assert all(r['gate'] == 'pass' and r['G_GW'] == 'differ'
                           for r in csv.DictReader(stream, delimiter='\t') if r['arm'] == 'beep-plain')
        # 誤り番号違い・q 印の有無違いも比較に届く。
        for aid, mutate in (('w-err-39', 'err'), ('w-q-err', 'q')):
            bad = copy.deepcopy(records)
            target = next(r for r in bad if r['arm']['id'] == aid)
            for o in target['obs']:
                if mutate == 'err': o['result']['rows'][1][2] = 6
                else: o['result']['rows'].pop(0)
            assert valid(target['obs'][0], target['arm']) and emit(measured, bad)
            assert not check(expected, measured)
        bad = copy.deepcopy(records)
        target = next(r for r in bad if r['arm']['id'] == 'cmp-num-eq-f')
        for o in target['obs']: o['result']['rows'].pop()
        assert not valid(target['obs'][0], target['arm'])
        assert not emit(measured, bad)
        # ポート腕でポートの観測が欠けた記録・ポートの無い腕に付いた記録は不正。
        for mutate in ('missing', 'extra'):
            bad = copy.deepcopy(records)
            if mutate == 'missing':
                target = next(r for r in bad if r['arm']['id'] == 'beep-plain')
                for o in target['obs']: o.pop('port')
            else:
                target = next(r for r in bad if r['arm']['id'] == 'cmp-num-eq-t')
                for o in target['obs']: o['port'] = dict(rise=[0]*8, fall=[0]*8, outs=0)
            assert not valid(target['obs'][0], target['arm']) and not emit(measured, bad)
        for mutation in ('repeat', 'capture', 'control', 'end', 'duplicate-mark'):
            bad = copy.deepcopy(records)
            if mutation == 'repeat': bad[-1]['obs'][1]['result']['rows'][1][2] = 99
            elif mutation == 'capture': bad[-1]['failed'][1] = True
            elif mutation == 'control':
                for o in bad[0]['obs']: o['result']['rows'][1][2] = 99
            elif mutation == 'end':
                for o in bad[-1]['obs']: o['result']['rows'].pop()
            else:
                for o in bad[-1]['obs']: o['result']['rows'].insert(0, ['s9nb', 1, 1])
            assert not emit(measured, bad) and not check(expected, measured)
        assert not emit(measured, records[1:]) and not emit(root/'empty.tsv', [])
        for mutation in ('missing', 'duplicate', 'unknown', 'flag', 'typing', 'counts'):
            rows = copy.deepcopy(saved)
            if mutation == 'missing': rows.pop()
            elif mutation == 'duplicate': rows.append(copy.deepcopy(rows[0]))
            elif mutation == 'unknown': rows[0]['arm'] = 'unknown'
            elif mutation == 'flag': rows[0]['typing_or_capture_failed'] = '2'
            elif mutation == 'counts':
                rows[0]['other_line_counts'] = '{}'
                write(measured, list(rows[0]), [list(r.values()) for r in rows])
                assert not rejudge(measured, out)
                continue
            else: rows[0]['typed_lines'] = '[]'
            write(measured, list(rows[0]), [list(r.values()) for r in rows])
            try:
                rejudge(measured, out)
                raise AssertionError('保存TSVの破損を受理')
            except ValueError:
                pass
        # merge
        assert emit(measured, records)
        with measured.open() as stream:
            rows0 = list(csv.DictReader(stream, delimiter='\t'))
        extra = [dict(r, arm='retired-arm') for r in rows0[:2]]
        new = [dict(r, arm='new-arm') for r in rows0[:2]]
        write(root/'base.tsv', list(rows0[0]), [list(r.values()) for r in rows0+extra])
        write(root/'patch.tsv', list(rows0[0]), [list(r.values()) for r in new+rows0[2:4]])
        assert merge(root/'base.tsv', root/'patch.tsv', {'retired-arm'}, root/'merged.tsv') == (len(rows0), 2)
        merged_arms = {r['arm'] for r in csv.DictReader((root/'merged.tsv').open(), delimiter='\t')}
        assert 'retired-arm' not in merged_arms and 'new-arm' in merged_arms
        try:
            merge(root/'base.tsv', root/'base.tsv', set(), root/'merged.tsv')
            raise AssertionError('同一入力を受理')
        except ValueError:
            pass
        unknown = by_id['w8025-scroll']
        obs = prediction(by_id['cmp-num-eq-t'])
        unknown_record = dict(arm=unknown, obs=[obs, copy.deepcopy(obs)], others=[counts, counts],
                              failed=[False, False], gate=True)
        # 予測なし腕は関門にも合格できる形の観測を持つ必要があるので、b/z だけの観測を与える。
        plain = dict(prepare=stage([['s9np', 1, 1]]), operation=stage([['s9no', 1, 1]]),
                     result=stage([['s9nb', 1, 1], value(3), ['s9nz', 1, 1]]))
        unknown_record['obs'] = [plain, copy.deepcopy(plain)]
        assert emit(measured, records+[unknown_record])
        freeze(selected)
        assert not check(expected, measured)
        assert check(expected, measured, predicted_only=True)
        assert rejudge(measured, out) and check(expected, out, predicted_only=True)
        with measured.open() as stream:
            subset_rows = list(csv.DictReader(stream, delimiter='\t'))
        missing = [r for r in subset_rows if r['arm'] != 'cmp-num-eq-t']
        write(out, list(missing[0]), [list(r.values()) for r in missing])
        assert not check(expected, out, predicted_only=True)
        freeze(selected+[unknown])
        assert check(expected, measured, predicted_only=True)
        assert not check(expected, measured)
        write(expected, ['arm', 'observation'],
              [(a['id'], json.dumps(plain if a['id'] == unknown['id'] else prediction(a))) for a in selected+[unknown]])
        assert not check(expected, measured)
        assert not check(expected, measured, predicted_only=True)
        with measured.open() as stream:
            assert all(r['G_GW'] == 'unpredicted' for r in csv.DictReader(stream, delimiter='\t') if r['arm'] == unknown['id'])
        print('OK 固定予測・戻し忘れの静的検査・取り出し陽性陰性・ポート集計の陽性陰性・本文非出力・exact除外・2走・破損拒否・予測なし拒否', flush=True)
        rom = root/'rom'
        built = subprocess.run([os.sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom),
                                '--work-dir', str(root/'asm')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert built.returncode == 0, '自作ROM一時ビルド失敗'
        own = controls()
        observed = measure(rom, False, own, root)
        bad_ids = [r['arm']['id'] for r in observed if not r['gate'] or comparable(r['obs'][0]) != comparable(prediction(r['arm']))]
        if bad_ids:
            print('NG 自作ROMの既知値対照: '+','.join(bad_ids))
            for r in observed:
                if r['arm']['id'] in bad_ids:
                    print(json.dumps(dict(arm=r['arm']['id'], observation=r['obs'], failed=r['failed'])))
        assert not bad_ids
        freeze(own)
        assert emit(measured, observed) and check(expected, measured)
        assert check(expected, measured, predicted_only=True)
        wrong = prediction(own[0]); wrong['result']['rows'][1][2] = 999
        write(expected, ['arm', 'prediction'], [(a['id'], json.dumps(wrong if i == 0 else prediction(a))) for i, a in enumerate(own)])
        assert not check(expected, measured)
        print(f'OK 自作ROM一時ビルド・既知値対照{len(own)}腕×2走（ポート採取の無音対照を含む）・期待値改変拒否')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('predict'); p.add_argument('--out', type=Path, required=True)
    m = sub.add_parser('measure'); m.add_argument('--rom-dir')
    m.add_argument('--official', action='store_true'); m.add_argument('--out', type=Path, required=True)
    m.add_argument('--work-dir', type=Path, default=WORK)
    m.add_argument('--only', help='追補: 指定した本体腕（コンマ区切り）と対照だけを測る')
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
        frames = traceback.extract_tb(error.__traceback__)
        print(f'NG 器具の検査または実行に失敗 ({type(error).__name__}, '
              f'行{frames[-1].lineno}、画面本文は非出力)')
        raise SystemExit(1)
