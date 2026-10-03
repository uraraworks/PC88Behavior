#!/usr/bin/env python3
"""l4-s8a の事前予測と PRINT 測定。公式画面の本文は保存しない。"""
import argparse
import csv
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time
from unittest.mock import patch

import l4_listkw_measure as kw
import l4_mbf_oracle_v2 as mbf
from l4_mbf_oracle_v11_away import encode_single_away, expected_binop_away

WORK = kw.REPO.parent / 'tmp/l4s8a-work'
MOD = 1 << 24
INITIAL = 0x4fc752
CANDIDATES = ('R_GW', 'R_GW_S')
# 追補2は棄却済み部分モデルの登録を保持。追補3に探索候補を追加する。
ADD2_CANDIDATES = ('R_P',)
ADD3_CANDIDATES = ('R_A', 'R_B', 'R_P')
ADD4_CANDIDATES = ('R_C', 'R_D', 'R_A', 'R_B')
RP_MULTIPLIERS = (-26514538, 16129081, -11769122, 13098250,
                  -10080595, -10426890, -13483109, 12482518)
RA_MULTIPLIERS = (*RP_MULTIPLIERS[:4], -20161190, *RP_MULTIPLIERS[5:])


def rp_scramble(number):
    packed = (number.mant & 0x7fffff) | (number.sign << 23)
    swapped = int.from_bytes((packed ^ 0x4f).to_bytes(3, 'little'), 'big')
    return encode_single_away(Fraction((swapped << 8) | number.exp, 1 << 32))


def rp_literal(expr):
    # 十進入力は未確定。測定時の負種は標本0のMBFを条件にして予測する。
    number = mbf.parse_literal(expr, fin_algo='gw', dfin_algo='drep10a')
    return encode_single_away(number.exact())


class RPState:
    """丸め済みMBF単精度＋8周期の位置。171個目の不一致を補修しない。"""
    def __init__(self):
        self.reset()

    def reset(self):
        self.number = encode_single_away(Fraction(0xcfc752, MOD))
        self.index = 1

    def rnd(self, arg=1):
        if arg < 0:
            seed = encode_single_away(abs(Fraction(arg)))
            seed.sign = 1
            self.number = rp_scramble(seed)
            self.index = 0
        elif arg:
            multiplier = encode_single_away(Fraction(RP_MULTIPLIERS[self.index]))
            product = expected_binop_away('*', self.number, multiplier)
            self.number = rp_scramble(product)
            self.index = (self.index + 1) % 8
        return self.number.exact()

    def randomize(self, arg):
        n = math.floor(abs(Fraction(arg)) + Fraction(1, 2)) * (-1 if arg < 0 else 1)
        packed = ((n & 65535) << 8) | (self.number.mant & 255)
        self.number = mbf.GwNum('single', sign=packed >> 23,
            exp=self.number.exp, mant=(packed & 0x7fffff) | 0x800000)
        self.rnd(1)


class RAState(RPState):
    """追補2からの候補。正更新171回ごとの加算とA_4の指数を修正。"""
    def reset(self):
        super().reset()
        self.count = 0

    def rnd(self, arg=1):
        if arg < 0:
            self.count = 0
            return super().rnd(arg)
        if arg:
            self.count = (self.count + 1) % 171
            multiplier = encode_single_away(Fraction(RA_MULTIPLIERS[self.index]))
            product = expected_binop_away('*', self.number, multiplier)
            self.number = self.transform(product)
            self.index = (self.index + 1) % 8
        return self.number.exact()

    def transform(self, product):
        if self.count == 0:
            # 正規化後の整数仮数に加算してから再正規化する。
            product = encode_single_away(Fraction((-1)**product.sign) *
                (product.mant + self.correction(product)) * Fraction(2)**(product.exp - 152))
        return rp_scramble(product)

    def correction(self, product):
        return 0x00feff


class RCState(RAState):
    """追補3後の暫定候補。位相はR_A、境界の低バイト零だけ追加32。

    この分岐の一般化は未確認。補正と積の丸めのどちらの差かも未分離。
    """
    def correction(self, product):
        return 0x00ff1f if product.mant & 255 == 0 else 0x00feff


class RBState(RAState):
    """未分離の対案: RANDOMIZEで171周期の位相を初期化。"""
    def randomize(self, arg):
        self.count = 0
        super().randomize(arg)


class RDState(RAState):
    """追補3後の事後候補。T内のバイト反転後に整数0x00ff01を加算。

    24ビット溢れは未確定。器具は暫定的にmod 2^24を使う。
    """
    def transform(self, product):
        packed = (product.mant & 0x7fffff) | (product.sign << 23)
        r = int.from_bytes((packed ^ 0x4f).to_bytes(3, 'little'), 'big')
        if self.count == 0:
            r = (r + 0x00ff01) & 0xffffff
        return encode_single_away(Fraction((r << 8) | product.exp, 1 << 32))


def rp_prediction(arm, candidate='R_P', seed_row=None):
    if candidate not in set(ADD3_CANDIDATES + ADD4_CANDIDATES):
        raise ValueError('候補が不正')
    if 'expected' in arm:
        return list(arm['expected'])
    state, rows, seed = {'R_A': RAState, 'R_B': RBState, 'R_C': RCState, 'R_D': RDState, 'R_P': RPState}[candidate](), [], None
    for op, arg, j in arm['rp_ops']:
        if op == 'reset':
            state.reset()
        elif op == 'input':
            seed = (encode_single_away(Fraction(decode(seed_row))) if seed_row is not None
                    else rp_literal(arg))
            rows.append(encode(seed.exact(), j))
        elif op == 'negative':
            rows.append(encode(state.rnd(-seed.exact()), j))
        elif op == 'randomize':
            state.randomize(arg)
        elif op == 'skip':
            for _ in range(arg):
                state.rnd(1)
        elif op == 'rnd':
            rows.append(encode(state.rnd(arg), j))
        else:
            raise ValueError('追補2の操作が不正')
    return rows
# 符号・指数・上位12ビット・下位12ビット。復元値は s*(h*4096+l)/2^24*2^e。
ENCODER = [
    '900 s=sgn(x):a=abs(x):e=0',
    '910 if a=0 then goto 950',
    '920 if a>=1 then a=a/2:e=e+1:goto 920',
    '930 if a<0.5 then a=a*2:e=e-1:goto 930',
    '950 a=a*4096',
    '960 print "s8";j;s;e;int(a);int((a-int(a))*4096)',
    '970 return',
]


def step(state):
    return (state * 214013 + 2531011) % MOD


def single(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def encode(x, j):
    if x == 0:
        return (j, 0, 0, 0, 0)
    m, e = math.frexp(abs(x))
    bits = int(m * MOD)
    assert bits / MOD == m
    return (j, 1 if x > 0 else -1, e, bits // 4096, bits % 4096)


def decode(row):
    _, sign, e, hi, lo = row
    return sign * math.ldexp((hi * 4096 + lo) / MOD, e)


def negative_seed(x):
    # GW の単精度 FACLO と FAC-1。指数は使わず、格納された符号ビットを残す。
    m, _ = math.frexp(abs(single(x)))
    return (int(m * MOD) & 0x7fffff) | 0x800000


def loop(expr, n):
    return f'for j=1 to {n}:x={expr}:gosub 900:next'


def arms():
    result = []
    def add(aid, lines, ops, counts, wait=0):
        result.append(dict(id=aid, lines=lines, ops=ops, counts=counts, wait=wait))
    for wait in (0, 137):
        add(f'start-{wait}', [loop('rnd(1)', 20)], [('rnd', 1)] * 20, [20], wait)
    add('zero-first', ['j=1:x=rnd(0):gosub 900'], [('rnd', 0)], [1])
    add('zero-after', ['j=1:x=rnd(1):gosub 900',
                      'for j=2 to 3:x=rnd(0):gosub 900:next'],
        [('rnd', 1), ('rnd', 0), ('rnd', 0)], [3])
    for name, arg in [('bare', None), ('two', 2), ('half', .5), ('large', 1e10)]:
        expr = 'rnd' if arg is None else f'rnd({arg:g})'
        add('arg-' + name, [loop(expr, 5)], [('rnd', 1 if arg is None else arg)] * 5, [5])
    for arg in (-1, -2, -1.5, -1e10):
        add(f'negative-{arg:g}', [f'j=1:x=rnd({arg:g}):gosub 900',
                                'for j=2 to 6:x=rnd(1):gosub 900:next'],
            [('rnd', arg)] + [('rnd', 1)] * 5, [6])
    add('negative-twice', ['for j=1 to 2:x=rnd(-1):gosub 900:next',
                          'for j=3 to 7:x=rnd(1):gosub 900:next'],
        [('rnd', -1)] * 2 + [('rnd', 1)] * 5, [7])
    for n in (0, 1, 2, 100, -1, 32767, 1.5):
        add(f'randomize-{n:g}', [f'randomize {n:g}', loop('rnd(1)', 5)],
            [('randomize', n)] + [('rnd', 1)] * 5, [5])
    add('rerun', ['10 for j=1 to 5:x=rnd(1):gosub 900:next',
                  'cls', 'run', 'cls', 'run', 'new', *ENCODER,
                  '10 for j=1 to 5:x=rnd(1):gosub 900:next', 'cls', 'run'],
        ([('reset', 0)] + [('rnd', 1)] * 5) * 3, [5, 5, 5])
    add('range', ['800 if x<mn then mn=x', '810 if x>mx then mx=x',
                  '820 if x=0 then z=z+1', '830 if x=1 then o=o+1',
                  '840 if x<0 then b=b+1', '850 if x>=1 then b=b+1',
                  '860 return', 'z=0:o=0:b=0:x=rnd(1):mn=x:mx=x:gosub 800',
                  'for j=2 to 2000:x=rnd(1):gosub 800:next',
                  'j=1:x=mn:gosub 900:j=2:x=mx:gosub 900',
                  'print "s8c";z;o;b'], [('range', 2000)], [3])
    return result


def controls(direct=False):
    return [dict(id='constant-' + name,
                 lines=([f'j=1:x={expr}:gosub 900'] if direct else
                        [f'10 j=1:x={expr}:gosub 900', '20 end', 'cls', 'run']), ops=[], counts=[1], wait=0,
                 expected=[encode(value, 1)])
            for name, expr, value in [('zero', '0', 0), ('threequarters', '.75', .75),
                ('third', '1/3', single(1/3)), ('negative', '-.75', -.75),
                ('one', '1', 1), ('large', '2', 2), ('tiny', '1/16777216', 2**-24)]]


def prediction(arm, candidate, observed=None, initial=None):
    if 'expected' in arm:
        return arm['expected']
    state = INITIAL if initial is None else initial
    rows = []
    anchored = candidate == 'R_GW' or initial is not None
    for op, arg in arm['ops']:
        if op == 'reset':
            state = INITIAL if initial is None else initial
            anchored = candidate == 'R_GW' or initial is not None
        elif op == 'randomize':
            n = math.floor(abs(arg) + .5) * (-1 if arg < 0 else 1)
            state = step((state & 255) | ((n & 65535) << 8))
        elif op == 'range':
            if not anchored:
                return None
            values = []
            for _ in range(arg):
                state = step(state)
                values.append(state / MOD)
            rows.extend([encode(min(values), 1), encode(max(values), 2),
                         (values.count(0), values.count(1),
                          sum(x < 0 or x >= 1 for x in values))])
        elif op == 'rnd':
            if arg < 0:
                state = negative_seed(arg)
                anchored = True
            if arg != 0:
                state = step(state)
            j = len(rows) % 5 + 1 if arm['id'] == 'rerun' else len(rows) + 1
            if not anchored:
                if observed is None or len(rows) >= len(observed):
                    return None
                value = decode(observed[len(rows)])
                scaled = value * MOD
                if not 0 <= scaled < MOD or scaled != int(scaled):
                    return None
                state = int(scaled)
                anchored = True
            rows.append(encode(state / MOD, j))
    return rows


# 固有の PRINT 印＋整数だけを受理。正数の先頭空白・負数の '-' を必須にする。
NUMBER = r'(?: +\d+| *-\d+)'
PATTERNS = [(re.compile(r'^s8' + ('(' + NUMBER + ')') * 5 + r' *$', re.IGNORECASE), 5),
            (re.compile(r'^s8c' + ('(' + NUMBER + ')') * 3 + r' *$', re.IGNORECASE), 3)]


def extract(data):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    rows, other = [], 0
    for r in range(25):
        raw = data[r*120:r*120+80]
        if all(b == 32 for b in raw):
            continue
        text = raw.decode('ascii', errors='replace').rstrip(' ')
        found = None
        for pattern, _ in PATTERNS:
            match = pattern.fullmatch(text)
            if match:
                found = tuple(int(x) for x in match.groups())
                break
        if found is None:
            other += 1
        else:
            rows.append(found)
    return rows, other


def valid(rows, counts):
    if len(rows) != sum(counts):
        return False
    offset = 0
    for count in counts:
        part = rows[offset:offset+count]
        for j, row in enumerate(part, 1):
            if len(row) == 3:
                if j != count or any(x < 0 or x > 2000 for x in row):
                    return False
                continue
            k, sign, e, hi, lo = row
            if k != j or sign not in (-1, 0, 1) or not -128 <= e <= 128:
                return False
            if not 0 <= lo < 4096 or not 0 <= hi < 4096:
                return False
            if sign == 0 and (e, hi, lo) != (0, 0, 0):
                return False
            if sign and hi < 2048:
                return False
        offset += count
    return True


def run_arm(rom, official, arm, work):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    snapshots = []
    lines = [*ENCODER, 'cls', *arm['lines']]
    for i, line in enumerate(lines):
        if i == len(ENCODER) + 1:
            at += arm['wait']
        args += ['--type-at', str(at), '--type', line + '\n']
        at += (len(line) + 1) * 8 + 240
        if 'to 2000' in line:
            at += 250000
        else:
            at += 3000 if (('gosub 900' in line and not line[0].isdigit()) or line == 'run') else 0
        if arm['id'] == 'rerun' and line == 'run':
            snapshots.append(at - 50)
    if arm['id'] != 'rerun':
        snapshots.append(at + 200)
    for frame in snapshots:
        args += ['--vram-dump', str(work / 'screen.bin'), '--vram-dump-at', str(frame)]
    args += ['--frames', str(max(at, snapshots[-1]) + 100)]
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=dict(os.environ, M6FH_LONG_TYPING='1'))
    if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
        raise RuntimeError('測定器の実行または打鍵に失敗')
    rows, others = [], []
    for frame in snapshots:
        path = work / ('screen.bin' if len(snapshots) == 1 else f'screen.f{frame:06d}.bin')
        part, other = extract(path.read_bytes())
        rows.extend(part)
        others.append(other)
        path.unlink()  # 画面本文を作業ログに残さない。
    return rows, others


def measure(rom, official, selected, work):
    records = []
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as temp:
        for arm in selected:
            obs, others, errors = [], [], []
            for repeat in range(2):
                try:
                    rows, counts = run_arm(rom, official, arm, Path(temp))
                    obs.append(rows)
                    others.append(counts)
                    errors.append(False)
                except Exception:
                    obs.append([])
                    others.append([])
                    errors.append(True)
            gate = (not any(errors) and obs[0] == obs[1] and valid(obs[0], arm['counts'])
                    and all(len(row) == (3 if arm['id'] == 'range' and i == 2 else 5)
                            for i, row in enumerate(obs[0])))
            statuses = {}
            for candidate in CANDIDATES:
                pred = prediction(arm, candidate, obs[0])
                statuses[candidate] = ('gate_failed' if not gate else 'undetermined'
                    if pred is None or (candidate == 'R_GW_S' and arm['id'] == 'zero-first') else 'agree' if obs[0] == pred else 'differ')
            records.append(dict(arm=arm, obs=obs, others=others, gate=gate, statuses=statuses,
                                predictions={c: prediction(arm, c, obs[0]) for c in CANDIDATES}))
    by_id = {r['arm']['id']: r for r in records}
    first = by_id.get('start-0')
    recovered = False
    if first and first['gate']:
        scaled = decode(first['obs'][0][0]) * MOD
        if scaled == int(scaled) and 0 <= scaled < MOD:
            recovered = True
            initial = ((int(scaled) - 2531011) * pow(214013, -1, MOD)) % MOD
            for r in records:
                pred = prediction(r['arm'], 'R_GW_S', initial=initial)
                r['predictions']['R_GW_S'] = pred
                r['statuses']['R_GW_S'] = ('gate_failed' if not r['gate'] else
                    'agree' if r['obs'][0] == pred else 'differ')
    if not recovered:
        for r in records:
            fixed = prediction(r['arm'], 'R_GW_S')
            if fixed is None:
                r['predictions']['R_GW_S'] = None
                r['statuses']['R_GW_S'] = ('gate_failed' if not r['gate'] else
                    'differ' if first and first['gate'] else 'undetermined')
    starts = [by_id.get('start-0'), by_id.get('start-137')]
    if all(r and r['gate'] for r in starts) and starts[0]['obs'][0] != starts[1]['obs'][0]:
        for r in starts:
            r['statuses'] = {c: 'differ' for c in CANDIDATES}
    rerun = by_id.get('rerun')
    if rerun and rerun['gate']:
        rows = rerun['obs'][0]
        if rows[:5] != rows[5:10] or rows[:5] != rows[10:]:
            rerun['statuses'] = {c: 'differ' for c in CANDIDATES}
    return records


def write_tsv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, delimiter='\t')
        writer.writerow(header)
        writer.writerows(rows)


def paged_arm(aid, pages):
    # ページごとに期待する番号を保持。RUN間の番号の再開は明示した場合だけ許す。
    return dict(id=aid, pages=pages)


def sequence_pages(expr, count, size=16, program=False):
    pages = []
    for first in range(1, count + 1, size):
        last = min(first + size - 1, count)
        body = f'for j={first} to {last}:x={expr}:gosub 900:next'
        if program:
            # 自作ROMの検査ではFOR/GOSUBを使わず、定数の各標本を明示する。
            lines = [f'{10*(i+1)} j={j}:x={expr}:gosub 900'
                     for i, j in enumerate(range(first, last + 1))]
            # 前ページの長いプログラムが残らないようNEW後に記録器も入れ直す。
            lines = ['new', *ENCODER, *lines, f'{10*(last-first+2)} end', 'cls', 'run']
        else:
            lines = ['cls', body]
        pages.append(dict(lines=lines, numbers=list(range(first, last + 1))))
    return pages


def add1_arms():
    result = [paged_arm('add1-start-400', sequence_pages('rnd(1)', 400))]
    seeds = [('1', '1'), ('1.5', '1.5'), ('1.25', '1.25'), ('1.125', '1.125'),
             ('1-ulp', '1+1/8388608'), ('1-plus-2^-16', '1+1/65536'),
             ('1-plus-2^-8', '1+1/256'), ('0.5', '.5'), ('4', '4'), ('3', '3'),
             ('1e-10', '1e-10'), ('65536', '65536')]
    for name, expr in seeds:
        result.append(paged_arm('add1-negative-' + name, [dict(
            lines=['cls', f'y={expr}:j=0:x=y:gosub 900',
                   'j=1:x=rnd(-y):gosub 900',
                   'for j=2 to 11:x=rnd(1):gosub 900:next'],
            numbers=list(range(12)))]))
    for n in (0, 1, 2, 3, 255, 256, 257, -1, -2, -32768, 32767):
        result.append(paged_arm(f'add1-randomize-{n}', [dict(
            lines=['cls', f'randomize {n}', 'j=0:x=rnd(0):gosub 900', loop('rnd(1)', 10)],
            numbers=list(range(11)))]))
    program = ['10 for j=1 to 5:x=rnd(1):gosub 900:next', '20 end']
    result.append(paged_arm('add1-rerun', [
        dict(lines=[*program, 'cls', 'run'], numbers=list(range(1, 6))),
        dict(lines=['cls', 'run'], numbers=list(range(1, 6))),
        dict(lines=['new', *ENCODER, *program, 'cls', 'run'], numbers=list(range(1, 6)))]))
    result.append(paged_arm('add1-start-0', sequence_pages('rnd(1)', 20, size=10)))
    return result


def add2_controls():
    result = []
    for control in controls(direct=True):
        arm = paged_arm('add2-' + control['id'], [dict(
            lines=['cls', *control['lines']], numbers=[1])])
        arm['expected'] = control['expected']
        result.append(arm)
    return result


def interval_pages(first, last):
    return [dict(lines=['cls', f'for j={lo} to {min(lo+15, last)}:x=rnd(1):gosub 900:next'],
                 numbers=list(range(lo, min(lo+15, last)+1)))
            for lo in range(first, last+1, 16)]


def add2_arms():
    result = []

    def add(aid, pages, ops):
        arm = paged_arm('add2-' + aid, pages)
        arm['rp_ops'] = ops
        result.append(arm)

    def negative(name, expr, skip=0):
        prefix = [f'for k=1 to {skip}:y=rnd(1):next'] if skip else []
        lines = ['cls',
                 'j=1:x=rnd(-y):gosub 900', 'j=2:x=rnd(0):gosub 900',
                 'for j=3 to 12:x=rnd(1):gosub 900:next']
        ops = ([('skip', skip, None)] if skip else []) + [
            ('input', expr, 0), ('negative', None, 1), ('rnd', 0, 2)] + [
            ('rnd', 1, j) for j in range(3, 13)]
        add(name, [dict(lines=[*prefix, 'cls', f'y={expr}:j=0:x=y:gosub 900'], numbers=[0]),
                   dict(lines=lines, numbers=list(range(1, 13)))], ops)

    for expr in ('7.25', '1e20', '.3', '12345.678'):
        negative('negative-' + expr, expr)
    for n in (12345, -12345, 4096, 99):
        add(f'randomize-{n}', [dict(lines=['cls', f'randomize {n}',
            'j=0:x=rnd(0):gosub 900', loop('rnd(1)', 10)], numbers=list(range(11)))],
            [('randomize', n, None), ('rnd', 0, 0)] + [('rnd', 1, j) for j in range(1, 11)])
    pages = interval_pages(401, 1000)
    pages[0]['lines'].insert(1, 'for k=1 to 400:y=rnd(1):next')
    add('start-401-1000', pages, [('skip', 400, None)] +
        [('rnd', 1, j) for j in range(401, 1001)])
    pages = [dict(lines=['cls', 'y=7.25:j=0:x=y:gosub 900'], numbers=[0]),
        dict(lines=['cls', 'j=1:x=rnd(-y):gosub 900',
                    'for j=2 to 12:x=rnd(1):gosub 900:next'], numbers=list(range(1, 13))),
        *interval_pages(13, 401)]
    add('negative-7.25-long', pages, [('input', '7.25', 0), ('negative', None, 1)] +
        [('rnd', 1, j) for j in range(2, 402)])
    program = ['10 for j=1 to 5:x=rnd(1):gosub 900:next', '20 end']
    add('randomize-12345-run', [dict(lines=['cls', 'randomize 12345',
        'j=0:x=rnd(0):gosub 900', loop('rnd(1)', 3)], numbers=list(range(4))),
        dict(lines=[*program, 'cls', 'run'], numbers=list(range(1, 6))),
        dict(lines=['cls', 'for j=6 to 10:x=rnd(1):gosub 900:next'], numbers=list(range(6, 11)))],
        [('randomize', 12345, None), ('rnd', 0, 0)] + [('rnd', 1, j) for j in range(1, 4)] +
        [('reset', 0, None)] + [('rnd', 1, j) for j in range(1, 11)])
    negative('history-137-negative-.3', '.3', 137)
    add('history-17-randomize-99', [dict(lines=['cls', 'for k=1 to 17:y=rnd(1):next',
        'randomize 99', 'j=0:x=rnd(0):gosub 900', loop('rnd(1)', 10)],
        numbers=list(range(11)))], [('skip', 17, None), ('randomize', 99, None), ('rnd', 0, 0)] +
        [('rnd', 1, j) for j in range(1, 11)])
    return result


def add3_controls():
    return [dict(arm, id=arm['id'].replace('add2-', 'add3-', 1)) for arm in add2_controls()]


def add3_arms():
    # 欠けた入力対照6腕を再採取。RND呼出しの順序・個数は追補2と同じ。
    result = [dict(arm, id=arm['id'].replace('add2-', 'add3-', 1))
              for arm in add2_arms() if 'negative-' in arm['id']]

    def add(name, pages, ops):
        result.append(dict(id='add3-' + name, pages=pages, rp_ops=ops))

    def negative(name, expr, last=12, skip=0, zero=True):
        prefix = [f'for k=1 to {skip}:y=rnd(1):next'] if skip else []
        pages = [dict(lines=[*prefix, 'cls', f'y={expr}:j=0:x=y:gosub 900'], numbers=[0])]
        ops = ([('skip', skip, None)] if skip else []) + [('input', expr, 0), ('negative', None, 1)]
        if zero:
            pages.append(dict(lines=['cls', 'j=1:x=rnd(-y):gosub 900',
                'j=2:x=rnd(0):gosub 900', 'for j=3 to 12:x=rnd(1):gosub 900:next'],
                numbers=list(range(1, 13))))
            ops += [('rnd', 0, 2)] + [('rnd', 1, j) for j in range(3, 13)]
        else:
            pages += [dict(lines=['cls', 'j=1:x=rnd(-y):gosub 900',
                'for j=2 to 12:x=rnd(1):gosub 900:next'], numbers=list(range(1, 13))),
                *interval_pages(13, last)]
            ops += [('rnd', 1, j) for j in range(2, last+1)]
        add(name, pages, ops)

    negative('negative-.625', '.625')
    negative('negative-2.75-long', '2.75', last=401, zero=False)
    for n in (2026, -2026):
        add(f'randomize-{n}', [dict(lines=['cls', f'randomize {n}',
            'j=0:x=rnd(0):gosub 900', loop('rnd(1)', 10)], numbers=list(range(11)))],
            [('randomize', n, None), ('rnd', 0, 0)] + [('rnd', 1, j) for j in range(1, 11)])
    pages = interval_pages(1001, 2000)
    pages[0]['lines'].insert(1, 'for k=1 to 1000:y=rnd(1):next')
    add('start-1001-2000', pages, [('skip', 1000, None)] + [('rnd', 1, j) for j in range(1001, 2001)])
    pages = [dict(lines=['for k=1 to 170:y=rnd(1):next', 'cls', 'randomize 2026',
        'j=0:x=rnd(0):gosub 900', loop('rnd(1)', 10)], numbers=list(range(11))),
        *interval_pages(11, 401)]
    add('history-170-randomize-2026-long', pages, [('skip', 170, None),
        ('randomize', 2026, None), ('rnd', 0, 0)] + [('rnd', 1, j) for j in range(1, 402)])
    negative('history-342-negative-.625-long', '.625', last=401, skip=342, zero=False)
    return result


def add4_controls():
    return [dict(arm, id=arm['id'].replace('add2-', 'add4-', 1)) for arm in add2_controls()]


def add4_arms():
    # 全腕未測定。正更新前歴と連続RANDOMIZEで位相保持を分離する。
    result = []
    for skip, seeds in [(k, (2026,)) for k in (0, 1, 85, 169, 171, 172, 341)] + [
            (0, (2026, 99)), (169, (2026, 99)), (170, (2026, 99)), (0, (92,)),
            (0, (25,)), (0, (37,)), (0, (46,))]:
        prefix = [f'for k=1 to {skip}:y=rnd(1):next'] if skip else []
        name = f'add4-history-{skip}-randomize-' + '-then-'.join(map(str, seeds)) + '-long'
        pages = [dict(lines=[*prefix, 'cls', *[f'randomize {n}' for n in seeds],
            'j=0:x=rnd(0):gosub 900', loop('rnd(1)', 10)], numbers=list(range(11))),
            *interval_pages(11, 401)]
        ops = ([('skip', skip, None)] if skip else []) + [
            ('randomize', n, None) for n in seeds] + [('rnd', 0, 0)] + [
            ('rnd', 1, j) for j in range(1, 402)]
        result.append(dict(id=name, pages=pages, rp_ops=ops))
    # 周期直前の負RNDがcを消すか。負RND自体を正更新として数えない。
    pages = [dict(lines=['for k=1 to 169:y=rnd(1):next', 'cls',
                        'y=.625:j=0:x=y:gosub 900'], numbers=[0]),
        dict(lines=['cls', 'j=1:x=rnd(-y):gosub 900',
                    'for j=2 to 12:x=rnd(1):gosub 900:next'], numbers=list(range(1, 13))),
        *interval_pages(13, 401)]
    ops = [('skip', 169, None), ('input', '.625', 0), ('negative', None, 1)] + [
        ('rnd', 1, j) for j in range(2, 402)]
    result.append(dict(id='add4-history-169-negative-.625-long', pages=pages, rp_ops=ops))
    return result


def page_valid(rows, numbers):
    # 値形式は既存の関門と共有し、番号はページの範囲と完全一致を要求する。
    if any(len(row) != 5 for row in rows) or [r[0] for r in rows] != numbers:
        return False
    return valid([(i, *row[1:]) for i, row in enumerate(rows, 1)], [len(numbers)])


def paged_valid(parts, arm):
    return (len(parts) == len(arm['pages']) and
            all(page_valid(rows, page['numbers']) for rows, page in zip(parts, arm['pages'])))


def paged_schedule(arm, official):
    at = 700 if official else 100
    events, snapshots = [], []
    for line in ENCODER:
        events.append((at, line))
        at += (len(line) + 1) * 8 + 240
    for page in arm['pages']:
        for line in page['lines']:
            assert line == line.lower(), '打鍵は小文字に限定'
            events.append((at, line))
            at += (len(line) + 1) * 8 + 240
            if line == 'run' or ('gosub 900' in line and not line[0].isdigit()):
                at += 3000
            skip = re.fullmatch(r'for k=1 to (\d+):y=rnd\(1\):next', line)
            if skip:
                at += 125 * int(skip[1])
        snapshots.append(at + 200)
        at += 400  # 次のCLS以前に確実に採取する。
    return events, snapshots, at + 100


def run_paged_arm(rom, official, arm, work):
    events, snapshots, frames = paged_schedule(arm, official)
    try:
        parts, others = [], []
        for first, last, stop in capture_batches(snapshots, frames):
            batch = snapshots[first:last]
            args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
            if official:
                args += ['--type-at', '300', '--type', '\n']
            # 上限16画面を越す場合は起動から同じ入力を再生。RNDの呼出列は連続。
            for frame, line in events:
                if frame < stop:
                    args += ['--type-at', str(frame), '--type', line + '\n']
            for frame in batch:
                args += ['--vram-dump', str(work / 'screen.bin'), '--vram-dump-at', str(frame)]
            args += ['--frames', str(stop)]
            proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=dict(os.environ, M6FH_LONG_TYPING='1'))
            if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
                raise RuntimeError('測定器の実行または打鍵に失敗')
            for i, frame in enumerate(batch, first):
                path = work / ('screen.bin' if len(batch) == 1 else f'screen.f{frame:06d}.bin')
                part, other = extract(path.read_bytes())
                path.unlink()
                if i < len(parts):
                    if part != parts[i]:
                        raise RuntimeError('再生した境界画面のPRINT値が不一致')
                else:
                    parts.append(part)
                    others.append(other)
        return parts, others
    finally:
        # 失敗時も画面本文を残さず、整数として抽出した自作PRINT値だけを返す。
        for path in work.glob('screen*.bin'):
            path.unlink()


def capture_batches(snapshots, frames):
    first = 0
    while first < len(snapshots):
        last = min(first + 16, len(snapshots))
        stop = frames if last == len(snapshots) else snapshots[last - 1] + 100
        yield first, last, stop
        if last == len(snapshots):
            break
        first = last - 1  # 境界1画面を再採取して一致を要求する。


def paged_frames(arm, official):
    _, snapshots, frames = paged_schedule(arm, official)
    return sum(stop for _, _, stop in capture_batches(snapshots, frames))


def measure_add1(rom, official, selected, work):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='add1-', dir=work) as temp:
        for arm in selected:
            obs, others, reasons = [], [], []
            for repeat in range(2):
                try:
                    parts, counts = run_paged_arm(rom, official, arm, Path(temp))
                    reason = '' if paged_valid(parts, arm) else '標本番号・形式・ページ件数不正'
                    # 1の隣の単精度数をBASIC側で生成できたか、PRINT値で確認する。
                    if arm['id'] == 'add1-negative-1-ulp' and parts[0][:1] != [(0, 1, 1, 2048, 1)]:
                        reason = '種の単精度最小差を確認できない'
                    obs.append(parts)
                    others.append(counts)
                    reasons.append(reason)
                except Exception:
                    obs.append([])
                    others.append([])
                    reasons.append('実行・打鍵・採取失敗')
            if obs[0] != obs[1]:
                reasons = [r or '2走不一致' for r in reasons]
            records.append(dict(arm=arm, obs=obs, others=others, reasons=reasons,
                                gate=not any(reasons)))
    return records


def cmd_measure_add1(args):
    selected = add1_arms()
    records = measure_add1(args.rom_dir, args.official, selected, args.work_dir)
    write_tsv(args.out, ['arm', 'repeat', 'typed_lines', 'page_sample_numbers',
                         'print_values', 'page_print_values', 'other_line_counts', 'gate',
                         'gate_reason', 'scheduled_frames'],
        [(r['arm']['id'], repeat + 1,
          json.dumps([*ENCODER, *(line for p in r['arm']['pages'] for line in p['lines'])], ensure_ascii=False),
          json.dumps([p['numbers'] for p in r['arm']['pages']]),
          json.dumps([row for part in r['obs'][repeat] for row in part]),
          json.dumps(r['obs'][repeat]), json.dumps(r['others'][repeat]),
          'pass' if r['gate'] else 'gate_failed', r['reasons'][repeat],
          paged_frames(r['arm'], args.official))
         for r in records for repeat in range(2)])
    print(f'追補1記録完了: {len(records)}腕×2走、関門通過 {sum(r["gate"] for r in records)}腕')
    return 0 if all(r['gate'] for r in records) else 1


def add2_comparison(record, candidate):
    arm = record['arm']
    observed = [tuple(row) for part in record['obs'][0] for row in part]
    conditional = any(op == 'input' for op, _, _ in arm.get('rp_ops', []))
    seed_row = observed[0] if conditional and record['gate'] and observed else None
    predicted = rp_prediction(arm, candidate, seed_row)
    status = ('gate_failed' if not record['gate'] else
              'agree' if observed == predicted else 'differ')
    return status, predicted


def cmd_predict_add2(args):
    write_tsv(args.out, ['arm', 'candidate', 'candidate_scope', 'prediction_condition',
        'prediction', 'page_sample_numbers', 'typed_lines'],
        [(arm['id'], candidate, '追補1で棄却済みの部分モデル',
          '負種は標本0の入力MBFを条件にする。以下はGW入力模型による暫定数値' if
          any(op == 'input' for op, _, _ in arm.get('rp_ops', [])) else '固定数値',
          json.dumps(rp_prediction(arm, candidate)),
          json.dumps([page['numbers'] for page in arm['pages']]),
          json.dumps([*ENCODER, *(line for page in arm['pages'] for line in page['lines'])], ensure_ascii=False))
         for arm in add2_controls() + add2_arms() for candidate in ADD2_CANDIDATES])
    return 0


def cmd_measure_add2(args, selected=None, candidates=ADD2_CANDIDATES, label='追補2'):
    if selected is None:
        selected = add2_controls() + add2_arms()
    records = measure_add1(args.rom_dir, args.official, selected, args.work_dir)
    calibration = all(r['gate'] and add2_comparison(r, 'R_P')[0] == 'agree' for r in records[:7])
    output = []
    for record in records:
        arm = record['arm']
        comparisons = {c: add2_comparison(record, c) for c in candidates}
        conditional = any(op == 'input' for op, _, _ in arm.get('rp_ops', []))
        for repeat in range(2):
            output.append((arm['id'], repeat+1,
                json.dumps([*ENCODER, *(line for p in arm['pages'] for line in p['lines'])], ensure_ascii=False),
                json.dumps([p['numbers'] for p in arm['pages']]),
                json.dumps([row for part in record['obs'][repeat] for row in part]),
                json.dumps(record['obs'][repeat]), json.dumps(record['others'][repeat]),
                'pass' if calibration and record['gate'] else 'gate_failed',
                record['reasons'][repeat] or ('' if calibration else '定数対照不成立'),
                *(comparisons[c][0] if calibration else 'gate_failed' for c in candidates),
                json.dumps({c: comparisons[c][1] for c in candidates}),
                '標本0の入力MBF（RND出力は使わない）' if conditional else '固定数値',
                paged_frames(arm, args.official)))
    write_tsv(args.out, ['arm', 'repeat', 'typed_lines', 'page_sample_numbers',
        'print_values', 'page_print_values', 'other_line_counts', 'gate', 'gate_reason',
        *candidates, 'candidate_predictions', 'prediction_condition', 'scheduled_frames'], output)
    print(f'{label}記録完了: {len(records)}腕×2走、関門通過 {sum(calibration and r["gate"] for r in records)}腕')
    return 0 if calibration and all(r['gate'] for r in records) else 1


def cmd_predict_add3(args):
    write_tsv(args.out, ['arm', 'candidate', 'candidate_scope', 'prediction_condition',
        'prediction', 'page_sample_numbers', 'typed_lines'],
        [(arm['id'], c, '追補2後の探索候補' if c != 'R_P' else '棄却済み部分モデル',
          '標本0の入力MBFに条件付け。測定前の数値は暫定' if
          any(op == 'input' for op, _, _ in arm.get('rp_ops', [])) else '固定数値',
          json.dumps(rp_prediction(arm, c)), json.dumps([p['numbers'] for p in arm['pages']]),
          json.dumps([*ENCODER, *(line for p in arm['pages'] for line in p['lines'])], ensure_ascii=False))
         for arm in add3_controls() + add3_arms() for c in ADD3_CANDIDATES])
    return 0


def cmd_measure_add3(args):
    # 追補2と同じ2走・全ページ・定数対照関門、候補ごとに全列を比較。
    return cmd_measure_add2(args, add3_controls() + add3_arms(), ADD3_CANDIDATES, '追補3')


def cmd_predict_add4(args):
    write_tsv(args.out, ['arm', 'candidate', 'candidate_scope', 'prediction_condition',
        'prediction', 'page_sample_numbers', 'typed_lines'],
        [(arm['id'], c, '追補3後の事後候補・溢れ未確定' if c == 'R_D' else
          '追補3後の暫定探索候補' if c == 'R_C' else '追補3で棄却済み',
          '標本0の入力MBFに条件付け' if
          any(op == 'input' for op, _, _ in arm.get('rp_ops', [])) else '固定数値',
          json.dumps(rp_prediction(arm, c)), json.dumps([p['numbers'] for p in arm['pages']]),
          json.dumps([*ENCODER, *(line for p in arm['pages'] for line in p['lines'])], ensure_ascii=False))
         for arm in add4_controls() + add4_arms() for c in ADD4_CANDIDATES])
    return 0


def cmd_measure_add4(args):
    return cmd_measure_add2(args, add4_controls() + add4_arms(), ADD4_CANDIDATES, '追補4')


def rp_training_predictions(state_class=RPState):
    """既測定腕の再計算。入力対照の条件以外に観測RND値を使わない。"""
    result = {}
    seeds = {'1': Fraction(1), '1.5': Fraction(3, 2), '1.25': Fraction(5, 4),
        '1.125': Fraction(9, 8), '1-ulp': 1 + Fraction(1, 8388608),
        '1-plus-2^-16': 1 + Fraction(1, 65536), '1-plus-2^-8': 1 + Fraction(1, 256),
        '0.5': Fraction(1, 2), '4': Fraction(4), '3': Fraction(3),
        '1e-10': Fraction(0xdbe6fd, MOD) * Fraction(2)**-33, '65536': Fraction(65536)}
    for arm in add1_arms():
        name, state = arm['id'], state_class()
        if name.startswith('add1-negative-'):
            seed = seeds[name.removeprefix('add1-negative-')]
            rows = [encode(seed, 0), encode(state.rnd(-seed), 1)]
            rows += [encode(state.rnd(1), j) for j in range(2, 12)]
        elif name.startswith('add1-randomize-'):
            state.randomize(int(name.removeprefix('add1-randomize-')))
            rows = [encode(state.rnd(0), 0)] + [encode(state.rnd(1), j) for j in range(1, 11)]
        elif name == 'add1-rerun':
            rows = []
            for _ in range(3):
                state.reset()
                rows += [encode(state.rnd(1), j) for j in range(1, 6)]
        else:
            rows = [encode(state.rnd(1), j) for j in range(1, sum(len(p['numbers']) for p in arm['pages'])+1)]
        result[name] = rows
    for arm in controls() + arms():
        name, state, rows = arm['id'], state_class(), []
        if 'expected' in arm:
            rows = arm['expected']
        else:
            for op, arg in arm['ops']:
                if op == 'reset':
                    state.reset()
                elif op == 'randomize':
                    state.randomize(Fraction(str(arg)))
                elif op == 'rnd':
                    j = len(rows) % 5 + 1 if name == 'rerun' else len(rows)+1
                    rows.append(encode(state.rnd(rp_literal(str(arg)).exact()), j))
                elif op == 'range':
                    values = [state.rnd(1) for _ in range(arg)]
                    rows = [encode(min(values), 1), encode(max(values), 2),
                        (values.count(0), values.count(1), sum(x < 0 or x >= 1 for x in values))]
        if name.startswith('start-'):
            rows = rows[3:]  # 当初の一画面採取で実際に残った番号4〜20。
        if name == 'rerun':
            rows = [row for i in range(3) for row in rows[i*5:(i+1)*5] + [(6, *rows[i*5+4][1:])]]
        result['round1-' + name] = rows
    return result


def rows_digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def rp_selftest(work):
    # 全値の照合はリポジトリ外の解析で実施。本検査は代表値と自己整合。
    # 全データ再現の成功を偽装せず、既知の171・342個目の棄却も検査する。
    training = rp_training_predictions()
    matching = {name: rows[1:] if name.startswith('add1-negative-') else rows
        for name, rows in training.items() if name not in ('add1-start-400', 'round1-range')}
    assert len(matching) == 53 and sum(map(len, matching.values())) == 437
    assert rows_digest(matching) == '95231f0375c2024647221398789619d91a0d60296ca5b69506a9d4e213abf79f'
    assert rows_digest(training['add1-start-400'][:170]) == 'e16f98e359e5b9a74d0fc492530f04f69251f5badf4190f0d293c63ee9334aaa'
    assert rows_digest(training['add1-start-400']) != '89e71b7a9a8183de1f4b67fce2503e318c57c6c7ed7e19800f96688a6f35f26a'
    assert rows_digest(training['round1-range']) != 'b226f1e5e5fcc784fb8d4979ad2119f1c1f3feb2d576b1c5c1a51702bcaf0951'
    assert training['round1-range'][2] == (0, 0, 0)
    state = RPState()
    assert encode(state.rnd(0), 1) == (1, 1, 0, 3324, 1874)
    first = [(-2, 4016, 286), (-1, 2498, 2401), (-1, 2554, 3303),
             (0, 2110, 448), (-4, 3821, 2617)]
    for j, triple in enumerate(first, 1):
        assert encode(state.rnd(1), j) == (j, 1, *triple)
    for j in range(6, 171):
        value = state.rnd(1)
    assert encode(value, 170) == (170, 1, -1, 2466, 305)
    assert encode(state.rnd(1), 171) == (171, 1, 0, 2234, 2417)
    assert encode(state.rnd(0), 171) != (171, 1, 0, 2250, 2162)
    state.number = encode_single_away(Fraction(0xa26fdb, MOD))
    state.index = 6
    assert encode(state.rnd(1), 342) == (342, 1, -1, 2641, 1797)
    assert encode(state.rnd(0), 342) != (342, 1, -1, 2673, 1287)
    for x in (1, 2, Fraction(1, 2), 4, 65536):
        state = RPState()
        assert encode(state.rnd(-x), 1) == (1, 1, -1, 2528, 257)
        assert state.index == 0
        assert encode(state.rnd(0), 2)[1:] == (1, -1, 2528, 257)
        assert encode(state.rnd(1), 2) == (2, 1, -1, 4086, 3059)
    state = RPState()
    assert encode(state.rnd(Fraction(-3, 2)), 1) == (1, 1, -1, 2528, 385)
    assert encode(state.rnd(1), 2) == (2, 1, 0, 2907, 1530)
    state = RPState()
    tiny_seed = Fraction(0xdbe6fd, MOD) * Fraction(2)**-33
    assert encode(state.rnd(-tiny_seed), 1) == (1, 1, 0, 2862, 1755)
    for n, zero, next_value in [
            (0, (0, 2433, 3191), (-1, 2285, 939)),
            (2, (0, 3586, 119), (-4, 2873, 2522)),
            (-32768, (0, 2433, 3319), (0, 3894, 2518))]:
        state = RPState()
        state.randomize(n)
        assert encode(state.rnd(0), 0) == (0, 1, *zero)
        assert encode(state.rnd(1), 1) == (1, 1, *next_value)
    selected = add2_controls() + add2_arms()
    assert len(selected) == 20
    assert sum(len(p['numbers']) for a in selected for p in a['pages']) == 1143
    predictions = {a['id']: rp_prediction(a) for a in selected}
    for arm in selected:
        rows, offset, parts = predictions[arm['id']], 0, []
        for page in arm['pages']:
            count = len(page['numbers'])
            parts.append(rows[offset:offset+count])
            offset += count
        assert offset == len(rows) and paged_valid(parts, arm)
    short = predictions['add2-negative-7.25']
    long = predictions['add2-negative-7.25-long']
    assert short[1][1:] == short[2][1:] == long[1][1:]
    assert [r[1:] for r in short[3:]] == [r[1:] for r in long[2:12]]
    assert predictions['add2-history-137-negative-.3'] == predictions['add2-negative-.3']
    reset = predictions['add2-randomize-12345-run'][4:]
    state = RPState()
    assert reset == [encode(state.rnd(1), j) for j in range(1, 11)]
    def fake(rom, official, arm, directory):
        rows, offset, parts = predictions[arm['id']], 0, []
        for page in arm['pages']:
            count = len(page['numbers'])
            parts.append(list(rows[offset:offset+count]))
            offset += count
        return parts, [0] * len(parts)
    with patch.object(os.sys.modules[__name__], 'run_paged_arm', fake):
        records = measure_add1('', False, selected, work)
    assert all(r['gate'] and add2_comparison(r, 'R_P')[0] == 'agree' for r in records)
    record = next(r for r in records if r['arm']['id'] == 'add2-negative-7.25')
    altered = [list(part) for part in record['obs'][0]]
    row = list(altered[1][0])
    row[4] ^= 1
    altered[1][0] = tuple(row)
    assert add2_comparison(dict(record, obs=[altered, altered]), 'R_P')[0] == 'differ'
    assert add2_comparison(dict(record, gate=False), 'R_P')[0] == 'gate_failed'
    assert add2_comparison(dict(record, gate=False, obs=[[[tuple([1, 2, 3])]], []]), 'R_P')[0] == 'gate_failed'
    seed_row = (0, 1, 3, 3712, 1)
    conditioned = rp_prediction(record['arm'], seed_row=seed_row)
    assert conditioned[0] == seed_row and conditioned != predictions[record['arm']['id']]
    with tempfile.TemporaryDirectory(prefix='add2-selftest-', dir=work) as temp:
        root = Path(temp)
        args = argparse.Namespace(rom_dir='', official=False, out=root/'comparison.tsv', work_dir=root)
        with patch.object(os.sys.modules[__name__], 'run_paged_arm', fake), patch('builtins.print'):
            assert cmd_measure_add2(args) == 0
        with args.out.open() as stream:
            written = list(csv.DictReader(stream, delimiter='\t'))
        assert len(written) == 40 and all(r['R_P'] == 'agree' and r['gate'] == 'pass' for r in written)
        def bad_calibration(rom, official, arm, directory):
            parts, other = fake(rom, official, arm, directory)
            if arm['id'] == 'add2-constant-zero':
                parts[0][0] = encode(Fraction(3, 4), 1)
            return parts, other
        with patch.object(os.sys.modules[__name__], 'run_paged_arm', bad_calibration), patch('builtins.print'):
            assert cmd_measure_add2(args) == 1
        with args.out.open() as stream:
            written = list(csv.DictReader(stream, delimiter='\t'))
        assert len(written) == 40 and all(r['R_P'] == 'gate_failed' and r['gate'] == 'gate_failed' for r in written)
        args.out = root/'predictions.tsv'
        assert cmd_predict_add2(args) == 0
        with args.out.open() as stream:
            written = list(csv.DictReader(stream, delimiter='\t'))
        assert len(written) == 20 and all(r['candidate'] == 'R_P' for r in written)
    print('OK R_P代表値・8周期・負種・RANDOMIZE・RUN、171/342の既知不一致を検出')
    print('OK 既測定全55腕の再計算: 53腕437組＋起動170組の署名一致、起動400・rangeは不一致')
    print('OK 追補2の13腕＋対照7腕、1143組の番号・区切り・条件付き種・改変検出、合成TSV・全体対照関門')


def ra_selftest(work):
    # ノートの代表測定値だけを固定。測定JSONを実行時に読まない。
    representatives = {171: (0, 2250, 2162), 342: (-1, 2673, 1287),
        513: (-1, 3233, 1749), 516: (-4, 3886, 3466),
        684: (0, 2258, 2716), 855: (0, 3861, 2666)}
    for cls in (RAState, RBState):
        state = cls()
        values = []
        for j in range(1, 2001):
            value = state.rnd()
            values.append(value)
            if j in representatives:
                assert encode(value, j) == (j, 1, *representatives[j])
        assert encode(min(values), 1) == (1, 1, -10, 2628, 3664)
        assert encode(max(values), 2) == (2, 1, 0, 4095, 3721)
        assert values.index(min(values))+1 == 747 and values.index(max(values))+1 == 1666
        assert not any(x <= 0 or x >= 1 for x in values)
        state.rnd(Fraction(-29, 4))
        assert state.count == 0 and state.index == 0
        for j in range(2, 402):
            value = state.rnd()
            if j == 172:
                assert encode(value, j) == (j, 1, -1, 3203, 501)
            if j == 343:
                assert encode(value, j) == (j, 1, -1, 3145, 3015)
        before = (state.count, state.index, state.number.exact())
        for _ in range(172):
            state.rnd(0)
        assert (state.count, state.index, state.number.exact()) == before
    # 修理は採取分割だけ。標本0を単独ページにし、呼出し列を保つ。
    for arm in add2_arms()+add3_arms():
        if any(op == 'input' for op, _, _ in arm['rp_ops']):
            assert arm['pages'][0]['numbers'] == [0]
            assert 'rnd(-y)' not in ''.join(arm['pages'][0]['lines'])
            assert len(arm['pages'][1]['numbers']) <= 12
            assert all(len(line) < 80 for p in arm['pages'] for line in p['lines'])
    selected = add3_controls()+add3_arms()
    assert len(selected) == 20 and len(add3_arms()) == 13
    assert sum(len(p['numbers']) for a in selected for p in a['pages']) == 2715
    predictions = {a['id']: rp_prediction(a, 'R_A') for a in selected}
    history = next(a for a in selected if a['id'] == 'add3-history-170-randomize-2026-long')
    assert predictions[history['id']][0] == (0, 1, 0, 2099, 1878)
    assert rp_prediction(history, 'R_B')[0] == (0, 1, 0, 2083, 2133)
    seed_arm = next(a for a in selected if a['id'] == 'add3-negative-1e20')
    conditioned = rp_prediction(seed_arm, 'R_A', (0, 1, 67, 2775, 2285))
    assert conditioned[1] == (1, 1, 0, 2599, 2222)
    predictions[seed_arm['id']] = conditioned

    def fake(rom, official, arm, directory):
        rows, offset, parts = predictions[arm['id']], 0, []
        for page in arm['pages']:
            count = len(page['numbers'])
            parts.append(list(rows[offset:offset+count]))
            offset += count
        assert offset == len(rows) and paged_valid(parts, arm)
        return parts, [0]*len(parts)

    with tempfile.TemporaryDirectory(prefix='add3-selftest-', dir=work) as temp:
        root = Path(temp)
        args = argparse.Namespace(rom_dir='', official=False, out=root/'comparison.tsv', work_dir=root)
        with patch.object(os.sys.modules[__name__], 'run_paged_arm', fake), patch('builtins.print'):
            assert cmd_measure_add3(args) == 0
        with args.out.open() as stream:
            written = list(csv.DictReader(stream, delimiter='\t'))
        assert len(written) == 40 and all(r['R_A'] == 'agree' and r['gate'] == 'pass' for r in written)
        assert all(r['R_B'] == 'differ' and r['R_P'] == 'differ' for r in written if r['arm'] == history['id'])
        assert all(len(json.loads(r['page_print_values'])[0]) == 1 for r in written if r['arm'] == seed_arm['id'])
        def missing_input(rom, official, arm, directory):
            parts, other = fake(rom, official, arm, directory)
            if arm['id'] == seed_arm['id']:
                parts[0] = []
            return parts, other
        with patch.object(os.sys.modules[__name__], 'run_paged_arm', missing_input), patch('builtins.print'):
            assert cmd_measure_add3(args) == 1
        with args.out.open() as stream:
            written = list(csv.DictReader(stream, delimiter='\t'))
        assert all(r[c] == 'gate_failed' for r in written if r['arm'] == seed_arm['id'] for c in ADD3_CANDIDATES)
        args.out = root/'predictions.tsv'
        assert cmd_predict_add3(args) == 0
        with args.out.open() as stream:
            written = list(csv.DictReader(stream, delimiter='\t'))
        assert len(written) == 60 and {r['candidate'] for r in written} == set(ADD3_CANDIDATES)
    print('OK R_A/R_B: 周期加算・A_4指数・起動代表値・負種172/343・range・RND(0)非更新')
    print('OK 標本0別ページ、追補3の13腕＋対照7腕、2715組、各2走・3候補TSV・欠落関門')


def rc_selftest(work):
    # 追補3の実測代表値。整数組以外の測定内容を読まない。
    history = next(a for a in add3_arms() if a['id'] == 'add3-history-170-randomize-2026-long')
    rows = rp_prediction(history, 'R_C')
    assert rows[0] == (0, 1, 0, 2099, 1878)
    assert rows[171] == (171, 1, -2, 4077, 2038)
    assert rows[342] == (342, 1, -1, 2574, 3767)
    assert rp_prediction(history, 'R_D') == rows
    assert rp_training_predictions(RDState) == rp_training_predictions(RCState)
    # 両候補の差はTの整数加算。独立に固定した未測定予測を照合する。
    for mant, c_row, d_row in [
            (0x9e51d0, (0, 2053, 32), (0, 2565, 32)),
            (0x89cd80, (-2, 3123, 42), (0, 3340, 3083)),
            (0xffb7cf, (-2, 2582, 3074), (0, 2075, 1665))]:
        c, d = RCState(), RDState()
        product = mbf.GwNum('single', sign=0, exp=152 if mant == 0x9e51d0 else 150, mant=mant)
        assert encode(c.transform(product).exact(), 0)[2:] == c_row
        assert encode(d.transform(product).exact(), 0)[2:] == d_row
    # 起動2000個はR_Aと同一、負種は前歴にかかわらずc=0。
    assert rp_training_predictions(RCState) == rp_training_predictions(RAState)
    state = RCState()
    for _ in range(170):
        state.rnd()
    state.randomize(2026)
    assert state.count == 0 and state.index == 4
    before = (state.number.exact(), state.count, state.index)
    state.rnd(0)
    assert before == (state.number.exact(), state.count, state.index)
    state.randomize(99)
    assert state.count == 1 and state.index == 5
    state.rnd(Fraction(-5, 8))
    assert state.count == 0 and state.index == 0
    selected = add4_controls()+add4_arms()
    assert len(selected) == 22 and len(add4_arms()) == 15
    assert sum(len(p['numbers']) for a in selected for p in a['pages']) == 6037
    assert sum(len(a['pages']) for a in selected) == 398
    predictions = {a['id']: rp_prediction(a, 'R_C') for a in selected}
    d_predictions = {a['id']: rp_prediction(a, 'R_D') for a in selected}
    split_ids = {a['id'] for a in selected if predictions[a['id']] != d_predictions[a['id']]}
    assert split_ids == {
        'add4-history-171-randomize-2026-long',
        'add4-history-169-randomize-2026-then-99-long',
        *(f'add4-history-0-randomize-{n}-long' for n in (25, 37, 46))}
    for n in (25, 37, 46):
        aid = f'add4-history-0-randomize-{n}-long'
        assert predictions[aid][:170] == d_predictions[aid][:170]
        assert predictions[aid][170] != d_predictions[aid][170]
    discriminator = next(a for a in selected if a['id'] == 'add4-history-0-randomize-92-long')
    a, c = rp_prediction(discriminator, 'R_A'), predictions[discriminator['id']]
    assert a[:170] == c[:170] and a[170] != c[170]
    negative = predictions['add4-history-169-negative-.625-long']
    reference = next(a for a in add3_arms() if a['id'] == 'add3-history-342-negative-.625-long')
    assert negative == rp_prediction(reference, 'R_C')
    for arm in selected:
        assert all(len(line) < 80 for p in arm['pages'] for line in p['lines'])
        assert len(predictions[arm['id']]) == sum(len(p['numbers']) for p in arm['pages'])

    def fake(rom, official, arm, directory):
        rows, offset, parts = predictions[arm['id']], 0, []
        for page in arm['pages']:
            count = len(page['numbers'])
            parts.append(rows[offset:offset+count])
            offset += count
        assert paged_valid(parts, arm)
        return parts, [0]*len(parts)

    with tempfile.TemporaryDirectory(prefix='add4-selftest-', dir=work) as temp:
        root = Path(temp)
        args = argparse.Namespace(rom_dir='', official=False, out=root/'comparison.tsv', work_dir=root)
        with patch.object(os.sys.modules[__name__], 'run_paged_arm', fake), patch('builtins.print'):
            assert cmd_measure_add4(args) == 0
        with args.out.open() as stream:
            written = list(csv.DictReader(stream, delimiter='\t'))
        assert len(written) == 44 and all(r['gate'] == 'pass' and r['R_C'] == 'agree' for r in written)
        assert all(r['R_A'] == 'differ' for r in written if r['arm'] == discriminator['id'])
        assert all(r['R_D'] == ('differ' if r['arm'] in split_ids else 'agree') for r in written)
        c_predictions = predictions
        predictions = d_predictions
        with patch.object(os.sys.modules[__name__], 'run_paged_arm', fake), patch('builtins.print'):
            assert cmd_measure_add4(args) == 0
        with args.out.open() as stream:
            written = list(csv.DictReader(stream, delimiter='\t'))
        assert len(written) == 44 and all(r['gate'] == 'pass' and r['R_D'] == 'agree' for r in written)
        assert all(r['R_C'] == ('differ' if r['arm'] in split_ids else 'agree') for r in written)
        predictions = c_predictions
        def missing(rom, official, arm, directory):
            parts, counts = fake(rom, official, arm, directory)
            if arm['id'] == discriminator['id']:
                parts[0] = parts[0][1:]
            return parts, counts
        with patch.object(os.sys.modules[__name__], 'run_paged_arm', missing), patch('builtins.print'):
            assert cmd_measure_add4(args) == 1
        with args.out.open() as stream:
            written = list(csv.DictReader(stream, delimiter='\t'))
        assert all(r[c] == 'gate_failed' for r in written if r['arm'] == discriminator['id'] for c in ADD4_CANDIDATES)
        args.out = root/'predictions.tsv'
        assert cmd_predict_add4(args) == 0
        with args.out.open() as stream:
            written = list(csv.DictReader(stream, delimiter='\t'))
        assert len(written) == 88 and {r['candidate'] for r in written} == set(ADD4_CANDIDATES)
        assert all(r['candidate_scope'] == '追補3後の事後候補・溢れ未確定'
                   for r in written if r['candidate'] == 'R_D')
    print('OK R_C暫定: 位相保持・追補3の171/342・起動列・負種リセット・零引数非更新')
    print('OK R_D事後候補: 追補3代表列・起動列再現、追加3腕と既存2腕の分離、両候補合成採取')
    print('OK 追補4: 未測定15腕＋対照7腕、6037組・398ページ、各2走・4候補・欠落関門')


def selftest(work):
    work.mkdir(parents=True, exist_ok=True)
    rp_selftest(work)
    ra_selftest(work)
    rc_selftest(work)
    fixed = [2035917, 10936412, 14577071, 12243382, 13402529]
    state = INITIAL
    for expected in fixed:
        state = step(state)
        assert state == expected
    assert negative_seed(-1) == negative_seed(-2) == 0x800000
    assert negative_seed(-1.5) == 0xc00000
    assert step(0x800000) == 10919619
    for arm in controls():
        row = arm['expected'][0]
        assert encode(decode(row), 1) == row
    synthetic = bytearray(b' ' * 3000)
    line = b's8 1 -1 -2 3072 0'
    synthetic[:len(line)] = line
    synthetic[120:132] = b'nonprintbody'
    assert extract(synthetic) == ([(1, -1, -2, 3072, 0)], 1)
    synthetic[0] = ord('x')
    assert extract(synthetic) == ([], 2)
    assert not valid([(1, 1, 0, 3072, 4096)], [1])
    assert not valid([(1, 1, 0, 1024, 0)], [1])
    a = arms()[0]
    expected = prediction(a, 'R_GW')
    assert prediction(a, 'R_GW_S', expected) == expected
    inferred = ((fixed[0] - 2531011) * pow(214013, -1, MOD)) % MOD
    assert inferred == INITIAL
    for arm in arms():
        assert prediction(arm, 'R_GW_S', initial=inferred) == prediction(arm, 'R_GW')
    wrong = list(expected)
    wrong[1] = encode((fixed[1] + 1) / MOD, 2)
    assert prediction(a, 'R_GW_S', wrong) != wrong
    seed = 123456
    selected = controls() + arms()
    def fake_run(rom, official, arm, directory):
        return prediction(arm, 'R_GW_S', initial=seed), [0] * len(arm['counts'])
    with patch.object(os.sys.modules[__name__], 'run_arm', fake_run):
        records = measure('', False, selected, work)
    assert all(r['gate'] and r['statuses']['R_GW_S'] == 'agree' for r in records)
    def altered_run(rom, official, arm, directory):
        altered = seed + 1 if arm['id'] == 'randomize-1' else seed
        return prediction(arm, 'R_GW_S', initial=altered), [0] * len(arm['counts'])
    with patch.object(os.sys.modules[__name__], 'run_arm', altered_run):
        records = measure('', False, selected, work)
    assert next(r for r in records if r['arm']['id'] == 'randomize-1')['statuses']['R_GW_S'] == 'differ'
    print('OK 合成の陽性・陰性対照、GW固定値、共通初期値と種の改変検出')
    chunk_control = paged_arm('chunk-constant', sequence_pages('.75', 36, program=True))
    def screen_of(rows):
        data = bytearray(b' ' * 3000)
        for i, row in enumerate(rows):
            text = ('s8' + ''.join(f' {n}' for n in row)).encode('ascii')
            data[i*120:i*120+len(text)] = text
        return data
    good = [[encode(.75, j) for j in p['numbers']] for p in chunk_control['pages']]
    parsed = [extract(screen_of(p))[0] for p in good]
    assert parsed == good and paged_valid(parsed, chunk_control)
    missing = [list(p) for p in parsed]
    missing[0].pop()
    assert not paged_valid(missing, chunk_control)
    duplicate = [list(p) for p in parsed]
    duplicate[1][0] = duplicate[0][-1]  # 件数は同じでもページ境界の重複を検出。
    assert not paged_valid(duplicate, chunk_control)
    assert not paged_valid(parsed[:-1], chunk_control)
    assert len(add1_arms()) == 26
    assert [(a, b) for a, b, _ in capture_batches(list(range(25)), 30)] == [(0, 16), (15, 25)]
    assert [j for p in add1_arms()[0]['pages'] for j in p['numbers']] == list(range(1, 401))
    assert encode(single(1 + 2**-23), 0) == (0, 1, 1, 2048, 1)
    def fake_paged(rom, official, arm, directory):
        return good, [0] * len(good)
    with patch.object(os.sys.modules[__name__], 'run_paged_arm', fake_paged):
        assert measure_add1('', False, [chunk_control], work)[0]['gate']
    for bad in (missing, duplicate):
        with patch.object(os.sys.modules[__name__], 'run_paged_arm',
                          lambda *args: (bad, [0] * len(bad))):
            assert not measure_add1('', False, [chunk_control], work)[0]['gate']
    different = [list(p) for p in good]
    different[1][0] = encode(.5, different[1][0][0])
    with patch.object(os.sys.modules[__name__], 'run_paged_arm',
                      side_effect=[(good, [0]*3), (different, [0]*3)]):
        assert not measure_add1('', False, [chunk_control], work)[0]['gate']
    print('OK 区切り採取の合成陽性、欠け・重複・ページ欠落・2走不一致の陰性対照')
    replay_control = paged_arm('replay-constant', sequence_pages('.75', 400))
    _, replay_snapshots, _ = paged_schedule(replay_control, False)
    replay_good = [[encode(.75, j) for j in p['numbers']] for p in replay_control['pages']]
    replay_calls = []
    def replay_process(args, **kwargs):
        pairs = [(Path(args[i+1]), int(args[i+3])) for i, arg in enumerate(args)
                 if arg == '--vram-dump']
        assert len(pairs) <= 16
        replay_calls.append(len(pairs))
        for path, frame in pairs:
            page = replay_snapshots.index(frame)
            rows = list(replay_good[page])
            if corrupt_boundary and len(replay_calls) % 2 == 0 and page == 15:
                rows[0] = encode(.5, rows[0][0])
            target = path if len(pairs) == 1 else path.with_name(f'{path.stem}.f{frame:06d}{path.suffix}')
            target.write_bytes(screen_of(rows))
        return subprocess.CompletedProcess(args, 0, b'', b'')
    corrupt_boundary = False
    with patch.object(subprocess, 'run', replay_process):
        replay_records = measure_add1('', False, [replay_control], work)
    assert replay_records[0]['gate'] and replay_records[0]['obs'] == [replay_good, replay_good]
    assert replay_calls == [16, 10, 16, 10]
    replay_calls.clear()
    corrupt_boundary = True
    with patch.object(subprocess, 'run', replay_process):
        assert not measure_add1('', False, [replay_control], work)[0]['gate']
    print('OK 25画面の再生採取、16画面上限、境界PRINT改変の陰性対照')
    with tempfile.TemporaryDirectory(prefix='selftest-', dir=work) as temp:
        root = Path(temp)
        rom = root / 'rom'
        proc = subprocess.run([os.sys.executable, str(kw.REPO / 'src/build_main_rom.py'),
                               str(rom), '--work-dir', str(root / 'asm')],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.returncode == 0, '自作ROMの一時ビルド失敗'
        records = measure(rom, False, controls(), root)
        assert all(r['gate'] and r['statuses']['R_GW'] == 'agree' for r in records), \
            '定数取り出し関門失敗: ' + ','.join(r['arm']['id'] for r in records if not r['gate'] or r['statuses']['R_GW'] != 'agree')
        assert all(r['obs'][0] != [encode(.5, 1)] for r in records)
        chunk_started = time.monotonic()
        chunk_records = measure_add1(rom, False, [chunk_control], root)
        chunk_seconds = time.monotonic() - chunk_started
        assert chunk_records[0]['gate'], '自作ROMの区切り採取関門失敗: ' + json.dumps({
            'reasons': chunk_records[0]['reasons'],
            'numbers': [[[r[0] for r in p] for p in run] for run in chunk_records[0]['obs']],
            'others': chunk_records[0]['others']}, ensure_ascii=False)
        assert chunk_records[0]['obs'] == [good, good], '自作ROMの定数36個の採取失敗'
        # 実際に定数PRINTから採ったページでも、欠け・重複を陰性対照にする。
        actual = chunk_records[0]['obs'][0]
        for change in ('missing', 'duplicate'):
            bad = [list(p) for p in actual]
            if change == 'missing':
                bad[1].pop(0)
            else:
                bad[1][0] = bad[0][-1]
            assert not paged_valid(bad, chunk_control)
    print('OK 自作ROM一時ビルド、定数7腕各2走、誤った期待値の陰性対照')
    print('OK 自作ROMの定数36個×2走を3画面採取、実採取値の欠け・重複を検出')
    frames = sum(paged_frames(a, True) for a in add1_arms())
    print(f'追補1見積: 26腕の1走合計 {frames}フレーム（60fps換算 {frames/3600:.1f}分）')
    estimate = frames * chunk_seconds / (2 * paged_frames(chunk_control, False))
    print(f'実時間参考: 自作ROM区切り採取 {chunk_seconds:.2f}秒からの外挿で1走約{estimate/60:.1f}分（公式ROM未計時）')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('predict')
    p.add_argument('--out', type=Path, required=True)
    m = subs.add_parser('measure')
    m.add_argument('--rom-dir', required=True)
    m.add_argument('--out', type=Path, required=True)
    m.add_argument('--official', action='store_true')
    m.add_argument('--work-dir', type=Path, default=WORK)
    a = subs.add_parser('measure-add1')
    a.add_argument('--rom-dir', required=True)
    a.add_argument('--out', type=Path, required=True)
    a.add_argument('--official', action='store_true')
    a.add_argument('--work-dir', type=Path, default=WORK)
    p2 = subs.add_parser('predict-add2')
    p2.add_argument('--out', type=Path, required=True)
    m2 = subs.add_parser('measure-add2')
    m2.add_argument('--rom-dir', required=True)
    m2.add_argument('--out', type=Path, required=True)
    m2.add_argument('--official', action='store_true')
    m2.add_argument('--work-dir', type=Path, default=WORK)
    p3 = subs.add_parser('predict-add3')
    p3.add_argument('--out', type=Path, required=True)
    m3 = subs.add_parser('measure-add3')
    m3.add_argument('--rom-dir', required=True)
    m3.add_argument('--out', type=Path, required=True)
    m3.add_argument('--official', action='store_true')
    m3.add_argument('--work-dir', type=Path, default=WORK)
    p4 = subs.add_parser('predict-add4')
    p4.add_argument('--out', type=Path, required=True)
    m4 = subs.add_parser('measure-add4')
    m4.add_argument('--rom-dir', required=True)
    m4.add_argument('--out', type=Path, required=True)
    m4.add_argument('--official', action='store_true')
    m4.add_argument('--work-dir', type=Path, default=WORK)
    s = subs.add_parser('selftest')
    s.add_argument('--work-dir', type=Path, default=WORK)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'measure-add1':
        return cmd_measure_add1(args)
    if args.command == 'predict-add2':
        return cmd_predict_add2(args)
    if args.command == 'measure-add2':
        return cmd_measure_add2(args)
    if args.command == 'predict-add3':
        return cmd_predict_add3(args)
    if args.command == 'measure-add3':
        return cmd_measure_add3(args)
    if args.command == 'predict-add4':
        return cmd_predict_add4(args)
    if args.command == 'measure-add4':
        return cmd_measure_add4(args)
    selected = controls(direct=args.command == 'measure' and args.official) + arms()
    if args.command == 'predict':
        write_tsv(args.out, ['arm', 'candidate', 'prediction', 'typed_lines'],
            [(a['id'], c, json.dumps(prediction(a, c)) if prediction(a, c) is not None
              else '起動列の初回観測から共通初期値を復元して予測',
              json.dumps([*ENCODER, 'cls', *a['lines']], ensure_ascii=False))
             for a in selected for c in CANDIDATES])
        return 0
    records = measure(args.rom_dir, args.official, selected, args.work_dir)
    calibration = all(r['gate'] and r['statuses']['R_GW'] == 'agree' for r in records[:7])
    write_tsv(args.out, ['arm', 'repeat', 'typed_lines', 'print_values', 'other_line_counts',
                         'gate', *CANDIDATES, 'candidate_predictions', 'extra_wait_frames'],
        [(r['arm']['id'], repeat + 1,
          json.dumps([*ENCODER, 'cls', *r['arm']['lines']], ensure_ascii=False),
          json.dumps(r['obs'][repeat]), json.dumps(r['others'][repeat]),
          'pass' if calibration and r['gate'] else 'gate_failed',
          *(r['statuses'][c] if calibration else 'gate_failed' for c in CANDIDATES),
          json.dumps(r['predictions']), r['arm']['wait'])
         for r in records for repeat in range(2)])
    print(f'記録完了: {len(records)}腕×2走、関門通過 {sum(calibration and r["gate"] for r in records)}腕')
    return 0 if calibration and all(r['gate'] for r in records) else 1


if __name__ == '__main__':
    raise SystemExit(main())
