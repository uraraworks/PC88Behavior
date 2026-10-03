#!/usr/bin/env python3
"""l4-s8a の事前予測と PRINT 測定。公式画面の本文は保存しない。"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
from unittest.mock import patch

import l4_listkw_measure as kw

WORK = kw.REPO.parent / 'tmp/l4s8a-work'
MOD = 1 << 24
INITIAL = 0x4fc752
CANDIDATES = ('R_GW', 'R_GW_S')
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


def selftest(work):
    work.mkdir(parents=True, exist_ok=True)
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
    print('OK 自作ROM一時ビルド、定数7腕各2走、誤った期待値の陰性対照')
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
    s = subs.add_parser('selftest')
    s.add_argument('--work-dir', type=Path, default=WORK)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
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
