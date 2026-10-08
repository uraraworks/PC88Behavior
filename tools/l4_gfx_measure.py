#!/usr/bin/env python3
"""l4-s9t: グラフィックの土台（グラフィックVRAMの構造と切替、座標系、PSET・PRESET・POINT、グラフィックの色、CLS の消去範囲）を測る器具。

画面本文は扱わない。採るのは次の数値・記号だけ。ここで「描いた」と言うのは、こちらの打ち込んだプログラムが描かせた点だけで、
公式が自分で描く図形は記録しない（lit は 100 バイト以下のときだけ記録し、それを超えたら統計だけ）。
 (1) グラフィックVRAM 3 プレーン（青・赤・緑、0x4000 バイトずつ）の統計と、光っているバイトの (オフセット, 3プレーンの値)。
     ハーネス --gvram-dump（コアの retro_q88h_gvram）から。生バイトは採取後に消し、コミットしない。
 (2) こちらのプログラムが印字した結果行 `s9t<番号>:値,値,..;`（誤り番号・最終参照点・POINT の値）。テキストVRAM写しから探す。
 (3) 制御ポート（0x30・0x31・0x32・0x34・0x35・0x53〜0x5F）の値の初出順と最後の値、VRAM 切替系 OUT（0x34・0x35・0x5C〜0x5F）の連長圧縮列。
 (4) --screenshot の PPM から、こちらが描いた点の位置の画素と、その隣の参照画素（pix を持つ腕だけ）。
事前登録は docs/notes/l4-s9t-graphics-base-preregistration.md。
"""
import argparse
import collections
import csv
import json
import math
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

WORK = kw.REPO.parent / 'tmp/s9t-work'
IO_LINE = wv.IO_LINE
PORTS = (0x30, 0x31, 0x32, 0x34, 0x35, 0x53) + tuple(range(0x54, 0x60))
EVP = (0x34, 0x35, 0x5C, 0x5D, 0x5E, 0x5F)
LIT_MAX = 100
EV_MAX = 60
EVX_PORTS = (0x31, 0x34, 0x35, 0x53, 0x5C, 0x5D, 0x5E, 0x5F)      # 追補1: VRAM 切替・表示系 OUT の全列（連長圧縮）
EVX_MAX = 3000
SENT = 's9tz'
GV_LEN = 0xC000
PLANE = 0x4000
VISIBLE = (400, 150)          # 画面に出る点の位置（結果行や Ok の文字が届かない所）

# ---------------------------------------------------------------- 項目（プログラムの 1 要素）。予測は Model が付ける


def num(v):
    return v if isinstance(v, str) else (str(v) if isinstance(v, int) else repr(v))


def pset(x, y, c=None, step=False, pre=False, probe=True):
    return dict(op='pset', x=x, y=y, c=c, step=step, pre=pre, probe=probe)


def rawdraw(stmt, **kw_):
    return dict(op='raw', stmt=stmt, **kw_)


def point_stmt(x, y, step=False):
    return dict(op='point_stmt', x=x, y=y, step=step)


def pfn(x, y):
    return dict(op='pfn', x=x, y=y)


def plp(n):
    return dict(op='plp', n=n)


def color(f=None, b=None):
    return dict(op='color', f=f, b=b)


def cls(n=None, probe=False):
    return dict(op='cls', n=n, probe=probe)


def screen(args, probe=False, restore=False):
    return dict(op='screen', args=args, probe=probe, restore=restore)


def text(stmt):
    return dict(op='text', stmt=stmt)


def arm(aid, items, pix=None, rec_lit=True, group=None, note='', evx=False):
    a = dict(id=aid, items=items, pix=pix or [], rec_lit=rec_lit, group=group or aid.split('-')[0], note=note)
    if evx:
        a['evx'] = True
    return a


PRE = [screen('0,0'), cls(3)]


def arms():
    out = []
    # ---- 土台と進入口（base・acc）
    out.append(arm('base-boot', [], rec_lit=False, note='起動直後（text の cls だけ）。lit は記録しない'))
    out.append(arm('base-cls3', [cls(3)]))
    out.append(arm('base-s00', [screen('0,0'), cls(3)]))
    out.append(arm('acc-1', PRE + [pset(1, 0, 7, probe=False)]))
    out.append(arm('map-nos', [cls(3), pset(100, 100, 7, probe=False), pset(1, 0, 5, probe=False)]))
    # ---- VRAM の構造（map）
    pts = [(0, 0), (1, 0), (7, 0), (8, 0), (15, 0), (16, 0), (0, 1), (0, 2), (9, 1), (100, 100), (319, 51), (320, 50),
           (638, 198), (639, 199), (0, 199), (639, 0), VISIBLE]
    out.append(arm('map-a', PRE + [pset(x, y, 7, probe=False) for x, y in pts], pix=[VISIBLE]))
    out.append(arm('map-col', PRE + [pset(40+16*c, 60, c, probe=False) for c in range(8)]))
    out.append(arm('map-over', PRE + [pset(10, 10, 7, probe=False), pset(10, 10, 2, probe=False), pset(20, 10, 7, probe=False),
                                      pset(20, 10, 0, probe=False), pset(30, 10, 1, probe=False), pset(30, 10, 6, probe=False),
                                      pset(40, 10, 5, probe=False), pset(40, 10, 5, probe=False)]))
    # ---- 座標系（co）
    cyc = lambda i: (i % 7)+1
    edge = [(0, 0), (639, 0), (0, 199), (639, 199), (320, 100), (1, 1)]
    out.append(arm('co-edge', PRE + [pset(x, y, cyc(i)) for i, (x, y) in enumerate(edge)]))
    o1 = [(640, 10), (641, 11), (10, 200), (11, 201), (-1, 12), (12, -1), (640, 200), (-1, -1), (700, 50), (50, 300), (1000, 60),
          (-100, 70), (-640, 80), (80, -200), (1279, 90), (1280, 91)]
    out.append(arm('co-out1', PRE + [pset(x, y, cyc(i)) for i, (x, y) in enumerate(o1)]))
    o2 = [(32767, 5), (32768, 6), (-32768, 7), (-32769, 8), (65535, 9), (65536, 10), (70000, 11), ('1e10', 12), (5, 32767), (5, 32768),
          ('-1e5', 5), (50, 50)]
    out.append(arm('co-out2', PRE + [pset(x, y, cyc(i)) for i, (x, y) in enumerate(o2)]))
    fr = [(10.4, 20.6), (10.5, 20.5), (11.5, 21.5), (12.49, 22.51), (13.6, 23.4), (-0.4, 24), (24, -0.4), (-0.6, 25), (639.4, 26),
          (639.6, 27), (28, 199.4), (29, 199.6)]
    out.append(arm('co-frac', PRE + [pset(x, y, cyc(i)) for i, (x, y) in enumerate(fr)]))
    out.append(arm('co-step', PRE + [plp(0), plp(1), pset(5, 6, 1, step=True), pset(10, 10, 2, step=True), pset(-5, -6, 3, step=True),
                                     point_stmt(300, 100), pset(1, 1, 4, step=True), point_stmt(50, 0, step=True), pset(1, 1, 5, step=True),
                                     pset(639, 199, 6), pset(1, 0, 7, step=True), pset(-1000, -1000, 3, step=True), pset(2, 3, 2, step=True),
                                     plp(2), plp(3)]))
    out.append(arm('co-lpscr', PRE + [pset(100, 100, 7, probe=False), screen('0,0', probe=True)]))
    # ---- PSET の引数（ps）
    cols = [-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 15, 16, 255, 256, 1000]
    out.append(arm('ps-col', PRE + [pset(10+10*i, 30, c) for i, c in enumerate(cols)]))
    cf = [0.4, 0.5, 0.6, 1.5, 2.5, '"a"', '1e10', -0.5]
    out.append(arm('ps-colf', PRE + [pset(10+10*i, 40, c) for i, c in enumerate(cf)]))
    syn = ['pset(10,40)', 'pset(11,40),', 'pset 12,40', 'pset(13)', 'pset(14,40),1,2', 'pset (15,40),3', 'pset(16,40) 3',
           'pset step(17,40),4', 'pset(18,40),,', 'pset(19,40);3', 'pset(20.5,40)', 'pset(,41)', 'pset(21,)', 'pset()', 'pset']
    out.append(arm('ps-syn', PRE + [rawdraw(s) for s in syn]))
    out.append(arm('ps-def', PRE + [pset(10, 10, probe=False), color(f=3), pset(20, 10, probe=False), text('color 5'),
                                    pset(30, 10, probe=False), color(f=0), pset(40, 10, probe=False), color(f=7),
                                    pset(50, 10, probe=False), color(b=2), pset(60, 10, probe=False)]))
    out.append(arm('ps-fg', PRE + [x for f in range(8) for x in (color(f=f), pset(10+10*f, 20, probe=False))]))
    # ---- PRESET（pr）
    out.append(arm('pr-def', PRE + [pset(10, 10, 7, probe=False), pset(20, 10, 7, probe=False), pset(30, 10, 7, probe=False),
                                    pset(10, 10, pre=True, probe=False), pset(20, 10, 3, pre=True, probe=False),
                                    pset(30, 10, 0, pre=True, probe=False), pset(40, 10, pre=True, probe=False),
                                    pset(5, 5, 5, step=True, pre=True, probe=False), pset(700, 10, pre=True)]))
    out.append(arm('pr-bg3', [screen('0,0'), color(b=3), cls(3), pset(10, 10, 7, probe=False), pset(10, 10, pre=True, probe=False),
                              pset(20, 10, pre=True, probe=False), pset(30, 10, 5, pre=True, probe=False),
                              pset(40, 10, 0, pre=True, probe=False)]))
    # ---- POINT 関数（pt）
    drawn = [pset(10+10*c, 10, c, probe=False) for c in range(1, 8)]
    reads = [pfn(10+10*c, 10) for c in range(1, 8)] + [pfn(5, 5), pfn(639, 199), pfn(0, 0), pfn(-1, 10), pfn(640, 10), pfn(10, 200),
                                                      pfn(10, -1), pfn(1000, 1000), pfn(15.4, 10.4)]
    out.append(arm('pt-fn', PRE + drawn + reads))
    out.append(arm('pt-lp', PRE + [pset(33, 44, 7, probe=False)] + [plp(n) for n in (0, 1, 2, 3, 4, -1, 0.5, 5)]))
    out.append(arm('pt-bg5', [screen('0,0'), color(b=5), cls(3), pfn(100, 100), pset(100, 100, 2, probe=False), pfn(100, 100),
                              pfn(101, 100), pset(102, 100, 0, probe=False), pfn(102, 100), pfn(-1, -1)]))
    # ---- 背景色と cls（bg）
    for b in range(8):
        out.append(arm(f'bg-b{b}', [screen('0,0'), color(b=b), cls(3)], group='bg'))
    out.append(arm('bg-c2', [screen('0,0'), cls(3), color(b=5), cls(2)], group='bg'))
    out.append(arm('bg-c1', [screen('0,0'), cls(3), color(b=5), cls(1)], group='bg'))
    out.append(arm('bg-nocls', [screen('0,0'), cls(3), color(b=5)], group='bg'))
    out.append(arm('bg-f', [screen('0,0'), color(b=0, f=3), cls(3), pfn(100, 100)], group='bg'))
    # ---- 白黒モード（mono）
    mono = lambda sargs: [screen(sargs), cls(3), pset(100, 100, 1), pset(110, 100, 7), pset(120, 100, 0), pset(120, 100, 6),
                          pset(130, 100, 5), pset(130, 100, 0), pfn(100, 100), pfn(110, 100), pfn(120, 100), pfn(130, 100), pfn(140, 100)]
    out.append(arm('mono-a0', mono('1,0,0,7')))
    out.append(arm('mono-a1', mono('1,0,1,7')))
    out.append(arm('mono-a2', mono('1,0,2,7')))
    out.append(arm('mono-def', mono('1')))
    out.append(arm('mono-back', [screen('1'), cls(3), screen('0,0'), cls(3), pset(100, 100, 5), pset(110, 100, 3), pfn(100, 100)]))
    # ---- cls の範囲（cls）
    for k, n in (('none', None), ('0', 0), ('1', 1), ('2', 2), ('3', 3), ('4', 4), ('m1', -1), ('f', 1.5), ('s', '"a"')):
        out.append(arm(f'cls-{k}', PRE + [pset(100, 100, 7, probe=False), text('locate 10,12:print "qqq";'), cls(n, probe=True)]))
    out.append(arm('cls-bg5', [screen('0,0'), cls(3), color(b=5), pset(100, 100, 7, probe=False), text('locate 10,12:print "qqq";'), cls(2, probe=True)]))
    # ---- 表示の切替（sw）
    for sw in range(4):
        out.append(arm(f'sw-{sw}', PRE + [pset(*VISIBLE, 7, probe=False), screen(f'0,{sw}')], pix=[VISIBLE]))
    # ---- screen 文の引数（scr）
    se = ['5', '-1', '0,4', '0,-1', '0,0,3', '0,0,-1', '0,0,0,8', '0,0,0,-1', ',1', ',,1', '1,0,2,5', '0.5', '1.5', '"a"', '0,0,0,0,0',
          '', '0,0', '1,0', '0,1']
    for k in range(0, len(se), 10):
        out.append(arm(f'scr-e{k//10}', PRE + [x for s in se[k:k+10] for x in (point_stmt(77, 66), screen(s, probe=True, restore=True))]))
    for m in ('2', '3', '4'):
        out.append(arm(f'scr-m{m}', PRE + [pset(100, 100, 7, probe=False), point_stmt(77, 66), screen(m, probe=True)]))
    return out + add1_arms()


def add1_arms():
    """追補1: 初回の公式観測で出た疑問（書き込み経路・screen 文ごとのポート）を詰める腕。docs/notes/l4-s9t-addendum1-access-and-screen-ports.md"""
    out = [arm('acc2-0', PRE, evx=True), arm('acc2-1', PRE + [pset(1, 0, 7, probe=False)], evx=True),
           arm('acc2-2', PRE + [pset(1, 0, 3, probe=False)], evx=True),
           arm('acc2-3', PRE + [pset(1, 0, 7, probe=False), pset(9, 1, 2, probe=False)], evx=True),
           arm('acc2-p', PRE + [pset(1, 0, pre=True, probe=False)], evx=True),
           arm('acc2-r', PRE + [pset(1, 0, 7, probe=False), pfn(1, 0)], evx=True),
           arm('acc2-m0', [screen('1'), cls(3)], evx=True),
           arm('acc2-m1', [screen('1'), cls(3), pset(1, 0, 1, probe=False)], evx=True),
           arm('acc2-m2', [screen('1,0,1,7'), cls(3), pset(1, 0, 1, probe=False)], evx=True),
           arm('acc2-mr', [screen('1'), cls(3), pset(1, 0, 1, probe=False), pfn(1, 0)], evx=True)]
    for x in ('0,0', '0,1', '0,2', '0,3', '1', '1,0,0,7', '1,0,0,1', '1,0,0,2', '1,0,0,4', '1,0,0,0', '1,0,1,3', '1,0,2,5', '2'):
        out.append(arm('scp-' + x.replace(',', '_'), PRE + [screen(x)], evx=True))
    return out


# ---------------------------------------------------------------- 予測のモデル（事前登録のとおり。強 s・中 m・弱 w）
def rnd(v):
    return math.floor(v + 0.5)


class Model:
    def __init__(self):
        self.lp = (0, 0)
        self.fg, self.bg = 7, 0
        self.mono, self.apage = False, 0
        self.pix = {}
        self.base = 0              # 何も描いていない画素の色

    def put(self, x, y, c):
        if self.mono:
            c = (1 << self.apage) if c else 0
        if c == self.base:
            self.pix.pop((x, y), None)
        else:
            self.pix[(x, y)] = c

    def get(self, x, y):
        return self.pix.get((x, y), self.base)

    def clear(self, c):
        self.pix = {}
        self.base = c

    def draw(self, x, y, c, step, pre):
        """pset/preset の予測。返り値 dict(e, lp, px)。値は (予測, 強さ)。None は予測なし。"""
        if isinstance(x, str) or isinstance(y, str):
            if x in ('1e10', '-1e5') or y in ('1e10', '-1e5'):
                return dict(e=(6, 'w'), lp=None, px=(None, 'w'))
        if isinstance(x, str) or isinstance(y, str):
            return dict(e=None, lp=None, px=(None, 'w'))
        frac = (x != int(x)) or (y != int(y))
        xr, yr = rnd(x), rnd(y)
        if step:
            xr, yr = self.lp[0]+xr, self.lp[1]+yr
        if abs(xr) > 32767 or abs(yr) > 32767:
            return dict(e=(6, 'w'), lp=(self.lp, 'w'), px=(None, 'w'))
        st = 'w' if frac else 's'
        lp = (xr, yr)
        inr = 0 <= xr < 640 and 0 <= yr < 200
        if c is None:
            cc, cst = (self.bg if pre else self.fg), 'm'
        elif c == '"a"':
            self.lp = lp
            return dict(e=(13, 'm'), lp=(lp, 'w'), px=([], 'm'))
        elif isinstance(c, str):
            self.lp = lp
            return dict(e=None, lp=(lp, 'w'), px=(None, 'w'))
        elif not float(c).is_integer():
            self.lp = lp
            return dict(e=None, lp=(lp, 'w'), px=(None, 'w'))
        else:
            cc, cst = int(c), 's'
            if not 0 <= cc <= 7:
                self.lp = lp
                return dict(e=(5, 'w'), lp=(lp, 'w'), px=([], 'w'))
        self.lp = lp
        if not inr:
            return dict(e=(0, 'm'), lp=(lp, 'w' if frac or not (0 <= x < 640) else 'w'), px=([], 'm'))
        self.put(xr, yr, cc)
        if self.mono:
            return dict(e=(0, 'm'), lp=(lp, st), px=([(xr, yr, (1 << self.apage) if cc else 0)], 'w'))
        return dict(e=(0, 's'), lp=(lp, st), px=([(xr, yr, cc)], st if cst == 's' else 'm'))

    def point_stmt(self, x, y, step):
        xr, yr = rnd(x), rnd(y)
        if step:
            xr, yr = self.lp[0]+xr, self.lp[1]+yr
        self.lp = (xr, yr)

    def pfn(self, x, y):
        xr, yr = rnd(x), rnd(y)
        frac = (x != int(x)) or (y != int(y))
        if not (0 <= xr < 640 and 0 <= yr < 200):
            return (-1, 'w' if frac else 'm')
        v = self.get(xr, yr)
        if self.mono:
            return (1 if v else 0, 'm')
        return (v, 'w' if frac else 's')

    def plp(self, n):
        if isinstance(n, float):
            return (None, 'w')
        if not 0 <= n <= 3:
            return (('err', 5), 'w')
        return ((self.lp[0] if n in (0, 2) else self.lp[1]), 's' if n in (0, 1) else 'm')

    def do_cls(self, n):
        if n is None or n == 1:
            return dict(e=(0, 's'), lp=(self.lp, 'w'))
        if isinstance(n, str):
            return dict(e=(13, 'm'), lp=None)
        if isinstance(n, float):
            return dict(e=None, lp=None)
        if n in (2, 3):
            self.clear(self.bg)
            self.lp = (0, 0)
            return dict(e=(0, 's'), lp=((0, 0), 'm'))
        return dict(e=(5, 'w'), lp=(self.lp, 'w'))

    def do_screen(self, args):
        parts = args.split(',') if args != '' else []
        mode = parts[0].strip() if parts else ''
        if '"' in args:
            return dict(e=(13, 'm'), lp=None)
        if len(parts) > 4:
            return dict(e=(2, 'm'), lp=None)
        try:
            vals = [float(p) if p.strip() else None for p in parts]
        except ValueError:
            return dict(e=None, lp=None)
        if any(v is not None and not float(v).is_integer() for v in vals):
            return dict(e=None, lp=None)
        lim = [(0, 2), (0, 3), (0, 2), (0, 7)]
        if args == '' or args == '0,0' or args == '1,0' or args == '0,1' or args == '1,0,2,5':
            ok = True
        else:
            ok = all(v is None or lim[i][0] <= v <= lim[i][1] for i, v in enumerate(vals))
        if not ok:
            return dict(e=(5, 'w'), lp=None)
        m0 = vals[0] if vals and vals[0] is not None else None
        if m0 == 1:
            self.mono, self.apage = True, (int(vals[2]) if len(vals) > 2 and vals[2] is not None else 0)
        elif m0 == 0:
            self.mono = False
        self.lp = (0, 0)
        return dict(e=(0, 's' if args in ('0,0', '1,0', '0,1') else 'w'), lp=((0, 0), 'm'))


def steps(a):
    """腕の項目を 1 つずつ、(項目, 描いた行の文, 印字の番号 or None, 予測 dict) にする。"""
    m = Model()
    out, idx = [], 0
    for it in a['items']:
        op = it['op']
        pred, stmt, pr = {}, None, None
        if op == 'pset':
            x, y, c = it['x'], it['y'], it['c']
            kwd = 'preset' if it['pre'] else 'pset'
            coord = f"{kwd} step({num(x)},{num(y)})" if it['step'] else f"{kwd}({num(x)},{num(y)})"
            stmt = coord + (f',{num(c)}' if c is not None else '')
            pred = m.draw(x, y, c, it['step'], it['pre'])
            pr = 'D' if it['probe'] else None
        elif op == 'raw':
            stmt = it['stmt']
            pred = rawdraw_pred(m, stmt)
            pr = 'D'
        elif op == 'point_stmt':
            stmt = f"point step({num(it['x'])},{num(it['y'])})" if it['step'] else f"point({num(it['x'])},{num(it['y'])})"
            m.point_stmt(it['x'], it['y'], it['step'])
        elif op == 'pfn':
            stmt = f"point({num(it['x'])},{num(it['y'])})"
            pred = dict(v=m.pfn(it['x'], it['y']))
            pr = 'V'
        elif op == 'plp':
            stmt = f"point({num(it['n'])})"
            pred = dict(v=m.plp(it['n']))
            pr = 'V'
        elif op == 'color':
            if it['f'] is not None:
                stmt = f"color ,,,{it['f']}"
                m.fg = it['f']
            elif it['b'] is not None:
                stmt = f"color ,{it['b']}"
                m.bg = it['b']
            else:
                stmt = 'color ,,,7'
                m.fg = 7
        elif op == 'cls':
            n = it['n']
            stmt = 'cls' + ('' if n is None else f' {num(n)}')
            pred = m.do_cls(n)
            pr = 'D' if it['probe'] else None
        elif op == 'screen':
            stmt = 'screen' + (f" {it['args']}" if it['args'] else '')
            pred = m.do_screen(it['args'])
            pr = 'D' if it['probe'] else None
        else:
            stmt = it['stmt']
        i = None
        if pr:
            i = idx
            idx += 1
        out.append((it, stmt, pr, i, pred))
        if op == 'screen' and it.get('restore'):
            m.do_screen('0,0')
            out.append((dict(op='screen', args='0,0', probe=False, restore=False), 'screen 0,0', None, None, {}))
    return out, m


def rawdraw_pred(m, stmt):
    """ps-syn の予測（事前登録の表）。構文が通るものは pset の規則、通らないものは ERR 2。"""
    table = {
        'pset(10,40)': ('ok', 10, 40, None), 'pset(11,40),': ('err2',), 'pset 12,40': ('err2',), 'pset(13)': ('err2',),
        'pset(14,40),1,2': ('err2',), 'pset (15,40),3': ('ok', 15, 40, 3), 'pset(16,40) 3': ('err2',),
        'pset step(17,40),4': ('ok', None, None, 4), 'pset(18,40),,': ('err2',), 'pset(19,40);3': ('err2',),
        'pset(20.5,40)': ('ok', 21, 40, None), 'pset(,41)': ('err2',), 'pset(21,)': ('err2',), 'pset()': ('err2',), 'pset': ('err2',)}
    t = table[stmt]
    if t[0] == 'err2':
        return dict(e=(2, 'm' if stmt in ('pset 12,40', 'pset(13)', 'pset(14,40),1,2', 'pset(16,40) 3', 'pset', 'pset()') else 'w'),
                    lp=None, px=([], 'm'))
    if t[1] is None:                                # step: 直前の LP から
        x, y = m.lp[0]+17, m.lp[1]+40
    else:
        x, y = t[1], t[2]
    c = t[3]
    m.lp = (x, y)
    cc = m.fg if c is None else c
    if 0 <= x < 640 and 0 <= y < 200:
        m.put(x, y, cc)
        return dict(e=(0, 's' if stmt != 'pset(20.5,40)' else 'w'), lp=((x, y), 'w'), px=([(x, y, cc)], 'm'))
    return dict(e=(0, 'm'), lp=((x, y), 'w'), px=([], 'm'))


# ---------------------------------------------------------------- 打ち込むプログラム
def program_lines(a):
    st, _ = steps(a)
    lines = {5: 'on error goto 900', 6: 'cls'}
    n = 10
    for it, stmt, pr, i, pred in st:
        if pr == 'D':
            lines[n] = f'e=0:{stmt}:g=e'; n += 10
            lines[n] = 'e=0:x=point(0):y=point(1)'; n += 10
            lines[n] = f'print "s9t{i}:";g;",";x;",";y;";"'; n += 10
        elif pr == 'V':
            lines[n] = f'e=0:v=-77:v={stmt}'; n += 10
            lines[n] = f'print "s9t{i}:";e;",";v;";"'; n += 10
        else:
            lines[n] = stmt; n += 10
    lines[n] = f'print "{SENT}";'; n += 10
    lines[n] = f'goto {n}'
    lines[900] = 'e=err:resume next'
    assert n < 900, a['id']
    assert all(len(f'{k} {s}') < 80 for k, s in lines.items()), [f'{k} {s}' for k, s in lines.items() if len(f'{k} {s}') >= 80]
    assert all(s.isascii() and s == s.lower() and '@' not in s for s in lines.values()), lines
    return lines


def plan(a):
    return ['new'] + [f'{n} {s}' for n, s in sorted(program_lines(a).items())] + ['cls', ('window',), 'run', ('capture', 'all')]


# ---------------------------------------------------------------- 写しの解析
def gv_analyze(data, rec_lit=True):
    if len(data) != GV_LEN:
        raise ValueError('グラフィックVRAM写しの長さが不正')
    planes = [data[p*PLANE:(p+1)*PLANE] for p in range(3)]
    stat = []
    for pl in planes:
        z, f = pl.count(0), pl.count(0xFF)
        nzs = [i for i, b in enumerate(pl) if b]
        stat.append([z, f, PLANE-z-f, nzs[0] if nzs else -1, nzs[-1] if nzs else -1])
    nz = [o for o in range(PLANE) if any(planes[p][o] for p in range(3))]
    gv = dict(stat=stat, nz=len(nz), tail=sum(1 for o in nz if o >= 16000))
    if rec_lit and len(nz) <= LIT_MAX:
        gv['lit'] = [[o]+[planes[p][o] for p in range(3)] for o in nz]
    else:
        gv['lit'] = None
        gv['vals'] = [sorted(set(pl))[:4] for pl in planes]
    return gv


def decode(lit):
    """仮説 H（1 ラインは 80 バイト・左端の画素が bit7・プレーン0=青 1=赤 2=緑）で光点 [(x,y,色)] にする。"""
    out = {}
    for o, b0, b1, b2 in lit:
        y, col = divmod(o, 80)
        for k in range(8):
            c = ((b0 >> k) & 1) | (((b1 >> k) & 1) << 1) | (((b2 >> k) & 1) << 2)
            if c:
                out[(col*8+(7-k), y)] = c
    return out


def parse_results(vram):
    if len(vram) != 3000:
        raise ValueError('画面写しの長さが不正')
    res, sent = {}, 0
    for r in range(25):
        line = bytes(vram[r*120:r*120+80])
        sent += line.count(SENT.encode())
        for m in re.finditer(rb's9t(\d+):([ \x20-\x7e]*?);', line):
            vals = []
            for tok in m[2].decode().replace(' ', '').split(','):
                try:
                    vals.append(int(tok))
                except ValueError:
                    try:
                        vals.append(float(tok))
                    except ValueError:
                        vals.append(tok)
            res[int(m[1])] = vals
    return res, sent


def marker_count(vram, tok=b'qqq'):
    return sum(bytes(vram[r*120:r*120+80]).count(tok) for r in range(25))


def events(text_, f0, evx=False):
    """VRAM 切替系 OUT の連長圧縮列 [[port, 値, 回数], ...] と総数、制御ポートの初出順と最後の値。"""
    seq, n = [], 0
    seen = {p: [] for p in PORTS}
    last = {}
    for line in text_.splitlines():
        m = IO_LINE.match(line)
        if not m or m[4] != 'main' or m[5] != 'OUT' or int(m[3]) < f0:
            continue
        port, val = int(m[6], 16), int(m[7], 16)
        if port in seen:
            if val not in seen[port]:
                seen[port].append(val)
            last[port] = val
        if port in EVP:
            n += 1
            if seq and seq[-1][0] == port and seq[-1][1] == val:
                seq[-1][2] += 1
            else:
                seq.append([port, val, 1])
    out = dict(ev=seq[:EV_MAX], ev_n=n, ev_runs=len(seq), ports={hex(p): v for p, v in seen.items() if v},
               last={hex(p): v for p, v in sorted(last.items())})
    if evx:
        x = []
        for line in text_.splitlines():
            m = IO_LINE.match(line)
            if not m or m[4] != 'main' or m[5] != 'OUT' or int(m[3]) < f0:
                continue
            port, val = int(m[6], 16), int(m[7], 16)
            if port in EVX_PORTS:
                if x and x[-1][0] == port and x[-1][1] == val:
                    x[-1][2] += 1
                else:
                    x.append([port, val, 1])
        out['evx'] = x[:EVX_MAX]
        out['evx_n'] = len(x)
    return out


def pix_stat(img, pts):
    w, h, data = img
    out = []
    for x, y in pts:
        rows = [data[((2*y+k)*w+x)*3:((2*y+k)*w+x)*3+3].hex() for k in (0, 1)]
        refs = [data[((2*y+k)*w+x+6)*3:((2*y+k)*w+x+6)*3+3].hex() for k in (0, 1)]
        out.append(dict(at=[x, y], dot=rows, ref=refs))
    return out


def analyze(a, gv, vram, iolog_text, window, img=None):
    obs = dict(arm=a['id'])
    obs['gv'] = gv_analyze(gv, a['rec_lit'])
    res, sent = parse_results(vram)
    obs['res'] = {str(k): v for k, v in sorted(res.items())}
    obs['sent'] = sent
    obs['qqq'] = marker_count(vram)
    obs.update(events(iolog_text, window, a.get('evx', False)))
    if a['pix'] and img is not None:
        obs['pix'] = pix_stat(img, a['pix'])
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
    ppm, iolog, vdump, gdump = work/'shot.ppm', work/'port.txt', work/'vram.bin', work/'gvram.bin'
    args += ['--vram-dump', str(vdump), '--vram-dump-at', str(cap), '--gvram-dump', str(gdump), '--gvram-dump-at', str(cap),
             '--io-log', str(iolog), '--io-log-from-frame', str(window), '--frames', str(cap+100)]
    if a['pix']:
        args += ['--screenshot', str(ppm)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
            raise RuntimeError('測定器の実行または打鍵に失敗')
        img = cp.read_ppm(ppm) if a['pix'] else None
        return analyze(a, gdump.read_bytes(), vdump.read_bytes(), iolog.read_text(encoding='utf-8', errors='replace'), window, img)
    finally:
        for p in (ppm, iolog, vdump, gdump):
            Path(p).unlink(missing_ok=True)
            Path(str(p)+'.info.txt').unlink(missing_ok=True)


def n_probes(a):
    return sum(1 for s in steps(a)[0] if s[2])


def valid(obs, a):
    if not isinstance(obs, dict) or obs.get('arm') != a['id'] or 'gv' not in obs:
        return False
    return obs['sent'] == 1 and len(obs['res']) == n_probes(a)


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
def ok(got, want):
    return 'agree' if got == want else 'differ'


def lit_of(obs):
    return decode(obs['gv']['lit']) if obs['gv']['lit'] is not None else None


def judge(obs, a, by=None):
    """予測のある項目ごとに 'agree:強さ' / 'differ:強さ'。予測なしは出さない。"""
    st, m = steps(a)
    res = {}
    gid = a['id']
    if gid.startswith(('acc2-', 'scp-')):
        return res                      # 追補1は初回を見たあとの記述的な腕。予測は付けない

    def put(name, got, want, strength):
        res[name] = ('agree:' if got == want else 'differ:') + strength

    r = obs['res']
    for it, stmt, pr, i, pred in st:
        if not pr:
            continue
        vals = r.get(str(i))
        if vals is None:
            continue
        if pr == 'D':
            for key, k in (('e', 0), ('lp', 1)):
                p = pred.get(key)
                if p is None or p[0] is None:
                    continue
                got = vals[0] if key == 'e' else tuple(vals[1:3])
                put(f'p{i}_{key}', got, p[0], p[1])
        else:
            p = pred.get('v')
            if p and p[0] is not None:
                got = vals[1] if vals[0] == 0 else ('err', vals[0])
                put(f'p{i}_v', got, p[0], p[1])
    # 光点全体（すべての描画の予測が付いている腕だけ）
    if gid.startswith(('bg-b', 'bg-c', 'bg-no')):
        return res | judge_bg(obs, a)
    lit = lit_of(obs)
    has_draw = any(it['op'] == 'pset' or it['op'] == 'raw' for it, *_ in st)
    if lit is not None and a['rec_lit'] and has_draw and all_known(st):
        # 予測の光点は、各項目の px を順に当てはめた最終状態（Model.pix）
        want = {k: v for k, v in m.pix.items() if v}
        put('lit', lit, want, lit_strength(st))
        put('tail', obs['gv']['tail'], 0, 's')
    if gid in ('base-cls3', 'base-s00') and lit is not None:
        put('lit', lit, {}, 'm')
    if gid.startswith('cls-'):
        res |= judge_cls(obs, a, m)
    if gid.startswith('sw-'):
        res |= judge_sw(obs, a)
    return res


def all_known(st):
    for it, stmt, pr, i, pred in st:
        if it['op'] == 'pset' and not it['probe']:
            if pred.get('px') is None or pred['px'][0] is None:
                return False
        if pr and it['op'] in ('pset', 'raw'):
            if pred.get('px') is None or pred['px'][0] is None:
                return False
        if it['op'] in ('cls', 'screen') and pred.get('e') is None:
            return False
    return True


def lit_strength(st):
    ranks = {'s': 3, 'm': 2, 'w': 1}
    low = 3
    for it, stmt, pr, i, pred in st:
        for key in ('px',):
            p = pred.get(key)
            if p and p[0] is not None:
                low = min(low, ranks[p[1]])
    return {3: 's', 2: 'm', 1: 'w'}[low]


def judge_bg(obs, a):
    """背景色で cls したあとの面。色 b のビットが立つプレーンは 16000 バイト以上が 0xFF、立たないプレーンは全 0。"""
    res = {}
    gid = a['id']
    exp = {'bg-c2': 5, 'bg-c1': 0, 'bg-nocls': 0}.get(gid)
    if gid.startswith('bg-b'):
        exp = int(gid[4:])
    stat = obs['gv']['stat']
    for p in range(3):
        z, f, o, first, last = stat[p]
        if (exp >> p) & 1:
            res[f'plane{p}'] = ('agree:' if f >= 16000 and o == 0 else 'differ:') + ('s' if gid.startswith('bg-b') else 'm')
        else:
            res[f'plane{p}'] = ('agree:' if f == 0 and o == 0 else 'differ:') + 's'
    return res


def judge_cls(obs, a, m):
    res = {}
    k = a['id'][4:]
    if k in ('0', '4', 'm1', 'f', 's', 'bg5') and k != 'bg5':
        n_dot = len(lit_of(obs) or {})
        res['dot_kept'] = ('agree:' if n_dot >= 1 else 'differ:') + 'w'
        return res
    gone_dot = {'none': False, '1': False, '2': True, '3': True, 'bg5': True}.get(k)
    gone_txt = {'none': True, '1': True, '2': False, '3': True, 'bg5': False}.get(k)
    if gone_dot is not None and k != 'bg5':
        lit = lit_of(obs)
        res['dot_gone'] = ('agree:' if (lit == {}) == gone_dot else 'differ:') + 's'
        res['text_gone'] = ('agree:' if (obs['qqq'] == 0) == gone_txt else 'differ:') + 's'
    if k == 'bg5':
        stat = obs['gv']['stat']
        res['filled'] = ('agree:' if stat[0][1] >= 16000 and stat[2][1] >= 16000 and stat[1][1] == 0 else 'differ:') + 'm'
        res['text_kept'] = ('agree:' if obs['qqq'] == 1 else 'differ:') + 's'
    return res


def judge_sw(obs, a):
    res = {}
    sw = int(a['id'][3:])
    p = obs.get('pix')
    if p:
        visible = p[0]['dot'] != p[0]['ref']
        res['visible'] = ('agree:' if visible == (sw in (0, 1)) else 'differ:') + 'm'
    lit = lit_of(obs)
    if lit is not None:
        res['vram_kept'] = ('agree:' if len(lit) == 1 else 'differ:') + 'm'
    bit3 = (obs['last'].get('0x31', 0) >> 3) & 1 if '0x31' in obs['last'] else None
    if bit3 is not None:
        res['p31_bit3'] = ('agree:' if bit3 == (1 if sw in (0, 1) else 0) else 'differ:') + 'w'
    return res


def group_judges(records):
    by = {r['arm']['id']: r['obs'][0] for r in records if r['gate'] and r['obs'][0]}
    out = {}

    def lastv(o, port):
        return o['last'].get(port)
    b00, b1 = by.get('base-s00'), by.get('mono-def')
    if b00:
        v = lastv(b00, '0x31')
        if v is not None:
            out['p31_color_graphic'] = ('agree:' if v & 0x19 == 0x19 else 'differ:') + 'm'
    if b1:
        v = lastv(b1, '0x31')
        if v is not None:
            out['p31_mono_graphic'] = ('agree:' if (v >> 4) & 1 == 0 and (v >> 3) & 1 == 1 else 'differ:') + 'm'
    a1, a0 = by.get('acc-1'), by.get('base-s00')
    if a1 and a0:
        out['acc_uses_5c_5e'] = ('agree:' if any(e[0] in (0x5C, 0x5D, 0x5E) for e in a1['ev']) else 'differ:') + 'm'
    for b in range(8):
        o = by.get(f'bg-b{b}')
        if o and '0x54' in o['ports']:
            pass
    return out


def calibrated(records):
    by = {r['arm']['id']: r for r in records}
    good = True
    for i in ('map-a',):
        if i in by:
            r = by[i]
            o = r['obs'][0] if r['obs'] else {}
            lit = lit_of(o) if o else None
            good = good and bool(r['gate'] and lit and len(lit) >= 1 and o['gv']['tail'] == 0)
            if o and o.get('pix'):
                good = good and o['pix'][0]['dot'] != o['pix'][0]['ref']
    if 'base-cls3' in by:
        r = by['base-cls3']
        good = good and bool(r['gate'])
    return good


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
    cal = calibrated(records) if strict else True
    rows = [(r['arm']['id'], i+1, json.dumps(plan(r['arm'])), json.dumps(r['obs'][i]),
             'pass' if cal and r['gate'] else 'gate_failed',
             json.dumps(judge(r['obs'][0], r['arm'])) if cal and r['gate'] else 'gate_failed',
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
        j = r['prediction_judgement']
        try:
            jj = json.loads(j)
            summ = f"agree={sum(1 for v in jj.values() if v.startswith('agree'))} differ={sum(1 for v in jj.values() if v.startswith('differ'))}"
            diff = [k for k, v in jj.items() if v.startswith('differ')]
        except Exception:
            summ, diff = j, []
        lines.append(f"## {r['arm']} gate={r['gate']} {summ} differ_items={diff}")
        if not o:
            continue
        g = o['gv']
        lit = decode(g['lit']) if g['lit'] is not None else None
        lines.append(f"  gv nz={g['nz']} tail={g['tail']} stat={g['stat']} lit={sorted(lit.items()) if lit is not None else g.get('vals')}")
        lines.append(f"  res={o['res']} qqq={o['qqq']} sent={o['sent']}")
        lines.append(f"  last={o['last']} ports={json.dumps(o['ports'])} ev_n={o['ev_n']} ev={o['ev'][:12]}")
        if o.get('pix'):
            lines.append(f"  pix={o['pix']}")
    return '\n'.join(lines)


# ---------------------------------------------------------------- 説明（事前登録用）
def describe():
    out = []
    for a in arms():
        st, m = steps(a)
        prog = ' / '.join(s[1] for s in st if s[1])
        out.append(f"- `{a['id']}` ({n_probes(a)}印字): {prog}")
    return '\n'.join(out)


# ---------------------------------------------------------------- 自己検査
def synth_gv(points, mono_page=None, fill=None):
    """合成のグラフィックVRAM。points は {(x,y): 色}。"""
    d = bytearray(GV_LEN)
    for (x, y), c in points.items():
        o = y*80+x//8
        bit = 1 << (7-x % 8)
        for p in range(3):
            if (c >> p) & 1:
                d[p*PLANE+o] |= bit
    if fill is not None:
        for p in range(3):
            if (fill >> p) & 1:
                d[p*PLANE:p*PLANE+16000] = b'\xff'*16000
    return bytes(d)


def synth_text(lines):
    d = bytearray(b' '*3000)
    for r, s in enumerate(lines):
        d[r*120:r*120+len(s)] = s.encode()
    return bytes(d)


def log(events_):
    out = ['# seq clock frame cpu kind port value pc']
    for i, (fr, cpu, kind, port, val) in enumerate(events_):
        out.append(f'{i:6d} {i:7d} {fr:6d}  {cpu:<4s}  {kind:<4s}  {port:04X}   {val:02X}   0000')
    return '\n'.join(out)+'\n'


def selftest(work=None):
    if work is not None:
        work.mkdir(parents=True, exist_ok=True)
    known = {a['id']: a for a in arms()}
    assert len(known) == len(arms())
    for a in known.values():
        program_lines(a)
        plan(a)
    # 復号: 仮説 H の陽性・陰性（手計算）
    gv = synth_gv({(0, 0): 7, (9, 1): 2, (639, 199): 5})
    g = gv_analyze(gv)
    assert g['nz'] == 3 and g['tail'] == 0 and g['lit'] == [[0, 0x80, 0x80, 0x80], [1*80+1, 0, 0x40, 0], [199*80+79, 1, 0, 1]], g['lit']
    assert decode(g['lit']) == {(0, 0): 7, (9, 1): 2, (639, 199): 5}
    assert decode([[0, 0x80, 0, 0]]) == {(0, 0): 1} and decode([[0, 0x01, 0, 0]]) == {(7, 0): 1}          # MSB が左端
    assert decode([[80, 0, 0, 1]]) == {(7, 1): 4}                                                          # 緑は色 4・次のラインは +80
    assert gv_analyze(synth_gv({(0, 16000//80+1): 1}))['tail'] == 1                                         # 範囲外のバイトを数える
    gf = gv_analyze(synth_gv({}, fill=5))
    assert gf['lit'] is None and gf['stat'][0][1] == 16000 and gf['stat'][1][0] == PLANE and gf['stat'][2][1] == 16000 and gf['vals'] == [[0, 255], [0], [0, 255]]
    assert gv_analyze(synth_gv({(1, 1): 7}), rec_lit=False)['lit'] is None                                   # 起動直後の腕は lit を持たない
    try:
        gv_analyze(gv[:-1]); assert False
    except ValueError:
        pass
    print('OK グラフィックVRAMの統計・復号（仮説 H の陽性・陰性）・範囲外バイト・塗りつぶし・本文非記録', flush=True)
    # 結果行の解析と印字の本文非出力
    t = synth_text(['s9t0:0,100,200;', 's9t1: 5, 1 , -1;   SECRETLINE', 'xx s9t2:0,1.5,3;s9tz'])
    res, sent = parse_results(t)
    assert res == {0: [0, 100, 200], 1: [5, 1, -1], 2: [0, 1.5, 3]} and sent == 1, (res, sent)
    assert marker_count(synth_text(['a qqq b', 'qqq'])) == 2
    # ポート・連長圧縮
    ev = [(1, 'main', 'OUT', 0x5C, 0x00), (1, 'main', 'OUT', 0x5C, 0x00), (1, 'main', 'OUT', 0x5F, 0x00), (1, 'sub', 'OUT', 0x5C, 0x55),
          (2, 'main', 'OUT', 0x31, 0x19), (3, 'main', 'OUT', 0x31, 0x11), (0, 'main', 'OUT', 0x31, 0x77), (3, 'main', 'IN', 0x5C, 0x01)]
    e = events(log(ev), 1)
    assert e['ev'] == [[0x5C, 0, 2], [0x5F, 0, 1]] and e['ev_n'] == 3 and e['ports']['0x31'] == [0x19, 0x11] and e['last']['0x31'] == 0x11, e
    ex = events(log(ev + [(3, 'main', 'OUT', 0x34, 0x07), (3, 'main', 'OUT', 0x34, 0x07), (3, 'main', 'OUT', 0x35, 0x80), (3, 'main', 'OUT', 0x20, 0x41)]), 1, True)
    assert ex['evx'] == [[0x5C, 0, 2], [0x5F, 0, 1], [0x31, 0x19, 1], [0x31, 0x11, 1], [0x34, 7, 2], [0x35, 0x80, 1]] and ex['evx_n'] == 6, ex['evx']   # データポート 0x20 は採らない
    assert 'evx' not in events(log(ev), 1)
    assert all(a.get('evx') for a in known.values() if a['id'].startswith(('acc2-', 'scp-'))) and not any(a.get('evx') for a in known.values() if a['id'].startswith(('map-', 'co-')))
    print('OK 結果行の解析・ポートの初出順と連長圧縮（サブCPU・IN・窓前は除外）・追補1の全列（データポート非採取）', flush=True)
    # PPM の画素
    img = (640, 400, bytes(640*400*3))
    d = bytearray(img[2])
    for k in (0, 1):
        d[((2*150+k)*640+400)*3:((2*150+k)*640+400)*3+3] = b'\xff\xff\xff'
    assert pix_stat((640, 400, bytes(d)), [(400, 150)])[0] == dict(at=[400, 150], dot=['ffffff', 'ffffff'], ref=['000000', '000000'])
    assert pix_stat(img, [(400, 150)])[0]['dot'] == pix_stat(img, [(400, 150)])[0]['ref']
    print('OK PPM の点と参照画素（陽性・陰性）', flush=True)
    # モデル（手計算）。事前登録の規則
    m = Model()
    assert m.draw(639, 199, 7, False, False)['px'] == ([(639, 199, 7)], 's')
    assert m.draw(640, 10, 3, False, False)['px'] == ([], 'm') and m.lp == (640, 10)
    m = Model(); m.lp = (100, 100)
    assert m.draw(10, -5, 2, True, False)['px'] == ([(110, 95, 2)], 's') and m.lp == (110, 95)
    assert m.draw(5, 5, None, False, True)['px'] == ([(5, 5, 0)], 'm')              # preset の既定は背景色（0 は消す）
    assert m.draw(8, 5, 9, False, False)['e'] == (5, 'w') and m.draw(8, 5, 'x', False, False) is not None
    assert m.draw(40000, 5, 1, False, False)['e'] == (6, 'w')
    m = Model(); m.put(3, 3, 5)
    assert m.pfn(3, 3) == (5, 's') and m.pfn(4, 3) == (0, 's') and m.pfn(-1, 3) == (-1, 'm') and m.pfn(640, 0) == (-1, 'm')
    m.do_cls(2)
    assert m.pfn(3, 3) == (0, 's') and m.lp == (0, 0)
    m = Model(); m.bg = 5; m.do_cls(3)
    assert m.pfn(10, 10) == (5, 's') and m.draw(1, 1, None, False, True)['px'] == ([(1, 1, 5)], 'm') and m.pfn(1, 1) == (5, 's')
    assert program_lines(known['map-a'])[10].startswith('screen 0,0') and program_lines(known['co-out1'])[40] == 'e=0:x=point(0):y=point(1)'
    # 判定の陽性・陰性: 完全に予測どおりの観測と、1 点ずらした観測
    a = known['map-col']
    want = {k: v for k, v in steps(a)[1].pix.items() if v}
    assert want == {(40+16*c, 60): c for c in range(1, 8)}, want
    good = dict(arm='map-col', gv=gv_analyze(synth_gv(want)), res={}, sent=1, qqq=0, ev=[], ev_n=0, ev_runs=0, ports={}, last={})
    assert judge(good, a)['lit'].startswith('agree') and judge(good, a)['tail'].startswith('agree')
    bad_pts = dict(want); bad_pts[(40+16*3, 61)] = bad_pts.pop((40+16*3, 60))
    bad = dict(good, gv=gv_analyze(synth_gv(bad_pts)))
    assert judge(bad, a)['lit'].startswith('differ')
    bad2 = dict(good, gv=gv_analyze(synth_gv({k: (v if v != 5 else 3) for k, v in want.items()})))              # 色のプレーンの取り違え
    assert judge(bad2, a)['lit'].startswith('differ')
    # cls の判定
    ac = known['cls-2']
    o = dict(good, arm='cls-2', gv=gv_analyze(synth_gv({})), qqq=1)
    assert judge(o, ac)['dot_gone'] == 'agree:s' and judge(o, ac)['text_gone'] == 'agree:s'
    o = dict(o, gv=gv_analyze(synth_gv({(100, 100): 7})))
    assert judge(o, ac)['dot_gone'] == 'differ:s'
    assert judge(dict(o, qqq=0), ac)['text_gone'] == 'differ:s'
    # bg の判定
    ab = known['bg-b5']
    o = dict(good, arm='bg-b5', gv=gv_analyze(synth_gv({}, fill=5)))
    assert set(judge(o, ab).values()) == {'agree:s'}
    o2 = dict(o, gv=gv_analyze(synth_gv({}, fill=6)))
    assert any(v.startswith('differ') for v in judge(o2, ab).values())
    # 印字の判定
    ap = known['co-edge']
    res = {str(i): [0, x, y] for i, (x, y) in enumerate([(0, 0), (639, 0), (0, 199), (639, 199), (320, 100), (1, 1)])}
    pts_ = {(0, 0): 1, (639, 0): 2, (0, 199): 3, (639, 199): 4, (320, 100): 5, (1, 1): 6}
    o = dict(good, arm='co-edge', gv=gv_analyze(synth_gv(pts_)), res=res)
    jd = judge(o, ap)
    assert all(v.startswith('agree') for v in jd.values()), jd
    o['res']['3'] = [5, 639, 199]
    assert judge(o, ap)['p3_e'].startswith('differ')
    print('OK モデル（手計算）・判定の陽性・陰性（光点・色の取り違え・cls・bg・印字）', flush=True)
    # 較正の関門と emit
    def rec(a_id, o, gate=True):
        return dict(arm=known[a_id], obs=[o, o], failed=[False, False], gate=gate)
    pts_a = {(0, 0): 7}
    o_a = dict(good, arm='map-a', gv=gv_analyze(synth_gv(pts_a)), pix=[dict(at=[400, 150], dot=['ffffff', 'ffffff'], ref=['000000', '000000'])])
    o_c = dict(good, arm='base-cls3', gv=gv_analyze(synth_gv({})))
    assert calibrated([rec('map-a', o_a), rec('base-cls3', o_c)])
    assert not calibrated([rec('map-a', dict(o_a, gv=gv_analyze(synth_gv({}))))])                                 # 何も描かれていない
    assert not calibrated([rec('map-a', dict(o_a, pix=[dict(at=[400, 150], dot=['000000']*2, ref=['000000']*2)]))])        # 画面に出ていない
    assert not calibrated([rec('map-a', dict(o_a, gv=gv_analyze(synth_gv({(0, 201): 7}))))])                       # 範囲外バイトに光る
    assert not calibrated([rec('map-a', o_a, gate=False)])
    with tempfile.TemporaryDirectory(prefix='l4s9t-emit-', dir=work) as temp:
        out = Path(temp)/'m.tsv'
        o_ok = lambda a_id: dict(good, arm=a_id, gv=gv_analyze(synth_gv({})), res={}, sent=1)
        rs = [rec('map-a', o_a), rec('base-cls3', o_c), rec('base-boot', o_ok('base-boot'))]
        assert emit(out, rs) and 'gate_failed' not in out.read_text()
        bad_ = dict(o_c, ev_n=5)
        rs2 = [rec('map-a', o_a), dict(arm=known['base-cls3'], obs=[o_c, bad_], failed=[False, False], gate=True)]      # 2 走が一致しない
        assert not emit(out, rs2) and 'gate_failed' in out.read_text()
    print('OK 較正の関門（陰性4種）・記録の出力・2走不一致の関門落ち', flush=True)
    # 自作ROMの対照: 器具が走り、グラフィックVRAMの写しが採れること。故障注入で写しの変化が見える
    with tempfile.TemporaryDirectory(prefix='l4s9t-selftest-', dir=work) as temp:
        root = Path(temp)
        rom = root/'rom'
        built = subprocess.run([sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom), '--work-dir', str(root/'asm')],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert built.returncode == 0, '自作ROM一時ビルド失敗'
        own = [known['base-cls3'], known['base-boot']]
        observed = measure(rom, False, own, root)
        for r in observed:
            assert r['obs'][0] and 'gv' in r['obs'][0] and not any(r['failed']), (r['arm']['id'], r['failed'])
            assert r['obs'][0]['gv']['tail'] == 0
            assert r['obs'][0]['gv']['stat'][0][0] + r['obs'][0]['gv']['stat'][0][1] + r['obs'][0]['gv']['stat'][0][2] == PLANE
        # 故障注入（ハーネス側）: 環境変数でグラフィックVRAM写しの 1 バイトを化けさせると、写しに現れる
        os.environ['Q88MEASURE_FAULT_CORRUPT_GVRAM_DUMP'] = '1'
        try:
            faulty = run_arm(rom, False, known['base-cls3'], root)
        finally:
            del os.environ['Q88MEASURE_FAULT_CORRUPT_GVRAM_DUMP']
        assert observed[0]['obs'][0]['gv']['nz'] == 0, '自作の cls 3 の後でグラフィックVRAMが空でない'
        assert faulty['gv']['nz'] == 1 and faulty['gv']['lit'] == [[80, 0, 1, 0]], faulty['gv']
        print('  自作の現状: base-cls3 gv統計='+json.dumps(observed[0]['obs'][0]['gv']['stat']), flush=True)
    print('OK 自作ROMの対照2腕×2走（グラフィックVRAM写しが採れる）・ハーネスの故障注入で写しが変わる', flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    m = sub.add_parser('measure'); m.add_argument('--rom-dir')
    m.add_argument('--official', action='store_true'); m.add_argument('--out', type=Path, required=True)
    m.add_argument('--work-dir', type=Path, default=WORK)
    m.add_argument('--only', default='', help='腕IDの接頭辞（カンマ区切り）。空なら全腕')
    m.add_argument('--no-calibration', action='store_true', help='自作ROMの現状記録用。較正の関門を免除する')
    r = sub.add_parser('report'); r.add_argument('--measured', type=Path, required=True)
    sub.add_parser('describe')
    s = sub.add_parser('selftest'); s.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'describe':
        print(describe()); return 0
    if args.command == 'report':
        print(report(args.measured)); return 0
    rom = os.environ.get('PC88_REF_ROM_DIR') if args.official else args.rom_dir
    if not rom or (args.official and args.rom_dir):
        parser.error('公式ROMはPC88_REF_ROM_DIRだけ、自作ROMは--rom-dirで指定する')
    if args.official and args.no_calibration:
        parser.error('公式は較正を免除できない')
    pre = tuple(x for x in args.only.split(',') if x)
    selected = [a for a in arms() if (a['id'].startswith(pre) if pre else True)]
    records = measure(rom, args.official, selected, args.work_dir)
    ok_ = emit(args.out, records, strict=not args.no_calibration)
    print(f'記録完了: {len(records)}腕×2走、関門'+('通過' if ok_ else '失敗'))
    return 0 if ok_ else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except AssertionError:
        raise
    except Exception as error:
        frames = traceback.extract_tb(error.__traceback__)
        print(f'NG 器具の検査または実行に失敗 ({type(error).__name__}, 行{frames[-1].lineno}、画面本文は非出力)')
        raise SystemExit(1)
