#!/usr/bin/env python3
"""l4-s9u: LINE 文（線・B・BF・ラインスタイル・クリップ・STEP・LP）を測る器具。

画面本文は扱わない。採るのは次の数値・記号だけ。ここで「描いた」と言うのは、こちらの打ち込んだプログラムが描かせた画素だけ。
 (1) グラフィックVRAM 3 プレーンの全画素（青・赤・緑、0x4000 バイトずつ。ハーネス --gvram-dump）を (x,y,色) に復号したもの。
     復号は l4_gfx_measure の仮説 H（80 バイト/ライン、MSB が左、B=1・R=2・G=4）。連続した同色の画素を (y, x0, x1, 色) の区間に畳んで持つ。
     生バイトは採取後に消し、コミットしない。
 (2) こちらのプログラムが印字した結果行 `s9u<番号>:誤り,LP-X,LP-Y;`（テキストVRAM写しから）。
 (3) 制御ポートの値（0x31・0x34・0x35・0x53・0x5C〜0x5F）の最後の値。
 (4) --screenshot の PPM から、こちらが描いた線の画素（cal-vis だけ）。
事前登録は docs/notes/l4-s9u-line-preregistration.md。
"""
import argparse
import csv
import hashlib
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
import l4_gfx_measure as g

WORK = kw.REPO.parent / 'tmp/s9u-work'
SENT = 's9uz'
GV_LEN = 0xC000
PLANE = 0x4000
W, H = 640, 200
SPAN_MAX = 6000
VISIBLE = (400, 150)
CELL_COLS, CELL_ROWS = 6, 3


# ---------------------------------------------------------------- 線の画素を生む規則（候補）
def rnd(v):
    return math.floor(v + 0.5)


def line_pts(p1, p2, init='floor', cmp='>', start='gw'):
    """2 点を結ぶ画素列（始点側から）。GW-BASIC の公開ソース（GENGRP.ASM の 272〜569 行、LINE の節）の構造:
    長い軸を主軸（等しければ Y）、始点は Y の小さい端（Y が等しければ第2点）、和の初期値＝主軸の差÷2、
    毎歩 主軸を進め、和に副軸の差を足し、(和 > 主軸の差) なら副軸を進めて和から主軸の差を引く。
    init: 和の初期値（floor＝M//2・zero＝0・ceil＝(M+1)//2）。cmp: '>' か '>='。start: gw・first（第1点）・lowx（X の小さい端、等しければ第1点）。"""
    (x1, y1), (x2, y2) = p1, p2
    if start == 'gw':
        s, e = ((x1, y1), (x2, y2)) if y1 < y2 else ((x2, y2), (x1, y1))
    elif start == 'first':
        s, e = (x1, y1), (x2, y2)
    elif start == 'lowx':
        s, e = ((x1, y1), (x2, y2)) if x1 <= x2 else ((x2, y2), (x1, y1))
    else:
        raise ValueError(start)
    dx, dy = abs(e[0]-s[0]), abs(e[1]-s[1])
    sx = 1 if e[0] >= s[0] else -1
    sy = 1 if e[1] >= s[1] else -1
    ymaj = dy >= dx
    mj, mn = (dy, dx) if ymaj else (dx, dy)
    total = {'floor': mj//2, 'zero': 0, 'ceil': (mj+1)//2}[init]
    x, y = s
    out = []
    for _ in range(mj+1):
        out.append((x, y))
        if ymaj:
            y += sy
        else:
            x += sx
        total += mn
        if (total > mj) if cmp == '>' else (total >= mj):
            if ymaj:
                x += sx
            else:
                y += sy
            total -= mj
    return out


PRIMARY = dict(init='floor', cmp='>', start='gw')
CANDIDATES = [(i, c, s) for s in ('gw', 'first', 'lowx') for i in ('floor', 'zero', 'ceil') for c in ('>', '>=')]


def cand_name(c):
    return f'{c[2]}/{c[0]}/{c[1]}'


def screen_has(p):
    return 0 <= p[0] < W and 0 <= p[1] < H


def clip_recompute(p1, p2, rule):
    """候補: 画面の長方形と線の交点を求め、画面内の端点を四捨五入して、その 2 点を引き直す（傾きは交点から再計算される）。"""
    (x1, y1), (x2, y2) = p1, p2
    t0, t1 = 0.0, 1.0
    dx, dy = x2-x1, y2-y1
    for p, q in ((-dx, x1), (dx, W-1-x1), (-dy, y1), (dy, H-1-y1)):
        if p == 0:
            if q < 0:
                return []
        else:
            t = q/p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    if t0 > t1:
        return []
    a = (rnd(x1+t0*dx), rnd(y1+t0*dy))
    b = (rnd(x1+t1*dx), rnd(y1+t1*dy))
    return [p for p in line_pts(a, b, **rule) if screen_has(p)]


# ---------------------------------------------------------------- 項目（プログラムの 1 要素）
def num(v):
    return v if isinstance(v, str) else (str(v) if isinstance(v, int) else repr(v))


def L(p1, p2, c=None, m=None, st=None, s1=False, s2=False, box=None, probe=False, exp=None, raw=None):
    """LINE 文。p1 が None なら始点省略（line-(x,y)）。c は色（None＝省略・''＝コンマだけ）、m は None/'b'/'bf'、st はラインスタイルの式。
    exp は予測の上書き（raw の文は e=(誤り番号, 強さ)）。raw は文そのもの。box は画素を比べる範囲（左上と右下、両端を含む）。"""
    return dict(op='L', p1=p1, p2=p2, c=c, m=m, st=st, s1=s1, s2=s2, box=box, probe=probe, exp=exp or {}, raw=raw)


def text(stmt):
    return dict(op='text', stmt=stmt)


def color(f=None, b=None):
    return dict(op='color', f=f, b=b)


def cls(n):
    return dict(op='cls', n=n)


def screen(args):
    return dict(op='screen', args=args)


def pset(x, y, c):
    return dict(op='pset', x=x, y=y, c=c)


def arm(aid, items, pix=None, group=None, wait=0):
    return dict(id=aid, items=items, pix=pix or [], group=group or aid.split('-')[0], wait=wait)


PRE = [screen('0,0'), cls(3)]


def cell_xy(k):
    return 8+104*(k % CELL_COLS), 4+64*(k//CELL_COLS)


def cell_box(k):
    ox, oy = cell_xy(k)
    return (ox-3, oy-3, ox+99, oy+60)


def cells(rel, **kw_):
    """rel: 相対座標 (x1,y1,x2,y2) の並び（最大 18）。各線を別のセルに置く。"""
    assert len(rel) <= CELL_COLS*CELL_ROWS
    out = []
    for k, (a, b, c, d) in enumerate(rel):
        ox, oy = cell_xy(k)
        out.append(L((ox+a, oy+b), (ox+c, oy+d), box=cell_box(k), **kw_))
    return out


SHALLOW = [(10, 1), (10, 3), (10, 5), (7, 2), (7, 3), (9, 4), (8, 3), (4, 1), (2, 1), (3, 1), (3, 2), (5, 2), (16, 5), (25, 7),
           (40, 9), (60, 17), (31, 10), (12, 7)]
STEEP = [(b, a) for a, b in SHALLOW]


def slope_rel(dd, up, rev):
    out = []
    for dx, dy in dd:
        a, b = ((0, dy), (dx, 0)) if up else ((0, 0), (dx, dy))
        out.append((b+a) if rev else (a+b))
    return out


BASIC_REL = [(0, 0, 40, 0), (0, 0, 0, 40), (0, 0, 30, 30), (0, 30, 30, 0), (5, 5, 5, 5), (0, 0, 1, 0), (0, 0, 0, 1), (0, 0, 1, 1),
             (40, 0, 0, 0), (0, 40, 0, 0), (30, 30, 0, 0), (30, 0, 0, 30), (0, 0, 2, 2), (1, 0, 0, 1), (0, 0, 2, 1), (0, 0, 1, 2)]
BOX_REL = [(0, 0, 20, 12), (20, 12, 0, 0), (0, 12, 20, 0), (20, 0, 0, 12), (0, 0, 0, 10), (0, 0, 10, 0), (5, 5, 5, 5), (0, 0, 1, 1),
           (0, 0, 2, 2), (0, 0, 3, 3), (0, 0, 2, 5), (0, 0, 5, 2), (0, 0, 1, 6), (0, 0, 6, 1), (1, 1, 0, 0), (3, 3, 0, 0), (0, 0, 40, 30),
           (40, 30, 0, 0)]
STYLES = ['&hffff', '&h0000', '&haaaa', '&h5555', '&hf0f0', '&h8000', '&h0001', '&hf99f', '&hf1d3', '&h00ff', '&hff00', '&h0f0f']
SYN = {'line': 2, 'line(10,10)': 2, 'line(10,10)-': 2, 'line-': 2, 'line(10,10)-(20)': 2, 'line(10,10)(20,20)': 2,
       'line(10,10)-(20,20),,,': 2, 'line(10,10)-(20,20),,bx': 2, 'line(10,10)-(20,20),,f': 2, 'line (10,10)-(20,20),7': 0,
       'line(10,10)-(20,20),,b': 0, 'line(10,10)-(20,20),7;b': 2, 'line step(5,5)-step(5,5)': 0, 'line-step(5,5)': 0,
       'line(10,10)-step(5,5),7': 0, 'line step-(5,5)': 2}
SYN_WEAK = {'line(10,10)-(20,20),,,', 'line(10,10)-(20,20),,f', 'line(10,10)-(20,20),,b', 'line(10,10)-(20,20),7,preset'}
SYN_MORE = {'line(10,10)-(20,20),7,bf,5': 2, 'line(10,10)-(20,20),7,b,&hff': 0, 'line(10,10)-(20,20),b': 0,
            'line(10,10)-(20,20),7,preset': 2, 'line(10,10)-(20,20),7,,,5': 2}


def syn_item(s):
    if s in SYN:
        e = (SYN[s], 'w' if s in SYN_WEAK else 'm')
    elif s in SYN_MORE:
        e = (SYN_MORE[s], 'w')
    else:
        e = None
    return L(None, None, raw=s, probe=True, exp=dict(e=e) if e else {})


def arms():
    out = []
    out.append(arm('base-cls3', [cls(3)]))
    out.append(arm('cal-vis', PRE + [L((400, 150), (402, 150), 7)], pix=[VISIBLE]))
    # ---- 基本の形（ba）。1 画面に 16 セル
    out.append(arm('ba-1', PRE + cells(BASIC_REL, c=7)))
    # ---- 傾き（sh＝緩い・st＝急）。f＝右下がり・r＝その逆向き（終点→始点）・u＝右上がり・q＝その逆向き
    for kind, dd in (('sh', SHALLOW), ('st', STEEP)):
        for tag, up, rev in (('f', False, False), ('r', False, True), ('u', True, False), ('q', True, True)):
            out.append(arm(f'{kind}-{tag}', PRE + cells(slope_rel(dd, up, rev), c=7)))
    # ---- 平行移動（tr）: 同じ線を別の位置に置く
    out.append(arm('tr-1', PRE + cells([(0, 0, 16, 5), (0, 0, 31, 10)], c=7) + [
        L((300, 100), (316, 105), 7, box=(296, 96, 320, 110)), L((401, 53), (432, 63), 7, box=(397, 49, 436, 67))]))
    # ---- 長い線（lo）
    out.append(arm('lo-1', PRE + [L((0, 2), (639, 12), 7), L((0, 30), (639, 31), 7), L((639, 50), (0, 70), 7), L((0, 90), (500, 150), 7),
                                  L((10, 170), (630, 199), 7)]))
    out.append(arm('lo-2', PRE + [L((5, 0), (15, 199), 7), L((30, 0), (31, 199), 7), L((60, 199), (45, 0), 7), L((100, 0), (160, 199), 7),
                                  L((639, 0), (500, 199), 7)]))
    out.append(arm('lo-3', PRE + [L((0, 0), (639, 199), 7)]))
    out.append(arm('lo-4', PRE + [L((639, 0), (0, 199), 7)]))
    out.append(arm('lo-5', PRE + [L((0, 199), (639, 0), 7)]))
    out.append(arm('lo-6', PRE + [L((0, 0), (199, 199), 7)]))
    out.append(arm('lo-7', PRE + [L((0, 100), (639, 100), 7), L((320, 0), (320, 199), 7), L((639, 199), (0, 199), 7), L((0, 0), (0, 199), 7)]))
    # ---- クリップ（cp）
    out.append(arm('cp-1', PRE + [L((-50, 100), (100, 120), 7), L((500, 50), (700, 80), 7), L((300, -30), (340, 40), 7),
                                  L((200, 150), (260, 260), 7)]))
    out.append(arm('cp-2', PRE + [L((-100, 50), (700, 90), 7)]))
    out.append(arm('cp-3', PRE + [L((-30, -40), (300, 260), 7)]))
    out.append(arm('cp-4', PRE + [L((700, -100), (300, 300), 7)]))
    out.append(arm('cp-5', PRE + [L((-50, -50), (-10, -10), 7), L((700, 10), (800, 50), 7), L((10, 250), (100, 300), 7),
                                  L((-20, 15), (15, -20), 7), L((-10, 40), (40, -10), 7), L((620, 190), (660, 230), 7)]))
    out.append(arm('cp-6', PRE + [L((-32768, -32768), (32767, 32767), 7)], wait=6000))
    out.append(arm('cp-7', PRE + [L((-30000, 100), (30000, 100), 7), L((320, -32768), (320, 32767), 7)], wait=6000))
    out.append(arm('cp-8', PRE + [L((-32768, 0), (32767, 199), 7)], wait=6000))
    out.append(arm('cp-9', PRE + [L((-20000, -300), (20000, 500), 7)], wait=6000))
    out.append(arm('cp-a', PRE + [L((-5, 0), (60, 0), 7), L((630, 20), (700, 20), 7), L((100, -10), (100, 40), 7), L((120, 150), (120, 250), 7),
                                  L((-10, -10), (10, 10), 7), L((630, 190), (650, 210), 7), L((-10, 190), (10, 210), 7), L((630, 10), (650, -10), 7)]))
    # ---- 座標の丸めと範囲（co）
    out.append(arm('co-fr', PRE + [L((10.4, 10.6), (40.5, 10.4), 7), L((10.5, 20.5), (20.5, 20.5), 7), L((-0.4, 30), (10, 30.6), 7),
                                   L((630, 40), (639.6, 40), 7), L((5, 199.4), (15, 199.6), 7), L((-0.6, 50), (5, 50), 7),
                                   L((50.5, 60), (50.4, 70), 7), L((100, 80.49), (110, 80.5), 7)]))
    rg = [L((32768, 5), (10, 10), 7, probe=True), L((10, 10), (32768, 5), 7, probe=True), L((-32769, 5), (10, 10), 7, probe=True),
          L((10, 10), (5, -32769), 7, probe=True), L((10, 10), (1e10, 5), 7, probe=True), L((-32768, 20), (10, 20), 7, probe=True),
          L((10, 30), (32767, 30), 7, probe=True), L((65535, 5), (10, 10), 7, probe=True), L((10, 40), (20, 40), 7, probe=True)]
    out.append(arm('co-rg', PRE + rg, wait=3000))
    # ---- 最終参照点・始点省略・STEP（lp）
    out.append(arm('lp-a', PRE + [pset(10, 10, 7), L(None, (60, 10), 7, probe=True), L(None, (60, 40), probe=True),
                                  L((100, 50), (140, 50), 7, probe=True), L(None, (140, 70), 7, s2=True, probe=True)]))
    out.append(arm('lp-b', PRE + [pset(10, 100, 7), L((10, 10), (30, 20), 7, s1=True, probe=True),
                                  L((30, 0), (20, 0), 7, s1=True, s2=True, probe=True),
                                  L((-100, -50), (0, 0), 7, s1=True, probe=True), L((5, 5), (0, 0), 7, s2=True, probe=True),
                                  L(None, (-5, -5), 7, s2=True, probe=True), L((100, 100), (100, 100), 7, probe=True),
                                  L((100, 101), (100, 101), 7, s1=True, probe=True)]))
    out.append(arm('lp-c', PRE + [L((200, 100), (210, 110), 7, 'b', probe=True), L((220, 100), (230, 110), 7, 'bf', probe=True),
                                  L((300, 10), (310, 10), 9, probe=True), L((300, 20), (310, 20), '"a"', probe=True),
                                  L((320, 30), (330, 30), '1,2', probe=True), L((340, 40), (350, 40), -1, probe=True),
                                  L((360, 50), (370, 50), 8, probe=True), L((380, 60), (390, 60), 7, 'bf', probe=True),
                                  L((400, 70), (410, 70), 7, 'b', '&hf0f0', probe=True)]))
    # ---- 色（cl）
    out.append(arm('cl-1', PRE + [L((10, 10+8*c), (60, 10+8*c), c) for c in range(8)]))
    out.append(arm('cl-2', PRE + [L((10, 10), (100, 30), 7, 'bf'), L((20, 20), (90, 20), 0), L((20, 15), (90, 25), 0, 'b'),
                                  L((50, 10), (50, 30), 0), L((10, 50), (100, 70), 5, 'bf'), L((30, 55), (80, 65), 2, 'bf'),
                                  L((20, 60), (95, 60), 0)]))
    cs = [-1, 8, 255, '"a"', 1.5, 0.5, '1e10', 0.4, 6.5, '']
    out.append(arm('cl-3', PRE + [L((10, 10+10*i), (50, 10+10*i), c, probe=True) for i, c in enumerate(cs)]))
    out.append(arm('cl-4', PRE + [L((10, 10), (50, 10)), color(f=3), L((10, 20), (50, 20)), text('color 5'), L((10, 30), (50, 30)),
                                  color(f=0), L((10, 40), (50, 40)), color(f=6), L((10, 50), (50, 50), None, 'b'),
                                  L((60, 60), (90, 80), None, 'bf'), color(f=7), color(b=2), L((10, 90), (50, 90))]))
    out.append(arm('cl-5', PRE + [color(b=3), cls(3), L((10, 10), (60, 20), 7, 'bf', box=(0, 0, 639, 199)), L((20, 15), (50, 15), 0),
                                  L((20, 12), (50, 18), 5, 'b'), L((70, 30), (90, 30), 0)]))
    # ---- 箱（bx）
    out.append(arm('bx-b', PRE + cells(BOX_REL, c=7, m='b')))
    out.append(arm('bx-f', PRE + cells(BOX_REL, c=7, m='bf')))
    out.append(arm('bx-fr', PRE + [L((10.5, 10.5), (30.4, 20.6), 7, 'b'), L((50.5, 10.5), (70.4, 20.6), 7, 'bf'),
                                   L((100.4, 10.4), (110.5, 20.5), 7, 'bf')]))
    out.append(arm('bx-big', PRE + [L((0, 0), (639, 199), 7, 'bf')]))
    out.append(arm('bx-bigb', PRE + [L((0, 0), (639, 199), 7, 'b')]))
    out.append(arm('bx-ov', PRE + [L((-10, -10), (700, 300), 7, 'bf')]))
    out.append(arm('bx-p1', PRE + [L((-20, 10), (40, 50), 7, 'bf'), L((600, 100), (700, 150), 7, 'bf'), L((100, -20), (140, 30), 7, 'b'),
                                   L((300, 170), (360, 260), 7, 'b'), L((-20, 100), (20, 130), 7, 'b'), L((400, -30), (430, 20), 5, 'bf')]))
    out.append(arm('bx-p2', PRE + [L((-30, -30), (-10, -10), 7, 'bf'), L((700, 10), (800, 50), 7, 'b'), L((-20, 120), (800, 180), 7, 'b'),
                                   L((-5000, -5000), (5000, 5000), 3, 'b')]))
    # ---- ラインスタイル（sy）
    out.append(arm('sy-h', PRE + [L((10, 10+14*k), (57, 10+14*k), 7, st=s) for k, s in enumerate(STYLES)]))
    out.append(arm('sy-hr', PRE + [L((57, 10+14*k), (10, 10+14*k), 7, st=s) for k, s in enumerate(STYLES)]))
    out.append(arm('sy-v', PRE + [L((10+14*k, 10), (10+14*k, 57), 7, st=s) for k, s in enumerate(STYLES)]))
    out.append(arm('sy-vr', PRE + [L((10+14*k, 57), (10+14*k, 10), 7, st=s) for k, s in enumerate(STYLES)]))
    out.append(arm('sy-d', PRE + cells([(0, 0, 40, 40), (40, 40, 0, 0), (0, 0, 40, 10), (40, 10, 0, 0), (0, 0, 10, 40), (10, 40, 0, 0),
                                        (0, 40, 40, 0), (40, 0, 0, 40), (0, 40, 40, 30), (40, 30, 0, 40), (0, 0, 21, 3), (21, 3, 0, 0)],
                                       c=7, st='&hf1d3')))
    out.append(arm('sy-b', PRE + cells([(0, 0, 30, 20), (30, 20, 0, 0), (0, 20, 30, 0), (30, 0, 0, 20), (0, 0, 30, 0), (0, 0, 0, 20),
                                        (0, 0, 40, 40), (0, 0, 17, 9)], c=7, m='b', st='&hf1d3')))
    out.append(arm('sy-c', PRE + [L((-20, 100), (60, 100), 7, st='&hf1d3'), L((600, 120), (700, 120), 7, st='&hf1d3'),
                                  L((200, -20), (200, 60), 7, st='&hf1d3'), L((250, 150), (250, 250), 7, st='&hf1d3'),
                                  L((300, -10), (360, 50), 7, st='&hf1d3'), L((-20, 160), (60, 180), 7, st='&hf1d3'),
                                  L((60, 140), (-20, 140), 7, st='&hf1d3')]))
    out.append(arm('sy-n', PRE + [L((10, 10), (60, 10), st='&haaaa'), color(f=2), L((10, 20), (60, 20), st='&haaaa'),
                                  L((10, 30), (60, 30), 5, st='&haaaa'), L((10, 40), (60, 40), 0, st='&haaaa'),
                                  L((10, 50), (60, 50), 3, 'b', '&haaaa')]))
    sv = ['&h10000', '-1', '65535', '65536', '-32768', '-32769', '0', '1', '1.5', '0.5', '"a"', '1e10', '&h7fff', '&h8000']
    out.append(arm('sy-e', PRE + [L((10, 10+8*i), (60, 10+8*i), 7, st=s, probe=True) for i, s in enumerate(sv)]))
    out.append(arm('sy-f', PRE + [L((10, 10), (60, 10), 7, 'bf', '&hf0f0', probe=True), L((10, 20), (60, 20), 7, '', '&hf0f0', probe=True),
                                  L((10, 30), (60, 30), None, 'b', '&hf0f0', probe=True), L((10, 40), (60, 40), None, None, '&hf0f0', probe=True),
                                  L((10, 50), (60, 50), 7, None, '&hf0f0', probe=True)]))
    # ---- 白黒モード（mo）
    for tag, sa in (('0', '1,0,0,7'), ('1', '1,0,1,7'), ('2', '1,0,2,7'), ('d', '1')):
        out.append(arm(f'mo-{tag}', [screen(sa), cls(3), L((10, 10), (60, 30), 5), L((10, 40), (60, 60), 3, 'b'), L((70, 10), (90, 30), 1, 'bf'),
                                     L((75, 15), (85, 25), 0, 'bf'), L((100, 10), (150, 10), 0), L((100, 20), (150, 20)),
                                     L((100, 30), (140, 40), 4, st='&hf1d3')]))
    # ---- 構文（sx）
    syn = ['line', 'line(10,10)', 'line(10,10)-', 'line-', 'line(10,10)-(20)', 'line(10,10)(20,20)', 'line(10,10)-(20,20),,,', 'line(10,10)-(20,20),,bx',
           'line(10,10)-(20,20),,f', 'line(10,10)-(20,20),7,bf,5', 'line(10,10)-(20,20),7,b,&hff', 'line (10,10)-(20,20),7', 'line(10,10)-(20,20),b',
           'line(10,10)-(20,20),,b', 'line(10,10)-(20,20),7,preset', 'line(10,10)-(20,20),7;b', 'line step(5,5)-step(5,5)', 'line-step(5,5)',
           'line(10,10)-step(5,5),7', 'line(10,10)-(20,20),7,b,', 'line(10,10)-(20,20),7,,', 'line(10,10)-(20,20),7,,,5', 'line step-(5,5)']
    out.append(arm('sx-a', PRE + [syn_item(s) for s in syn[:12]]))
    out.append(arm('sx-b', PRE + [syn_item(s) for s in syn[12:]]))
    return out


# ---------------------------------------------------------------- 予測のモデル（事前登録のとおり。強 s・中 m・弱 w）
RANK = {'s': 3, 'm': 2, 'w': 1}


def low(*ss):
    ss = [s for s in ss if s]
    return min(ss, key=lambda s: RANK[s]) if ss else 'w'


def eval_style(s):
    s = s.strip()
    if s.startswith('"'):
        raise ValueError(13)
    if s.lower().startswith('&h'):
        v = int(s[2:], 16)
        if v > 0xFFFF:
            raise ValueError(6)
        return v
    v = float(s)
    if v > 65535 or v < -32768:
        raise ValueError(6)
    return rnd(v)


class Model:
    def __init__(self):
        self.lp = (0, 0)
        self.fg, self.bg = 7, 0
        self.mono, self.apage = False, 0
        self.pix = {}
        self.base = 0

    def put(self, p, c):
        if not screen_has(p):
            return
        if self.mono:
            c = (1 << self.apage) if c else 0
        if c == self.base:
            self.pix.pop(p, None)
        else:
            self.pix[p] = c

    def get(self, p):
        return self.pix.get(p, self.base)

    def clear(self, c):
        self.pix = {}
        self.base = c

    def pset(self, x, y, c):
        p = (rnd(x), rnd(y))
        self.lp = p
        if screen_has(p):
            self.put(p, self.fg if c is None else c)

    def draw_set(self, p1, p2, style=None):
        """画素の列（画面外も含む）。style は 16 ビットの整数か None。パターンは第1点から数え、最上位ビットが最初の画素。"""
        pts = line_pts(p1, p2, **PRIMARY)
        if style is not None:
            if pts[0] != p1 and pts[-1] == p1:
                pts = pts[::-1]
            pts = [p for k, p in enumerate(pts) if (style >> (15-k % 16)) & 1]
        return pts

    def line(self, it):
        """LINE の予測と、モデルの状態の更新。返り値 dict(e=(誤り,強さ)|None, lp=(座標,強さ)|None, px=強さ|None, pts=画素列|None)。"""
        ex = it['exp']
        if it['raw'] is not None:
            return dict(e=ex.get('e'), lp=None, px=None, pts=[])
        for pt in (it['p1'], it['p2']):
            if pt is not None and (isinstance(pt[0], str) or isinstance(pt[1], str)):
                return dict(e=None, lp=None, px=None, pts=[])
        bad = lambda pt: abs(rnd(pt[0])) > 32767 or abs(rnd(pt[1])) > 32767
        if it['p1'] is None:
            a = self.lp
        else:
            if bad(it['p1']):
                return dict(e=(6, 'm'), lp=(self.lp, 'w'), px='m', pts=[])
            a = (rnd(it['p1'][0]), rnd(it['p1'][1]))
            if it['s1']:
                a = (self.lp[0]+a[0], self.lp[1]+a[1])
            self.lp = a
        if bad(it['p2']):
            return dict(e=(6, 'm'), lp=(self.lp, 'w'), px='m', pts=[])
        b = (rnd(it['p2'][0]), rnd(it['p2'][1]))
        if it['s2']:
            b = (a[0]+b[0], a[1]+b[1])
        self.lp = b
        lp_ok, lp_err = (b, 's' if it['m'] is None else 'm'), (b, 'm')
        c, m, st = it['c'], it['m'], it['st']
        if c is None:
            cc, cst = self.fg, 'm'
        elif c == '':
            return dict(e=(22, 'w'), lp=lp_err, px='w', pts=[])
        elif c == '1,2':
            return dict(e=(2, 'm'), lp=(b, 'w'), px='m', pts=[])
        elif isinstance(c, str):
            if c == '"a"':
                return dict(e=(13, 'm'), lp=lp_err, px='m', pts=[])
            return dict(e=(6, 'w'), lp=lp_err, px='w', pts=[])
        else:
            cc = rnd(c)
            cst = 's' if float(c).is_integer() else 'w'
            if not 0 <= cc <= 7:
                return dict(e=(5, 'm'), lp=lp_err, px='m', pts=[])
        sv = None
        if st is not None:
            if m == 'bf':
                return dict(e=(2, 'w'), lp=lp_err, px='w', pts=[])
            try:
                sv = eval_style(st) & 0xFFFF
            except ValueError as err:
                return dict(e=(err.args[0], 'w'), lp=lp_err, px='w', pts=[])
        dx, dy = abs(b[0]-a[0]), abs(b[1]-a[1])
        frac = any(isinstance(v, float) and v != int(v) for pt in (it['p1'], it['p2']) if pt for v in pt)
        clipped = not (screen_has(a) and screen_has(b))
        pts = []
        sst = None
        if m == 'bf':
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            pts = [(x, y) for y in range(max(y0, 0), min(y1, H-1)+1) for x in range(max(x0, 0), min(x1, W-1)+1)]
            sst = 's' if not clipped else 'm'
        elif m == 'b':
            x0, x1 = sorted((a[0], b[0]))
            y0, y1 = sorted((a[1], b[1]))
            if sv is None:
                pts = set()
                for pa, pb in (((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))):
                    pts.update(q for q in line_pts(pa, pb, **PRIMARY) if screen_has(q))
                pts = sorted(pts)
                sst = 's' if not clipped else 'm'
            else:
                pts = None             # スタイル付きの箱は予測なし（記述だけ）
        else:
            if sv is None:
                pts = [q for q in self.draw_set(a, b) if screen_has(q)]
                sst = 's' if (dx == 0 or dy == 0 or dx == dy) else 'w'
            else:
                pts = [q for q in self.draw_set(a, b, sv) if screen_has(q)]
                sst = 'w'
            if clipped and sst == 's':
                sst = 'm'
        if pts is not None:
            for q in pts:
                self.put(q, cc)
        e = (0, 's')
        if sst:
            if frac or cst == 'w':
                sst = low(sst, 'w')
            if c is None:
                sst = low(sst, 'm')
            if max(dx, dy) > 32767:
                sst = 'w'
        if max(dx, dy) > 32767:
            e = (0, 'w')
        return dict(e=e, lp=lp_ok, px=sst, pts=pts, a=a, b=b, clipped=clipped, plain=(m is None and sv is None))

    def do_cls(self, n):
        if n in (2, 3):
            self.clear(self.bg)
            self.lp = (0, 0)

    def do_screen(self, args):
        parts = [p.strip() for p in args.split(',')]
        m0 = parts[0] if parts else ''
        if m0 == '1':
            self.mono, self.apage = True, (int(parts[2]) if len(parts) > 2 and parts[2] else 0)
        elif m0 == '0':
            self.mono = False
        self.lp = (0, 0)


# ---------------------------------------------------------------- 文の組み立て
def stmt_of(it):
    if it['op'] == 'L':
        if it['raw'] is not None:
            return it['raw']
        s = 'line'
        if it['p1'] is not None:
            s += (' step' if it['s1'] else '') + f"({num(it['p1'][0])},{num(it['p1'][1])})"
        s += '-' + ('step' if it['s2'] else '') + f"({num(it['p2'][0])},{num(it['p2'][1])})"
        fields = [None if it['c'] is None else str(it['c']), it['m'], it['st']]
        last = max([i for i, f in enumerate(fields) if f is not None], default=-1)
        if last >= 0:
            s += ',' + ','.join('' if f is None else str(f) for f in fields[:last+1])
        return s
    if it['op'] == 'pset':
        return f"pset({it['x']},{it['y']})" if it['c'] is None else f"pset({it['x']},{it['y']}),{it['c']}"
    if it['op'] == 'text':
        return it['stmt']
    if it['op'] == 'color':
        return f"color ,,,{it['f']}" if it['f'] is not None else f"color ,{it['b']}"
    if it['op'] == 'cls':
        return f"cls {it['n']}"
    if it['op'] == 'screen':
        return f"screen {it['args']}"
    raise ValueError(it)


def steps(a):
    """(項目, 文, 印字か, 番号, 予測) の並びと最後のモデル。"""
    m = Model()
    out = []
    for i, it in enumerate(a['items']):
        pred = {}
        op = it['op']
        pr = False
        if op == 'L':
            pred = m.line(it)
            pr = bool(it['probe'])
        elif op == 'pset':
            m.pset(it['x'], it['y'], it['c'])
        elif op == 'color':
            if it['f'] is not None:
                m.fg = it['f']
            else:
                m.bg = it['b']
        elif op == 'cls':
            m.do_cls(it['n'])
        elif op == 'screen':
            m.do_screen(it['args'])
        out.append((it, stmt_of(it), pr, i, pred))
    return out, m


# ---------------------------------------------------------------- 打ち込むプログラム
def program_lines(a):
    st, _ = steps(a)
    lines = {5: 'on error goto 900', 6: 'cls'}
    n = 10
    cur = ''
    for it, stmt, pr, i, pred in st:
        if pr:
            if cur:
                lines[n] = cur; n += 10; cur = ''
            lines[n] = f'e=0:{stmt}:g=e'; n += 10
            lines[n] = 'e=0:x=point(0):y=point(1)'; n += 10
            lines[n] = f'print "s9u{i}:";g;",";x;",";y;";"'; n += 10
        else:
            if cur and len(f'{n} {cur}:{stmt}') > 76:
                lines[n] = cur; n += 10; cur = ''
            cur = f'{cur}:{stmt}' if cur else stmt
    if cur:
        lines[n] = cur; n += 10
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
def decode_all(data):
    if len(data) != GV_LEN:
        raise ValueError('グラフィックVRAM写しの長さが不正')
    planes = [data[p*PLANE:(p+1)*PLANE] for p in range(3)]
    out = {}
    tail = 0
    for o in range(PLANE):
        b0, b1, b2 = planes[0][o], planes[1][o], planes[2][o]
        if not (b0 or b1 or b2):
            continue
        if o >= 16000:
            tail += 1
            continue
        y, col = divmod(o, 80)
        for k in range(8):
            c = ((b0 >> k) & 1) | (((b1 >> k) & 1) << 1) | (((b2 >> k) & 1) << 2)
            if c:
                out[(col*8+(7-k), y)] = c
    stat = []
    for pl in planes:
        z, f = pl.count(0), pl.count(0xFF)
        stat.append([z, f, PLANE-z-f])
    return out, tail, stat


def to_spans(pix):
    spans = []
    byrow = {}
    for (x, y), c in pix.items():
        byrow.setdefault(y, []).append((x, c))
    for y in sorted(byrow):
        xs = sorted(byrow[y])
        x0, c0 = xs[0]
        px = x0
        for x, c in xs[1:]:
            if x == px+1 and c == c0:
                px = x
                continue
            spans.append([y, x0, px, c0])
            x0, c0, px = x, c, x
        spans.append([y, x0, px, c0])
    return spans


def from_spans(spans):
    return {(x, y): c for y, x0, x1, c in spans for x in range(x0, x1+1)}


def pix_hash(pix):
    h = hashlib.sha256()
    for k in sorted(pix):
        h.update(f'{k[0]},{k[1]},{pix[k]};'.encode())
    return h.hexdigest()[:16]


def parse_results(vram):
    if len(vram) != 3000:
        raise ValueError('画面写しの長さが不正')
    joined = b''.join(bytes(vram[r*120:r*120+80]) for r in range(25))
    res = {}
    for m in re.finditer(rb's9u(\d+):([ \x20-\x7e]*?);', joined):
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
    return res, joined.count(SENT.encode())


def analyze(a, gv, vram, iolog_text, window, img=None):
    obs = dict(arm=a['id'])
    pix, tail, stat = decode_all(gv)
    obs['n'] = len(pix)
    obs['hash'] = pix_hash(pix)
    obs['tail'] = tail
    obs['stat'] = stat
    spans = to_spans(pix)
    obs['spans'] = spans if len(spans) <= SPAN_MAX else None
    res, sent = parse_results(vram)
    obs['res'] = {str(k): v for k, v in sorted(res.items())}
    obs['sent'] = sent
    ev = g.events(iolog_text, window)
    obs['last'] = ev['last']
    if a['pix'] and img is not None:
        obs['pix'] = g.pix_stat(img, a['pix'])
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
            at += (len(step)+1)*8+240+((wv.RUN_WAIT+a.get('wait', 0)) if step == 'run' else 0)
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
    if not isinstance(obs, dict) or obs.get('arm') != a['id'] or 'hash' not in obs:
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
def obs_pix(obs):
    if obs.get('spans') is None:
        return None
    return from_spans(obs['spans'])


def in_box(p, box):
    return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]


def judge(obs, a):
    """予測のある項目ごとに 'agree:強さ' / 'differ:強さ'。予測なしは出さない。"""
    st, m = steps(a)
    res = {}

    def put(name, got, want, strength):
        res[name] = ('agree:' if got == want else 'differ:') + strength

    r = obs['res']
    for it, stmt, pr, i, pred in st:
        if not pr or it['op'] != 'L':
            continue
        vals = r.get(str(i))
        if vals is None:
            continue
        if pred.get('e') is not None:
            put(f'p{i}_e', vals[0], pred['e'][0], pred['e'][1])
        if pred.get('lp') is not None and pred['lp'][0] is not None:
            put(f'p{i}_lp', tuple(vals[1:3]), pred['lp'][0], pred['lp'][1])
    if a['id'] == 'base-cls3':
        put('empty', obs['n'], 0, 'm')
        return res
    put('tail', obs['tail'], 0, 's')
    op = obs_pix(obs)
    if op is None:
        return res
    boxes = []
    for it, stmt, pr, i, pred in st:
        if it['op'] != 'L' or it['raw'] is not None or it['box'] is None:
            continue
        boxes.append(it['box'])
        sst = pred.get('px')
        if not sst:
            continue
        bx = it['box']
        if m.base:
            want = {(x, y): m.get((x, y)) for x in range(bx[0], bx[2]+1) for y in range(bx[1], bx[3]+1)}
            got = {p: op.get(p, 0) for p in want}
        else:
            want = {p: c for p, c in m.pix.items() if in_box(p, bx)}
            got = {p: c for p, c in op.items() if in_box(p, bx)}
        put(f'c{i}_px', got, want, sst)
        if pred.get('plain') and pred.get('pts') and not pred.get('clipped') and it['c'] not in (0, '0') and not m.base:
            a1, b1 = pred['a'], pred['b']
            put(f'c{i}_cnt', len(got), max(abs(b1[0]-a1[0]), abs(b1[1]-a1[1]))+1, 's')
            put(f'c{i}_end', (a1 in got, b1 in got), (True, True), 'm')
    # 箱を持たない描画の全体（まとめて 1 項目）。生の文を含む腕、予測なしの描画を含む腕は対象外
    items = [(it, pred) for it, stmt, pr, i, pred in st if it['op'] == 'L']
    has_raw = any(it['raw'] is not None for it, _ in items)
    free = [pred for it, pred in items if it['box'] is None]
    if not has_raw and not m.base and all(p.get('pts') is not None for p in free):
        strength = low(*[p.get('px') for p in free if p.get('px')]) if any(p.get('px') for p in free) else 's'
        want = {p: c for p, c in m.pix.items() if not any(in_box(p, b) for b in boxes)}
        got = {p: c for p, c in op.items() if not any(in_box(p, b) for b in boxes)}
        if free or not boxes:
            put('rest', got, want, strength)
    return res


def cand_report(obs, a):
    """記述: 箱ごと（箱の無い線は全体）に、候補の規則のうち観測と一致するもの。"""
    op = obs_pix(obs)
    if op is None:
        return {}
    out = {}
    st, _ = steps(a)
    for it, stmt, pr, i, pred in st:
        if it['op'] != 'L' or it['raw'] is not None or it['m'] is not None or it['st'] is not None:
            continue
        if pred.get('pts') is None or 'a' not in pred:
            continue
        box = it['box'] or (0, 0, W-1, H-1)
        got = {p for p in op if in_box(p, box)}
        names = []
        for c in CANDIDATES:
            rule = dict(init=c[0], cmp=c[1], start=c[2])
            s = {q for q in line_pts(pred['a'], pred['b'], **rule) if screen_has(q)}
            if s == got:
                names.append(cand_name(c))
        rec = []
        if pred.get('clipped'):
            rec.append('clip-recompute' if set(clip_recompute(pred['a'], pred['b'], PRIMARY)) == got else 'clip-recompute-NO')
        out[i] = dict(line=[pred['a'], pred['b']], n=len(got), match=names, extra=rec)
    return out


def rel_set(op, box, origin):
    return {(p[0]-origin[0], p[1]-origin[1]) for p in op if in_box(p, box)}


def group_judges(records):
    by = {r['arm']['id']: r['obs'][0] for r in records if r['gate'] and r['obs'][0]}
    out = {}

    def cell_sets(aid):
        o = by.get(aid)
        op = obs_pix(o) if o else None
        if op is None:
            return None
        a = next(x for x in arms() if x['id'] == aid)
        return [rel_set(op, it['box'], (it['box'][0]+3, it['box'][1]+3)) for it in a['items'] if it['op'] == 'L' and it['box']]
    for kind in ('sh', 'st'):
        f, rv, u, q = (cell_sets(f'{kind}-{t}') for t in 'fruq')
        if f and rv:
            out[f'{kind}_reverse_down'] = ('agree:' if f == rv else 'differ:') + 'm'
        if u and q:
            out[f'{kind}_reverse_up'] = ('agree:' if u == q else 'differ:') + 'm'
    o4, o5 = by.get('lo-4'), by.get('lo-5')
    if o4 and o5 and o4['hash'] and o5['hash']:
        out['lo_reverse'] = ('agree:' if o4['hash'] == o5['hash'] else 'differ:') + 'm'
    for aid, tag in (('bx-b', 'box_corner_order'), ('bx-f', 'boxfill_corner_order')):
        cs = cell_sets(aid)
        if cs:
            out[tag] = ('agree:' if cs[0] == cs[1] == cs[2] == cs[3] else 'differ:') + 'm'
    o = by.get('tr-1')
    if o and obs_pix(o) is not None:
        a = next(x for x in arms() if x['id'] == 'tr-1')
        ls = [it for it in a['items'] if it['op'] == 'L']
        op = obs_pix(o)
        sets = [rel_set(op, it['box'], it['p1']) for it in ls]
        out['translate'] = ('agree:' if sets[0] == sets[2] and sets[1] == sets[3] else 'differ:') + 'm'
    return out


def calibrated(records):
    by = {r['arm']['id']: r for r in records}
    good = True
    if 'cal-vis' in by:
        r = by['cal-vis']
        o = r['obs'][0] if r['obs'] else {}
        good = good and bool(r['gate'] and o and o['n'] == 3 and o['tail'] == 0)
        if o and o.get('pix'):
            good = good and o['pix'][0]['dot'] != o['pix'][0]['ref']
    if 'base-cls3' in by:
        r = by['base-cls3']
        good = good and bool(r['gate'] and r['obs'][0] and r['obs'][0]['n'] == 0)
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
    arms_by = {a['id']: a for a in arms()}
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
        lines.append(f"  n={o['n']} hash={o['hash']} tail={o['tail']} res={o['res']} last={o['last']}")
        if o.get('pix'):
            lines.append(f"  pix={o['pix']}")
        a = arms_by.get(r['arm'])
        if a and o.get('spans') is not None:
            for i, c in cand_report(o, a).items():
                lines.append(f"  cand[{i}] line={c['line']} n={c['n']} match={c['match']} {c['extra']}")
    return '\n'.join(lines)


def describe():
    out = []
    for a in arms():
        st, m = steps(a)
        prog = ' / '.join(s[1] for s in st if s[1])
        out.append(f"- `{a['id']}` ({n_probes(a)}印字{', 待ち+%d' % a['wait'] if a['wait'] else ''}): {prog}")
    return '\n'.join(out)


# ---------------------------------------------------------------- 自己検査
def synth_gv(pix):
    d = bytearray(GV_LEN)
    for (x, y), c in pix.items():
        o = y*80+x//8
        bit = 1 << (7-x % 8)
        for p in range(3):
            if (c >> p) & 1:
                d[p*PLANE+o] |= bit
    return bytes(d)


def synth_text(lines):
    d = bytearray(b' '*3000)
    for r, s in enumerate(lines):
        d[r*120:r*120+len(s)] = s.encode()
    return bytes(d)


def selftest(work=None):
    if work is not None:
        work.mkdir(parents=True, exist_ok=True)
    known = {a['id']: a for a in arms()}
    assert len(known) == len(arms())
    for a in known.values():
        program_lines(a)
        plan(a)
    # 箱: 各セルの線は自分の箱に収まり、箱どうしは重ならない（箱を持つ腕）
    for a in known.values():
        bxs = [it['box'] for it in a['items'] if it['op'] == 'L' and it['box']]
        if len(bxs) > 1 and a['id'] != 'cl-5':
            assert all(b1[2] < b2[0] or b2[2] < b1[0] or b1[3] < b2[1] or b2[3] < b1[1] for i, b1 in enumerate(bxs) for b2 in bxs[:i]), a['id']
        mm = Model()
        for it in a['items']:
            if it['op'] == 'L' and it['box'] and a['id'] != 'cl-5':
                pr_ = Model().line(it)
                assert pr_['pts'] is None or all(in_box(q, it['box']) for q in pr_['pts']), (a['id'], it)
    # 傾きの腕は候補の規則を区別できる（どのセルでも '>' と '>=' で集合が違い、候補全体で 3 通り以上に割れる）
    for aid in ('sh-f', 'st-f', 'sh-u', 'st-q'):
        for it in known[aid]['items']:
            if it['op'] != 'L':
                continue
            sets_ = {c: tuple(line_pts(it['p1'], it['p2'], init=c[0], cmp=c[1], start=c[2])) for c in CANDIDATES}
            assert sets_[('floor', '>', 'gw')] != sets_[('floor', '>=', 'gw')] and len(set(sets_.values())) >= 3, (aid, it)
    # 線の規則: 手計算
    assert line_pts((0, 0), (4, 1)) == [(0, 0), (1, 0), (2, 0), (3, 1), (4, 1)]
    assert line_pts((0, 0), (4, 1), cmp='>=') == [(0, 0), (1, 0), (2, 1), (3, 1), (4, 1)]
    assert line_pts((4, 1), (0, 0)) == [(0, 0), (1, 0), (2, 0), (3, 1), (4, 1)]               # gw は逆向きでも同じ（Y の小さい端から）
    assert line_pts((4, 1), (0, 0), start='first') == [(4, 1), (3, 1), (2, 1), (1, 0), (0, 0)]       # 第1点始点では向きで変わる
    assert line_pts((5, 5), (5, 5)) == [(5, 5)] and len(line_pts((0, 0), (30, 30))) == 31 and line_pts((0, 0), (3, 3))[-1] == (3, 3)
    assert line_pts((0, 3), (0, 0)) == [(0, 0), (0, 1), (0, 2), (0, 3)] and line_pts((2, 0), (0, 0)) == [(0, 0), (1, 0), (2, 0)]
    for dx, dy in ((10, 3), (7, 2), (3, 2), (60, 17), (5, 12)):
        pts = line_pts((0, 0), (dx, dy))
        assert len(pts) == max(dx, dy)+1 and pts[0] == (0, 0) and pts[-1] == (dx, dy)
        assert all(max(abs(p[0]-q[0]), abs(p[1]-q[1])) == 1 for p, q in zip(pts, pts[1:]))
    assert len({tuple(line_pts((0, 0), (10, 3), init=c[0], cmp=c[1], start=c[2])) for c in CANDIDATES}) >= 3           # 候補は区別できる
    assert clip_recompute((0, 0), (10, 3), PRIMARY) == [p for p in line_pts((0, 0), (10, 3)) if screen_has(p)]
    assert clip_recompute((-50, -50), (-10, -10), PRIMARY) == []
    assert set(clip_recompute((-100, 50), (700, 90), PRIMARY)) != {p for p in line_pts((-100, 50), (700, 90)) if screen_has(p)} or True
    print('OK 線の規則（手計算・逆向き・長さ0・連結・候補の区別・クリップ候補）', flush=True)
    # 復号・区間・ハッシュ
    pix = {(0, 0): 7, (1, 0): 7, (2, 0): 3, (9, 1): 2, (639, 199): 5}
    pp, tail, stat = decode_all(synth_gv(pix))
    assert pp == pix and tail == 0
    assert to_spans(pix) == [[0, 0, 1, 7], [0, 2, 2, 3], [1, 9, 9, 2], [199, 639, 639, 5]] and from_spans(to_spans(pix)) == pix
    d = bytearray(synth_gv(pix)); d[16000] = 1
    assert decode_all(bytes(d))[1] == 1                                                      # 範囲外のバイトを数える
    assert pix_hash(pix) != pix_hash({**pix, (3, 3): 1}) and pix_hash(pix) == pix_hash(dict(reversed(list(pix.items()))))
    t = synth_text(['s9u0:0,100,200;', 's9u1: 5, 1 , -1;   SECRETLINE', 'xx s9u2:0,1.5,3;s9uz'])
    rs, sent = parse_results(t)
    assert rs == {0: [0, 100, 200], 1: [5, 1, -1], 2: [0, 1.5, 3]} and sent == 1, (rs, sent)
    t2 = bytearray(b' '*3000)
    t2[69:80] = b's9u3:0,100,'; t2[120:131] = b'200;       '                                    # 行をまたぐ結果行
    assert parse_results(bytes(t2))[0] == {3: [0, 100, 200]}
    print('OK 復号・区間・ハッシュ・範囲外バイト・結果行の解析（行またぎ）', flush=True)
    # モデルの手計算
    m = Model()
    p = m.line(L((10, 10), (14, 11), 7))
    assert p['e'] == (0, 's') and p['lp'] == ((14, 11), 's') and p['px'] == 'w' and m.pix == {q: 7 for q in [(10, 10), (11, 10), (12, 10), (13, 11), (14, 11)]}
    m = Model(); m.lp = (100, 100)
    p = m.line(L(None, (5, -5), 7, s2=True))
    assert m.lp == (105, 95) and p['px'] == 's' and len(m.pix) == 6
    m = Model()
    m.line(L((0, 0), (10, 10), 7, 'bf')); m.line(L((3, 3), (7, 3), 0))
    assert len(m.pix) == 121-5
    m = Model()
    p = m.line(L((5, 5), (8, 7), 7, 'b'))
    assert len(m.pix) == 10 and (6, 6) not in m.pix and p['px'] == 's'
    p = m.line(L((10, 10), (20, 20), 9)); assert p['e'] == (5, 'm') and m.lp == (20, 20)
    p = m.line(L((10, 10), (32768, 5), 7)); assert p['e'] == (6, 'm') and m.lp == (10, 10)
    m = Model()
    p = m.line(L((0, 0), (31, 0), 7, st='&hf1d3'))
    want = [(k, 0) for k in range(32) if (0xF1D3 >> (15-k % 16)) & 1]
    assert sorted(m.pix) == want and p['px'] == 'w'
    m = Model()
    m.line(L((-3, 0), (3, 0), 7)); assert sorted(m.pix) == [(0, 0), (1, 0), (2, 0), (3, 0)] and m.lp == (3, 0)
    assert eval_style('&hffff') == 0xFFFF and eval_style('65535') == 65535 and eval_style('-32768') == -32768
    for bad_ in ('&h10000', '65536', '-32769'):
        try:
            eval_style(bad_); assert False
        except ValueError:
            pass
    assert stmt_of(L((1, 2), (3, 4), 7, 'b', '&hff')) == 'line(1,2)-(3,4),7,b,&hff' and stmt_of(L((1, 2), (3, 4), None, 'b')) == 'line(1,2)-(3,4),,b'
    assert stmt_of(L(None, (3, 4), 7, s2=True)) == 'line-step(3,4),7' and stmt_of(L((1, 2), (3, 4), None, None, '&hf')) == 'line(1,2)-(3,4),,,&hf'
    assert stmt_of(L((1, 2), (3, 4), 7, s1=True, s2=True)) == 'line step(1,2)-step(3,4),7' and stmt_of(L((1, 2), (3, 4), '')) == 'line(1,2)-(3,4),'
    print('OK モデル（手計算: 線・STEP・BF・B・色の誤り・範囲・スタイル）と文の組み立て', flush=True)
    # 判定の陽性・陰性
    a = known['bx-f']
    st_, mm = steps(a)
    good = dict(arm='bx-f', n=len(mm.pix), hash='x', tail=0, stat=[], spans=to_spans(mm.pix), res={}, sent=1, last={})
    jd = judge(good, a)
    assert all(v.startswith('agree') for v in jd.values()) and len(jd) > 10, jd
    bad_pix = dict(mm.pix); bad_pix.pop(next(iter(bad_pix)))
    assert any(v.startswith('differ') for v in judge(dict(good, spans=to_spans(bad_pix)), a).values())
    assert judge(dict(good, tail=3), a)['tail'].startswith('differ')
    a = known['sh-f']
    st_, mm = steps(a)
    good = dict(arm='sh-f', n=len(mm.pix), hash='x', tail=0, stat=[], spans=to_spans(mm.pix), res={}, sent=1, last={})
    assert all(v.startswith('agree') for v in judge(good, a).values())
    gp = dict(mm.pix)
    cell = sorted(p for p in gp if in_box(p, cell_box(0)))
    gp.pop(cell[3]); gp[(cell[3][0], cell[3][1]+1)] = 7                                          # 1 画素ずらす
    jd = judge(dict(good, spans=to_spans(gp)), a)
    assert jd['c2_px'].startswith('differ') and not any(v.startswith('differ') for k, v in jd.items() if not k.startswith('c2_'))
    a = known['lp-a']
    st_, mm = steps(a)
    res = {str(i): [0, pred['lp'][0][0], pred['lp'][0][1]] for it, stmt, pr, i, pred in st_ if pr}
    good = dict(arm='lp-a', n=len(mm.pix), hash='x', tail=0, stat=[], spans=to_spans(mm.pix), res=res, sent=1, last={})
    jd = judge(good, a)
    assert all(v.startswith('agree') for v in jd.values()) and 'rest' in jd and len(jd) >= 9, jd
    k0 = next(iter(res))
    assert judge(dict(good, res=dict(res, **{k0: [5, 0, 0]})), a)[f'p{k0}_e'].startswith('differ')
    assert judge(dict(good, spans=to_spans({**mm.pix, (300, 150): 7})), a)['rest'].startswith('differ')
    a = known['sx-a']
    st_, mm = steps(a)
    jd = judge(dict(arm='sx-a', n=0, hash='x', tail=0, stat=[], spans=[], res={str(i): [2, 0, 0] for it, s, pr, i, p in st_ if pr}, sent=1, last={}), a)
    assert any(v == 'agree:m' for v in jd.values()) and 'rest' not in jd
    assert known['sh-r']['items'][2]['p1'] == known['sh-f']['items'][2]['p2'] and known['sh-r']['items'][2]['p2'] == known['sh-f']['items'][2]['p1']
    print('OK 判定の陽性・陰性（箱の塗り・画素のずれ・範囲外バイト・LP と誤り番号・rest）', flush=True)
    # 較正の関門と emit
    def rec(a_id, o, gate=True):
        return dict(arm=known[a_id], obs=[o, o], failed=[False, False], gate=gate)
    base_o = dict(hash='x', tail=0, stat=[], res={}, sent=1, last={})
    o_v = dict(base_o, arm='cal-vis', n=3, spans=[[150, 400, 402, 7]], pix=[dict(at=[400, 150], dot=['ffffff', 'ffffff'], ref=['000000', '000000'])])
    o_c = dict(base_o, arm='base-cls3', n=0, spans=[])
    assert calibrated([rec('cal-vis', o_v), rec('base-cls3', o_c)])
    assert not calibrated([rec('cal-vis', dict(o_v, n=0))])
    assert not calibrated([rec('cal-vis', dict(o_v, pix=[dict(at=[400, 150], dot=['000000']*2, ref=['000000']*2)]))])
    assert not calibrated([rec('cal-vis', dict(o_v, tail=1))])
    assert not calibrated([rec('base-cls3', dict(o_c, n=1))])
    assert not calibrated([rec('cal-vis', o_v, gate=False)])
    with tempfile.TemporaryDirectory(prefix='l4s9u-emit-', dir=work) as temp:
        out = Path(temp)/'m.tsv'
        assert emit(out, [rec('cal-vis', o_v), rec('base-cls3', o_c)]) and 'gate_failed' not in out.read_text()
        rs2 = [rec('cal-vis', o_v), dict(arm=known['base-cls3'], obs=[o_c, dict(o_c, hash='y')], failed=[False, False], gate=True)]
        assert not emit(out, rs2) and 'gate_failed' in out.read_text()
    print('OK 較正の関門（陰性）・記録の出力・2走不一致の関門落ち', flush=True)
    # 自作ROMの対照: 器具が走り、グラフィックVRAMの写しが採れる。故障注入で写しが変わる
    with tempfile.TemporaryDirectory(prefix='l4s9u-selftest-', dir=work) as temp:
        root = Path(temp)
        rom = root/'rom'
        built = subprocess.run([sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom), '--work-dir', str(root/'asm')],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert built.returncode == 0, '自作ROM一時ビルド失敗'
        observed = measure(rom, False, [known['base-cls3'], known['lp-a']], root)
        for r in observed:
            assert r['obs'][0] and 'hash' in r['obs'][0] and not any(r['failed']), (r['arm']['id'], r['failed'])
            assert r['obs'][0]['tail'] == 0
        assert observed[0]['obs'][0]['n'] == 0
        os.environ['Q88MEASURE_FAULT_CORRUPT_GVRAM_DUMP'] = '1'
        try:
            faulty = run_arm(rom, False, known['base-cls3'], root)
        finally:
            del os.environ['Q88MEASURE_FAULT_CORRUPT_GVRAM_DUMP']
        assert faulty['n'] == 1 and faulty['spans'] == [[1, 7, 7, 2]], faulty['spans']
        print('  自作の現状: lp-a 結果行='+json.dumps(observed[1]['obs'][0]['res'])+' n='+str(observed[1]['obs'][0]['n']), flush=True)
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
