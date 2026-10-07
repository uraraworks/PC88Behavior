#!/usr/bin/env python3
"""l4-s9p: COLOR の属性域への書き方と、40桁時の CRTC カーソル位置を測る器具。

画面本文は扱わない。採るのは次の3種だけ。
 (1) 自作のアンカー（qa1・qb2・qc3）と自作の印（qi9・qz9・qs1・qs2）の、写し内の位置。
 (2) 自作の文字しか書かれない行（行9〜16 の一部）の属性域40バイトの生値（0x00 と 0x20 を区別）。
 (3) 誤りを起こす腕だけ、非空白行の署名（行番号・非空白文字数・SHA-256 先頭12桁）。本文は出さない。
     署名は既知の誤り（参照腕）の署名と一致するかの比較にだけ使う。
CRTC カーソルコマンド（0x80・0x81）に続くパラメータ列（制御ポートの値。データポートではない）。
生ログ・写しは作業置き場の一時ファイルで、採取後に器具が消す。事前登録は docs/notes/l4-s9p-color-attr-preregistration.md。
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
sys.path.insert(0, str(Path(__file__).resolve().parent))
import l4_listkw_measure as kw
import l4_widthvram_measure as wv

WORK = kw.REPO.parent / 'tmp/s9p-work'
IO_LINE = wv.IO_LINE
DEFAULT_PAIR = [0x80, 0x00]
ANCHORS = (('qa1', 0, 6), ('qb2', 0, 7), ('qc3', 10, 8))
CURSOR_CMDS = (0x80, 0x81)

# stmt 腕: (id, 文, 予測)。予測: cont 続行するか、row13・row14 の組（None は予測なし）、err 参照の誤り名（誤りを予測するとき）
STMT = [
    ('rem', 'rem', dict(cont=True, row13=[], row14=[])),
    ('fc', 'a$=chr$(300)', dict(cont=False, ref=True)),
    ('sn', 'a=*3', dict(cont=False, ref=True)),
    ('ul', 'goto 999', dict(cont=False, ref=True)),
    ('tm', 'a$=1', dict(cont=False, ref=True)),
    ('ov', 'a%=40000', dict(cont=False, ref=True)),
    ('c8', 'color 8', dict(cont=False, err='fc')),
    ('c255', 'color 255', dict(cont=False, err='fc')),
    ('c256', 'color 256', dict(cont=False, err='fc')),
    ('cm1', 'color -1', dict(cont=False, err='fc')),
    ('c2p5', 'color 2.5', dict(cont=True, row13=[[3, 3]], row14=[[3, 3]])),
    ('cbg8', 'color ,8', dict(cont=False, err='fc')),
    ('cstr', 'color "a"', dict(cont=False, err='tm')),
    ('fbg', 'color ,3', dict(cont=True, row13=[], row14=[])),
    ('ftwo', 'color 2,3', dict(cont=True, row13=[[3, 2]], row14=[[3, 2]])),
    ('ffg', 'color ,,,5', dict(cont=True, row13=[], row14=[])),
    ('fbare', 'color', dict(cont=True, row13=[], row14=[])),
    ('ffive', 'color 5,1,1,2,3', dict(cont=False, err='sn')),
    ('ffour', 'color 3,0,0,6', dict(cont=True, row13=[[3, 3]], row14=[[3, 3]])),
    ('fseq', 'color 3:color 5', dict(cont=True, row13=[[3, 5]], row14=[[3, 5]])),
]
REFS = ('fc', 'sn', 'ul', 'tm', 'ov')
CUR80 = ((0, 0), (1, 3), (10, 7), (39, 12), (79, 15))
CUR40 = ((0, 0), (1, 3), (10, 7), (20, 9), (39, 12))
MIX = ('m1', 'm2', 'm3', 'm4', 'm5')


def arms():
    out = []
    for cols, lst in ((80, CUR80), (40, CUR40)):
        for c, r in lst:
            out.append(dict(id=f'cur{cols}-c{c}r{r}', kind='cur', cols=cols, c=c, r=r))
    out.append(dict(id='val-80', kind='val', cols=80))
    for key, stmt, exp in STMT:
        out.append(dict(id=f'stmt-{key}', kind='stmt', cols=80, key=key, stmt=stmt))
    for cols in (80, 40):
        for m in MIX:
            out.append(dict(id=f'mix{cols}-{m}', kind='mix', cols=cols, m=m))
    return out


def program_lines(a):
    lines = {}
    if a['cols'] == 40:
        lines[5] = 'width 40'
    lines[10] = 'locate 0,6:print "qa1";:locate 0,7:print "qb2";'
    lines[12] = 'locate 10,8:print "qc3";'
    k = a['kind']
    if k == 'cur':
        lines[20] = f"locate {a['c']},{a['r']}"
        lines[30] = 'goto 30'
    elif k == 'val':
        n = 20
        for c in range(8):
            lines[n] = f'locate 0,{9+c}:color {c}:print "zzz";'
            n += 10
        lines[n] = f'goto {n}'
    elif k == 'stmt':
        lines[20] = a['stmt']
        lines[30] = 'locate 0,13:print "qi9";'
        lines[40] = 'locate 0,14:print "qz9";'
        lines[50] = 'goto 50'
    else:
        m = a['m']
        if m == 'm1':
            lines[20] = 'locate 0,13:color 2:print "zzz";:color 4:print "zzz";'
            end = 30
        elif m == 'm2':
            lines[20] = 'locate 0,13:for i=1 to 24:color 2+(i and 1):print "z";:next'
            end = 30
        elif m == 'm3':
            lines[20] = 'locate 0,13:color 2:print "zzz";:color 4:print "zzz";:color 6:print "zzz";'
            lines[30] = 'locate 3,13:color 5:print "yy";'
            end = 40
        elif m == 'm4':
            lines[20] = 'locate 0,13:color 2:print "zzz";:color 0:print "zzz";:color 4:print "zzz";'
            end = 30
        else:
            lines[20] = 'locate 0,14:color 2:print "qs1";:color 4:print "qs2";:color 0'
            lines[30] = 'locate 0,15:for i=1 to 6:print:next'
            end = 40
        lines[end] = f'goto {end}'
    assert all(len(f'{n} {s}') < 80 and s.isascii() and s == s.lower() for n, s in lines.items()), lines
    return lines


def plan(a):
    return ['new'] + [f'{n} {s}' for n, s in sorted(program_lines(a).items())] + ['cls', ('window',), 'run', ('capture', 'result')]


# ---------------------------------------------------------------- 写しの解析
def pairs_of(raw):
    return [[raw[2*i], raw[2*i+1]] for i in range(20)]


def nontrivial(raw):
    return [p for p in pairs_of(raw) if p != DEFAULT_PAIR]


def rest_default(raw):
    """最初の未使用の組より後ろが全て未使用の組か（組が先頭から詰まっているか）。"""
    ps = pairs_of(raw)
    seen = False
    for p in ps:
        if p == DEFAULT_PAIR:
            seen = True
        elif seen:
            return False
    return True


def row_sig(data, S, skip):
    """非空白行の署名（行番号・非空白文字数・SHA-256先頭12桁）。本文は出さない。文字域は行内0〜79。"""
    out = []
    for r in range(0, 19):
        if r in skip:
            continue
        seg = data[r*S:r*S+80]
        n = sum(b not in (0x20, 0x00) for b in seg)
        if n:
            out.append([r, n, hashlib.sha256(bytes(seg)).hexdigest()[:12]])
    return out


def analyze(data, a):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    toks = {t: wv.find_token(data, t) for t, _, _ in ANCHORS}
    missing = [[t, len(h)] for t, h in toks.items() if len(h) != 1]
    out = dict(kind=a['kind'], missing=missing, fit=dict(linear=False))
    if missing:
        return out
    found = {t: h[0] for t, h in toks.items()}
    S = found['qb2'][0]-found['qa1'][0]
    k10 = found['qc3'][0]-found['qa1'][0]-2*S
    gap = found['qa1'][1]
    ok = S > 0 and k10 % 10 == 0 and len({v[1] for v in found.values()}) == 1
    k = k10//10 if ok else None
    out['fit'] = dict(S=S, k=k, gap=gap, linear=bool(ok), qa1_row=found['qa1'][0]//S if S > 0 else None)
    if not ok:
        return out
    row = lambda r: list(data[r*S+80:r*S+120])
    kind = a['kind']
    if kind == 'val':
        out['raw'] = {str(9+c): row(9+c) for c in range(8)}
    elif kind == 'stmt':
        qi, qz = wv.find_token(data, 'qi9'), wv.find_token(data, 'qz9')
        out['tok'] = dict(qi9=len(qi), qz9=len(qz))
        out['cont'] = len(qi) == 1 and len(qz) == 1
        out['raw'] = {'13': row(13), '14': row(14)}
        out['sig'] = row_sig(data, S, {6, 7, 8, 13, 14})
    elif kind == 'mix':
        if a['m'] == 'm5':
            h1, h2 = wv.find_token(data, 'qs1'), wv.find_token(data, 'qs2')
            out['tok'] = dict(qs1=len(h1), qs2=len(h2))
            if len(h1) == 1 and len(h2) == 1:
                r1 = h1[0][0]//S
                out['row'] = r1
                out['raw'] = {'row': row(r1)}
        else:
            out['raw'] = {'13': row(13)}
    return out


# ---------------------------------------------------------------- ポート（カーソルコマンドのパラメータ）
def cursor_summary(text, win_from, win_to):
    cmds, cur = [], None
    for line in text.splitlines():
        m = IO_LINE.match(line)
        if not m or m[4] != 'main' or m[5] != 'OUT':
            continue
        frame, port, val = int(m[3]), int(m[6], 16), int(m[7], 16)
        if not (win_from <= frame < win_to):
            continue
        if port == 0x51:
            if cur is not None:
                cmds.append(cur)
            cur = [val, []]
        elif port == 0x50 and cur is not None:
            cur[1].append(val)
    if cur is not None:
        cmds.append(cur)
    rle = []
    for c in cmds:
        if c[0] not in CURSOR_CMDS:
            continue
        if rle and rle[-1][:2] == c:
            rle[-1][2] += 1
        else:
            rle.append([c[0], list(c[1]), 1])
    return dict(n=len(rle), last=rle[-4:])


# ---------------------------------------------------------------- 走らせる
def run_arm(rom, official, a, work):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    window, dump = None, None
    for step in plan(a):
        if isinstance(step, str):
            args += ['--type-at', str(at), '--type', step+'\n']
            at += (len(step)+1)*8+240+(wv.RUN_WAIT if step == 'run' else 0)
        elif step[0] == 'window':
            window = at
        else:
            dump = (work/'vram.bin', at+200)
            args += ['--vram-dump', str(dump[0]), '--vram-dump-at', str(dump[1])]
            at = dump[1]+100
    iolog = work/'port.txt'
    args += ['--io-log', str(iolog), '--io-log-from-frame', str(wv.PORT_FROM), '--frames', str(at+100)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if (proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr):
            raise RuntimeError('測定器の実行または打鍵に失敗')
        data = dump[0].read_bytes()
        obs = analyze(data, a)
        obs['cur'] = cursor_summary(iolog.read_text(encoding='utf-8', errors='replace'), window, dump[1]+1)
        return obs
    finally:
        for p in (dump[0] if dump else None, iolog):
            if p:
                Path(p).unlink(missing_ok=True)
                Path(str(p)+'.info.txt').unlink(missing_ok=True)


def valid(obs, a):
    if not isinstance(obs, dict) or obs.get('kind') != a['kind'] or obs.get('missing') or not obs['fit'].get('linear'):
        return False
    k = a['kind']
    if k == 'cur':
        return obs['cur']['n'] >= 1
    if k == 'val':
        return len(obs.get('raw', {})) == 8
    if k == 'stmt':
        return 'raw' in obs and 'sig' in obs
    if a['m'] == 'm5':
        return 'row' in obs and 'raw' in obs
    return 'raw' in obs


def measure(rom, official, selected, work):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='measure-', dir=work) as temp:
        for a in selected:
            obs, failed = [], []
            for _ in range(2):
                try:
                    obs.append(run_arm(rom, official, a, Path(temp))); failed.append(False)
                except Exception:
                    obs.append({}); failed.append(True)
            gate = not any(failed) and all(valid(o, a) for o in obs) and obs[0] == obs[1]
            records.append(dict(arm=a, obs=obs, failed=failed, gate=gate))
    return records


# ---------------------------------------------------------------- 予測（事前登録 l4-s9p-color-attr-preregistration.md）
def mix_expect(a):
    """混在の予測。80桁は区間終端桁そのもの、40桁は 2×終端桁−1（s9o の規則）。"""
    pos = (lambda e: e) if a['cols'] == 80 else (lambda e: 2*e-1)
    m = a['m']
    if m in ('m1', 'm5'):
        return [[pos(3), 2], [pos(6), 4]]
    if m == 'm2':
        return [[pos(i), 3 if i % 2 else 2] for i in range(1, 21)]
    if m == 'm3':
        return [[pos(3), 2], [pos(5), 5], [pos(6), 4], [pos(9), 6]]
    return [[pos(3), 2], [pos(6), 0], [pos(9), 4]]


def errsig(obs, base):
    b = {tuple(x) for x in (base or [])}
    return sorted(tuple(x) for x in obs.get('sig', []) if tuple(x) not in b)


def judge(obs, a, ctx=None):
    """予測との比較。ctx に base（stmt-rem の署名）と refs（参照名→誤り署名）。"""
    k = a['kind']
    if k == 'cur':
        last = obs['cur']['last'][-1] if obs['cur']['last'] else None
        want = [a['c'], a['r']] if a['cols'] == 80 else [2*a['c'], a['r']]
        alt = [a['c'], a['r']]
        got = last[1] if last else None
        return dict(params='agree' if got == want else 'differ', alt_plain='match' if got == alt else 'no')
    if k == 'val':
        res = {}
        for c in range(8):
            want = [] if c == 0 else [[3, c]]
            res[f'n{c}'] = 'agree' if nontrivial(obs['raw'][str(9+c)]) == want else 'differ'
        return res
    if k == 'stmt':
        exp = {key: e for key, _, e in STMT}[a['key']]
        res = dict(cont='agree' if obs['cont'] == exp['cont'] else 'differ')
        if exp['cont'] and obs['cont']:
            res['row13'] = 'agree' if nontrivial(obs['raw']['13']) == exp['row13'] else 'differ'
            res['row14'] = 'agree' if nontrivial(obs['raw']['14']) == exp['row14'] else 'differ'
        if 'err' in exp and ctx:
            got = errsig(obs, ctx.get('base'))
            res['err'] = 'agree' if got and got == ctx['refs'].get(exp['err']) else 'differ'
        return res
    if a['m'] == 'm5':
        return dict(pairs='agree' if nontrivial(obs['raw']['row']) == mix_expect(a) else 'differ')
    return dict(pairs='agree' if nontrivial(obs['raw']['13']) == mix_expect(a) else 'differ')


def context(records):
    by = {r['arm']['id']: r for r in records if r['obs'] and r['obs'][0]}
    base = by['stmt-rem']['obs'][0].get('sig') if 'stmt-rem' in by else None
    refs = {n: errsig(by[f'stmt-{n}']['obs'][0], base) for n in REFS if f'stmt-{n}' in by}
    return dict(base=base, refs=refs)


def calibrated(records):
    """較正の関門: stmt-rem が続行・組なし・S=120/k=1、参照の誤り署名が空でなく互いに異なる。"""
    by = {r['arm']['id']: r for r in records}
    ok = True
    if 'stmt-rem' in by:
        r = by['stmt-rem']
        o = r['obs'][0] if r['obs'] else {}
        ok = bool(r['gate'] and o.get('cont') and nontrivial(o['raw']['13']) == [] and nontrivial(o['raw']['14']) == []
                  and o['fit'].get('S') == 120 and o['fit'].get('k') == 1)
        refs = context(records)['refs']
        vals = [tuple(refs[n]) for n in refs]
        ok = ok and all(vals) and len(set(vals)) == len(vals) and len(refs) == len(REFS)
    return ok


def write_tsv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        w = csv.writer(stream, delimiter='\t')
        w.writerow(header); w.writerows(rows)


def emit(path, records, need_cal=True):
    known = {a['id']: a for a in arms()}
    for r in records:
        r['gate'] = (r['gate'] and r['arm'] == known.get(r['arm']['id']) and len(r['obs']) == 2
                     and all(valid(o, r['arm']) for o in r['obs']) and r['obs'][0] == r['obs'][1])
    cal = calibrated(records) if need_cal else True
    ctx = context(records) if any(r['arm']['id'] == 'stmt-rem' for r in records) else None
    write_tsv(path, ['arm', 'repeat', 'plan', 'observation', 'gate', 'prediction_judgement', 'failed'],
              [(r['arm']['id'], i+1, json.dumps(plan(r['arm'])), json.dumps(r['obs'][i]),
                'pass' if cal and r['gate'] else 'gate_failed',
                json.dumps(judge(r['obs'][0], r['arm'], ctx)) if cal and r['gate'] else 'gate_failed',
                int(r['failed'][i])) for r in records for i in range(2)])
    return cal and bool(records) and all(r['gate'] for r in records)


def report(measured):
    """結果ノートに書く数値だけを出す（属性域の組・カーソルのパラメータ・署名の一致。本文なし）。"""
    with measured.open(encoding='utf-8', newline='') as stream:
        rows = [r for r in csv.DictReader(stream, delimiter='\t') if r['repeat'] == '1']
    known = {a['id']: a for a in arms()}
    recs = [dict(arm=known[r['arm']], obs=[json.loads(r['observation'])], gate=r['gate']) for r in rows]
    ctx = context(recs)
    lines = []
    for r in recs:
        a, o = r['arm'], r['obs'][0]
        lines.append(f"## {a['id']} gate={r['gate']} judge={json.dumps(judge(o, a, ctx))}")
        k = a['kind']
        lines.append(f"  fit={json.dumps(o['fit'])}")
        if k == 'cur':
            lines.append(f"  cursor last4[cmd,params,count]={json.dumps(o['cur']['last'])}")
        elif k == 'val':
            for row, raw in o['raw'].items():
                lines.append(f"  row{row} pairs={json.dumps(nontrivial(raw))} rest_default={rest_default(raw)} raw[:8]={raw[:8]}")
        elif k == 'stmt':
            e = errsig(o, ctx['base'])
            match = [n for n, s in ctx['refs'].items() if s and s == e]
            lines.append(f"  cont={o['cont']} errrows={[x[0] for x in e]} matches_ref={match}")
            for row, raw in o['raw'].items():
                lines.append(f"  row{row} pairs={json.dumps(nontrivial(raw))} rest_default={rest_default(raw)}")
        else:
            for row, raw in o['raw'].items():
                lines.append(f"  row{row} pairs={json.dumps(nontrivial(raw))} rest_default={rest_default(raw)} raw={raw}")
            if a['m'] == 'm5':
                lines.append(f"  qs1_row={o['row']} qa1_row={o['fit']['qa1_row']} (起動時 qa1=6)")
        lines.append(f"  [cursor n={o['cur']['n']}]")
    return '\n'.join(lines)


# ---------------------------------------------------------------- 自己検査
def synthetic_dump(S=120, k=1, rows=None, toks=(), sig_rows=()):
    data = bytearray([0x20]*3000)
    for t, c, r in ANCHORS+tuple(toks):
        for j, ch in enumerate(t):
            data[r*S+c*k+j*k] = ord(ch)
            for q in range(1, k):
                data[r*S+c*k+j*k+q] = 0x20
    for r in range(25 if S >= 120 else 0):
        data[r*S+80:r*S+120] = bytes([0x80, 0x00]*20)
    for r, raw in (rows or {}).items():
        data[r*S+80:r*S+80+len(raw)] = bytes(raw)
    for r in sig_rows:
        data[r*S+2:r*S+7] = b'ZZSEC'
    return bytes(data)


def pairs_raw(*pairs):
    raw = [x for p in pairs for x in p]
    return raw+[0x80, 0x00]*(20-len(pairs))


def fake_obs(a, cont=True, **kw_):
    a2 = a
    toks = (('qi9', 0, 13), ('qz9', 0, 14)) if a['kind'] == 'stmt' and cont else ()
    rows = {13: pairs_raw(), 14: pairs_raw()}
    rows.update(kw_.get('rows', {}))
    o = analyze(synthetic_dump(rows=rows, toks=toks, sig_rows=kw_.get('sig_rows', ())), a2)
    o['cur'] = dict(n=0, last=[])
    return o


def selftest(work=None):
    if work is not None:
        work.mkdir(parents=True, exist_ok=True)
    known = {a['id']: a for a in arms()}
    assert len(known) == 41, len(known)
    for a in known.values():
        program_lines(a); plan(a)
    # アンカーの回復（陽性）と欠け・ずれ・重複（陰性）
    for S, k in ((120, 1), (120, 2), (100, 2)):
        o = analyze(synthetic_dump(S, k), known['stmt-rem'])
        assert o['fit']['linear'] and o['fit']['S'] == S and o['fit']['k'] == k, o['fit']
    d = bytearray(synthetic_dump()); d[wv.find_token(bytes(d), 'qb2')[0][0]] = ord('x')
    assert analyze(bytes(d), known['stmt-rem'])['missing'] == [['qb2', 0]]
    d = bytearray(synthetic_dump()); d[2990:2993] = b'qa1'
    assert analyze(bytes(d), known['stmt-rem'])['missing'] == [['qa1', 2]]
    d = bytearray(synthetic_dump()); p = wv.find_token(bytes(d), 'qc3')[0][0]
    d[p:p+3] = b'   '; d[p+1:p+4] = b'qc3'
    assert not analyze(bytes(d), known['stmt-rem'])['fit']['linear']
    # 属性域の組の読み出し（0x00 と 0x20 の区別・先頭詰め）
    assert nontrivial(pairs_raw([3, 2], [6, 4])) == [[3, 2], [6, 4]]
    raw = pairs_raw([3, 0x20]); assert nontrivial(raw) == [[3, 0x20]] and rest_default(raw)
    raw = pairs_raw([3, 2]); raw[10:12] = [9, 1]; assert not rest_default(raw)
    # val・mix・stmt の判定（陽性・陰性）
    av = known['val-80']
    rows = {9+c: pairs_raw() if c == 0 else pairs_raw([3, c]) for c in range(8)}
    o = analyze(synthetic_dump(rows=rows), av); o['cur'] = dict(n=0, last=[])
    assert set(judge(o, av).values()) == {'agree'}
    rows[12] = pairs_raw([3, 0x30])
    o = analyze(synthetic_dump(rows=rows), av)
    assert judge(o, av)['n3'] == 'differ'
    for cols, S, k in ((80, 120, 1), (40, 120, 2)):
        for m in MIX:
            am = known[f'mix{cols}-{m}']
            e = mix_expect(am)
            raw = pairs_raw(*e)
            key = '13' if m != 'm5' else 'row'
            toks = (('qs1', 0, 14), ('qs2', 3, 14)) if m == 'm5' else ()
            rowsd = {14: raw} if m == 'm5' else {13: raw}
            o = analyze(synthetic_dump(S, k, rowsd, toks), am)
            assert judge(o, am)['pairs'] == 'agree', (m, e)
            bad = [list(p) for p in e]; bad[0][0] += 1
            rowsd = {14: pairs_raw(*bad)} if m == 'm5' else {13: pairs_raw(*bad)}
            o = analyze(synthetic_dump(S, k, rowsd, toks), am)
            assert judge(o, am)['pairs'] == 'differ'
    assert mix_expect(known['mix40-m2'])[0] == [1, 3] and mix_expect(known['mix40-m2'])[19] == [39, 2]
    # stmt: 続行しない腕は qi9 が無い。署名は本文を出さず、参照との一致で誤りの種類を比べる
    ctx_sig = {}
    base = fake_obs(known['stmt-rem'])
    assert base['cont']
    def err_obs(arm_id, row, text):
        d = bytearray(synthetic_dump(sig_rows=()))
        d[row*120+1:row*120+1+len(text)] = text
        o = analyze(bytes(d), known[arm_id]); o['cur'] = dict(n=0, last=[]); return o
    o_fc, o_sn = err_obs('stmt-fc', 2, b'ZZFCERROR'), err_obs('stmt-sn', 2, b'ZZSNERROR')
    o_c8 = err_obs('stmt-c8', 2, b'ZZFCERROR')
    assert not o_c8['cont'] and 'ZZ' not in json.dumps(o_c8) and 'ERROR' not in json.dumps(o_c8)
    ctx = dict(base=base['sig'], refs={'fc': errsig(o_fc, base['sig']), 'sn': errsig(o_sn, base['sig'])})
    assert errsig(o_fc, base['sig']) != errsig(o_sn, base['sig']) and errsig(o_fc, base['sig'])
    assert judge(o_c8, known['stmt-c8'], ctx)['err'] == 'agree'
    o_c8s = err_obs('stmt-c8', 2, b'ZZSNERROR')
    assert judge(o_c8s, known['stmt-c8'], ctx)['err'] == 'differ'       # 別の誤りなら differ
    o_ok = fake_obs(known['stmt-ftwo'], rows={13: pairs_raw([3, 2]), 14: pairs_raw([3, 2])})
    assert set(judge(o_ok, known['stmt-ftwo']).values()) == {'agree'}
    o_ok = fake_obs(known['stmt-ftwo'], rows={13: pairs_raw([3, 2]), 14: pairs_raw()})
    assert judge(o_ok, known['stmt-ftwo'])['row14'] == 'differ'
    # カーソルコマンドの集計（窓・サブCPU・IN・他のコマンドの除外、連続同一の畳み込み）
    def log(events):
        lines = ['# seq clock frame cpu kind port value pc']
        for i, (fr, cpu, kind, port, val) in enumerate(events):
            lines.append(f'{i:6d} {i:7d} {fr:6d}  {cpu:<4s}  {kind:<4s}  {port:04X}   {val:02X}   0000')
        return '\n'.join(lines)+'\n'
    ev = [(5, 'main', 'OUT', 0x51, 0x81), (5, 'main', 'OUT', 0x50, 0x01), (5, 'main', 'OUT', 0x50, 0x01),
          (100, 'main', 'OUT', 0x51, 0x81), (100, 'main', 'OUT', 0x50, 0x14), (100, 'main', 'OUT', 0x50, 0x09),
          (101, 'main', 'OUT', 0x51, 0x81), (101, 'main', 'OUT', 0x50, 0x14), (101, 'main', 'OUT', 0x50, 0x09),
          (101, 'sub', 'OUT', 0x51, 0x81), (101, 'sub', 'OUT', 0x50, 0x63),
          (102, 'main', 'OUT', 0x51, 0x00), (102, 'main', 'OUT', 0x50, 0x4F),
          (103, 'main', 'OUT', 0x51, 0x80), (103, 'main', 'OUT', 0x50, 0x28), (103, 'main', 'OUT', 0x50, 0x09),
          (900, 'main', 'OUT', 0x51, 0x81), (900, 'main', 'OUT', 0x50, 0x00)]
    cs = cursor_summary(log(ev), 100, 300)
    assert cs == dict(n=2, last=[[0x81, [0x14, 9], 2], [0x80, [0x28, 9], 1]]), cs
    ac = known['cur40-c10r7']
    oc = dict(cur=dict(n=2, last=[[0x81, [20, 7], 5]]))
    assert judge(oc, ac) == dict(params='agree', alt_plain='no')
    oc = dict(cur=dict(n=2, last=[[0x81, [10, 7], 5]]))
    assert judge(oc, ac) == dict(params='differ', alt_plain='match')
    assert judge(dict(cur=dict(n=2, last=[[0x81, [10, 7], 5]])), known['cur80-c10r7'])['params'] == 'agree'
    print('OK アンカー回復・欠け・ずれ・重複・組の読み出し・val/mix/stmt の判定（陽性・陰性）・署名の本文非出力・カーソル集計', flush=True)
    # 較正の関門と記録の出力（合成）
    def good_records():
        recs = []
        errtext = {'fc': b'ZZ1', 'sn': b'ZZ2', 'ul': b'ZZ3', 'tm': b'ZZ4', 'ov': b'ZZ5'}
        for a in known.values():
            if a['id'] in [f'stmt-{n}' for n in REFS]:
                o = err_obs(a['id'], 2, errtext[a['key']])
            elif a['kind'] == 'stmt':
                o = fake_obs(a)
            else:
                o = dict(kind=a['kind'], missing=[], fit=dict(S=120, k=1, linear=True), cur=dict(n=1, last=[[0x81, [0, 0], 1]]),
                         raw={'13': pairs_raw()})
            recs.append(dict(arm=a, obs=[o, o], failed=[False, False], gate=True))
        return recs
    recs = good_records()
    assert calibrated(recs)
    with tempfile.TemporaryDirectory(prefix='l4s9p-emit-', dir=work) as temp:
        out = Path(temp)/'m.tsv'
        cal_only = [r for r in recs if r['arm']['kind'] == 'stmt']
        emit(out, cal_only)
        assert 'ZZ' not in out.read_text() and 'gate_failed' not in out.read_text()
        bad = good_records()
        bad[[r['arm']['id'] for r in bad].index('stmt-sn')]['obs'] = [err_obs('stmt-sn', 2, b'ZZ1')]*2   # 参照どうしの署名が同じ
        assert not calibrated(bad)
        bad = good_records()
        i = [r['arm']['id'] for r in bad].index('stmt-rem')
        bad[i]['obs'] = [fake_obs(known['stmt-rem'], rows={13: pairs_raw([3, 1])})]*2     # 基準に組がある
        assert not calibrated(bad)
        bad = good_records()
        i = [r['arm']['id'] for r in bad].index('stmt-fc')
        bad[i]['obs'] = [fake_obs(known['stmt-fc'])]*2                                     # 誤りが起きていない参照
        assert not calibrated(bad)
        assert not emit(out, bad) and 'gate_failed' in out.read_text()
    print('OK 較正の関門（陰性3種）・記録の出力・本文非出力', flush=True)
    # 自作ROMの既知値対照: stmt-rem（80桁・組なし）・mix80-m1・cur80
    with tempfile.TemporaryDirectory(prefix='l4s9p-selftest-', dir=work) as temp:
        root = Path(temp)
        rom = root/'rom'
        built = subprocess.run([sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom),
                                '--work-dir', str(root/'asm')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert built.returncode == 0, '自作ROM一時ビルド失敗'
        own = [known['stmt-rem'], known['mix80-m1'], known['cur80-c10r7']]
        observed = measure(rom, False, own, root)
        bad = [r['arm']['id'] for r in observed if not r['gate']]
        if bad:
            print('NG 自作ROMの既知値対照: '+','.join(bad))
            for r in observed:
                print(json.dumps(dict(arm=r['arm']['id'], failed=r['failed'], gate=r['gate'],
                                      obs=[{k: v for k, v in o.items() if k in ('missing', 'fit', 'cont', 'cur')} for o in r['obs']])))
        assert not bad
        o = observed[0]['obs'][0]
        assert o['cont'] and o['fit']['S'] == 120 and o['fit']['k'] == 1 and nontrivial(o['raw']['13']) == []
        # 自作の現状（一致・不一致は報告するだけ。自作が公式の規則を実装済みかは別の段の話）
        print('  自作の現状: m1='+json.dumps(judge(observed[1]['obs'][0], own[1]))+' cur80='
              +json.dumps(judge(observed[2]['obs'][0], own[2])), flush=True)
        # 故障注入: 基準（組なし）の観測を (3,2) を期待する腕で判定すると differ になる
        assert judge(observed[0]['obs'][0], known['stmt-ftwo'])['row13'] == 'differ'
        assert judge(observed[0]['obs'][0], known['stmt-rem'])['row13'] == 'agree'
    print('OK 自作ROMの既知値対照3腕×2走（stmt-rem・mix80-m1・cur80）・故障注入で判定が differ', flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    m = sub.add_parser('measure'); m.add_argument('--rom-dir')
    m.add_argument('--official', action='store_true'); m.add_argument('--out', type=Path, required=True)
    m.add_argument('--work-dir', type=Path, default=WORK)
    m.add_argument('--only', default='', help='腕IDの接頭辞（カンマ区切り）。空なら全腕')
    r = sub.add_parser('report'); r.add_argument('--measured', type=Path, required=True)
    s = sub.add_parser('selftest'); s.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'report':
        print(report(args.measured)); return 0
    rom = os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir):
        parser.error('公式ROMはPC88_REF_ROM_DIRだけ、自作ROMは--rom-dirで指定する')
    pre = tuple(x for x in args.only.split(',') if x)
    selected = [a for a in arms() if not pre or a['id'].startswith(pre)]
    records = measure(rom, args.official, selected, args.work_dir)
    full = len(selected) == len(arms())
    ok = emit(args.out, records, need_cal=full)
    print(f'記録完了: {len(records)}腕×2走、関門'+('通過' if ok else '失敗')+('' if full else '（部分腕。較正と署名の判定は結合後に report で）'))
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
