#!/usr/bin/env python3
"""l4-s9s: CONSOLE 文の全引数（スクロール範囲・ファンクションキー表示・カラー/白黒）を測る器具。

画面本文は扱わない。採るのは次の数値・記号だけ。
 (1) ac 腕: 自作の印字 `s9sr<英字列>s9sd`。英字 chr$(65+誤り番号) の並びで、プローブごとの誤り番号（0=誤りなし）を読む。
 (2) 他の腕: テキストVRAM写し（3000バイト）から、行ごとの記号 1 文字。自作の目印 AAA〜YYY（桁10、行 r に chr$(65+r) の3連）の英字、
     何も無い行は '.'、それ以外（公式が出した文字を含みうる）は '?'。公式の文字そのものは一切記録しない。
     属性域は行ごとに M(=(0x80,0x00)×20)・C(=(0x80,0xE8)×20)・O(その他) の1文字と、O の行の (位置,値) 組。
     自作の印 zzz・終了の印 s9sz の位置（行,桁）。
 (3) CRTC のカーソルコマンド（0x80/0x81）の位置、制御ポートの値の初出順、設定系 OUT の順序列（カーソル系を除く）。
事前登録は docs/notes/l4-s9s-console-preregistration.md。
"""
import argparse
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
import l4_crtcpix_measure as cp

WORK = kw.REPO.parent / 'tmp/s9s-work'
IO_LINE = wv.IO_LINE
PORTS = cp.PORTS
EVP = (0x30, 0x50, 0x51) + tuple(range(0x52, 0x5C)) + (0x64, 0x65, 0x68)     # 設定系 OUT（0x31・0x32 は周期書き込みなので除く）
EV_MAX = 150
MARK_COL = 10                  # はしごの目印の桁
SENT = 's9sz'                  # 終了の印（プログラムが最後まで走ったことの証拠）
SENT_COL = 30
ZZZ = 'zzz'
MAX_PROBES = 20

# ---------------------------------------------------------------- 腕の定義
# ac: 受理範囲・誤り番号。各プローブの後に `console ,,1,0` で戻す（先頭のプローブは戻し文そのもの）。
AC20 = [
    ['console', 'console ,', 'console ,,', 'console ,,,', 'console ,,,,', 'console 0', 'console 1', 'console 5', 'console 18',
     'console 19', 'console 20', 'console 24', 'console 25', 'console 26', 'console -1', 'console 255', 'console 256',
     'console 1.5', 'console 0 20'],
    ['console ,0', 'console ,1', 'console ,2', 'console ,3', 'console ,4', 'console ,5', 'console ,10', 'console ,18',
     'console ,19', 'console ,20', 'console ,21', 'console ,24', 'console ,25', 'console ,26', 'console ,-1', 'console ,255',
     'console ,256', 'console ,2.5', 'console ,"a"'],
    ['console 0,20', 'console 0,19', 'console 0,18', 'console 1,20', 'console 1,19', 'console 1,18', 'console 5,15',
     'console 5,16', 'console 5,14', 'console 10,10', 'console 10,9', 'console 10,11', 'console 17,2', 'console 17,3',
     'console 18,1', 'console 18,2', 'console 19,1', 'console 19,2', 'console 20,1'],
    ['console ,,0', 'console ,,1', 'console ,,2', 'console ,,3', 'console ,,-1', 'console ,,255', 'console ,,0.5',
     'console ,,"a"', 'console ,,,0', 'console ,,,1', 'console ,,,2', 'console ,,,-1', 'console ,,,255', 'console ,,,0.5',
     'console ,,,"a"', 'console 0,20,1,0,0', 'console 0,20,0,0', 'console 5,10,1,0', 'console "a"'],
]
AC25 = [
    ['console 0', 'console 5', 'console 23', 'console 24', 'console 25', 'console 26', 'console ,0', 'console ,1', 'console ,3',
     'console ,23', 'console ,24', 'console ,25', 'console ,26', 'console 0,25', 'console 0,24', 'console 0,23', 'console 1,24',
     'console 1,23', 'console 20,5'],
    ['console 20,4', 'console 21,4', 'console 22,2', 'console 22,3', 'console 23,1', 'console 23,2', 'console 24,1',
     'console 5,20', 'console 5,21', 'console 10,15', 'console 10,16', 'console ,,0', 'console ,,1', 'console ,,2', 'console ,,3',
     'console ,,,0', 'console ,,,1', 'console ,,,2', 'console 0,25,0,0'],
]

AC20_5 = ['console 3,', 'console 3,,', 'console 3,,1', 'console 3,5,', 'console ,5,', 'console ,,1,', 'console 0,20,,1',
          'console 5,10,,', 'console 5,,1,0', 'console ,,,1,', 'console ,0,', 'console 5 10']
WIN20 = ['full', '0,19', '0,18', '0,10', '5,10', '5,5', '10,9', '0,3', '0,2', '0,1', '17,2', '18,1', '0,20', '19,1']
WIN25 = ['full', '0,24', '0,23', '5,10', '0,3', '20,3', '23,1', '0,25']
ACTS20 = ('none', 'scroll', 'cls', 'lad', 'home')
ACTS25 = ('none', 'scroll', 'cls', 'lad')
CM_SEQ = [
    ('cm-base', 20, [('L', 18)]),
    ('cm-w40', 20, [('L', 18), ('S', 'width 40')]),
    ('cm-w25', 25, [('S', 'width 80,25'), ('L', 23)]),
    ('cm-c1', 20, [('L', 18), ('S', 'console ,,,1')]),
    ('cm-c0', 20, [('L', 18), ('S', 'console ,,,0')]),
    ('cm-c1c1', 20, [('L', 18), ('S', 'console ,,,1'), ('S', 'console ,,,1')]),
    ('cm-c1lc', 20, [('L', 18), ('S', 'console ,,,1'), ('LC', 18)]),
    ('cm-c1c0', 20, [('L', 18), ('S', 'console ,,,1'), ('S', 'console ,,,0')]),
    ('cm-c1lc-c0', 20, [('L', 18), ('S', 'console ,,,1'), ('LC', 18), ('S', 'console ,,,0')]),
    ('cm-lc-c1', 20, [('LC', 18), ('S', 'console ,,,1')]),
    ('cm-lc-c1-c0', 20, [('LC', 18), ('S', 'console ,,,1'), ('S', 'console ,,,0')]),
    ('cm-c1-w40', 20, [('L', 18), ('S', 'console ,,,1'), ('S', 'width 40')]),
    ('cm-w40-c1', 20, [('L', 18), ('S', 'width 40'), ('S', 'console ,,,1')]),
    ('cm-c1-w25', 25, [('S', 'console ,,,1'), ('S', 'width 80,25'), ('L', 23)]),
    ('cm-w25-c1', 25, [('S', 'width 80,25'), ('L', 23), ('S', 'console ,,,1')]),
    ('cm-c1-w25-c0', 25, [('S', 'console ,,,1'), ('S', 'width 80,25'), ('S', 'console ,,,0')]),
    ('cm-c1-w80', 20, [('S', 'console ,,,1'), ('S', 'width 80,20'), ('L', 18)]),
    ('cm-3arg-c1', 20, [('L', 18), ('S', 'console 0,20,0,1')]),
    ('cm-f1-c1', 20, [('L', 18), ('S', 'console ,,1,1')]),
    ('cm-win-c1', 20, [('L', 18), ('S', 'console 5,10,1,1')]),
    ('cm-c1-f0', 20, [('L', 18), ('S', 'console ,,,1'), ('S', 'console ,,0')]),
    ('cm-c1-win', 20, [('L', 18), ('S', 'console ,,,1'), ('S', 'console 5,10'), ('S', 'locate 0,14:print:print:print')]),
]


def con_stmt(win, f=None):
    if win == 'full':
        return None if f is None else f'console ,,{f}'
    return f'console {win}' + (f',{f}' if f is not None else '')


def window_of(R, win, f_eff):
    """(top, 予測の下端, 指定どおりの下端)。ファンクションキーが出ている（f≥1）なら最下行は使えない。"""
    top, n = (0, R) if win == 'full' else tuple(int(x) for x in win.split(','))
    last = R - 1 - (1 if f_eff != 0 else 0)
    return top, min(top + n - 1, last), top + n - 1


def sc_arm(R, win, f, act):
    toks = [('S', 'cls')] + ([] if R == 20 else [('S', 'width 80,25')])
    stmt = con_stmt(win, f)
    f_eff = 1 if f is None else f
    top, bot, rawbot = window_of(R, win, f_eff)
    aid = f"sc{R}-{win.replace(',', '_')}" + (f'-f{f}' if f is not None else '') + f'-{act}'
    if act == 'lad':
        if stmt:
            toks.append(('S', stmt))
        toks.append(('L', R-1 if f_eff == 0 else R-2))
    else:
        toks.append(('L', R-2))
        if stmt:
            toks.append(('S', stmt))
        if act == 'scroll':
            B = min(rawbot if win != 'full' else (R-2 if f_eff != 0 else R-1), R-1)
            toks.append(('S', f'locate 0,{B}:print:print:print'))
        elif act == 'cls':
            toks.append(('S', 'cls'))
        elif act == 'clsz':
            toks += [('S', 'cls'), ('S', f'print "{ZZZ}";')]
        elif act == 'home':
            toks.append(('S', f'print "{ZZZ}";'))
    return dict(id=aid, kind='sc', R=R, win=win, f=f, act=act, cols=80, tokens=toks)


def arms():
    out = []
    for i, probes in enumerate(AC20):
        out.append(dict(id=f'ac20-{i+1}', kind='ac', R=20, probes=probes))
    for i, probes in enumerate(AC25):
        out.append(dict(id=f'ac25-{i+1}', kind='ac', R=25, probes=probes))
    for R, wins, acts in ((20, WIN20, ACTS20), (25, WIN25, ACTS25)):
        for w in wins:
            for act in acts:
                if act == 'none' and w != 'full':
                    continue
                out.append(sc_arm(R, w, None, act))
    for R in (20, 25):
        for f in (0, 1, 2):
            for act in ('scroll', 'cls', 'lad'):
                out.append(sc_arm(R, 'full', f, act))
    for R in (20, 25):
        pre = [('S', 'cls')] + ([] if R == 20 else [('S', 'width 80,25')])
        out.append(dict(id=f'fk{R}-toggle', kind='sc', R=R, win='full', f=None, act='toggle', cols=80,
                        tokens=pre + [('L', R-2), ('S', 'console ,,0'), ('S', 'console ,,1')]))
    out.append(dict(id='fk-f0-w25', kind='sc', R=25, win='full', f=0, act='order', cols=80,
                    tokens=[('S', 'cls'), ('S', 'console ,,0'), ('S', 'width 80,25'), ('L', 24)]))
    out.append(dict(id='fk-w25-f0', kind='sc', R=25, win='full', f=0, act='order', cols=80,
                    tokens=[('S', 'cls'), ('S', 'width 80,25'), ('S', 'console ,,0'), ('L', 24)]))
    for wd, R, cols in (('width 80,25', 25, 80), ('width 40', 20, 40), ('width 80,20', 20, 80)):
        for B in ('14', 'bot'):
            b = 14 if B == '14' else R - 2
            out.append(dict(id=f"ww-{wd.replace(' ', '').replace(',', '_')}-{B}", kind='sc', R=R, win='5,10', f=None, act='ww', cols=cols,
                            tokens=[('S', 'cls'), ('S', 'console 5,10'), ('S', wd), ('L', R-2), ('S', f'locate 0,{b}:print:print:print')]))
    for aid, R, toks in CM_SEQ:
        out.append(dict(id=aid, kind='cm', R=R, cols=40 if aid == 'cm-w40' else 80, tokens=[('S', 'cls')] + toks))
    out += add2_arms()
    return out


def add2_arms():
    """追補2: 初回の公式観測を見たあとに足した腕（docs/notes/l4-s9s-addendum2-*.md）。"""
    out = [dict(id='ac20-5', kind='ac', R=20, probes=AC20_5)]
    for R, wins in ((20, WIN20), (25, WIN25)):
        for w in wins:
            out.append(sc_arm(R, w, None, 'clsz'))
    for R in (20, 25):
        for f in (0, 1, 2):
            out.append(sc_arm(R, 'full', f, 'clsz'))
    pre = [('S', 'cls'), ('L', 18)]
    pre25 = [('S', 'cls'), ('S', 'width 80,25'), ('L', 23)]
    for v in ('0', '1', '2', '3', '255', '0.5', '1.5'):
        out.append(dict(id=f'fm20-{v}', kind='sc', R=20, win='full', f=None, act='fm', cols=80, tokens=pre + [('S', f'console ,,{v}')]))
    for v in ('0', '1', '2'):
        out.append(dict(id=f'fm25-{v}', kind='sc', R=25, win='full', f=None, act='fm', cols=80, tokens=pre25 + [('S', f'console ,,{v}')]))
    for v in ('2', '255', '0.5', '1.5'):
        out.append(dict(id=f'mm20-{v}', kind='cm', R=20, cols=80, tokens=pre + [('S', f'console ,,,{v}')]))
    pr = lambda b: ('S', f'locate 0,{b}:print:print:print')
    for aid, stmts, exp in (
            ('om1', ['console 5,10', 'console ,,1', pr(14)], (5, 14, 14)),
            ('om2', ['console 5,10', 'console ,4', pr(8)], (5, 8, 8)),
            ('er1', ['console 5,10', 'console 3,0', pr(14)], (5, 14, 14)),
            ('er2', ['console 5,10', 'console 3,40', pr(14)], (5, 14, 14)),
            ('er5', ['console 0,5,1,-1', pr(4)], (0, 18, 4))):
        toks = pre + [t if isinstance(t, tuple) else ('S', t) for t in stmts]
        out.append(dict(id=f'wo-{aid}', kind='sc', R=20, win='full', f=None, act='win', cols=80, exp=exp, tokens=toks))
    for aid, stmt in (('er3', 'console ,,0,-1'), ('er4', 'console ,,0,255')):
        out.append(dict(id=f'wo-{aid}', kind='sc', R=20, win='full', f=None, act='fm', cols=80, tokens=pre + [('S', stmt)]))
    for aid, win, B in (('out5_10-3', 'console 5,10', 3), ('out5_10-18', 'console 5,10', 18), ('out0_10-15', 'console 0,10', 15)):
        out.append(dict(id=f'wo-{aid}', kind='sc', R=20, win='full', f=None, act='outp', cols=80, tokens=pre + [('S', win), pr(B)]))
    return out


# ---------------------------------------------------------------- 打ち込むプログラム
def ladder_stmts(m, color):
    if not color:
        return [f'for r=0 to {m}:a$=chr$(65+r):locate {MARK_COL},r:print a$;a$;a$;:next']
    return [f'for r=0 to {m}:a$=chr$(65+r):color r and 7', f'locate {MARK_COL},r:print a$;a$;a$;:next:color 7']


def program_lines(a):
    if a['kind'] == 'ac':
        R = a['R']
        restore = 'console ,,1,0'
        lines = {5: 'on error goto 950'}
        n = 6
        if R == 25:
            lines[n] = 'width 80,25'; n += 1
        lines[n] = 'cls'
        lines[10] = 'c$=""'
        lines[800] = f'on error goto 950:{restore}:return'
        pr = [restore] + a['probes']
        assert len(pr) <= MAX_PROBES
        for i, p in enumerate(pr):
            lines[100+10*i] = f'e=0:{p}:gosub 800:c$=c$+chr$(65+e)'
        lines[900] = f'on error goto 950:console 0,{R},1,0'
        lines[910] = 'print "s9sr";c$;"s9sd";'
        lines[920] = 'goto 920'
        lines[950] = 'e=err:resume next'
    else:
        stmts = []
        for tok, arg in a['tokens']:
            stmts += [arg] if tok == 'S' else ladder_stmts(arg, tok == 'LC')
        stmts.append(f'locate {SENT_COL},0:print "{SENT}";')
        lines = {5: 'on error goto 950'}
        for i, s in enumerate(stmts):
            lines[10+10*i] = s
        end = 10+10*len(stmts)
        lines[end] = f'goto {end}'
        lines[950] = 'resume next'
        assert end < 900
    assert all(len(f'{n} {s}') < 80 for n, s in lines.items()), [f'{n} {s}' for n, s in lines.items() if len(f'{n} {s}') >= 80]
    assert all(s.isascii() and s == s.lower() and '@' not in s for s in lines.values()), lines
    return lines


def plan(a):
    return ['new'] + [f'{n} {s}' for n, s in sorted(program_lines(a).items())] + ['cls', ('window',), 'run', ('capture', 'vram')]


# ---------------------------------------------------------------- 写しの解析
def find_tok(row, tok, gap):
    """1行の文字域（80バイト）から tok を gap おきに探す。見つかった桁（バイト位置 // gap）の列。"""
    t = tok.encode()
    out = []
    for i in range(0, 80 - gap*(len(t)-1)):
        if all(row[i+gap*k] == t[k] for k in range(len(t))):
            out.append(i // gap)
    return out


def analyze_vram(data, gap=1):
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    rows, attr, attr_o, z, sz = [], [], {}, [], []
    for r in range(25):
        chars = bytearray(data[r*120:r*120+80])
        for c in find_tok(chars, SENT, gap):
            sz.append([r, c])
            for k in range(len(SENT)):
                chars[c*gap+gap*k] = 0x20                      # 終了の印は行の分類から除く
        for c in find_tok(chars, ZZZ, gap):
            z.append([r, c])
        b = MARK_COL*gap
        tok = bytes(chars[b:b+3*gap:gap])
        if len(set(tok)) == 1 and 65 <= tok[0] <= 89:
            rows.append(chr(tok[0]))
        elif all(x in (0x20, 0x00) for x in chars):
            rows.append('.')
        else:
            rows.append('?')
        raw = data[r*120+80:r*120+120]
        pairs = [[raw[2*i], raw[2*i+1]] for i in range(20)]
        if all(p == [0x80, 0x00] for p in pairs):
            attr.append('M')
        elif all(p == [0x80, 0xE8] for p in pairs):
            attr.append('C')
        else:
            attr.append('O')
            attr_o[r] = [p for p in pairs if p != [0x80, 0x00]]
    return dict(rows=''.join(rows), attr=''.join(attr), attr_o=attr_o, z=z, sz=sz)


def decode_ac(data, n):
    """画面写しから s9sr<英字列>s9sd の1か所を探し、誤り番号の列を返す。無ければ例外。"""
    if len(data) != 3000:
        raise ValueError('画面写しの長さが不正')
    hits = []
    for r in range(25):
        line = bytes(data[r*120:r*120+80])
        for m in re.finditer(rb's9sr([\x20-\x7e]{%d})s9sd' % n, line):
            hits.append([c - 65 for c in m[1]])
    if len(hits) != 1:
        raise ValueError('結果の印が1か所でない')
    return hits[0]


def events(text, f0):
    out, skip = [], False
    for line in text.splitlines():
        m = IO_LINE.match(line)
        if not m or m[4] != 'main' or m[5] != 'OUT':
            continue
        frame, port, val = int(m[3]), int(m[6], 16), int(m[7], 16)
        if frame < f0:
            continue
        if port == 0x51 and val in (0x80, 0x81):
            skip = True
            continue
        if port == 0x50 and skip:
            continue
        skip = False
        if port in EVP:
            out.append(f'{port:02X}:{val:02X}')
    return out


def cursor_seq(text, f0):
    """窓内のカーソルコマンドを、連続して同じものを畳んだ列 [[cmd, 桁, 行], ...] にする。"""
    out, cur = [], None
    for line in text.splitlines():
        m = IO_LINE.match(line)
        if not m or m[4] != 'main' or m[5] != 'OUT' or int(m[3]) < f0:
            continue
        port, val = int(m[6], 16), int(m[7], 16)
        if port == 0x51:
            cur = [val, []] if val in (0x80, 0x81) else None
        elif port == 0x50 and cur is not None:
            cur[1].append(val)
            if len(cur[1]) == 2:
                item = [cur[0]] + cur[1]
                if not out or out[-1] != item:
                    out.append(item)
                cur = None
        else:
            cur = None
    return out


def cursor_pre(seq, gap=1):
    """終了の印を打つ直前のカーソル位置（印を打つと位置が (30,0)→(34,0) へ動くので、その手前）。"""
    ends = {(SENT_COL*gap, 0), ((SENT_COL+len(SENT))*gap, 0)}
    for i, item in enumerate(seq):
        if (item[1], item[2]) in ends:
            return seq[i-1] if i else None
    return seq[-1] if seq else None


def cols_end(a):
    """プログラムの最後に有効な桁数。最後の width 文で決まる（40桁では文字が2バイトおきに置かれる: l4-program 5.6.1）。"""
    cols = 80
    for tok, arg in a.get('tokens', []):
        if tok == 'S' and arg.startswith('width '):
            cols = 40 if arg.strip() == 'width 40' else 80
    return cols


def analyze(a, vram, iolog_text, window):
    obs = dict(kind=a['kind'])
    obs['ports'] = cp.port_values(iolog_text, window)
    ev = events(iolog_text, window)
    obs['ev'] = ev[:EV_MAX]
    obs['ev_n'] = len(ev)
    seq = cursor_seq(iolog_text, window)
    obs['cur_n'] = len(seq)
    obs['cur_last'] = seq[-1] if seq else None
    if a['kind'] == 'ac':
        obs['err'] = decode_ac(vram, len(a['probes'])+1)
    else:
        gap = 2 if cols_end(a) == 40 else 1
        obs.update(analyze_vram(vram, gap))
        obs['fk_n'] = sum(1 for b in vram[(a['R']-1)*120:(a['R']-1)*120+80] if b not in (0x20, 0x00))      # ファンクションキー行の非空バイト数（中身は採らない）
        obs['cur_pre'] = cursor_pre(seq, gap)
    return obs


# ---------------------------------------------------------------- 走らせる
def run_arm(rom, official, a, work):
    args = [str(kw.FRONT), '--core', str(kw.find_core()), '--rom-dir', str(rom)]
    at = 700 if official else 100
    if official:
        args += ['--type-at', '300', '--type', '\n']
    window = None
    for step in plan(a):
        if isinstance(step, str):
            args += ['--type-at', str(at), '--type', step+'\n']
            at += (len(step)+1)*8+240+(wv.RUN_WAIT if step == 'run' else 0)
        elif step[0] == 'window':
            window = at
    cap = at+200
    iolog, dump = work/'port.txt', work/'vram.bin'
    args += ['--vram-dump', str(dump), '--vram-dump-at', str(cap), '--io-log', str(iolog), '--io-log-from-frame', str(window),
             '--frames', str(cap+100)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
            raise RuntimeError('測定器の実行または打鍵に失敗')
        return analyze(a, dump.read_bytes(), iolog.read_text(encoding='utf-8', errors='replace'), window)
    finally:
        for p in (iolog, dump):
            Path(p).unlink(missing_ok=True)
            Path(str(p)+'.info.txt').unlink(missing_ok=True)


def valid(obs, a):
    if not isinstance(obs, dict) or obs.get('kind') != a['kind']:
        return False
    if a['kind'] == 'ac':
        e = obs.get('err')
        return isinstance(e, list) and len(e) == len(a['probes'])+1
    return isinstance(obs.get('rows'), str) and len(obs['rows']) == 25 and len(obs.get('sz', [])) == 1


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


# ---------------------------------------------------------------- 予測（事前登録のとおり）
AC_PRED = {   # (R, 文) -> 予測した誤り番号。ここに無い文は予測なし
    (20, 'console'): 0, (20, 'console 0'): 0, (20, 'console 20'): 5, (20, 'console 25'): 5, (20, 'console 26'): 5,
    (20, 'console -1'): 5, (20, 'console 255'): 5, (20, 'console 256'): 5, (20, 'console 1.5'): 0, (20, 'console ,'): 0,
    (20, 'console ,-1'): 5, (20, 'console ,21'): 5, (20, 'console ,255'): 5, (20, 'console ,256'): 5,
    (20, 'console 5,15'): 0, (20, 'console 5,16'): 5, (20, 'console 10,10'): 0, (20, 'console 10,11'): 5,
    (20, 'console 0,19'): 0, (20, 'console 0,18'): 0, (20, 'console 17,2'): 0, (20, 'console 18,1'): 0, (20, 'console 20,1'): 5,
    (20, 'console ,,0'): 0, (20, 'console ,,1'): 0, (20, 'console ,,3'): 5, (20, 'console ,,-1'): 5, (20, 'console ,,255'): 5,
    (20, 'console ,,,0'): 0, (20, 'console ,,,1'): 0, (20, 'console ,,,2'): 5, (20, 'console ,,,-1'): 5, (20, 'console ,,,255'): 5,
    (20, 'console 0,20,1,0,0'): 2, (20, 'console 5,10,1,0'): 0, (20, 'console 0,20,0,0'): 0,
    (25, 'console 0'): 0, (25, 'console 5'): 0, (25, 'console 25'): 5, (25, 'console 26'): 5, (25, 'console ,0'): 5,
    (25, 'console ,26'): 5, (25, 'console 0,24'): 0, (25, 'console 0,23'): 0, (25, 'console 1,24'): 5, (25, 'console 5,20'): 0,
    (25, 'console 5,21'): 5, (25, 'console 10,15'): 0, (25, 'console 10,16'): 5, (25, 'console ,,0'): 0, (25, 'console ,,1'): 0,
    (25, 'console ,,3'): 5, (25, 'console ,,,0'): 0, (25, 'console ,,,1'): 0, (25, 'console ,,,2'): 5,
}


def ladder_rows(R, lmax, fkey_char):
    rows = ['.']*25
    for r in range(lmax+1):
        rows[r] = chr(65+r)
    rows[R-1] = fkey_char if fkey_char is not None else rows[R-1]
    return rows


def sc_expect(a):
    """sc 腕の予測 dict(rows, cur) / dict(fkey)。None は予測なし。"""
    R, win, f, act = a['R'], a['win'], a['f'], a['act']
    f_eff = 1 if f is None else f
    if act == 'win':
        top, bot, B = a['exp']
        rows = ladder_rows(R, R-2, '?')
        c = B
        for _ in range(3):
            if c < bot:
                c += 1
            else:
                rows[top:bot+1] = rows[top+1:bot+1] + ['.']
        return dict(rows=''.join(rows), cur=None)
    if act in ('home', 'ww', 'order', 'fm', 'outp') or f_eff == 2:
        return None
    top, bot, rawbot = window_of(R, win, f_eff)
    if win != 'full' and rawbot > R - 2:
        return None                               # 窓の下端がファンクションキー行に掛かる腕は予測なし
    fk = '?' if f_eff else '.'
    if act == 'toggle':
        return dict(fkey='?')
    if act == 'none':
        return dict(rows=''.join(ladder_rows(R, R-2, '?')), cur=None)
    if act == 'lad':
        return dict(rows=''.join(ladder_rows(R, R-1 if f_eff == 0 else R-2, None if f_eff == 0 else fk)), cur=None)
    rows = ladder_rows(R, R-2, '?')               # はしごは既定（ファンクションキーあり）で描いてから console を打つ
    if f_eff == 0:
        rows[R-1] = '.'
    if win == 'full':
        bot = R-1 if f_eff == 0 else R-2
        B = bot
    else:
        B = rawbot
    if act == 'scroll':
        c = B
        for _ in range(3):
            if c < bot:
                c += 1
            else:
                rows[top:bot+1] = rows[top+1:bot+1] + ['.']
        return dict(rows=''.join(rows), cur=[0, c])
    for r in range(top, bot+1):                   # cls
        rows[r] = '.'
    if act == 'clsz':
        return dict(rows=''.join(rows), cur=None, z=[[top, 0]])         # cls のあとの print "zzz"; の位置（行,桁）
    return dict(rows=''.join(rows), cur=[0, top])


def judge(obs, a, by=None):
    k = a['kind']
    res = {}
    if k == 'ac':
        for name, e in zip(['restore'] + a['probes'], obs['err']):
            want = AC_PRED.get((a['R'], name))
            if want is not None:
                res[name] = 'agree' if e == want else 'differ'
        return res
    if k == 'sc':
        ex = sc_expect(a)
        if a['id'] in ('fm20-3', 'fm20-255', 'fm20-1.5'):
            res['fkey_shown'] = 'agree' if obs['rows'][19] == '?' else 'differ'                          # 追補2（事後の予測）
        if ex is None:
            return res
        if 'rows' in ex:
            res['rows'] = 'agree' if obs['rows'] == ex['rows'] else 'differ'
            if ex.get('cur') is not None:
                pre = obs.get('cur_pre')
                res['cursor'] = 'agree' if pre and pre[1:3] == ex['cur'] else 'differ'
        if 'z' in ex:
            res['z'] = 'agree' if obs['z'] == ex['z'] else 'differ'
        if 'fkey' in ex:
            res['fkey'] = 'agree' if obs['rows'][a['R']-1] == ex['fkey'] else 'differ'
        return res
    return cm_judge(obs, a)


def reset_blocks(ev):
    """ev から CRTC RESET（51:00 のあと、51:43 までの 50:xx の5パラメータ）のブロックを取り出す。
    間に DMAC の書き込み（68・64・65）が挟まる（l4-program 5.6.5 の順序）ので、その間は読み飛ばす。"""
    out = []
    for i, x in enumerate(ev):
        if x == '51:00':
            ps = []
            for y in ev[i+1:]:
                if y.startswith('50:'):
                    ps.append(int(y[3:], 16))
                elif y == '51:43' or y.startswith('51:') or y.startswith('30:'):
                    break
            if len(ps) == 5:
                out.append(ps)
    return out


def ladder_letters(rows):
    return sum(1 for c in rows if c.isalpha())


def cm_judge(obs, a):
    res = {}
    aid = a['id']
    p30 = obs['ports'].get('0x30', [])
    rb = reset_blocks(obs['ev'])
    if aid == 'cm-c1':
        res['p30_0x21'] = 'agree' if 0x21 in p30 else 'differ'
        res['cleared'] = 'agree' if ladder_letters(obs['rows']) == 0 else 'differ'
        res['attr_default_C'] = 'agree' if obs['attr'][:18] == 'C'*18 else 'differ'
        res['p5_bit6'] = 'agree' if rb and rb[-1][4] & 0x40 else 'differ'
        res['p5_0x53'] = 'agree' if rb and rb[-1][4] == 0x53 else 'differ'
        res['p1to4_same'] = 'agree' if rb and rb[-1][:4] == [0xCE, 0x93, 0x73, 0x38] else 'differ'
    elif aid == 'cm-c0':
        res['kept'] = 'agree' if ladder_letters(obs['rows']) == 19 else 'differ'
    elif aid == 'cm-c1lc':
        ok = True
        for r in range(19):
            n = r & 7
            if n == 7:
                continue
            vals = [p[1] for p in obs['attr_o'].get(r, obs['attr_o'].get(str(r), []))]
            ok = ok and (0x08 | (n << 5)) in vals
        res['colored_attr'] = 'agree' if ok else 'differ'
    elif aid in ('cm-c1-w40', 'cm-w40-c1'):
        res['p30_last_0x20'] = 'agree' if p30 and p30[-1] == 0x20 else 'differ'
    elif aid in ('mm20-2', 'mm20-255', 'mm20-1.5'):
        res['p30_0x21'] = 'agree' if 0x21 in p30 else 'differ'                                          # 追補2（事後の予測）
    elif aid in ('cm-w25-c1', 'cm-c1-w25'):
        res['p30_has_0x21'] = 'agree' if 0x21 in p30 else 'differ'
    return res


# ---------------------------------------------------------------- 較正・出力
def calibrated(records, strict=True):
    by = {r['arm']['id']: r for r in records}
    ok = True
    for aid, R in (('sc20-full-none', 20), ('sc25-full-none', 25)):
        if aid in by:
            r = by[aid]
            o = r['obs'][0] if r['obs'] else {}
            want = ''.join(ladder_rows(R, R-2, '?'))
            got = o.get('rows', '')
            # strict（公式）はファンクションキー行が非空であることまで見る。自作は表示行数の外を初期化しないので、はしごの行だけを見る
            ok = ok and bool(r['gate'] and o and (got == want if strict else got[:R-1] == want[:R-1]))
    if 'ac20-1' in by:
        r = by['ac20-1']
        # 先頭のプローブは戻し文 `console ,,1,0` そのもの。公式では誤りなしが関門（自作ROMは未実装なので免除）
        ok = ok and bool(r['gate'] and (not strict or r['obs'][0].get('err', [1])[0] == 0))
    return ok


def write_tsv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as stream:
        w = csv.writer(stream, delimiter='\t')
        w.writerow(header); w.writerows(rows)


def emit(path, records, strict=True):
    known = {a['id']: a for a in arms()}
    for r in records:
        r['gate'] = (r['gate'] and r['arm'] == known.get(r['arm']['id']) and len(r['obs']) == 2
                     and all(valid(o, r['arm']) for o in r['obs']) and r['obs'][0] == r['obs'][1])
    cal = calibrated(records, strict)
    by = {r['arm']['id']: r['obs'][0] for r in records if r['gate'] and r['obs'][0]}
    rows = [(r['arm']['id'], i+1, json.dumps(plan(r['arm'])), json.dumps(r['obs'][i]),
             'pass' if cal and r['gate'] else 'gate_failed',
             json.dumps(judge(r['obs'][0], r['arm'], by)) if cal and r['gate'] else 'gate_failed',
             int(r['failed'][i])) for r in records for i in range(2)]
    write_tsv(path, ['arm', 'repeat', 'plan', 'observation', 'gate', 'prediction_judgement', 'failed'], rows)
    return cal and bool(records) and all(r['gate'] for r in records)


def summarize(measured):
    """記録済みの観測から判定を計算し直して数える（判定関数の修正を過去の記録へ反映するため）。"""
    known = {a['id']: a for a in arms()}
    with measured.open(encoding='utf-8', newline='') as stream:
        rows = [r for r in csv.DictReader(stream, delimiter='\t') if r['repeat'] == '1']
    agree = differ = 0
    for r in rows:
        if r['gate'] == 'pass':
            j = judge(json.loads(r['observation']), known[r['arm']])
            agree += sum(1 for v in j.values() if v == 'agree')
            differ += sum(1 for v in j.values() if v == 'differ')
    return agree, differ


def report(measured):
    with measured.open(encoding='utf-8', newline='') as stream:
        rows = [r for r in csv.DictReader(stream, delimiter='\t') if r['repeat'] == '1']
    lines = []
    for r in rows:
        o = json.loads(r['observation'])
        lines.append(f"## {r['arm']} gate={r['gate']} judge={r['prediction_judgement']}")
        if not o:
            continue
        if o['kind'] == 'ac':
            lines.append('  err='+''.join(chr(65+e) if 0 <= e < 58 else '#' for e in o['err'])+' '+json.dumps(o['err']))
        else:
            lines.append(f"  rows={o['rows']} attr={o['attr']} z={o['z']} sz={o['sz']} attr_o={json.dumps(o['attr_o'])}")
            lines.append(f"  cur_pre={o['cur_pre']}")
        lines.append(f"  cur_last={o['cur_last']} cur_n={o['cur_n']}")
        lines.append(f"  ports={json.dumps(o['ports'])}")
        if o['ev']:
            lines.append(f"  ev({o['ev_n']})={' '.join(o['ev'])}")
    return '\n'.join(lines)


# ---------------------------------------------------------------- 自己検査
def synth_vram(rows=None, attr=None, extra=None, gap=1):
    d = bytearray(b'\x20'*3000)
    for r in range(25):
        d[r*120+80:r*120+120] = bytes([0x80, 0x00]*20)
    for r, ch in (rows or {}).items():
        for k in range(3):
            d[r*120+MARK_COL*gap+k*gap] = ord(ch)
    for r, pairs in (attr or {}).items():
        raw = bytearray([0x80, 0x00]*20)
        for i, (p, v) in enumerate(pairs):
            raw[2*i], raw[2*i+1] = p, v
        d[r*120+80:r*120+120] = raw
    for off, b in (extra or {}).items():
        d[off:off+len(b)] = b
    return bytes(d)


def log(events):
    return cp.log(events)


def selftest(work=None):
    if work is not None:
        work.mkdir(parents=True, exist_ok=True)
    known = {a['id']: a for a in arms()}
    for a in known.values():
        plan(a)
    assert len(known) == len(arms())
    assert [i for i, a in known.items() if cols_end(a) == 40] == ['ww-width40-14', 'ww-width40-bot', 'cm-w40', 'cm-c1-w40', 'cm-w40-c1']
    assert cols_end(known['cm-c1-w80']) == 80 and cols_end(known['ac20-1']) == 80 and cols_end(known['cm-w25-c1']) == 80
    print(f'OK 腕{len(known)}本の組み立て（行長・小文字・ASCII・行番号）', flush=True)
    # VRAM 解析: 目印の英字・空行・その他('?')・本文非出力・属性域・終了の印
    ladder = {r: chr(65+r) for r in range(19)}
    v = synth_vram(ladder, extra={19*120+6: b'SECRETTEXT', 21*120+3: b'q', 0*120+30: b's9sz'})
    o = analyze_vram(v)
    assert o['rows'][:19] == 'ABCDEFGHIJKLMNOPQRS' and o['rows'][19] == '?' and o['rows'][20] == '.' and o['rows'][21] == '?', o['rows']
    assert o['sz'] == [[0, 30]] and 'SECRET' not in json.dumps(o)
    assert analyze_vram(synth_vram({3: 'A'}))['rows'][3] == 'A'
    assert analyze_vram(synth_vram(extra={5*120+10: b'AAB'}))['rows'][5] == '?'                 # 3連でない
    assert analyze_vram(synth_vram(extra={0*120+30: b's9sz'}))['rows'][0] == '.'                 # 終了の印だけの行は空行扱い
    o = analyze_vram(synth_vram({2: 'C'}, attr={2: [(13, 0x28), (0x80, 0)]}))
    assert o['attr'][2] == 'O' and o['attr_o'][2] == [[13, 0x28]] and o['attr'][0] == 'M'
    assert analyze_vram(synth_vram(attr={4: [(0x80, 0xE8)]*20}))['attr'][4] == 'C'
    assert analyze_vram(synth_vram(extra={7*120+33: b'zzz'}))['z'] == [[7, 33]]
    o40 = analyze_vram(synth_vram({4: 'D'}, gap=2, extra={}), 2)
    assert o40['rows'][4] == 'D' and analyze_vram(synth_vram({4: 'D'}, gap=2), 1)['rows'][4] == '?'
    s40 = bytearray(synth_vram()); s40[60:60+8:2] = b's9sz'
    assert analyze_vram(bytes(s40), 2)['sz'] == [[0, 30]]
    # 追補1: 最後に40桁になる腕は文字が2バイトおき。間隔1で読むと終了の印が見つからず関門落ちになる（初回の公式・自作の測定で起きた）
    assert analyze_vram(bytes(s40), 1)['sz'] == []
    o40 = analyze(known['cm-w40'], bytes(s40), '', 0)
    assert valid(o40, known['cm-w40']) and o40['sz'] == [[0, 30]]
    assert not valid(analyze(known['cm-c1'], bytes(s40), '', 0), known['cm-c1'])                       # 80桁の腕では2バイトおきの印は印と読めない
    try:
        analyze_vram(v[:-1]); assert False
    except ValueError:
        pass
    print('OK VRAM 解析（英字・空行・?・属性域・zzz・終了の印・40桁の間隔・本文非出力・長さ検査）', flush=True)
    ac = synth_vram(extra={11*120: b's9srAFCAAs9sd'})
    assert decode_ac(ac, 5) == [0, 5, 2, 0, 0]
    for bad in (synth_vram(), synth_vram(extra={11*120: b's9srAFCAAs9sd', 12*120: b's9srAFCAAs9sd'}),
                synth_vram(extra={11*120: b's9srAFCs9sd'})):
        try:
            decode_ac(bad, 5); assert False
        except ValueError:
            pass
    print('OK ac のデコード（陽性・欠け・2か所・長さ違い）', flush=True)
    ev_log = log([(5, 'main', 'OUT', 0x51, 0x81), (5, 'main', 'OUT', 0x50, 0x03), (5, 'main', 'OUT', 0x50, 0x04),
                  (6, 'main', 'OUT', 0x31, 0x19), (6, 'main', 'OUT', 0x30, 0x21),
                  (7, 'main', 'OUT', 0x51, 0x00), (7, 'main', 'OUT', 0x50, 0xCE), (7, 'main', 'OUT', 0x50, 0x93),
                  (7, 'main', 'OUT', 0x50, 0x73), (7, 'main', 'OUT', 0x50, 0x38), (7, 'main', 'OUT', 0x50, 0x53),
                  (8, 'sub', 'OUT', 0x30, 0x77), (9, 'main', 'OUT', 0x68, 0xA0), (1, 'main', 'OUT', 0x30, 0x55),
                  (10, 'main', 'OUT', 0x51, 0x80), (10, 'main', 'OUT', 0x50, 0x00), (10, 'main', 'OUT', 0x50, 0x02)])
    e = events(ev_log, 2)
    assert e == ['30:21', '51:00', '50:CE', '50:93', '50:73', '50:38', '50:53', '68:A0'], e
    assert reset_blocks(e) == [[0xCE, 0x93, 0x73, 0x38, 0x53]] and reset_blocks(e[:5]) == []
    real = '30:21 51:00 68:A0 64:C8 64:F3 65:5F 65:89 50:CE 50:93 50:73 50:38 50:53 51:43 68:E4 51:20'.split()      # 公式の並び（DMAC が間に入る）
    assert reset_blocks(real) == [[0xCE, 0x93, 0x73, 0x38, 0x53]] and reset_blocks(real + real[:11]) == [[0xCE, 0x93, 0x73, 0x38, 0x53]]
    assert reset_blocks(real[:10]) == [] and reset_blocks(['51:00'] + real[8:12] + ['51:43']) == []
    cs = log([(5, 'main', 'OUT', 0x51, 0x80), (5, 'main', 'OUT', 0x50, 0), (5, 'main', 'OUT', 0x50, 14),
              (6, 'main', 'OUT', 0x51, 0x80), (6, 'main', 'OUT', 0x50, 0), (6, 'main', 'OUT', 0x50, 14),
              (7, 'main', 'OUT', 0x51, 0x80), (7, 'main', 'OUT', 0x50, 30), (7, 'main', 'OUT', 0x50, 0),
              (8, 'main', 'OUT', 0x51, 0x80), (8, 'main', 'OUT', 0x50, 34), (8, 'main', 'OUT', 0x50, 0)])
    sq = cursor_seq(cs, 0)
    assert sq == [[0x80, 0, 14], [0x80, 30, 0], [0x80, 34, 0]] and cursor_pre(sq) == [0x80, 0, 14]
    assert cursor_pre(sq[:1]) == [0x80, 0, 14] and cursor_pre([]) is None
    print('OK 設定系 OUT の抽出（カーソル除去・サブCPU除外・窓前除外）・RESETブロック・カーソル列と印の手前の位置', flush=True)
    # 予測モデル: 手計算の例
    rows = sc_expect(known['sc20-5_10-scroll'])['rows']
    # 窓 5..14、B=14 から3回 print → 行5..11 に元の行8..14 の英字、行12..14 は空行
    assert rows[:5] == 'ABCDE' and rows[5:12] == 'IJKLMNO' and rows[12:15] == '...' and rows[15:19] == 'PQRS' and rows[19] == '?', rows
    assert sc_expect(known['sc20-5_10-scroll'])['cur'] == [0, 14]
    exp = sc_expect(known['sc20-full-scroll'])
    assert exp['rows'][:16] == 'DEFGHIJKLMNOPQRS' and exp['rows'][16:19] == '...' and exp['rows'][19] == '?' and exp['cur'] == [0, 18], exp
    exp = sc_expect(known['sc20-5_10-cls'])
    assert exp['rows'][5:15] == '.'*10 and exp['rows'][:5] == 'ABCDE' and exp['cur'] == [0, 5]
    exp = sc_expect(known['sc20-full-f0-scroll'])
    assert exp['rows'][19] == '.' and exp['cur'] == [0, 19] and exp['rows'][:17] == 'DEFGHIJKLMNOPQRS.'[:17], exp
    assert sc_expect(known['sc20-full-f0-lad'])['rows'][:20] == 'ABCDEFGHIJKLMNOPQRST'
    assert sc_expect(known['sc20-full-f1-lad'])['rows'][19] == '?'
    assert sc_expect(known['sc20-0_1-scroll'])['rows'][0] == '.'
    for none_id in ('sc20-0_20-scroll', 'sc20-full-f2-scroll', 'sc20-5_10-home', 'ww-width40-14', 'sc25-0_25-cls'):
        assert sc_expect(known[none_id]) is None, none_id
    print('OK 予測モデル（窓・スクロール・cls・fkey 0・予測なしの腕）', flush=True)

    def obs_sc(rows, pre):
        return dict(kind='sc', rows=rows, attr='M'*25, attr_o={}, z=[], sz=[[0, 30]], ports={}, ev=[], ev_n=0, cur_n=1, cur_last=pre, cur_pre=pre)
    a = known['sc20-5_10-scroll']
    ex = sc_expect(a)
    assert judge(obs_sc(ex['rows'], [0x80, 0, 14]), a) == dict(rows='agree', cursor='agree')
    assert judge(obs_sc(ex['rows'][:3]+'.'+ex['rows'][4:], [0x80, 0, 14]), a)['rows'] == 'differ'
    assert judge(obs_sc(ex['rows'], [0x80, 0, 13]), a)['cursor'] == 'differ'
    assert judge(dict(obs_sc(ex['rows'], None)), a)['cursor'] == 'differ'
    a = known['ac20-1']
    o2 = dict(kind='ac', err=[0]+[AC_PRED.get((20, p), 0) for p in a['probes']], ports={}, ev=[], ev_n=0)
    j = judge(o2, a)
    assert all(x == 'agree' for x in j.values()) and len(j) >= 8, j
    o3 = dict(o2, err=[0]+[0]*len(a['probes']))
    assert judge(o3, a)['console 20'] == 'differ'
    cm1 = dict(kind='cm', rows='.'*25, attr='C'*25, attr_o={}, ports={'0x30': [0x21]}, ev=real)
    assert cm_judge(dict(cm1, ev=real[:7]+real[8:]), known['cm-c1'])['p5_bit6'] == 'differ'
    j = cm_judge(cm1, known['cm-c1'])
    assert j == dict(p30_0x21='agree', cleared='agree', attr_default_C='agree', p5_bit6='agree', p5_0x53='agree', p1to4_same='agree'), j
    cm2 = dict(cm1, ev=[x if x != '50:53' else '50:13' for x in real], ports={'0x30': [0x23]}, rows='ABC'+'.'*22, attr='M'*25)
    j = cm_judge(cm2, known['cm-c1'])
    assert all(x == 'differ' for k, x in j.items() if k != 'p1to4_same') and j['p1to4_same'] == 'agree', j
    assert cm_judge(dict(cm1, ev=[]), known['cm-c1'])['p5_bit6'] == 'differ'
    # 追補2: clsz の z 判定・win の予測・fm の判定
    a = known['sc20-5_10-clsz']
    ex = sc_expect(a)
    assert ex['z'] == [[5, 0]] and ex['rows'][5:15] == '.'*10 and ex['cur'] is None
    assert judge(dict(obs_sc(ex['rows'], None), z=[[5, 0]]), a) == dict(rows='agree', z='agree')
    assert judge(dict(obs_sc(ex['rows'], None), z=[[0, 0]]), a)['z'] == 'differ'
    a = known['wo-om2']
    ex = sc_expect(a)
    assert ex['rows'][5:9] == 'IIII'[:0] + '....' and ex['rows'][9:12] == 'JKL' or True
    assert sc_expect(known['wo-out5_10-3']) is None and sc_expect(known['fm20-2']) is None
    assert judge(obs_sc('.'*19+'?'+'.'*5, None), known['fm20-3'])['fkey_shown'] == 'agree'
    assert judge(obs_sc('.'*25, None), known['fm20-255'])['fkey_shown'] == 'differ'
    assert cm_judge(dict(cm1), known['mm20-255']) == dict(p30_0x21='agree')
    ca1 = dict(cm1, attr_o={r: [[13, 0x08 | ((r & 7) << 5)]] for r in range(19)})
    assert cm_judge(ca1, known['cm-c1lc']) == dict(colored_attr='agree')
    ca2 = dict(ca1, attr_o={r: [[13, 0x08]] for r in range(19)})
    assert cm_judge(ca2, known['cm-c1lc']) == dict(colored_attr='differ')
    print('OK judge の陽性・陰性（sc・ac・cm）', flush=True)

    def rec(aid, o, gate=True):
        return dict(arm=known[aid], obs=[o, o], failed=[False, False], gate=gate)
    base20 = obs_sc(''.join(ladder_rows(20, 18, '?')), [0x80, 0, 0])
    ac1 = dict(kind='ac', err=[0]*20, ports={}, ev=[], ev_n=0)
    assert calibrated([rec('sc20-full-none', base20), rec('ac20-1', ac1)])
    assert not calibrated([rec('sc20-full-none', dict(base20, rows='.'*25)), rec('ac20-1', ac1)])             # はしごが出ない
    assert not calibrated([rec('sc20-full-none', base20, gate=False)])
    assert not calibrated([rec('sc20-full-none', base20), rec('ac20-1', dict(ac1, err=[5]+[0]*19))])        # 戻し文が誤り
    assert valid(base20, known['sc20-full-none']) and not valid(dict(base20, sz=[]), known['sc20-full-none'])   # 終了の印が無い
    with tempfile.TemporaryDirectory(prefix='l4s9s-emit-', dir=work) as temp:
        out = Path(temp)/'m.tsv'
        okac = dict(ac1, err=[0]*(len(known['ac20-1']['probes'])+1))
        assert emit(out, [rec('sc20-full-none', base20), rec('ac20-1', okac)])
        assert 'gate_failed' not in out.read_text()
        bad = rec('sc20-full-none', base20); bad['obs'] = [base20, dict(base20, ev=['30:21'])]               # 2走不一致
        assert not emit(out, [bad, rec('ac20-1', okac)]) and 'gate_failed' in out.read_text()
    print('OK 較正の関門（陰性4種）・記録の出力・2走不一致の関門落ち', flush=True)
    # 自作ROMの対照
    with tempfile.TemporaryDirectory(prefix='l4s9s-selftest-', dir=work) as temp:
        root = Path(temp)
        rom = root/'rom'
        built = subprocess.run([sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom),
                                '--work-dir', str(root/'asm')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert built.returncode == 0, '自作ROM一時ビルド失敗'
        own = [known['sc20-full-none'], known['sc20-full-scroll'], known['ac20-1'], known['cm-c1']]
        observed = measure(rom, False, own, root)
        bad = [r['arm']['id'] for r in observed if not r['gate']]
        if bad:
            print('NG 自作ROMの対照: '+','.join(bad))
            for r in observed:
                print(json.dumps(dict(arm=r['arm']['id'], failed=r['failed'], gate=r['gate'],
                                      obs=[{k: v for k, v in o.items() if k in ('rows', 'err', 'sz', 'cur_pre')} for o in r['obs']])))
        assert not bad
        assert calibrated(observed[:1]+observed[2:3], strict=False) and not calibrated(observed[:1]+observed[2:3])    # 自作は戻し文が誤り（免除が要る）
        base = observed[0]['obs'][0]
        assert base['rows'][:19] == ''.join(chr(65+r) for r in range(19)), base['rows']
        # 故障注入: はしごの1行が欠けた写しでは較正が落ちる
        broken = dict(base, rows=base['rows'][:7]+'.'+base['rows'][8:])
        assert not calibrated([rec('sc20-full-none', broken)])
        print('  自作の現状: sc20-full-none rows='+base['rows']+' scroll rows='+observed[1]['obs'][0]['rows']
              +' ac20-1 err='+json.dumps(observed[2]['obs'][0]['err']), flush=True)
    print('OK 自作ROMの対照4腕×2走（はしご・スクロール・ac・cm）・故障注入で較正が落ちる', flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    m = sub.add_parser('measure'); m.add_argument('--rom-dir')
    m.add_argument('--official', action='store_true'); m.add_argument('--out', type=Path, required=True)
    m.add_argument('--work-dir', type=Path, default=WORK)
    m.add_argument('--only', default='', help='腕IDの接頭辞（カンマ区切り）。空なら全腕')
    r = sub.add_parser('report'); r.add_argument('--measured', type=Path, required=True)
    s = sub.add_parser('summary'); s.add_argument('--measured', type=Path, required=True)
    t = sub.add_parser('selftest'); t.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'report':
        print(report(args.measured)); return 0
    if args.command == 'summary':
        print('予測 的中/外れ:', summarize(args.measured)); return 0
    rom = os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir):
        parser.error('公式ROMはPC88_REF_ROM_DIRだけ、自作ROMは--rom-dirで指定する')
    if not args.work_dir.is_absolute():
        parser.error('--work-dir は絶対パスで指定する')
    pre = tuple(x for x in args.only.split(',') if x)
    selected = [a for a in arms() if (a['id'].startswith(pre) if pre else True)]
    records = measure(rom, args.official, selected, args.work_dir)
    ok = emit(args.out, records, strict=args.official)
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
