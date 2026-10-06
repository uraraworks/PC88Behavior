#!/usr/bin/env python3
"""l4-s9o: WIDTH 40／行数20 のときのテキストVRAMの並びと、モード切替のポート・CRTC 設定を測る器具。

画面本文は扱わない。採るのは次の3種だけ。
 (1) こちらが打った既知の短い印（小文字2字＋数字1字。例 qa1）の、写し（F3C8〜FF7F の3000バイト）の中の
     バイト位置と文字の間隔。位置は「印の文字そのもの」に限る。
 (2) 印を置いた行の、印のセルの外にある空白でないバイト（属性域）の行内位置と値。印の行は自作の印しか書かれない行だけ。
 (3) 印の行以外で、空白でないバイトを含む行の番号と領域の区別（文字域か属性域か）。値・長さは出さない。
モード切替の OUT は、窓の中のメインCPUの OUT のうち、制御ポート（0x30・0x31 等のシステム制御、CRTC の 0x51 コマンドと 0x50 の
パラメータ、DMAC の 0x64・0x65・0x68）だけを順序つきで採る。カーソル位置の更新（CRTC コマンド 0x80・0x81）は件数だけ。
公式ROM由来のバイト列は扱わない。生ログ・写しは作業置き場の一時ファイルで、採取後に器具が消す。
"""
import argparse
import contextlib
import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import traceback
import l4_listkw_measure as kw

WORK = kw.REPO.parent / 'tmp/s9o-work'
STRIDE_BOOT = 120
IO_LINE = re.compile(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(main|sub)\s+(OUT|IN)\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})\s')
PORT_FROM = 1
RUN_WAIT = 3000            # run を打ってから写しを取るまでの余裕（フレーム）
# 制御ポート: システム制御・CRTC・DMAC のみ。0x50/0x51 はコマンド単位に畳む。
VALUE_PORTS = (0x30, 0x31, 0x32, 0x34, 0x35, 0x53, 0x64, 0x65, 0x66, 0x67, 0x68)
CURSOR_CMDS = (0x80, 0x81)   # カーソル位置の読み込み（0x81 は表示つき）。パラメータは位置なので件数だけ採る

# 印: (名前, 桁, 行)。桁 None は「最終桁−2」（桁数で変わる）。
TOKENS = [('qa1', 0, 6), ('qb2', 0, 7), ('qc3', 0, 8), ('qd4', 10, 9), ('qe5', 20, 10),
          ('qf6', None, 11), ('qg7', 0, 12), ('qh8', 5, 12)]
LAST = ('qz9', 0, 16)       # 最後の印。直後の行（17）に公式のプロンプトが出る
OK_ROW = 17
TOKEN_ROWS = (6, 7, 8, 9, 10, 11, 12, 16)
ERASE_TOKENS = [('qk1', 0, 6), ('qm3', 60, 8), ('qn4', 0, 21)]
ERASE_POST = ('qz9', 0, 14)

# モード行。layout 腕は起動時の 80桁・20行 から切り替える。erase 腕は先に width 80,25 にして印を置く。
MODES = (
    ('rem', 'rem', 80, 20),
    ('w40', 'width 40', 40, 20),
    ('w40-20', 'width 40,20', 40, 20),
    ('w40-25', 'width 40,25', 40, 25),
    ('w80-20', 'width 80,20', 80, 20),
    ('w80-25', 'width 80,25', 80, 25),
)
ERASE_MODES = (
    ('rem', 'rem', None, None),
    ('w40', 'width 40', 40, 25),
    ('w40-20', 'width 40,20', 40, 20),
    ('w80-20', 'width 80,20', 80, 20),
    ('w80-25', 'width 80,25', 80, 25),
)


COLOR_MODES = ('rem', 'w40', 'w40-25', 'w80-20', 'w80-25')
COLOR_TOKENS = [('qa1', 0, 6, None), ('qb2', 0, 7, None), ('qi9', 0, 13, 2), ('qj0', 10, 14, 3), ('qy7', 20, 15, 4)]


def arms():
    out = []
    for key, line, cols, rows in MODES:
        out.append(dict(id=f'layout-{key}', kind='layout', mode=line, cols=cols, rows=rows))
    for key, line, cols, rows in ERASE_MODES:
        out.append(dict(id=f'erase-{key}', kind='erase', mode=line, cols=cols, rows=rows))
    for key, line, cols, rows in MODES:      # 追補1: 色の境界の位置バイトの規則と、切替のOUTの順序
        if key in COLOR_MODES:
            out.append(dict(id=f'color-{key}', kind='color', mode=line, cols=cols, rows=rows))
    return out


def base_arms():
    return [a for a in arms() if a['kind'] != 'color']


def lastcol(a):
    return a['cols']-3


def program_lines(a):
    """打鍵する行（行番号つき）。1行は80文字未満・小文字ASCII。先頭の行から run で実行する。"""
    def put(tok, col, row):
        return f'locate {col},{row}:print "{tok}";'
    lines = {}
    if a['kind'] == 'color':
        lines[10] = a['mode']
        n = 20
        for tok, col, row, color in COLOR_TOKENS:
            lines[n] = (put(tok, col, row) if color is None else
                        f'locate {col},{row}:color {color}:print "{tok}";:color 7')
            n += 10
        lines[n] = put(*LAST)
    elif a['kind'] == 'layout':
        lines[10] = a['mode']
        n = 20
        for tok, col, row in TOKENS:
            col = lastcol(a) if col is None else col
            if tok == 'qh8':
                lines[n] = f'locate {col},{row}:color 2:print "{tok}";:color 7'
            else:
                lines[n] = put(tok, col, row)
            n += 10
        lines[n] = put(*LAST)
    else:
        lines[10] = ('' if a.get('nowidth') else 'width 80,25:')+':'.join(put(*t) for t in ERASE_TOKENS[:1])
        lines[20] = ':'.join(put(*t) for t in ERASE_TOKENS[1:])
        lines[30] = a['mode']
        lines[40] = put(*ERASE_POST)
    assert all(len(f'{n} {s}') < 80 and s.isascii() and s == s.lower() for n, s in lines.items())
    return lines


def plan(a):
    out = ['new']
    out += [f'{n} {s}' for n, s in sorted(program_lines(a).items())]
    out += ['cls', ('window',), 'run', ('capture', 'result')]
    return out


# ---------------------------------------------------------------- 写しの解析（印だけ）
def find_token(data, tok):
    hits = []
    for g in (1, 2, 3, 4):
        for i in range(len(data)-2*g):
            if (data[i] == ord(tok[0]) and data[i+g] == ord(tok[1]) and data[i+2*g] == ord(tok[2])):
                hits.append([i, g])
    return hits


def cells(off, g):
    return {off, off+g, off+2*g}


def analyze_layout(data, a):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    L = lastcol(a)
    want = [(t, L if c is None else c, r) for t, c, r in TOKENS]
    found, missing, gaps = {}, [], set()
    for tok, col, row in want+[(LAST[0], LAST[1], LAST[2])]:
        hits = find_token(data, tok)
        if len(hits) == 1:
            found[tok] = hits[0]
            gaps.add(hits[0][1])
        else:
            missing.append([tok, len(hits)])
    out = dict(kind='layout', found=found, missing=missing)
    base = found.get('qa1')
    fit = dict(linear=False)
    if not missing and len(gaps) == 1 and base is not None:
        S = found['qb2'][0]-base[0]
        k = (found['qd4'][0]-base[0]-3*S)
        fit = dict(S=S, k=k/10 if k % 10 else k//10, gap=found['qa1'][1], base=base[0])
        pos = {t: (c, r) for t, c, r in want}
        pos['qz9'] = (LAST[1], LAST[2])
        ok = k % 10 == 0 and S > 0
        if ok:
            for tok, (c, r) in pos.items():
                ok = ok and found[tok][0] == base[0]+S*(r-6)+(k//10)*c
        fit['linear'] = bool(ok)
    out['fit'] = fit
    S = fit.get('S')
    if S and fit['linear']:
        own = set()
        for tok, (off, g) in found.items():
            own |= cells(off, g)
        tails, gapvals = {}, set()
        for tok, (off, g) in found.items():
            for j in (1, 2):
                if g > 1:
                    gapvals.add(data[off+(j-1)*g+1])
        for r in (6, 7, 8, 9, 10, 11, 12, 16):
            tails[r] = [[i-r*S, data[i]] for i in range(r*S, min((r+1)*S, 3000))
                        if i not in own and data[i] not in (0x20, 0x00)]
        nb = {}
        for i, b in enumerate(data):
            if i not in own and b not in (0x20, 0x00) and i//S not in TOKEN_ROWS:
                nb.setdefault(i//S, set()).add('c' if i % S < fit['k']*a['cols']+0 else 'a')
        out['tails'] = {str(r): v for r, v in tails.items()}
        out['gap_values'] = sorted(gapvals)
        out['nonblank_rows'] = [[r, ''.join(sorted(v))] for r, v in sorted(nb.items())]
        empty = data[0:6*S]
        out['empty_rows_fill'] = [sum(b == 0x20 for b in empty), sum(b == 0x00 for b in empty),
                                  sum(b not in (0x20, 0x00) for b in empty)]
    return out


def color_diff(obs):
    """色を付けた行（12）と、付けていない行（11）の、印のセルの外の空白でないバイトの差（行内位置・値）。"""
    t = obs.get('tails')
    if not t:
        return None
    a, b = {o: v for o, v in t['12']}, {o: v for o, v in t['11']}
    return [[o, a.get(o), b.get(o)] for o in sorted(set(a)|set(b)) if a.get(o) != b.get(o)]


def analyze_color(data, a):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    found, missing = {}, []
    for tok, col, row, color in COLOR_TOKENS+[(LAST[0], LAST[1], LAST[2], None)]:
        hits = find_token(data, tok)
        if len(hits) == 1:
            found[tok] = hits[0]
        else:
            missing.append([tok, len(hits)])
    out = dict(kind='color', found=found, missing=missing, fit=dict(linear=False))
    if not missing:
        S = found['qb2'][0]-found['qa1'][0]
        k10 = found['qj0'][0]-found['qi9'][0]-S
        k = k10//10
        ok = S > 0 and k10 % 10 == 0 and len({v[1] for v in found.values()}) == 1
        for tok, col, row, color in COLOR_TOKENS+[(LAST[0], LAST[1], LAST[2], None)]:
            ok = ok and found[tok][0] == found['qa1'][0]+S*(row-6)+k*col
        out['fit'] = dict(S=S, k=k, gap=found['qa1'][1], base=found['qa1'][0], linear=bool(ok))
        if ok:
            # 印の行（自作の印しか書かれない行）の属性域40バイトの生値。行7は色なしの対照。
            out['tail_raw'] = {str(r): list(data[r*S+80:r*S+120]) for r in (7, 13, 14, 15)}
    return out


def analyze_erase(data, a):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    survive = {tok: find_token(data, tok) for tok, _, _ in ERASE_TOKENS}
    post = find_token(data, ERASE_POST[0])
    return dict(kind='erase', survive=survive, post=post)


# ---------------------------------------------------------------- ポート
def port_summary(text, win_from, win_to):
    """窓 [win_from, win_to) のメインCPUの制御ポート OUT。値の列は制御ポート（システム制御・CRTC・DMAC）だけ。"""
    ports, crtc, cursor, cur = {}, [], 0, None
    ordered, skipping = [], False
    for line in text.splitlines():
        m = IO_LINE.match(line)
        if not m or m[4] != 'main' or m[5] != 'OUT':
            continue
        frame, port, val = int(m[3]), int(m[6], 16), int(m[7], 16)
        if not (win_from <= frame < win_to):
            continue
        if port in (0x50, 0x51) or port in VALUE_PORTS:
            if port == 0x51:
                skipping = (val in CURSOR_CMDS)
            if not (port in (0x50, 0x51) and skipping):
                if ordered and ordered[-1][:2] == [port, val]:
                    ordered[-1][2] += 1
                else:
                    ordered.append([port, val, 1])
        if port == 0x51:
            if cur is not None:
                crtc.append(cur)
            cur = [val, []]
        elif port == 0x50:
            if cur is not None:
                cur[1].append(val)
        elif port in VALUE_PORTS:
            ports.setdefault(f'{port:02X}', []).append(val)
    if cur is not None:
        crtc.append(cur)
    cursor = sum(1 for c in crtc if c[0] in CURSOR_CMDS)
    rle = []
    for c in crtc:
        if c[0] in CURSOR_CMDS:
            continue
        if rle and rle[-1][:2] == c:
            rle[-1][2] += 1
        else:
            rle.append([c[0], list(c[1]), 1])
    return dict(ports=ports, crtc=rle, cursor_cmds=cursor, ordered=ordered)


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
            at += (len(step)+1)*8+240+(RUN_WAIT if step == 'run' else 0)
        elif step[0] == 'window':
            window = at
        else:
            dump = (work/'vram.bin', at+200)
            args += ['--vram-dump', str(dump[0]), '--vram-dump-at', str(dump[1])]
            at = dump[1]+100
    iolog = work/'port.txt'
    args += ['--io-log', str(iolog), '--io-log-from-frame', str(PORT_FROM), '--frames', str(at+100)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if (proc.returncode or b'untypable' in proc.stderr.lower()
                or '打てない'.encode() in proc.stderr):
            raise RuntimeError('測定器の実行または打鍵に失敗')
        data = dump[0].read_bytes()
        obs = {'layout': analyze_layout, 'erase': analyze_erase, 'color': analyze_color}[a['kind']](data, a)
        obs['port'] = port_summary(iolog.read_text(encoding='utf-8', errors='replace'), window, dump[1]+1)
        return obs
    finally:
        for p in (dump[0] if dump else None, iolog):
            if p:
                Path(p).unlink(missing_ok=True)
                Path(str(p)+'.info.txt').unlink(missing_ok=True)


def valid(obs, a):
    if not isinstance(obs, dict) or obs.get('kind') != a['kind'] or 'port' not in obs:
        return False
    if a['kind'] in ('layout', 'color'):
        return not obs['missing'] and obs['fit'].get('linear') is True and (a['kind'] == 'layout' or 'tail_raw' in obs)
    return (set(obs['survive']) == {t for t, _, _ in ERASE_TOKENS} and len(obs['post']) == 1)


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


# ---------------------------------------------------------------- 予測（事前登録 l4-s9o-width-vram-preregistration.md）
def prediction(a):
    """予測は並びの規則と制御ポートの最後のDMA設定だけ。None は予測なし。"""
    if a['kind'] == 'color':
        return dict(S=120, k=1 if a['cols'] == 80 else 2, linear=True)
    if a['kind'] == 'layout':
        wide = a['cols'] == 80
        pred = dict(S=120, k=1 if wide else 2, linear=True, fkey_row=a['rows']-1 if a['mode'] != 'rem' else 19)
        dma = {'rem': None, 'w40': [0x5F, 0x89], 'w40-20': [0x5F, 0x89], 'w80-20': [0x5F, 0x89],
               'w40-25': [0xB7, 0x8B], 'w80-25': [0xB7, 0x8B]}[a['id'][len('layout-'):]]
        pred['dma65_tail'] = dma
        return pred
    # erase: width が受理されれば pre-width の印は全て消える（rem は全部残る）。
    # 20行へ変える腕の21行目の印は予測なし。
    key = a['id'][len('erase-'):]
    if key == 'rem':
        return dict(survive=dict(qk1=True, qm3=True, qn4=True))
    pred = dict(survive=dict(qk1=False, qm3=False, qn4=None if a['rows'] == 20 else False))
    return pred


def summarize(obs, a):
    """比較に使う観測の要約（予測と同じキー）。"""
    if a['kind'] == 'color':
        return dict(S=obs['fit'].get('S'), k=obs['fit'].get('k'), linear=obs['fit']['linear'])
    if a['kind'] == 'layout':
        fit = obs['fit']
        # 文字域 c に空白でないバイトがある行。属性域 a だけの行は既定の属性の組（全行にある）なので数えない。行0〜5は run の打鍵の跡（rem 腕）
        rows = [r for r, reg in obs.get('nonblank_rows', []) if 'c' in reg and r >= 6 and r != OK_ROW]
        d = obs['port']['ports'].get('65', [])
        return dict(S=fit.get('S'), k=fit.get('k'), linear=fit['linear'], fkey_rows=rows,
                    dma65_tail=d[-2:] if d else None)
    return dict(survive={t: bool(v) for t, v in obs['survive'].items()})


def judge(obs, a):
    p = prediction(a)
    s = summarize(obs, a)
    if a['kind'] == 'erase':
        res = {}
        for t, want in p['survive'].items():
            res[t] = 'noprediction' if want is None else ('agree' if s['survive'][t] == want else 'differ')
        return res
    if a['kind'] == 'color':
        return dict(S='agree' if s['S'] == p['S'] else 'differ', k='agree' if s['k'] == p['k'] else 'differ')
    res = dict(S='agree' if s['S'] == p['S'] else 'differ', k='agree' if s['k'] == p['k'] else 'differ',
               fkey='agree' if s['fkey_rows'] == [p['fkey_row']] else 'differ',
               dma='noprediction' if p['dma65_tail'] is None else
               ('agree' if s['dma65_tail'] == p['dma65_tail'] else 'differ'))
    return res


def write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        w = csv.writer(stream, delimiter='\t')
        w.writerow(header); w.writerows(rows)


def emit(path, records):
    known = {a['id']: a for a in arms()}
    for r in records:
        r['gate'] = (r['gate'] and r['arm'] == known.get(r['arm']['id']) and len(r['obs']) == 2
                     and all(valid(o, r['arm']) for o in r['obs']) and r['obs'][0] == r['obs'][1])
    # 陽性対照: rem は 80桁・120/1 の並びで印が全て見つかり、erase-rem は3つの印が全て残ること。
    # 対照が崩れたら全腕を関門落ちにする。測った種類（layout・erase・color）ごとに対応する rem 腕を要る。
    kinds = {r['arm']['kind'] for r in records}
    calibrated = True
    for kind in kinds:
        rem = [r for r in records if r['arm']['id'] == f'{kind}-rem']
        ok = len(rem) == 1 and rem[0]['gate']
        if ok and kind == 'erase':
            ok = all(rem[0]['obs'][0]['survive'].values())
        elif ok:
            sm = summarize(rem[0]['obs'][0], rem[0]['arm'])
            ok = sm.get('S') == 120 and sm.get('k') == 1
        calibrated = calibrated and ok
    write(path, ['arm', 'repeat', 'plan', 'observation', 'gate', 'prediction_judgement', 'failed'],
          [(r['arm']['id'], i+1, json.dumps(plan(r['arm'])), json.dumps(r['obs'][i]),
            'pass' if calibrated and r['gate'] else 'gate_failed',
            json.dumps(judge(r['obs'][0], r['arm'])) if calibrated and r['gate'] else 'gate_failed',
            int(r['failed'][i])) for r in records for i in range(2)])
    return calibrated and bool(records) and all(r['gate'] for r in records)


def rle(vals):
    out = []
    for v in vals:
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def report(measured):
    """作業置き場の記録から、結果ノートに書く数値だけを出す（印の位置・制御ポートの値。画面本文なし）。"""
    with measured.open(encoding='utf-8', newline='') as stream:
        rows = [r for r in csv.DictReader(stream, delimiter='\t') if r['repeat'] == '1']
    known = {a['id']: a for a in arms()}
    base = {}
    for r in rows:
        if r['arm'] == 'layout-rem':
            base = json.loads(r['observation'])['port']
    lines = []
    for r in rows:
        a, o = known[r['arm']], json.loads(r['observation'])
        lines.append(f"## {a['id']} gate={r['gate']} judge={json.dumps(judge(o, a))}")   # 判定は観測から毎回計算し直す
        if a['kind'] == 'layout':
            lines.append(f"  fit={json.dumps(o['fit'])} missing={o['missing']}")
            lines.append(f"  offsets={json.dumps({t: v for t, v in o['found'].items()})}")
            lines.append(f"  tail_row11={json.dumps(o.get('tails', {}).get('11'))}")
            lines.append(f"  color_diff(off,row12,row11)={json.dumps(color_diff(o))} gap_values={o.get('gap_values')}")
            lines.append(f"  nonblank_rows={o.get('nonblank_rows')} fill(20,00,other)={o.get('empty_rows_fill')}")
        elif a['kind'] == 'color':
            lines.append(f"  fit={json.dumps(o['fit'])} missing={o['missing']}")
            lines.append(f"  offsets={json.dumps(o['found'])}")
            for row, raw in o.get('tail_raw', {}).items():
                lines.append(f"  tail_raw[row{row}][0:12]={raw[:12]}  (残り{raw[12:] == raw[12:13]*28 or 'varied'})")
        else:
            lines.append(f"  survive={json.dumps(o['survive'])} post={o['post']}")
        p = o['port']
        for port, vals in sorted(p['ports'].items()):
            if base.get('ports', {}).get(port) != vals:
                lines.append(f"  OUT {port} [値,連続回数]: {json.dumps(rle(vals))}")
        if p.get('ordered'):
            first = next((i for i, e in enumerate(p['ordered']) if e[0] == 0x30), 0)
            lines.append(f"  ordered[port,val,count] 0x30 の前4件から後40件: {json.dumps(p['ordered'][max(0, first-4):first+40])}")
        crtc = [c for c in p['crtc'] if c not in base.get('crtc', [])]
        lines.append(f"  crtc(非カーソル,制御との差)={json.dumps(crtc)} cursor_cmds={p['cursor_cmds']}")
    return '\n'.join(lines)


# ---------------------------------------------------------------- 自己検査
def synthetic_dump(a, S, k, gap_fill=0x00, color_extra=None, extra_rows=(), leak=None):
    """既知の並び（行ストライド S、桁の間隔 k）で印を置いた合成写し。"""
    data = bytearray([0x20]*3000)
    L = lastcol(a) if a['kind'] == 'layout' else 0
    toks = [(t, L if c is None else c, r) for t, c, r in TOKENS]+[LAST]
    for tok, col, row in toks:
        off = row*S+col*k
        for j, ch in enumerate(tok):
            data[off+j*k] = ord(ch)
            if k > 1:
                for q in range(1, k):
                    data[off+j*k+q] = gap_fill
    if color_extra:
        for off, v in color_extra:
            data[12*S+off] = v
    for r in extra_rows:
        data[r*S+3] = 0x41            # 公式風の本文（値は出力に出ないはず）
    if leak:
        data[2900:2900+len(leak)] = leak
    return bytes(data)


def selftest(work=None):
    if work is not None:
        work.mkdir(parents=True, exist_ok=True)
    known = {a['id']: a for a in arms()}
    assert len(known) == 16
    for a in known.values():
        lines = program_lines(a)
        assert all(len(f'{n} {s}') < 80 for n, s in lines.items())
        plan(a)
    a80, a40 = known['layout-w80-25'], known['layout-w40']
    # 合成写し: 既知の並びを回復できること（陽性）
    for a, S, k in ((a80, 120, 1), (a40, 120, 2), (a40, 80, 2), (a40, 120, 1), (a80, 100, 1)):
        o = analyze_layout(synthetic_dump(a, S, k), a)
        assert o['fit']['linear'] and o['fit']['S'] == S and o['fit']['k'] == k, (S, k, o['fit'])
        assert o['fit']['gap'] == k
    # 陰性: 印が欠けたら欠けとして報告し、並びを当て推量しない
    d = bytearray(synthetic_dump(a80, 120, 1))
    p = find_token(bytes(d), 'qb2')[0][0]
    d[p] = ord('x')
    o = analyze_layout(bytes(d), a80)
    assert o['missing'] == [['qb2', 0]] and not o['fit']['linear']
    # 陰性: 位置を1つだけずらした（桁の間隔が不揃い）印は線形と認めない
    d = bytearray(synthetic_dump(a80, 120, 1))
    p = find_token(bytes(d), 'qe5')[0][0]
    d[p:p+3] = b'   '; d[p+1:p+4] = b'qe5'
    o = analyze_layout(bytes(d), a80)
    assert not o['fit']['linear']
    # 陰性: 同じ印が2箇所にあれば一意でない
    d = bytearray(synthetic_dump(a80, 120, 1)); d[2990:2993] = b'qa1'
    assert analyze_layout(bytes(d), a80)['missing'] == [['qa1', 2]]
    # 属性域の抽出: 印の行の印のセルの外の空白でないバイトだけ（行内位置・値）
    o = analyze_layout(synthetic_dump(a80, 120, 1, color_extra=[(80, 5), (81, 2)]), a80)
    assert o['tails']['12'] == [[80, 5], [81, 2]] and o['tails']['11'] == [], o['tails']
    assert color_diff(o) == [[80, 5, None], [81, 2, None]]
    # 本文の非出力: 公式風の本文を入れても、値は出力に現れず行番号と領域の区別だけ
    secret = b'ZZSECRETZZ'
    o = analyze_layout(synthetic_dump(a80, 120, 1, extra_rows=(19,), leak=secret), a80)
    text = json.dumps(o)
    assert 'SECRET' not in text and 'ZZ' not in text and ord('A') not in [e[1] for v in o['tails'].values() for e in v]
    assert [r for r, _ in o['nonblank_rows']] == [19, 24], o['nonblank_rows']
    # 消去の検出（陽性・陰性）
    ea = known['erase-rem']
    d = bytearray([0x20]*3000)
    for tok, col, row in ERASE_TOKENS+[ERASE_POST]:
        d[row*120+col:row*120+col+3] = tok.encode()
    o = analyze_erase(bytes(d), ea)
    assert all(o['survive'].values()) and len(o['post']) == 1
    d[6*120:6*120+3] = b'   '
    o = analyze_erase(bytes(d), ea)
    assert o['survive']['qk1'] == [] and o['survive']['qm3']
    d40 = bytearray([0x20]*3000)
    for tok, col, row in ERASE_TOKENS+[ERASE_POST]:
        d40[row*120+col*2:row*120+col*2+6:2] = tok.encode()
    assert all(analyze_erase(bytes(d40), ea)['survive'].values())
    # ポート集計（窓の中・外、サブCPU、IN、他ポート、カーソルコマンドの除外、RLE）
    def log(events):
        lines = ['# seq clock frame cpu kind port value pc']
        for i, (fr, cpu, kind, port, val) in enumerate(events):
            lines.append(f'{i:6d} {i:7d} {fr:6d}  {cpu:<4s}  {kind:<4s}  {port:04X}   {val:02X}   0000')
        return '\n'.join(lines)+'\n'
    ev = [(5, 'main', 'OUT', 0x30, 0x11),                       # 窓の手前
          (100, 'main', 'OUT', 0x30, 0x10), (100, 'main', 'IN', 0x30, 0x77), (100, 'sub', 'OUT', 0x30, 0x66),
          (101, 'main', 'OUT', 0x51, 0x00), (101, 'main', 'OUT', 0x50, 0x4F), (101, 'main', 'OUT', 0x50, 0x93),
          (102, 'main', 'OUT', 0x51, 0x80), (102, 'main', 'OUT', 0x50, 0x01), (102, 'main', 'OUT', 0x50, 0x02),
          (103, 'main', 'OUT', 0x51, 0x00), (103, 'main', 'OUT', 0x50, 0x4F), (103, 'main', 'OUT', 0x50, 0x93),
          (104, 'main', 'OUT', 0x65, 0x5F), (104, 'main', 'OUT', 0x65, 0x89), (104, 'main', 'OUT', 0x77, 0x01),
          (900, 'main', 'OUT', 0x30, 0x12)]                      # 窓の後
    got = port_summary(log(ev), 100, 300)
    assert got['ports'] == {'30': [0x10], '65': [0x5F, 0x89]}, got
    assert got['crtc'] == [[0, [0x4F, 0x93], 2]], got['crtc']
    assert got['cursor_cmds'] == 1
    assert got['ordered'] == [[0x30, 0x10, 1], [0x51, 0, 1], [0x50, 0x4F, 1], [0x50, 0x93, 1], [0x51, 0, 1],
                              [0x50, 0x4F, 1], [0x50, 0x93, 1], [0x65, 0x5F, 1], [0x65, 0x89, 1]], got['ordered']
    # 色の境界の解析（追補1）: 並びの回復・生の属性域・欠け・ずれ
    ac = known['color-w40']
    for S, k in ((120, 2), (120, 1), (100, 2)):
        o = analyze_color(synthetic_color_dump(S, k), ac)
        assert o['fit']['linear'] and o['fit']['S'] == S and o['fit']['k'] == k and set(o['tail_raw']) == {'7', '13', '14', '15'}
        assert o['tail_raw']['13'][:4] == [7, 0, 9, 2] and len(o['tail_raw']['13']) == 40 and o['tail_raw']['7'][:2] == [0, 0]
    d = bytearray(synthetic_color_dump(120, 2)); d[find_token(bytes(d), 'qj0')[0][0]] = ord('x')
    assert analyze_color(bytes(d), ac)['missing'] == [['qj0', 0]]
    d = bytearray(synthetic_color_dump(120, 2)); p0 = find_token(bytes(d), 'qy7')[0][0]
    d[p0:p0+5] = b'     '; d[p0+2:p0+7] = b'q\x20y\x207'
    assert not analyze_color(bytes(d), ac)['fit']['linear']
    assert port_summary('', 0, 10) == dict(ports={}, crtc=[], cursor_cmds=0, ordered=[])
    assert judge(synthetic_obs(a40, 120, 2), a40)['S'] == 'agree'
    assert judge(synthetic_obs(a40, 120, 1), a40)['k'] == 'differ'
    print('OK 並びの回復（陽性5種）・欠け・ずれ・重複の拒否・属性域の抽出・本文非出力・消去の検出・ポート集計', flush=True)
    # 自作ROMの既知値対照: rem 腕（80桁20行の起動状態）の並び 120/1 と、印が残ること。
    with tempfile.TemporaryDirectory(prefix='l4s9o-selftest-', dir=work) as temp:
        root = Path(temp)
        rom = root/'rom'
        built = subprocess.run([os.sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom),
                                '--work-dir', str(root/'asm')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert built.returncode == 0, '自作ROM一時ビルド失敗'
        own = [known['layout-rem'], dict(known['erase-rem'], nowidth=True), known['color-rem']]   # 自作ROMは width を持たない
        observed = measure(rom, False, own, root)
        bad = [r['arm']['id'] for r in observed if not r['gate']]
        if bad:
            print('NG 自作ROMの既知値対照: '+','.join(bad))
            for r in observed:
                print(json.dumps(dict(arm=r['arm']['id'], failed=r['failed'], obs=[
                    {k: v for k, v in o.items() if k in ('found', 'missing', 'fit', 'survive', 'post')} for o in r['obs']])))
        assert not bad
        l = summarize(observed[0]['obs'][0], own[0])
        assert l['S'] == 120 and l['k'] == 1 and l['linear'], l
        assert all(observed[1]['obs'][0]['survive'].values())
        c = summarize(observed[2]['obs'][0], own[2])
        assert c['S'] == 120 and c['k'] == 1 and c['linear'], c
        # 故障注入: 並びを 80/2 とした期待に対する判定は differ になる（検査が一致を作り出さない）
        assert judge(observed[0]['obs'][0], known['layout-w40'])['S'] == 'agree'
        assert judge(observed[0]['obs'][0], known['layout-w40'])['k'] == 'differ'
    # 記録の出力と較正の関門（合成の観測。全11腕が予測どおりなら通り、陽性対照が崩れれば落ちる）
    with tempfile.TemporaryDirectory(prefix='l4s9o-emit-', dir=work) as temp:
        recs = [dict(arm=a, obs=[synthetic_obs_for(a)]*2, failed=[False, False], gate=True) for a in known.values()]
        out = Path(temp)/'m.tsv'
        assert emit(out, recs)
        text = out.read_text()
        assert 'gate_failed' not in text and 'differ' not in text, 'differ' in text
        recs[0] = dict(recs[0], obs=[synthetic_obs(a40, 120, 2)]*2)    # rem 腕の並びを壊す
        assert not emit(out, recs)
        assert 'gate_failed' in out.read_text()
    print('OK 記録の出力・較正の関門（陽性対照が崩れると全腕が gate_failed）')
    print('OK 自作ROMの既知値対照3腕×2走（80桁の並び120/1・印の残存）・故障注入で判定が differ になる', flush=True)
    return 0


def synthetic_color_dump(S, k):
    data = bytearray([0x20]*3000)
    for tok, col, row, color in COLOR_TOKENS+[(LAST[0], LAST[1], LAST[2], None)]:
        off = row*S+col*k
        for j, ch in enumerate(tok):
            data[off+j*k] = ord(ch)
    data[13*S+80:13*S+84] = bytes([7, 0, 9, 2])      # 既知の属性域の値（合成）
    data[7*S+80:7*S+82] = bytes([0, 0])
    return bytes(data)


def synthetic_obs_for(a):
    if a['kind'] == 'color':
        p = prediction(a)
        o = analyze_color(synthetic_color_dump(p['S'], p['k']), a)
        o['port'] = dict(ports={}, crtc=[], cursor_cmds=0, ordered=[])
        return o
    if a['kind'] == 'erase':
        p = prediction(a)['survive']
        return dict(kind='erase', survive={t: ([[0, 1]] if p[t] is not False else []) for t, _, _ in ERASE_TOKENS},
                    post=[[0, 1]], port=dict(ports={}, crtc=[], cursor_cmds=0))
    p = prediction(a)
    o = synthetic_obs(a, p['S'], p['k'])
    o['nonblank_rows'] = [[0, 'a'], [5, 'a'], [p['fkey_row'], 'ac'], [OK_ROW, 'ac'], [24 if p['fkey_row'] != 24 else 23, 'a']]
    if p['dma65_tail']:
        o['port']['ports'] = {'65': p['dma65_tail']}
    return o


def synthetic_obs(a, S, k):
    o = analyze_layout(synthetic_dump(a, S, k), a)
    o['port'] = dict(ports={}, crtc=[], cursor_cmds=0)
    return o


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    m = sub.add_parser('measure'); m.add_argument('--rom-dir')
    m.add_argument('--official', action='store_true'); m.add_argument('--out', type=Path, required=True)
    m.add_argument('--work-dir', type=Path, default=WORK)
    m.add_argument('--kind', choices=('base', 'color'), default='base', help='base=layout+erase（登録の本体）、color=追補1')
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
    records = measure(rom, args.official, base_arms() if args.kind == 'base' else [a for a in arms() if a['kind'] == 'color'], args.work_dir)
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
