#!/usr/bin/env python3
"""l4-s9r: CRTC カーソル位置コマンド 0x80/0x81 の使い分けと、COLOR の値が描画に与える色を測る器具。

画面本文は扱わない。採るのは次の数値だけ。
 (1) 窓の終わりの CRTC カーソルコマンド（0x80・0x81）の件数と最後のパラメータ（制御ポートの値）。
 (2) --screenshot の PPM から、数セル（8x20 画素）の画素値の頻度（RGB と個数の上位）。対象は自作の印 MMM のセル、
     空白の参照セル、カーソルのセルとその参照セル。画面全体の色ヒストグラム（位置情報なし）。画像は採取後に消す。
 (3) 制御ポート（0x30・0x32・0x52・0x53・0x54〜0x5B）の値の初出順と最後の値。
 (4) px・bg 腕だけ、自作の行10 の属性域の組（vram 写しから。写しは採取後に消す）。
事前登録は docs/notes/l4-s9r-cursor-color-pixel-preregistration.md。
"""
import argparse
import collections
import csv
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
import l4_colorattr_measure as ca

WORK = kw.REPO.parent / 'tmp/s9r-work'
IO_LINE = wv.IO_LINE
CELL_W, CELL_H = 8, 20
PORTS = (0x30, 0x32, 0x52, 0x53) + tuple(range(0x54, 0x5C))
PH = 19                     # 位相違い腕の採取の遅れ（フレーム）
TAIL = 60                   # カーソルコマンドを見る窓（採取の直前フレーム数）
MARK = (10, 10)             # 印 MMM の桁・行
PRINT_M = 'print chr$(77);chr$(77);chr$(77);'      # 打鍵は小文字で届くので、大文字の印は chr$ で作る
MCELL, RCELL = (11, 10), (30, 10)     # 印の中のセル／空白の参照セル

# st 腕: (id, 計画, 予測の最後のコマンド, 予測の桁（None は予測なし）)
ST = [
    ('idle', [], 0x81, None),
    ('typing', [('raw', 'print 12')], 0x81, 8),
    ('width40', [('direct', 'width 40')], 0x81, 0),
    ('width80', [('direct', 'width 80')], 0x81, 0),
    ('locate', [('direct', 'locate 10,5')], 0x81, 0),
    ('cls', [('direct', 'cls')], 0x81, 0),
    ('err', [('direct', 'a=*3')], 0x81, 0),
    ('progend', [('prog', {10: 'print 1'}), ('run',)], 0x81, 0),
    ('goto', [('prog', {10: 'goto 10'}), ('run',)], 0x80, None),
    ('for', [('prog', {10: 'for i=1 to 30000:for j=1 to 30000:next:next'}), ('run',)], 0x80, None),
    ('input', [('prog', {10: 'input a$'}), ('run',)], 0x81, 2),
    ('inkey', [('prog', {10: 'a$=inkey$:goto 10'}), ('run',)], 0x80, None),
    ('inputtyped', [('prog', {10: 'input a$'}), ('run',), ('raw', 'ab')], 0x81, 4),
]
PHASE = ('idle', 'input', 'goto')       # 位相違い -b を足す腕
PHASE_PRED = {'idle': True, 'input': True, 'goto': False}      # カーソルが画素で見えるか（弱）
# px 腕の予測（白黒）: n -> (字形が見える, 反転)
PX0 = {0: (True, False), 1: (False, False), 2: (True, False), 3: (False, False),
       4: (True, True), 5: (False, True), 6: (True, True), 7: (False, True)}


def arms():
    out = []
    for key, steps, cmd, col in ST:
        out.append(dict(id=f'st-{key}', kind='st', key=key, steps=steps, ph=0))
    for key in PHASE:
        s = [x for x in ST if x[0] == key][0]
        out.append(dict(id=f'st-{key}-b', kind='st', key=key, steps=s[1], ph=PH))
    for mode in (0, 1):
        for n in range(8):
            out.append(dict(id=f'px{mode}-n{n}', kind='px', mode=mode, n=n))
    out.append(dict(id='bg-base', kind='bg', stmt='rem'))
    for b in range(8):
        out.append(dict(id=f'bg-b{b}', kind='bg', stmt=f'color ,{b}'))
    for f in range(8):
        out.append(dict(id=f'fg-f{f}', kind='bg', stmt=f'color ,,,{f}'))
    return out


def program_lines(a):
    k = a['kind']
    if k == 'px':
        lines = {20: f"locate {MARK[0]},{MARK[1]}:color {a['n']}:{PRINT_M}", 30: 'goto 30'}
        if a['mode']:
            lines[10] = 'console ,,,1'
    elif k == 'bg':
        lines = {20: a['stmt'], 30: f'locate {MARK[0]},{MARK[1]}:{PRINT_M}', 40: 'goto 40'}
    else:
        lines = {}
        for s in a['steps']:
            if s[0] == 'prog':
                lines.update(s[1])
    assert all(len(f'{n} {s}') < 80 and s.isascii() and s == s.lower() for n, s in lines.items()), lines
    return lines


def plan(a):
    """段: ('new',)->行の入力, ('cls',), ('window',), ('direct'|'raw', 文), ('run',), ('capture',)"""
    k = a['kind']
    if k in ('px', 'bg'):
        lines = program_lines(a)
        return ['new'] + [f'{n} {s}' for n, s in sorted(lines.items())] + ['cls', ('window',), 'run', ('capture', 'vram')]
    out = []
    for s in a['steps']:
        if s[0] == 'prog':
            out += ['new'] + [f'{n} {t}' for n, t in sorted(s[1].items())] + ['cls', ('window',)]
        elif s[0] == 'run':
            out.append('run')
        elif s[0] == 'direct':
            if not any(x == ('window',) for x in out):
                out.append(('window',))
            out.append(s[1])
        else:
            if not any(x == ('window',) for x in out):
                out.append(('window',))
            out.append(('raw', s[1]))
    if ('window',) not in out:
        out.append(('window',))
    out.append(('capture', 'none'))
    return out


# ---------------------------------------------------------------- 画素
def read_ppm(path):
    b = Path(path).read_bytes()
    m = re.match(rb'P6\s+(\d+)\s+(\d+)\s+255\s', b)
    if not m:
        raise ValueError('PPM の形式が不正')
    w, h = int(m[1]), int(m[2])
    data = b[m.end():]
    if (w, h) != (640, 400) or len(data) != w*h*3:
        raise ValueError('PPM の大きさが不正')
    return w, h, data


def cell_stat(img, c, r, top=4):
    w, h, data = img
    cnt = collections.Counter()
    for y in range(r*CELL_H, r*CELL_H+CELL_H):
        base = (y*w+c*CELL_W)*3
        for x in range(CELL_W):
            cnt[data[base+3*x:base+3*x+3].hex()] += 1
    return [[k, v] for k, v in cnt.most_common(top)]


def hist(img, top=6):
    w, h, data = img
    cnt = collections.Counter(data[i:i+3].hex() for i in range(0, len(data), 3))
    return [[k, v] for k, v in cnt.most_common(top)]


def glyph_visible(stat):
    return len(stat) >= 2


def main_color(stat):
    return stat[0][0] if stat else None


# ---------------------------------------------------------------- ポート
def cursor_tail(text, f0, f_all=0):
    """f0 以降のメイン OUT の CRTC コマンド列から、カーソルコマンドの件数と最後のパラメータ。"""
    cmds, cur = [], None
    for line in text.splitlines():
        m = IO_LINE.match(line)
        if not m or m[4] != 'main' or m[5] != 'OUT':
            continue
        frame, port, val = int(m[3]), int(m[6], 16), int(m[7], 16)
        if frame < f_all:
            continue
        if port == 0x51:
            if cur is not None:
                cmds.append(cur)
            cur = [val, [], frame]
        elif port == 0x50 and cur is not None:
            cur[1].append(val)
    if cur is not None:
        cmds.append(cur)
    cc = [c for c in cmds if c[0] in (0x80, 0x81)]
    tail = [c for c in cc if c[2] >= f0]
    count = collections.Counter(c[0] for c in tail)
    return dict(n=len(tail), count={hex(k): v for k, v in sorted(count.items())},
                last=[tail[-1][0], tail[-1][1]] if tail else None,
                last_any=[cc[-1][0], cc[-1][1]] if cc else None, n_any=len(cc))


def port_values(text, f0):
    seen = {p: [] for p in PORTS}
    for line in text.splitlines():
        m = IO_LINE.match(line)
        if not m or m[4] != 'main' or m[5] != 'OUT':
            continue
        frame, port, val = int(m[3]), int(m[6], 16), int(m[7], 16)
        if frame >= f0 and port in seen and val not in seen[port]:
            seen[port].append(val)
    return {hex(p): v for p, v in seen.items() if v}


# ---------------------------------------------------------------- 解析
def analyze(a, img, iolog_text, cap, window, vram=None):
    obs = dict(kind=a['kind'], hist=hist(img))
    obs['ports'] = port_values(iolog_text, window)
    cur = cursor_tail(iolog_text, cap-TAIL, window)
    obs['cur'] = cur
    if a['kind'] == 'st':
        last = cur['last'] or cur['last_any']
        if last and len(last[1]) >= 2:
            c, r = last[1][0], last[1][1]
            if a['key'] != 'width40' and 0 <= c < 60 and 0 <= r < 20:
                rc = c+20 if c+20 < 80 else c-20
                obs['pix'] = dict(cursor=cell_stat(img, c, r), ref=cell_stat(img, rc, r))
        return obs
    cell, ref = cell_stat(img, *MCELL), cell_stat(img, *RCELL)
    obs['pix'] = dict(cell=cell, ref=ref, m10=cell_stat(img, MARK[0], MARK[1]), m12=cell_stat(img, MARK[0]+2, MARK[1]))
    obs['tok'] = None
    if vram is not None:
        hits = wv.find_token(vram, 'MMM')
        obs['tok'] = [hits[0][0] // 120, (hits[0][0] % 120)//max(hits[0][1], 1), hits[0][1]] if len(hits) == 1 else len(hits)
        if obs['tok'] and isinstance(obs['tok'], list):
            obs['attr'] = ca.nontrivial(list(vram[MARK[1]*120+80:MARK[1]*120+120]))
    return obs


# ---------------------------------------------------------------- 走らせる
def run_arm(rom, official, a, work):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    window, dump, cap_mode = None, None, 'none'
    for step in plan(a):
        if isinstance(step, str):
            args += ['--type-at', str(at), '--type', step+'\n']
            at += (len(step)+1)*8+240+(wv.RUN_WAIT if step == 'run' else 0)
        elif step[0] == 'window':
            window = at
        elif step[0] == 'raw':
            args += ['--type-at', str(at), '--type', step[1]]
            at += len(step[1])*8+240
        else:
            cap_mode = step[1]
    cap = at+200+a.get('ph', 0)
    ppm, iolog = work/'shot.ppm', work/'port.txt'
    if cap_mode == 'vram':
        dump = work/'vram.bin'
        args += ['--vram-dump', str(dump), '--vram-dump-at', str(cap)]
    args += ['--screenshot', str(ppm), '--io-log', str(iolog), '--io-log-from-frame', str(window), '--frames', str(cap+100)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
            raise RuntimeError('測定器の実行または打鍵に失敗')
        img = read_ppm(ppm)
        vram = dump.read_bytes() if dump else None
        return analyze(a, img, iolog.read_text(encoding='utf-8', errors='replace'), cap, window, vram)
    finally:
        for p in (ppm, iolog, dump):
            if p:
                Path(p).unlink(missing_ok=True)
                Path(str(p)+'.info.txt').unlink(missing_ok=True)


def valid(obs, a):
    if not isinstance(obs, dict) or obs.get('kind') != a['kind'] or not obs.get('hist'):
        return False
    if a['kind'] == 'st':
        return obs['cur']['last_any'] is not None
    return isinstance(obs.get('tok'), list) and obs['tok'][:3] == [MARK[1], MARK[0], 1] and 'pix' in obs


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


# ---------------------------------------------------------------- 判定
def rgb_class(hexs):
    v = bytes.fromhex(hexs)
    return tuple(int(x > 128) for x in v)


def fg_color(pix):
    """参照セルの主色（背景）と異なる色のうち最多のもの。無ければ None。"""
    bg = main_color(pix['ref'])
    for k, v in pix['cell']:
        if k != bg:
            return k
    return None


def judge(obs, a, by=None):
    k = a['kind']
    if k == 'st':
        s = [x for x in ST if x[0] == a['key']][0]
        res = {}
        cnt = obs['cur']['count']
        last = obs['cur']['last'] or obs['cur']['last_any']
        res['cmd'] = 'agree' if last[0] == s[2] and (set(cnt) <= {hex(s[2])}) else 'differ'
        if s[3] is not None and not a['ph']:
            res['col'] = 'agree' if last[1] and last[1][0] == s[3] else 'differ'
        return res
    pix = obs['pix']
    if k == 'px':
        seen_vis = glyph_visible(pix['cell'])
        bg = main_color(pix['ref'])
        reversed_ = main_color(pix['cell']) != bg
        if a['mode'] == 0:
            want = PX0[a['n']]
            return dict(visible='agree' if seen_vis == want[0] else 'differ',
                        reversed='agree' if reversed_ == want[1] else 'differ')
        fg = fg_color(pix)
        n = a['n']
        want = None if n == 0 else (int(bool(n & 2)), int(bool(n & 4)), int(bool(n & 1)))     # R=2・G=4・B=1
        got = rgb_class(fg) if fg else None
        return dict(fg='agree' if got == want else 'differ')
    # bg
    base = by.get('bg-base') if by else None
    if a['id'] == 'bg-base' or base is None:
        return {}
    same = main_color(pix['ref']) == main_color(base['pix']['ref'])
    same_fg = fg_color(pix) == fg_color(base['pix']) and glyph_visible(pix['cell']) == glyph_visible(base['pix']['cell'])
    if a['id'].startswith('bg-b'):
        return dict(blank_unchanged='agree' if same else 'differ')
    return dict(glyph_unchanged='agree' if same_fg and same else 'differ')


def group_judges(records):
    """腕をまたぐ予測: bg-b の 0x54 最後の値が互いに異なる／位相違いでカーソルが見えるか。"""
    by = {r['arm']['id']: r['obs'][0] for r in records if r['gate'] and r['obs'][0]}
    out = {}
    lasts = []
    for b in range(8):
        o = by.get(f'bg-b{b}')
        if o and '0x54' in o['ports']:
            lasts.append(o['ports']['0x54'][-1])
    if len(lasts) == 8:
        out['port54_distinct'] = 'agree' if len(set(lasts)) == 8 else 'differ'
    for key in PHASE:
        a, b = by.get(f'st-{key}'), by.get(f'st-{key}-b')
        if a and b and 'pix' in a and 'pix' in b:
            vis = any(glyph_visible(o['pix']['cursor']) or main_color(o['pix']['cursor']) != main_color(o['pix']['ref']) for o in (a, b))
            out[f'cursor_visible_{key}'] = 'agree' if vis == PHASE_PRED[key] else 'differ'
    base = by.get('bg-base')
    if base:
        for g in ('bg-b', 'fg-f'):
            attrs = [by.get(f'{g}{i}', {}).get('attr') for i in range(8)]
            if all(x is not None for x in attrs):
                out[f'{g}_attr_empty'] = 'agree' if all(x == [] for x in attrs) else 'differ'
    return out


def calibrated(records):
    by = {r['arm']['id']: r for r in records}
    ok = True
    pix_arms = [i for i in ('bg-base', 'px0-n0') if i in by]
    for i in pix_arms:
        r = by[i]
        o = r['obs'][0] if r['obs'] else {}
        ok = ok and bool(r['gate'] and o and glyph_visible(o['pix']['cell']) and len(o['pix']['ref']) == 1)
    if 'st-idle' in by:
        r = by['st-idle']
        ok = ok and bool(r['gate'] and r['obs'][0].get('cur', {}).get('last') and r['obs'][0]['cur']['n'] >= 1)
    return ok


def write_tsv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        w = csv.writer(stream, delimiter='\t')
        w.writerow(header); w.writerows(rows)


def emit(path, records):
    known = {a['id']: a for a in arms()}
    for r in records:
        r['gate'] = (r['gate'] and r['arm'] == known.get(r['arm']['id']) and len(r['obs']) == 2
                     and all(valid(o, r['arm']) for o in r['obs']) and r['obs'][0] == r['obs'][1])
    cal = calibrated(records)
    by = {r['arm']['id']: r['obs'][0] for r in records if r['gate'] and r['obs'][0]}
    rows = [(r['arm']['id'], i+1, json.dumps(plan(r['arm'])), json.dumps(r['obs'][i]),
             'pass' if cal and r['gate'] else 'gate_failed',
             json.dumps(judge(r['obs'][0], r['arm'], by)) if cal and r['gate'] else 'gate_failed',
             int(r['failed'][i])) for r in records for i in range(2)]
    if cal:
        rows.append(('_group', 1, '[]', '{}', 'pass', json.dumps(group_judges(records)), 0))
    write_tsv(path, ['arm', 'repeat', 'plan', 'observation', 'gate', 'prediction_judgement', 'failed'], rows)
    return cal and bool(records) and all(r['gate'] for r in records)


def report(measured):
    with measured.open(encoding='utf-8', newline='') as stream:
        rows = [r for r in csv.DictReader(stream, delimiter='\t') if r['repeat'] == '1']
    lines = []
    for r in rows:
        if r['arm'] == '_group':
            lines.append(f"## _group judge={r['prediction_judgement']}")
            continue
        o = json.loads(r['observation'])
        lines.append(f"## {r['arm']} gate={r['gate']} judge={r['prediction_judgement']}")
        if not o:
            continue
        if o['kind'] == 'st':
            lines.append(f"  cursor count={o['cur']['count']} last={o['cur']['last']}")
            if 'pix' in o:
                lines.append(f"  pix cursor={o['pix']['cursor']} ref={o['pix']['ref']}")
        else:
            lines.append(f"  tok={o['tok']} attr={o.get('attr')}")
            lines.append(f"  cell(11,10)={o['pix']['cell']} ref={o['pix']['ref']}")
        lines.append(f"  ports={json.dumps(o['ports'])}")
        lines.append(f"  hist={o['hist']}")
    return '\n'.join(lines)


# ---------------------------------------------------------------- 自己検査
def synth_img(cells=None, bg=(0, 0, 0)):
    data = bytearray(bytes(bg)*(640*400))
    for (c, r), spec in (cells or {}).items():
        for y in range(r*CELL_H, r*CELL_H+CELL_H):
            for x in range(c*CELL_W, c*CELL_W+CELL_W):
                col = spec(x-c*CELL_W, y-r*CELL_H) if callable(spec) else spec
                if col is not None:
                    data[(y*640+x)*3:(y*640+x)*3+3] = bytes(col)
    return (640, 400, bytes(data))


def log(events):
    lines = ['# seq clock frame cpu kind port value pc']
    for i, (fr, cpu, kind, port, val) in enumerate(events):
        lines.append(f'{i:6d} {i:7d} {fr:6d}  {cpu:<4s}  {kind:<4s}  {port:04X}   {val:02X}   0000')
    return '\n'.join(lines)+'\n'


def selftest(work=None):
    if work is not None:
        work.mkdir(parents=True, exist_ok=True)
    known = {a['id']: a for a in arms()}
    assert len(known) == 13+3+16+17, len(known)
    for a in known.values():
        plan(a)
        program_lines(a)
    # ppm の読み書き・セル統計の陽性・陰性
    with tempfile.TemporaryDirectory(prefix='l4s9r-px-', dir=work) as temp:
        p = Path(temp)/'a.ppm'
        w, h, data = synth_img({(11, 10): lambda x, y: (255, 255, 255) if x < 3 else None})
        p.write_bytes(b'P6\n640 400\n255\n'+data)
        img = read_ppm(p)
        st = cell_stat(img, 11, 10)
        assert st == [['000000', 8*20-3*20], ['ffffff', 60]], st
        assert cell_stat(img, 30, 10) == [['000000', 160]]                          # 参照セルは単色
        assert cell_stat(img, 12, 10) == [['000000', 160]]                          # 隣のセルに漏れない
        assert cell_stat(img, 11, 9) == [['000000', 160]] and cell_stat(img, 11, 11) == [['000000', 160]]   # 行の境界
        p.write_bytes(b'P6\n640 400\n255\n'+data[:-3])
        try:
            read_ppm(p); assert False
        except ValueError:
            pass
        assert hist(img)[0][0] == '000000' and hist(img)[1] == ['ffffff', 60]
    # カーソルコマンドの集計（窓・サブCPU・IN・畳み込み）
    ev = [(5, 'main', 'OUT', 0x51, 0x81), (5, 'main', 'OUT', 0x50, 0x01), (5, 'main', 'OUT', 0x50, 0x01),
          (100, 'main', 'OUT', 0x51, 0x81), (100, 'main', 'OUT', 0x50, 0x02), (100, 'main', 'OUT', 0x50, 0x09),
          (101, 'sub', 'OUT', 0x51, 0x80), (101, 'sub', 'OUT', 0x50, 0x63), (101, 'main', 'OUT', 0x51, 0x00), (101, 'main', 'OUT', 0x50, 0x4F),
          (102, 'main', 'OUT', 0x51, 0x80), (102, 'main', 'OUT', 0x50, 0x28), (102, 'main', 'OUT', 0x50, 0x09),
          (102, 'main', 'OUT', 0x54, 0x07), (102, 'main', 'OUT', 0x54, 0x03), (102, 'main', 'OUT', 0x54, 0x07), (50, 'main', 'OUT', 0x54, 0x55)]
    t = cursor_tail(log(ev), 100)
    assert t == dict(n=2, count={'0x80': 1, '0x81': 1}, last=[0x80, [0x28, 9]], last_any=[0x80, [0x28, 9]], n_any=3), t
    assert cursor_tail(log(ev), 103)['n'] == 0 and cursor_tail(log(ev), 103)['last'] is None and cursor_tail(log(ev), 103)['last_any'] == [0x80, [0x28, 9]]
    assert cursor_tail(log(ev), 100, 101)['n_any'] == 1                     # 窓より前のコマンドは数えない
    assert port_values(log(ev), 100) == {'0x54': [7, 3]}
    # st の判定（陽性・陰性）
    def st_obs(cmd, col, vis=False):
        o = dict(kind='st', hist=[['000000', 1]], ports={}, cur=dict(n=1, count={hex(cmd): 3}, last=[cmd, [col, 4]], last_any=[cmd, [col, 4]], n_any=3))
        o['pix'] = dict(cursor=[['000000', 100], ['ffffff', 60]] if vis else [['000000', 160]], ref=[['000000', 160]])
        return o
    assert judge(st_obs(0x81, 2), known['st-input']) == dict(cmd='agree', col='agree')
    assert judge(st_obs(0x80, 2), known['st-input']) == dict(cmd='differ', col='agree')
    assert judge(st_obs(0x81, 3), known['st-input']) == dict(cmd='agree', col='differ')
    mixed = st_obs(0x81, 2); mixed['cur']['count'] = {'0x80': 1, '0x81': 2}
    assert judge(mixed, known['st-input'])['cmd'] == 'differ'
    assert 'col' not in judge(st_obs(0x80, 0), known['st-goto'])
    # px の判定
    def px_obs(a_id, cell_cols, ref=[['000000', 160]]):
        return dict(kind='px', hist=[['000000', 1]], ports={}, cur={}, tok=[10, 10, 1],
                    pix=dict(cell=cell_cols, ref=ref, m10=cell_cols, m12=cell_cols))
    assert judge(px_obs('', [['000000', 100], ['ffffff', 60]]), known['px0-n0']) == dict(visible='agree', reversed='agree')
    assert judge(px_obs('', [['000000', 160]]), known['px0-n1']) == dict(visible='agree', reversed='agree')
    assert judge(px_obs('', [['ffffff', 100], ['000000', 60]]), known['px0-n4']) == dict(visible='agree', reversed='agree')
    assert judge(px_obs('', [['ffffff', 160]]), known['px0-n5']) == dict(visible='agree', reversed='agree')
    assert judge(px_obs('', [['000000', 100], ['ffffff', 60]]), known['px0-n4'])['reversed'] == 'differ'
    cols = {1: '0000ff', 2: 'ff0000', 3: 'ff00ff', 4: '00ff00', 5: '00ffff', 6: 'ffff00', 7: 'ffffff'}
    for n, hx in cols.items():
        assert judge(px_obs('', [['000000', 100], [hx, 60]]), known[f'px1-n{n}']) == dict(fg='agree'), n
    assert judge(px_obs('', [['000000', 160]]), known['px1-n0']) == dict(fg='agree')
    assert judge(px_obs('', [['000000', 100], ['ffffff', 60]]), known['px1-n2']) == dict(fg='differ')     # 白は赤ではない
    # bg の判定
    base = px_obs('', [['000000', 100], ['ffffff', 60]])
    same = px_obs('', [['000000', 100], ['ffffff', 60]])
    diff = px_obs('', [['0000ff', 160]], ref=[['0000ff', 160]])
    assert judge(same, known['bg-b3'], {'bg-base': base}) == dict(blank_unchanged='agree')
    assert judge(diff, known['bg-b3'], {'bg-base': base}) == dict(blank_unchanged='differ')
    assert judge(same, known['fg-f3'], {'bg-base': base}) == dict(glyph_unchanged='agree')
    assert judge(diff, known['fg-f3'], {'bg-base': base}) == dict(glyph_unchanged='differ')
    # 解析（vram 写しの印の位置）と本文非出力
    vram = bytearray([0x20]*3000)
    vram[10*120+10:10*120+13] = b'MMM'
    for r in range(25):
        vram[r*120+80:r*120+120] = bytes([0x80, 0]*20)
    vram[3*120+5:3*120+11] = b'SECRET'
    img = synth_img({(11, 10): lambda x, y: (255, 255, 255) if x < 3 else None})
    o = analyze(known['bg-base'], img, log(ev), 150, 100, bytes(vram))
    assert o['tok'] == [10, 10, 1] and o['attr'] == [] and 'SECRET' not in json.dumps(o) and valid(o, known['bg-base'])
    vram2 = bytearray(vram); vram2[10*120+13:10*120+16] = b'MMM'
    assert not valid(analyze(known['bg-base'], img, log(ev), 150, 100, bytes(vram2)), known['bg-base'])    # 印が2か所
    vram3 = bytearray(vram); vram3[10*120+10:10*120+13] = b'   '; vram3[11*120+10:11*120+13] = b'MMM'
    assert not valid(analyze(known['bg-base'], img, log(ev), 150, 100, bytes(vram3)), known['bg-base'])    # 行がずれた
    vram4 = bytearray(vram); vram4[10*120+80:10*120+84] = bytes([3, 2, 0x80, 0])
    assert analyze(known['bg-base'], img, log(ev), 150, 100, bytes(vram4))['attr'] == [[3, 2]]
    print('OK PPM・セル統計・カーソル集計・ポート・st/px/bg の判定（陽性・陰性）・印の位置の関門・本文非出力', flush=True)
    # 較正の関門と群の判定（合成）
    def rec(a_id, o, gate=True):
        o = dict(o, kind=known[a_id]['kind'])
        return dict(arm=known[a_id], obs=[o, o], failed=[False, False], gate=gate)
    good_base = px_obs('', [['000000', 100], ['ffffff', 60]])
    idle = st_obs(0x81, 0)
    recs = [rec('bg-base', good_base), rec('px0-n0', good_base), rec('st-idle', idle)]
    assert calibrated(recs)
    assert not calibrated([rec('bg-base', px_obs('', [['000000', 160]])), rec('px0-n0', good_base), rec('st-idle', idle)])      # 字形が見えない
    assert not calibrated([rec('bg-base', px_obs('', [['000000', 100], ['ffffff', 60]], ref=[['000000', 100], ['ffffff', 60]])),
                           rec('px0-n0', good_base), rec('st-idle', idle)])                                                    # 参照セルが単色でない
    nocur = st_obs(0x81, 0); nocur['cur'] = dict(n=0, count={}, last=None, last_any=None, n_any=0)
    assert not calibrated([rec('bg-base', good_base), rec('st-idle', nocur)])
    assert not calibrated([rec('bg-base', good_base, gate=False), rec('st-idle', idle)])
    grp = [rec(f'bg-b{b}', dict(good_base, ports={'0x54': [7, 0x10+b]}, attr=[])) for b in range(8)]
    assert group_judges(grp)['port54_distinct'] == 'agree'
    grp[3] = rec('bg-b3', dict(good_base, ports={'0x54': [7, 0x10]}, attr=[]))
    assert group_judges(grp)['port54_distinct'] == 'differ'
    ph = [rec('st-goto', st_obs(0x80, 0)), rec('st-goto-b', st_obs(0x80, 0)), rec('st-idle', st_obs(0x81, 0, True)), rec('st-idle-b', st_obs(0x81, 0))]
    g = group_judges(ph)
    assert g['cursor_visible_idle'] == 'agree' and g['cursor_visible_goto'] == 'agree', g
    ph[0] = rec('st-goto', st_obs(0x80, 0, True))
    assert group_judges(ph)['cursor_visible_goto'] == 'differ'
    with tempfile.TemporaryDirectory(prefix='l4s9r-emit-', dir=work) as temp:
        out = Path(temp)/'m.tsv'
        assert emit(out, [rec('bg-base', good_base), rec('px0-n0', good_base), rec('st-idle', idle)])
        txt = out.read_text()
        assert 'gate_failed' not in txt and '_group' in txt
        assert not emit(out, [rec('bg-base', px_obs('', [['000000', 160]])), rec('st-idle', idle)]) and 'gate_failed' in out.read_text()
        bad = rec('bg-base', good_base); bad['obs'] = [good_base, dict(good_base, ports={'0x54': [1]})]       # 2走が一致しない
        assert not emit(out, [bad, rec('st-idle', idle)])
    print('OK 較正の関門（陰性4種）・群の判定（陽性・陰性）・記録の出力・2走不一致の関門落ち', flush=True)
    # 自作ROMの対照: st-goto・bg-base・px0-n0 が走り、PPM のセルが読めること
    with tempfile.TemporaryDirectory(prefix='l4s9r-selftest-', dir=work) as temp:
        root = Path(temp)
        rom = root/'rom'
        built = subprocess.run([sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom),
                                '--work-dir', str(root/'asm')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert built.returncode == 0, '自作ROM一時ビルド失敗'
        own = [known['st-goto'], known['bg-base'], known['px0-n0'], known['px0-n1']]
        observed = measure(rom, False, own, root)
        bad = [r['arm']['id'] for r in observed if not r['gate']]
        if bad:
            print('NG 自作ROMの対照: '+','.join(bad))
            for r in observed:
                print(json.dumps(dict(arm=r['arm']['id'], failed=r['failed'], gate=r['gate'],
                                      obs=[{k: v for k, v in o.items() if k in ('tok', 'cur', 'pix')} for o in r['obs']])))
        assert not bad
        base = observed[1]['obs'][0]
        assert glyph_visible(base['pix']['cell']) and len(base['pix']['ref']) == 1
        # 故障注入: 印のセルを塗りつぶした画像では較正が落ちる
        blank = dict(base, pix=dict(base['pix'], cell=[[main_color(base['pix']['ref']), 160]]))
        assert not calibrated([rec('bg-base', blank)])
        print('  自作の現状: st-goto cmd/last='+json.dumps(observed[0]['obs'][0]['cur'])+' px0-n0 判定='
              +json.dumps(judge(observed[2]['obs'][0], own[2]))+' px0-n1 判定='+json.dumps(judge(observed[3]['obs'][0], own[3])), flush=True)
    print('OK 自作ROMの対照4腕×2走（st-goto・bg-base・px0-n0・px0-n1）・故障注入で較正が落ちる', flush=True)
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
    selected = [a for a in arms() if (a['id'].startswith(pre) if pre else True)]
    records = measure(rom, args.official, selected, args.work_dir)
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
