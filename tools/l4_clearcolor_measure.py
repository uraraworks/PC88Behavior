#!/usr/bin/env python3
"""l4-s9q: CLEAR の上限（第2引数）の下限境界と、COLOR の第2〜第4引数を測る器具。

画面本文は扱わない。採るのは (1) 自作の印字 `s9q[ard]`（印・整数だけ）、(2) 制御ポート（0x30〜0x35・0x52〜0x5B）の書き込み値列。
複数プローブ方式: 1走行に文を直列に並べ、`on error goto`＋`e=err`＋`resume next` で誤り番号と fre(0) を1行ずつ印字する。
CLEAR の境界は k 分探索（b5＝誤り5でない最小、b7＝受理の最小、m＝b7 での fre(0)）。事前登録は docs/notes/l4-s9q-clear-color-preregistration.md。
"""
import argparse
import concurrent.futures
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import l4_listkw_measure as kw
import l4_widthvram_measure as wv
import l4_memlimit_measure as mm

WORK = kw.REPO.parent / 'tmp/s9q-work'
IO_LINE = wv.IO_LINE
MARK = re.compile(r'^(s9q[ared])((?: *-?\d+)+) *$')
PORTS = (0x30, 0x31, 0x32, 0x34, 0x35, 0x52, 0x53) + tuple(range(0x54, 0x5C))
ANCHOR_X = 0xE000
GRID = [0x8000 + 0x200*i for i in range(14)]          # 0x8000〜0x9A00（0x200 刻み、14点）
ROMAN = {0: 'OK', 5: 'E5', 7: 'E7'}
RANK = {'E5': 0, 'E7': 1, 'OK': 2}
STR36 = 'abcdefghijklmnopqrstuvwxyz0123456789'

# ---------------------------------------------------------------- 腕の定義
CL_CONDS = [
    dict(id='cl-base'),
    dict(id='cl-n10', nvar=8),
    dict(id='cl-padrem', pad=('rem', 800)),
    dict(id='cl-padrem2', pad=('rem', 2400)),
    dict(id='cl-paddata', pad=('data', 800)),
    dict(id='cl-stk128', n=128), dict(id='cl-stk256', n=256),
    dict(id='cl-stk1024', n=1024), dict(id='cl-stk2048', n=2048),
    dict(id='cl-str1000', first=1000), dict(id='cl-str20000', first=20000),
    dict(id='cl-var', var=True),
]
CF_ARMS = [dict(id='cf-plain'), dict(id='cf-arr500', arr=500), dict(id='cf-arr3000', arr=3000)]
CV_N = (0, 64, 72, 80, 88, 96, 104, 112, 120, 124, 126, 127, 128, 129, 1024, 32767, -1, 32768)
CV_STMTS = (['clear ,&h8400', 'clear ,&h8800', 'clear ,&h8c00', 'clear', 'clear 0', 'clear 1000', 'clear 20000',
             'clear 65535', 'clear -1', 'clear 70000']
            + [f'clear ,&he000,{n}' for n in CV_N] + ['clear ,,128', 'clear ,,64'])
CO_REFS = ['a$=chr$(300)', 'a$=1']
CO_VALS = (-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 255, 256)
CO_STMTS = (['color 0', 'color 7']
            + [f'color ,{v}' for v in CO_VALS] + [f'color ,,{v}' for v in CO_VALS] + [f'color ,,,{v}' for v in CO_VALS]
            + [f'color 3,{b},{bo},{fg}' for b in range(3) for bo in range(3) for fg in range(3)]
            + ['color 3,1,1', 'color 3,1', 'color 3,,1', 'color 3,,,2', 'color ,1,1', 'color ,,1,2', 'color ,1,,2',
               'color ,2.5', 'color ,,,2.5', 'color ,"a"', 'color ,,"a"', 'color ,,,"a"'])
CP_STMTS = ([('base', 'rem')] + [(f'bg{b}', f'color ,{b}') for b in range(8)]
            + [(f'bo{b}', f'color ,,{b}') for b in range(8)] + [(f'fg{b}', f'color ,,,{b}') for b in range(8)]
            + [('t2', 'color 2'), ('t7', 'color 7'), ('out52', 'out &h52,&h40')])
CHUNK = 14


def chunks(stmts, size, refs=()):
    return [list(refs) + stmts[i:i+size] for i in range(0, len(stmts), size)]


def arms():
    out = []
    for c in CL_CONDS:
        out.append(dict(c, kind='cl'))
    for c in CF_ARMS:
        out.append(dict(c, kind='cf'))
    for i, st in enumerate(chunks(CV_STMTS, 16)):
        out.append(dict(id=f'cv-{i+1}', kind='stmts', wrap='clear', stmts=st))
    for i, st in enumerate(chunks(CO_STMTS, CHUNK, CO_REFS)):
        out.append(dict(id=f'co-{i+1}', kind='stmts', wrap='color', stmts=st))
    for key, st in CP_STMTS:
        out.append(dict(id=f'cp-{key}', kind='port', stmt=st))
    return out


def known_arms():
    """較正: s9d の既存器具（l4_memlimit_measure）の腕をそのまま使い、既知値（0x8400→誤り5・0x8800→誤り7・0x8C00→受理）を再現する。"""
    return [dict(id=f'kn-{x:04x}', kind='known', limit=x) for x in (0x8400, 0x8800, 0x8c00)]


def hexs(x):
    return f'&h{x:04x}'


# ---------------------------------------------------------------- 打ち込むプログラム
def clear_stmt(spec, x):
    first = '' if spec.get('first') is None else str(spec['first'])
    s = f'clear {first},{hexs(x)}'
    if spec.get('n'):
        s += f",{spec['n']}"
    if spec.get('var'):
        s = f'a$="{STR36}":b$=a$+a$+a$:' + s
    return s


def pad_lines(spec):
    if not spec.get('pad'):
        return []
    kind, size = spec['pad']
    body = 'x'*60
    n = max(1, round(size/67))                  # 1行は保存形でおよそ67バイト（正確な長さは T の差で測る）
    return [f'{20+i} {kind} {body}' for i in range(n)]


def probe_lines(spec, xs):
    """kind=cl / cf。プローブ直列。cl は先頭アンカー＋xs＋末尾アンカー、cf は xs＋末尾アンカー。"""
    stmts = ([clear_stmt(spec, ANCHOR_X)] if spec['kind'] == 'cl' else []) + [clear_stmt(spec, x) for x in xs] + [clear_stmt(spec, ANCHOR_X)]
    return build(spec, stmts, f'e=0:')


def build(spec, stmts, prefix, wrap=None):
    lines = ['new', '5 on error goto 950', '10 print "s9qa";1;1']
    lines += pad_lines(spec)
    if spec.get('arr'):
        lines.append(f"15 dim a({spec['arr']})")
    for i, s in enumerate(stmts):
        body = s if wrap is None else wrap(s)
        lines.append(f'{100+2*i} {prefix}{body}')
        lines.append(f'{101+2*i} on error goto 950:print "s9qr";{i+1};e;fre(0)')
    lines += ['900 print "s9qd";1;1:end', '950 e=err:resume next', 'cls', 'run']
    assert len(stmts) <= 20
    assert all(len(l) < 80 and l == l.lower() and l.isascii() and '@' not in l for l in lines if l not in ('new', 'cls', 'run')), \
        [l for l in lines if len(l) >= 80]
    return lines


def stmts_lines(spec):
    wrap = (lambda s: f'clear ,&he000:on error goto 950:{s}') if spec['wrap'] == 'clear' else None
    return build(spec, spec['stmts'], 'e=0:', wrap)


def port_lines(spec):
    lines = ['new', '5 on error goto 950', '10 print "s9qa";1;1', f"20 {spec['stmt']}", '30 print "s9qd";1;1', '40 end',
             '950 print "s9qe";2;err:resume 30', 'cls', 'run']
    assert all(len(l) < 80 and l.isascii() for l in lines)
    return lines


def program_lines(spec, xs=None):
    k = spec['kind']
    if k in ('cl', 'cf'):
        return probe_lines(spec, xs)
    if k == 'stmts':
        return stmts_lines(spec)
    if k == 'port':
        return port_lines(spec)
    return mm.program(spec)


# ---------------------------------------------------------------- 写しの解析
def extract(data):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    rows, other = [], 0
    for i in range(25):
        raw = data[i*120:i*120+80]
        if all(b in (0x20, 0x00) for b in raw):
            continue
        m = MARK.fullmatch(raw.decode('ascii', errors='replace').rstrip(' '))
        if not m:
            other += 1
            continue
        rows.append([m[1]] + [int(x) for x in re.findall(r'-?\d+', m[2])])
    return rows, other


def probe_result(rows, n):
    """プローブ走行の印 → [(e, fre), ...]。形が崩れていれば例外。"""
    if not rows or rows[0] != ['s9qa', 1, 1] or rows[-1] != ['s9qd', 1, 1]:
        raise ValueError('開始・終了の印が無い')
    mid = rows[1:-1]
    if len(mid) != n or any(r[0] != 's9qr' or len(r) != 4 or r[1] != i+1 or not (0 <= r[2] <= 255) for i, r in enumerate(mid)):
        raise ValueError('プローブ行が崩れている')
    return [(r[2], r[3]) for r in mid]


def port_result(rows):
    if not rows or rows[0] != ['s9qa', 1, 1] or rows[-1] != ['s9qd', 1, 1]:
        raise ValueError('開始・終了の印が無い')
    mid = rows[1:-1]
    if len(mid) > 1 or any(r[0] != 's9qe' or len(r) != 3 for r in mid):
        raise ValueError('印が崩れている')
    return mid[0][2] if mid else 0


def port_summary(text, win_from, win_to):
    seq, crtc = {}, 0
    for line in text.splitlines():
        m = IO_LINE.match(line)
        if not m or m[4] != 'main' or m[5] != 'OUT':
            continue
        frame, port, val = int(m[3]), int(m[6], 16), int(m[7], 16)
        if not (win_from <= frame < win_to):
            continue
        if port in (0x50, 0x51):
            crtc += 1
        if port in PORTS:
            s = seq.setdefault(f'{port:02X}', [])
            if not s or s[-1] != val:
                s.append(val)
    return dict(crtc=crtc, ports=seq)


# ---------------------------------------------------------------- 走らせる
def run_lines(rom, official, lines, work, ports=False):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    window = None
    for line in lines:
        if line == 'run':
            window = at
        args += ['--type-at', str(at), '--type', line+'\n']
        at += (len(line)+1)*8 + 240 + (15000 if line == 'run' else 0)
    screen = work/'screen.bin'
    iolog = work/'port.txt'
    frame = at+200
    args += ['--vram-dump', str(screen), '--vram-dump-at', str(frame), '--frames', str(at+300)]
    if ports:
        args += ['--io-log', str(iolog), '--io-log-from-frame', str(wv.PORT_FROM)]
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if p.returncode or b'untypable' in p.stderr.lower() or '打てない'.encode() in p.stderr:
            raise RuntimeError('打鍵または採取に失敗')
        files = ([screen] if screen.exists() else []) + mm.snapshots(screen)
        target = screen if screen.exists() else work/f'screen.f{frame:06d}.bin'
        if target not in files:
            raise RuntimeError('指定フレームの採取がない')
        rows, _ = extract(target.read_bytes())
        ps = port_summary(iolog.read_text(encoding='utf-8', errors='replace'), window, frame+1) if ports else None
        return rows, ps
    finally:
        for q in [screen, *mm.snapshots(screen), iolog, Path(str(iolog)+'.info.txt')]:
            q.unlink(missing_ok=True)


# ---------------------------------------------------------------- CLEAR 境界の探索（純粋関数。probe_fn を差し替えて検査する）
def classify(e):
    return ROMAN.get(e, f'X{e}')


def run_probes(rom, official, spec, xs, work):
    """cl: 先頭アンカー・xs・末尾アンカーの結果。cf: xs・末尾アンカー。返り値 dict(anchor=[(e,fre)...], res=[(e,fre)...])。"""
    rows, _ = run_lines(rom, official, program_lines(spec, xs), work)
    lead = 1 if spec['kind'] == 'cl' else 0
    got = probe_result(rows, lead + len(xs) + 1)
    return dict(anchor=[got[0], got[-1]] if lead else [got[-1]], res=got[lead:lead+len(xs)])


def pick(lo, hi, k, known):
    """(lo,hi) の内側から k 点を等間隔に。既知の点は除く。"""
    if hi - lo <= 1 or k <= 0:
        return []
    inner = hi - lo - 1
    if inner <= k:
        pts = list(range(lo+1, hi))
    else:
        pts = [lo + (hi-lo)*j//(k+1) for j in range(1, k+1)]
    return sorted({p for p in pts if lo < p < hi and p not in known})


def boundaries(known):
    cls = {x: {classify(e) for e, _ in v} for x, v in known.items()}
    xs = sorted(cls)
    one = {x: next(iter(c)) for x, c in cls.items() if len(c) == 1}
    e5 = [x for x in xs if x in one and one[x] == 'E5']
    lo5 = max(e5) if e5 else None
    hi5c = [x for x in xs if lo5 is not None and x > lo5 and x in one and one[x] != 'E5']
    hi5 = min(hi5c) if hi5c else None
    nonok = [x for x in xs if x in one and one[x] != 'OK']
    lo7 = max(nonok) if nonok else None
    okc = [x for x in xs if x in one and one[x] == 'OK' and (lo7 is None or x > lo7)]
    hi7 = min(okc) if okc else None
    return lo5, hi5, lo7, hi7


def search(probe_fn, nvar=14, max_rounds=10):
    """k分探索。probe_fn(xs) → dict(anchor=[(e,fre),(e,fre)], res=[(e,fre)...])。nvar は1走行の可変プローブ数（固定）。"""
    known, anchors, trace = {}, [], []
    def do(xs, rev):
        order = sorted(xs, reverse=rev)
        assert len(order) == nvar
        r = probe_fn(order)
        anchors.extend(r['anchor'])
        trace.append(dict(xs=order, res=[list(t) for t in r['res']], anchor=[list(t) for t in r['anchor']]))
        for x, t in zip(order, r['res']):
            known.setdefault(x, []).append(tuple(t))
        for t in r['anchor']:
            known.setdefault(ANCHOR_X, []).append(tuple(t))
    def fill(pts):
        pool = sorted(known) or GRID
        out, i = list(pts), 0
        while len(out) < nvar:
            out.append(pool[(i*3) % len(pool)] if pts or known else GRID[i % len(GRID)])
            i += 1
        return out[:nvar]
    do(GRID[:nvar], False)
    rounds = 1
    while rounds < max_rounds:
        lo5, hi5, lo7, hi7 = boundaries(known)
        ivs = [(a, b) for a, b in ((lo5, hi5), (lo7, hi7)) if a is not None and b is not None and b - a > 1]
        if not ivs:
            break
        k = nvar // len(ivs)
        pts = sorted({p for a, b in ivs for p in pick(a, b, k, known)})
        do(fill(pts), rounds % 2 == 1)
        rounds += 1
    lo5, hi5, lo7, hi7 = boundaries(known)
    res = dict(rounds=rounds, b5=hi5 if lo5 is not None and hi5 is not None and hi5 - lo5 == 1 else None,
               b7=hi7 if lo7 is not None and hi7 is not None and hi7 - lo7 == 1 else None,
               lo5=lo5, hi5=hi5, lo7=lo7, hi7=hi7)
    # 検証走行: 境界の両側と各領域の内部。既知の点も測り直して一致を見る。
    if res['b5'] is not None and res['b7'] is not None:
        ver = [res['b5']-1, res['b5'], res['b7']-1, res['b7'], 0x8000, res['b7']+0x200, 0xE5FF, 0xE600]
        do(fill(sorted(set(ver))[:nvar]) if nvar < 8 else fill(ver), True)
    T = None
    if anchors and all(e == 0 for e, _ in anchors):
        Ts = {ANCHOR_X - f for _, f in anchors}
        T = Ts.pop() if len(Ts) == 1 else None
    consistent = all(len(set(v)) == 1 for v in known.values())
    ranks = [(x, RANK.get(classify(v[0][0]))) for x, v in sorted(known.items())]
    mono = all(r is not None for _, r in ranks) and all(a[1] <= b[1] for a, b in zip(ranks, ranks[1:]))
    slope = T is not None and all(f == x - T for x, v in known.items() for e, f in v if e == 0)
    res.update(T=T, anchors_equal=T is not None, consistent=consistent, mono=mono, slope=slope,
               m=known[res['b7']][0][1] if res['b7'] in known else None,
               other=sorted({e for v in known.values() for e, _ in v if e not in ROMAN}),
               trace=trace)
    return res


def search_ok(r):
    return (r['b5'] is not None and r['b7'] is not None and r['anchors_equal'] and r['consistent'] and r['mono']
            and r['slope'] and not r['other'])


def confirm(probe_fn, base, nprobe=1):
    """cf: base（cl-base の探索結果）の式 b7 = T + m、b5（固定番地）が、先頭プローブ（配列のある状態）でも成り立つか。"""
    r0 = probe_fn([ANCHOR_X])
    (e_last, f_last), = r0['anchor']
    (e0, f0), = r0['res']
    T = ANCHOR_X - f_last
    out = dict(T=T, t_first=ANCHOR_X - f0 if e0 == 0 else None, e0=e0, e_last=e_last, tests=[])
    if base['m'] is None or base['b5'] is None:
        out['tests_ok'] = False
        return out
    want = [(base['b5']-1, 'E5'), (base['b5'], 'E7' if base['b5'] < T + base['m'] else 'OK'),
            (T + base['m'] - 1, 'E7'), (T + base['m'], 'OK')]
    for x, w in want:
        r = probe_fn([x])
        e, f = r['res'][0]
        out['tests'].append(dict(x=x, want=w, got=classify(e), fre=f, anchor_T=ANCHOR_X - r['anchor'][0][1]))
    out['tests_ok'] = e0 == 0 and e_last == 0 and out['t_first'] == T and all(
        t['want'] == t['got'] and t['anchor_T'] == T for t in out['tests'])
    return out


# ---------------------------------------------------------------- 測定
def search_arm(rom, official, spec, work):
    nvar = spec.get('nvar', 14)
    def fn(xs):
        with tempfile.TemporaryDirectory(prefix='run-', dir=work) as t:
            return run_probes(rom, official, spec, xs, Path(t))
    return search(fn, nvar)


def confirm_arm(rom, official, spec, base, work):
    def fn(xs):
        with tempfile.TemporaryDirectory(prefix='run-', dir=work) as t:
            return run_probes(rom, official, spec, xs, Path(t))
    return confirm(fn, base)


def stmts_arm(rom, official, spec, work):
    with tempfile.TemporaryDirectory(prefix='run-', dir=work) as t:
        rows, _ = run_lines(rom, official, program_lines(spec), Path(t))
    return dict(res=[list(x) for x in probe_result(rows, len(spec['stmts']))])


def port_arm(rom, official, spec, work):
    with tempfile.TemporaryDirectory(prefix='run-', dir=work) as t:
        rows, ps = run_lines(rom, official, program_lines(spec), Path(t), ports=True)
    return dict(err=port_result(rows), crtc=ps['crtc'], ports=ps['ports'])


def known_arm(rom, official, spec, work):
    with tempfile.TemporaryDirectory(prefix='run-', dir=work) as t:
        rows, _ = mm.run_arm(rom, official, spec, Path(t))
    return dict(rows=rows)


KNOWN_WANT = {0x8400: [['s9de', 1, 5], ['s9dd', 1, 1]], 0x8800: [['s9de', 1, 7], ['s9dd', 1, 1]]}


def known_ok(spec, obs):
    rows = obs.get('rows')
    if spec['limit'] in KNOWN_WANT:
        return rows == KNOWN_WANT[spec['limit']]
    return rows == [['s9da', 1, 1], ['s9dv', 2, 742], ['s9dd', 1, 1]]


def measure_one(rom, official, spec, work, base=None):
    k = spec['kind']
    try:
        if k == 'cl':
            return search_arm(rom, official, spec, work)
        if k == 'cf':
            return confirm_arm(rom, official, spec, base, work)
        if k == 'stmts':
            return stmts_arm(rom, official, spec, work)
        if k == 'port':
            return port_arm(rom, official, spec, work)
        return known_arm(rom, official, dict(spec, kind='limit'), work)
    except Exception as error:      # 例外名と行だけ。画面本文は持たない
        return dict(failed=f'{type(error).__name__}')


def measure(rom, official, selected, work, jobs=4):
    work.mkdir(parents=True, exist_ok=True)
    pairs = [(a, i) for a in selected for i in range(2)]
    records = {a['id']: dict(arm=a, obs=[None, None]) for a in selected}
    def need_base(a):
        return a['kind'] == 'cf'
    first = [(a, i) for a, i in pairs if not need_base(a)]
    with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
        futs = {ex.submit(measure_one, rom, official, a, work): (a['id'], i) for a, i in first}
        for f in concurrent.futures.as_completed(futs):
            aid, i = futs[f]
            records[aid]['obs'][i] = f.result()
        base = (records.get('cl-base') or {}).get('obs', [None])[0]
        second = [(a, i) for a, i in pairs if need_base(a)]
        futs = {ex.submit(measure_one, rom, official, a, work, base if base and 'b5' in base else dict(b5=None, m=None)): (a['id'], i) for a, i in second}
        for f in concurrent.futures.as_completed(futs):
            aid, i = futs[f]
            records[aid]['obs'][i] = f.result()
    return [records[a['id']] for a in selected]


# ---------------------------------------------------------------- 関門と記録
def arm_gate(r):
    a, o = r['arm'], r['obs']
    if any(x is None or 'failed' in x for x in o) or o[0] != o[1]:
        return False
    x = o[0]
    k = a['kind']
    if k == 'cl':
        return search_ok(x)
    if k == 'cf':
        return bool(x.get('tests_ok'))
    if k == 'stmts':
        return len(x['res']) == len(a['stmts'])
    if k == 'port':
        return x['crtc'] >= 1
    return known_ok(a, x)


def calibrated(records):
    """較正: (1) s9d の既知3腕が既知値、(2) co の各チャンクの参照が 5・13、(3) cp は基準走で窓内に CRTC・陽性対照が 0x52 に 0x40。
    該当する腕が記録に無ければ、その項目は問わない（--only の部分走行）。"""
    by = {r['arm']['id']: r for r in records}
    ok = True
    for r in records:
        a, o = r['arm'], r['obs'][0]
        if a['kind'] == 'known':
            ok = ok and bool(r['gate'])
        if a['kind'] == 'stmts' and a['wrap'] == 'color':
            ok = ok and bool(r['gate']) and [e for e, _ in o['res'][:2]] == [5, 13]
    if 'cp-out52' in by:
        o = by['cp-out52']['obs'][0]
        ok = ok and 0x40 in (o.get('ports') or {}).get('52', []) and 'cp-base' in by and bool(by['cp-base']['gate'])
    if any(a.startswith('kn-') for a in by):
        ok = ok and all(by[f'kn-{x:04x}']['gate'] for x in (0x8400, 0x8800, 0x8c00) if f'kn-{x:04x}' in by)
    return ok


def write_tsv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        w = csv.writer(stream, delimiter='\t')
        w.writerow(header)
        w.writerows(rows)


def emit(path, records):
    for r in records:
        r['gate'] = arm_gate(r)
    cal = calibrated(records)
    write_tsv(path, ['arm', 'repeat', 'spec', 'observation', 'gate'],
              [(r['arm']['id'], i+1, json.dumps(r['arm']), json.dumps(r['obs'][i]),
                'pass' if cal and r['gate'] else 'gate_failed') for r in records for i in range(2)])
    return cal and bool(records) and all(r['gate'] for r in records)


def load(path):
    with path.open(encoding='utf-8', newline='') as stream:
        rows = [r for r in csv.DictReader(stream, delimiter='\t') if r['repeat'] == '1']
    return [dict(arm=json.loads(r['spec']), obs=[json.loads(r['observation'])], gate=r['gate'] == 'pass') for r in rows]


def report(path):
    """結果ノートに書く数値だけ（境界・m・T・誤り番号・ポートの値列）。本文なし。"""
    recs = load(path)
    out = []
    base = None
    for r in recs:
        a, o = r['arm'], r['obs'][0]
        if 'failed' in o:
            out.append(f"{a['id']} 採取失敗 {o['failed']}")
        elif a['kind'] == 'cl':
            line = f"{a['id']} gate={r['gate']} b5={o['b5']} ({o['b5'] and hex(o['b5'])}) b7={o['b7']} ({o['b7'] and hex(o['b7'])}) m={o['m']} T={o['T']} "\
                   f"b7-T={None if o['T'] is None or o['b7'] is None else o['b7']-o['T']} b5-T={None if o['T'] is None or o['b5'] is None else o['b5']-o['T']} rounds={o['rounds']} mono={o['mono']} slope={o['slope']} other={o['other']}"
            out.append(line)
        elif a['kind'] == 'cf':
            out.append(f"{a['id']} gate={r['gate']} T={o.get('T')} tests={[(t['x'], t['want'], t['got']) for t in o.get('tests', [])]}")
        elif a['kind'] == 'stmts':
            out.append(f"{a['id']} gate={r['gate']}")
            for s, (e, f) in zip(a['stmts'], o['res']):
                out.append(f"  {s!r}: err={e} fre={f}")
        elif a['kind'] == 'port':
            out.append(f"{a['id']} gate={r['gate']} err={o['err']} crtc={o['crtc']} ports={json.dumps(o['ports'], sort_keys=True)}")
        else:
            out.append(f"{a['id']} gate={r['gate']} rows={o['rows']}")
    return '\n'.join(out)


# ---------------------------------------------------------------- 自己検査
def model(T, m, b5, bad=None):
    """合成の公式モデル: x<b5 → 誤り5、b5<=x<T+m → 誤り7、それ以外は受理（fre = x−T）。"""
    def fn(xs):
        def one(x):
            if x < b5:
                return (5, 0)
            if x - T < m:
                return (7, 0)
            return (0, x - T)
        res = [one(x) for x in xs]
        if bad == 'leak':       # 失敗プローブの後ろのアンカーが壊れる
            return dict(anchor=[one(ANCHOR_X), (0, ANCHOR_X - T - 1)], res=res)
        if bad == 'slope':
            res = [(e, f + 1) if e == 0 and x % 2 else (e, f) for (e, f), x in zip(res, xs)]
        if bad == 'nonmono':
            res = [(5, 0) if x == 0x9000 else t for t, x in zip(res, xs)]
        return dict(anchor=[one(ANCHOR_X), one(ANCHOR_X)], res=res)
    return fn


def synthetic_dump(rows):
    data = bytearray(b' '*3000)
    for i, row in enumerate(rows):
        text = (row[0] + ''.join(f' {x} ' for x in row[1:])).encode('ascii')
        data[i*120:i*120+len(text)] = text
    return bytes(data)


def selftest(work=None):
    work = work or WORK
    work.mkdir(parents=True, exist_ok=True)
    # --- 腕と打鍵行
    al = arms()
    assert len({a['id'] for a in al}) == len(al)
    for a in al:
        if a['kind'] in ('cl', 'cf'):
            program_lines(a, [0x8000+i for i in range(a.get('nvar', 14 if a['kind'] == 'cl' else 1))])
        else:
            program_lines(a)
    for a in known_arms():
        program_lines(a)
    base = program_lines(dict(id='x', kind='cl'), GRID[:14])
    assert base[:3] == ['new', '5 on error goto 950', '10 print "s9qa";1;1'] and base[-3:] == ['950 e=err:resume next', 'cls', 'run']
    assert '100 e=0:clear ,&he000' in base and '130 e=0:clear ,&he000' in base and '132 e=0:clear ,&he000' not in base  # 先頭・末尾アンカー（16本=100..130）
    stk = program_lines(dict(id='x', kind='cl', n=1024), [0x8000]*14)
    assert '100 e=0:clear ,&he000,1024' in stk
    strs = program_lines(dict(id='x', kind='cl', first=1000), [0x8000]*14)
    assert '100 e=0:clear 1000,&he000' in strs
    var = program_lines(dict(id='x', kind='cl', var=True), [0x8000]*14)
    assert any('b$=a$+a$+a$:clear ,&he000' in l for l in var)
    prem = [l for l in program_lines(dict(id='x', kind='cl', pad=('rem', 800)), [0x8000]*14) if ' rem ' in l]
    pdat = [l for l in program_lines(dict(id='x', kind='cl', pad=('data', 800)), [0x8000]*14) if ' data ' in l]
    assert len(prem) == len(pdat) >= 10 and all(len(l) < 80 for l in prem+pdat)
    arr = program_lines(dict(id='x', kind='cf', arr=500), [0x8400])
    assert '15 dim a(500)' in arr and sum('clear ,' in l for l in arr) == 2 and arr.index('15 dim a(500)') < arr.index('100 e=0:clear ,&h8400')
    cv = program_lines(al[[a['id'] for a in al].index('cv-1')])
    assert '100 e=0:clear ,&he000:on error goto 950:clear ,&h8400' in cv
    co = program_lines(al[[a['id'] for a in al].index('co-1')])
    assert '100 e=0:a$=chr$(300)' in co and '102 e=0:a$=1' in co
    assert all('clear' not in l for l in co)
    assert sum(1 for a in al if a['id'].startswith('co-')) == 6 and len(CO_STMTS) == 2+39+27+12
    assert sum(1 for a in al if a['id'].startswith('cp-')) == 28
    # --- 写しの解析（陽性・陰性）と本文非出力
    rows = [['s9qa', 1, 1], ['s9qr', 1, 5, 0], ['s9qr', 2, 0, 12345], ['s9qd', 1, 1]]
    d = bytearray(synthetic_dump(rows)); d[5*120:5*120+10] = b'SECRETTEXT'
    got, other = extract(bytes(d))
    assert got == rows and other == 1 and 'SECRET' not in json.dumps(got)
    assert probe_result(rows, 2) == [(5, 0), (0, 12345)]
    for bad in (rows[1:], rows[:-1], [rows[0], rows[2], rows[1], rows[3]], rows[:2]+[['s9qr', 2, 300, 1], rows[3]]):
        try:
            probe_result(bad, 2); raise AssertionError('不正な形が通った')
        except ValueError:
            pass
    assert extract(synthetic_dump([['s9qr', 1, 7, -282]]))[0] == [['s9qr', 1, 7, -282]]
    assert port_result([['s9qa', 1, 1], ['s9qe', 2, 5], ['s9qd', 1, 1]]) == 5 and port_result([['s9qa', 1, 1], ['s9qd', 1, 1]]) == 0
    # --- ポート記録: 窓・サブCPU・IN・対象外ポートの除外、連続同一の畳み込み
    def log(ev):
        lines = ['# seq clock frame cpu kind port value pc']
        for i, (fr, cpu, kind, port, val) in enumerate(ev):
            lines.append(f'{i:6d} {i:7d} {fr:6d}  {cpu:<4s}  {kind:<4s}  {port:04X}   {val:02X}   0000')
        return '\n'.join(lines)+'\n'
    ev = [(5, 'main', 'OUT', 0x52, 0x11), (100, 'main', 'OUT', 0x52, 0x40), (100, 'main', 'OUT', 0x52, 0x40),
          (101, 'main', 'OUT', 0x52, 0x00), (101, 'sub', 'OUT', 0x52, 0x77), (102, 'main', 'IN', 0x52, 0x66),
          (102, 'main', 'OUT', 0x40, 0x01), (102, 'main', 'OUT', 0x51, 0x81), (103, 'main', 'OUT', 0x58, 0x07),
          (900, 'main', 'OUT', 0x52, 0x22)]
    ps = port_summary(log(ev), 100, 300)
    assert ps == dict(crtc=1, ports={'52': [0x40, 0x00], '58': [7]}), ps
    # --- k分探索: 合成モデルで境界・m・T を復元（陽性）
    for T, m, b5 in ((35098, 0, 0x8600), (35600, 40, 0x8600), (36500, 0, 0x8200), (37900, 100, 0x8600), (0x9a00+70, 5, 0x8000+0x40)):
        r = search(model(T, m, b5))
        assert search_ok(r), (T, m, b5, {k: v for k, v in r.items() if k != 'trace'})
        assert r['b5'] == b5 and r['b7'] == T + m and r['m'] == m and r['T'] == T, (T, m, b5, r['b5'], r['b7'])
        assert all(len(t['xs']) == 14 for t in r['trace'])
    r = search(model(35098, 0, 0x8600), nvar=8)
    assert search_ok(r) and r['b7'] == 35098 and r['b5'] == 0x8600
    # --- k分探索の陰性: 失敗後のアンカー崩れ・傾き崩れ・非単調・境界が見つからない を拒否
    for bad in ('leak', 'slope', 'nonmono'):
        r = search(model(35098, 0, 0x8600, bad))
        assert not search_ok(r), bad
    r = search(model(35098, 0, 0x7000))         # b5 が格子の外（0x8000 が既に誤り5でない）
    assert r['b5'] is None and not search_ok(r)
    # --- 確認腕（cf）: base の式がそのまま通る陽性と、b5 が動くモデルの陰性
    base = search(model(35098, 0, 0x8600))
    def conf_fn(T, m, b5):
        mod = model(T, m, b5)
        return lambda xs: dict(anchor=[mod(xs)['anchor'][1]], res=mod(xs)['res'])
    assert confirm(conf_fn(35400, 0, 0x8600), base)['tests_ok']
    assert not confirm(conf_fn(35400, 7, 0x8600), base)['tests_ok']          # m が違う
    assert not confirm(conf_fn(35400, 0, 0x8700), base)['tests_ok']          # b5 が違う
    assert not confirm(conf_fn(35400, 0, 0x8600), dict(b5=None, m=None))['tests_ok']
    print('OK 腕・打鍵行・写しの解析（陽性・陰性・本文非出力）・ポート集計・k分探索（陽性5・陰性4）・確認腕（陽性・陰性3）', flush=True)
    # --- 関門・較正・記録（合成）
    def rec(spec, ob, ob2=None):
        return dict(arm=spec, obs=[ob, ob2 if ob2 is not None else ob])
    cl_ok = search(model(35098, 0, 0x8600))
    ks = [rec(a, dict(rows=[['s9de', 1, 5], ['s9dd', 1, 1]] if a['limit'] == 0x8400 else
                      [['s9de', 1, 7], ['s9dd', 1, 1]] if a['limit'] == 0x8800 else
                      [['s9da', 1, 1], ['s9dv', 2, 742], ['s9dd', 1, 1]])) for a in known_arms()]
    co1 = al[[a['id'] for a in al].index('co-1')]
    co_ok = rec(co1, dict(res=[[5, 0], [13, 0]] + [[0, 100]]*(len(co1['stmts'])-2)))
    cpb = rec(dict(id='cp-base', kind='port', stmt='rem'), dict(err=0, crtc=3, ports={}))
    cpo = rec(dict(id='cp-out52', kind='port', stmt='out &h52,&h40'), dict(err=0, crtc=3, ports={'52': [0x40]}))
    good = [rec(dict(id='cl-base', kind='cl'), cl_ok), co_ok, cpb, cpo] + ks
    with tempfile.TemporaryDirectory(prefix='l4s9q-emit-', dir=work) as t:
        out = Path(t)/'m.tsv'
        assert emit(out, [dict(r, obs=list(r['obs'])) for r in good])
        assert 'gate_failed' not in out.read_text()
        def failing(mod):
            gs = [dict(r, obs=list(r['obs'])) for r in good]
            mod(gs)
            return not emit(out, gs) and 'gate_failed' in out.read_text()
        assert failing(lambda g: g[4].update(obs=[dict(rows=[['s9de', 1, 7], ['s9dd', 1, 1]])]*2))       # 既知腕 0x8400 が誤り7
        assert failing(lambda g: g[1].update(obs=[dict(res=[[5, 0], [6, 0]] + [[0, 1]]*(len(co1['stmts'])-2))]*2))   # 参照の番号が違う
        assert failing(lambda g: g[3].update(obs=[dict(err=0, crtc=3, ports={'52': [0x41]})]*2))          # 陽性対照が0x52に0x40を示さない
        assert failing(lambda g: g[2].update(obs=[dict(err=0, crtc=0, ports={})]*2))                       # 捕捉が死んでいる（CRTC書き込み無し）
        assert failing(lambda g: g[0].update(obs=[cl_ok, dict(cl_ok, b7=cl_ok['b7']+1)]))                  # 2反復が不一致
        assert failing(lambda g: g[0].update(obs=[dict(failed='RuntimeError'), cl_ok]))                    # 採取失敗
        assert 'trace' not in report(out) and 'SECRET' not in report(out)
        emit(out, [dict(r, obs=list(r['obs'])) for r in good])
        assert 'cl-base' in report(out) and 'b7=35098' in report(out)
    print('OK 関門と較正の陽性・陰性6種（既知腕・参照番号・陽性対照・捕捉死・反復不一致・採取失敗）・記録の出力', flush=True)
    # --- 自作ROM: 既知腕の打鍵行は s9d と一致、複数プローブ方式と cp 基準を通す（現状は報告のみ）
    k = known_arms()[1]
    assert program_lines(k) == mm.program(dict(id='limit-8800', kind='limit', limit=0x8800))
    with tempfile.TemporaryDirectory(prefix='l4s9q-selftest-', dir=work) as t:
        root = Path(t)
        rom = root/'rom'
        built = subprocess.run([sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom), '--work-dir', str(root/'asm')],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert built.returncode == 0, '自作ROM一時ビルド失敗'
        spec = dict(id='own-cv', kind='stmts', wrap='clear', stmts=['clear ,&h8400', 'clear ,&h8800', 'clear ,&h8c00'])
        o1 = measure_one(rom, False, spec, root)
        o2 = measure_one(rom, False, spec, root)
        print('  自作の現状: cv（0x8400・0x8800・0x8C00）= '+json.dumps(o1.get('res', o1)), flush=True)
        assert o1 == o2 and 'failed' not in o1, '自作ROMで複数プローブ方式が走らない'
        pb = measure_one(rom, False, dict(id='cp-base', kind='port', stmt='rem'), root)
        assert 'failed' not in pb and pb['crtc'] >= 1 and pb['err'] == 0, pb
    print('OK 自作ROM: 複数プローブ方式（2走一致）・cp 基準（窓内にCRTC書き込み）', flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    m = sub.add_parser('measure')
    m.add_argument('--rom-dir')
    m.add_argument('--official', action='store_true')
    m.add_argument('--out', type=Path, required=True)
    m.add_argument('--work-dir', type=Path, default=WORK)
    m.add_argument('--only', default='', help='腕IDの接頭辞（カンマ区切り）。空なら全腕＋較正')
    m.add_argument('--jobs', type=int, default=4)
    r = sub.add_parser('report')
    r.add_argument('--measured', type=Path, required=True)
    s = sub.add_parser('selftest')
    s.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'report':
        print(report(args.measured))
        return 0
    rom = os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir):
        parser.error('公式ROMはPC88_REF_ROM_DIRだけ、自作ROMは--rom-dirで指定する')
    pre = tuple(x for x in args.only.split(',') if x)
    pool = known_arms() + arms()
    selected = [a for a in pool if (a['id'].startswith(pre) if pre else True)]
    records = measure(rom, args.official, selected, args.work_dir, args.jobs)
    ok = emit(args.out, records)
    print(f'記録完了: {len(records)}腕×2走、関門'+('通過' if ok else '失敗'))
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except AssertionError:
        raise
    except Exception as error:
        frames = traceback.extract_tb(error.__traceback__)
        print(f'NG 器具の検査または実行に失敗 ({type(error).__name__}, 行{frames[-1].lineno}、画面本文は非出力)')
        raise SystemExit(1)
