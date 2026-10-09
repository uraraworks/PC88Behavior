#!/usr/bin/env python3
"""l4-s9w: PAINT 文（領域の塗り・境界色・タイル塗り）と、塗りの速さ・作業領域（補助の腕）を測る器具。

画面本文は扱わない。採るのは次の数値・記号だけ。ここで「描いた」と言うのは、こちらの打ち込んだプログラムが描かせた画素だけ。
 (1) グラフィックVRAM 3 プレーンの全画素（ハーネス --gvram-dump）を (x,y,色) に復号したもの。連続した同色を (y,x0,x1,色) の区間に畳む。
     復号は l4_line_measure と同じ（80 バイト/ライン、MSB が左、B=1・R=2・G=4）。生バイトは採取後に消し、コミットしない。
 (2) こちらのプログラムが印字した結果行 `s9w<番号>:誤り,LP-X,LP-Y;`（テキストVRAM写しから）。
 (3) 制御ポートの最後の値。
 (4) 速さの腕だけ: プログラムが利用者領域の1バイトへ書いた開始の印(1)と終了の印(2)のフレーム番号（--mem-write-log）。差が所要フレーム。
 (5) --screenshot の PPM から、描いた画素（cal-vis だけ）。
事前登録は docs/notes/l4-s9w-paint-preregistration.md。
"""
import argparse
import csv
import itertools
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
import l4_gfx_measure as g
import l4_line_measure as lm
import l4_circle_measure as cm

WORK = kw.REPO.parent / 'tmp/s9w-work'
SENT = 's9wz'
PFX = 's9w'
W, H = lm.W, lm.H
SPAN_MAX = 24000
VISIBLE = (401, 150)
MARK_ADDR, MARK_HEX = cm.MARK_ADDR, cm.MARK_HEX
rnd, screen_has, in_box, num, low = lm.rnd, lm.screen_has, lm.in_box, lm.num, lm.low
csv.field_size_limit(1 << 30)     # 区間の多い腕の観測は 1 欄が 131072 字を超える
CAL_N = 110          # cal-vis: 10x11 の枠 38 画素 + 内部 8x9=72 画素（追補1で 16x11 から狭めた）


# ---------------------------------------------------------------- タイル（色モード: 1行=3バイト 青・赤・緑、白黒: 1行=1バイト。横8ドット、MSBが左）
def tile_bytes(rows):
    """rows: 各行 8 個の色(0〜7)。色モードの文字列(行ごとに B,R,G の3バイト)。"""
    out = bytearray()
    for row in rows:
        assert len(row) == 8
        for bit in (0, 1, 2):
            out.append(sum(((c >> bit) & 1) << (7-col) for col, c in enumerate(row)))
    return bytes(out)


def tile_px(data, mono, col, row, n):
    if mono:
        return 1 if (data[row] >> (7-col)) & 1 else 0
    b, r, gg = data[3*row:3*row+3]
    return ((b >> (7-col)) & 1) | (((r >> (7-col)) & 1) << 1) | (((gg >> (7-col)) & 1) << 2)


def tile_defs(name, data):
    """文字列変数 name に data を作る文（chr$(&hNN) を5個ずつ）。"""
    if not data:
        return [lm.text(f'{name}=""')]
    out = []
    for i in range(0, len(data), 5):
        chunk = '+'.join(f'chr$(&h{b:02x})' for b in data[i:i+5])
        out.append(lm.text(f'{name}={chunk}' if i == 0 else f'{name}={name}+{chunk}'))
    return out


# ---------------------------------------------------------------- 項目
def P(ctr, f=None, b=None, tile=None, bg=None, s1=False, box=None, probe=False, st='m', exp=None, raw=None):
    """PAINT 文。f＝領域色（None は省略、'' は末尾のコンマだけ、'"..."' は文字列リテラル＝タイル）、b＝境界色、
    tile＝タイルの文字列(bytes。文 t$ を別に作っておく)、bg＝バックグラウンドストリング(bytes。g$)。st＝画素の予測の強さ。"""
    return dict(op='P', ctr=ctr, f=f, b=b, tile=tile, bg=bg, s1=s1, box=box, probe=probe, st=st, exp=exp or {}, raw=raw)


def X(stmt, fn):
    """画素を作る文(ループなど)。fn(model) がモデルに同じ画素を描く。"""
    return dict(op='X', stmt=stmt, fn=fn)


def arm(aid, items, pix=None, group=None, wait=0, speed=False, prog=None, pre=None, sys_pre=None, guard=False):
    return dict(id=aid, items=items, pix=pix or [], group=group or aid.split('-')[0], wait=wait, speed=speed, prog=prog, pre=pre or [], sys_pre=sys_pre or [], guard=guard)


PRE = [lm.screen('0,0'), lm.cls(3)]
cell_xy, cell_box = lm.cell_xy, lm.cell_box


def LN(k, a, b, c=7, m=None, st=None):
    ox, oy = cell_xy(k)
    return lm.L((ox+a[0], oy+a[1]), (ox+b[0], oy+b[1]), c, m, st)


def FR(k, c=7, x0=0, y0=0, w=96, h=56):
    return LN(k, (x0, y0), (x0+w, y0+h), c, 'b')


def CI(k, ctr, r, c=7):
    ox, oy = cell_xy(k)
    return cm.C((ox+ctr[0], oy+ctr[1]), r, c)


def PSX(k, xy, c=7):
    ox, oy = cell_xy(k)
    return lm.pset(ox+xy[0], oy+xy[1], c)


def PP(k, xy, f=None, b=None, st='m', **kw_):
    ox, oy = cell_xy(k)
    return P((ox+xy[0], oy+xy[1]), f, b, box=cell_box(k), st=st, **kw_)


def cell_arm(aid, builders, wait=3000, pre_items=None, **kw_):
    assert len(builders) <= lm.CELL_COLS*lm.CELL_ROWS
    items = list(pre_items if pre_items is not None else PRE)
    for k, bf in enumerate(builders):
        items += bf(k)
    return arm(aid, items, wait=wait, **kw_)


def framed(at, f=5, b=7, extra=(), fc=7, st='m', fr=None, **kw_):
    """枠(fc)を描き、extra（k→項目）を描いてから at で塗る 1 セル。"""
    def fn(k):
        out = [FR(k, fc)] if fr is None else [fr(k)]
        for e in extra:
            r = e(k)
            out += r if isinstance(r, list) else [r]
        out.append(PP(k, at, f, b, st=st, **kw_))
        return out
    return fn


def seg(a, b, c=7, m=None):
    return lambda k: LN(k, a, b, c, m)


def box_(a, b, c=7):
    return lambda k: LN(k, a, b, c, 'b')


def bf_(a, b, c):
    return lambda k: LN(k, a, b, c, 'bf')


def circ(ctr, r, c=7):
    return lambda k: CI(k, ctr, r, c)


def pts_(pl, c=7):
    return lambda k: [PSX(k, p, c) for p in pl]


# ---------------------------------------------------------------- 腕
T_MAN1 = bytes([0x55, 0x33, 0x0f])
T_MAN2 = bytes([0x33, 0x33, 0xcc])
T_CHK = tile_bytes([[5, 0]*4, [0, 5]*4])
T_4 = tile_bytes([[1+(c+2*r) % 6 for c in range(8)] for r in range(4)])
T_3 = tile_bytes([[1+(3*c+r) % 7 for c in range(8)] for r in range(3)])
T_SOLID = tile_bytes([[5]*8])
T_BD = tile_bytes([[7, 5]*4])
T_6 = tile_bytes([[1, 2, 3, 4, 5, 6, 1, 2], [6, 5, 4, 3, 2, 1, 6, 5]])
T_Z1, T_Z2, T_Z3 = bytes(3), bytes(6), bytes(9)


def tcell(data, at=(22, 10), b=7, bg=None, dx=3, dy=1, w=44, h=18, f=None, st='w', extra=(), **kw_):
    """タイルの 1 セル: 枠(dx,dy,w,h)を描き、タイルで塗る。at は枠の左上からの相対。"""
    def fn(k):
        out = [FR(k, 7, dx, dy, w, h)]
        for e in extra:
            r = e(k)
            out += r if isinstance(r, list) else [r]
        if data is not None:
            out += tile_defs('t$', data)
        if bg is not None:
            out += tile_defs('g$', bg)
        out.append(PP(k, (dx+at[0], dy+at[1]), f, b, tile=data, bg=bg, st=st, **kw_))
        return out
    return fn


def comb_items(n, x0, y0, h=50):
    return [lm.L((x0, y0), (x0+2*n, y0+h+5), 7, 'b'),
            X(f'for i=1 to {n-1}:line({x0}+2*i,{y0+1})-({x0}+2*i,{y0+h}),7:next',
              lambda m, n=n, x0=x0, y0=y0, h=h: [m.line(lm.L((x0+2*i, y0+1), (x0+2*i, y0+h), 7)) for i in range(1, n)])]


def dots_items(x0, y0, w, h):
    """frame と、偶数行に 1 ドット置きの点線(0xAAAA)。"""
    return [lm.L((x0, y0), (x0+w, y0+h), 7, 'b'),
            X(f'for j={y0+2} to {y0+h-2} step 2:line({x0+2},j)-({x0+w-2},j),7,,&haaaa:next',
              lambda m: [m.line(lm.L((x0+2, j), (x0+w-2, j), 7, None, '&haaaa')) for j in range(y0+2, y0+h-1, 2)])]


def maze_items(x0, y0, w, rows):
    def draw(m):
        for i in range(1, rows):
            y = y0+2*i
            m.line(lm.L((x0+1+2*(i % 2 == 0), y), (x0+w-1-2*(i % 2), y), 7))
    return [lm.L((x0, y0), (x0+w, y0+2*rows), 7, 'b'),
            X(f'for i=1 to {rows-1}:y={y0}+2*i:line({x0+1}-2*(i mod 2=0),y)-({x0+w-1}-2*(i mod 2),y),7:next', draw)]


def arms():
    out = [arm('base-cls3', [lm.cls(3)]),
           arm('cal-vis', PRE + [lm.L((395, 145), (404, 155), 7, 'b'), P((401, 150), 4, 7)], pix=[VISIBLE])]
    # ---- 形(sh): 枠の中の図形。f=5 b=7
    obstacle3 = bf_((30, 20), (40, 30), 3)
    obstacle5 = bf_((30, 20), (40, 30), 5)
    out.append(cell_arm('sh-1', [
        framed((48, 28), st='s'),
        framed((1, 1), st='s'),
        framed((8, 8), extra=[box_((20, 14), (76, 42))]),
        framed((48, 28), extra=[box_((20, 14), (76, 42))]),
        framed((48, 28), extra=[circ((48, 28), 20)]),
        framed((4, 4), extra=[circ((48, 28), 20)]),
        framed((48, 28), extra=[circ((48, 28), 2)]),
        framed((48, 28), extra=[circ((48, 28), 1)]),
        framed((48, 28), extra=[circ((48, 28), 0)]),
        framed((48, 28), extra=[circ((48, 28), 40)]),
        framed((48, 34), extra=[seg((48, 6), (88, 50)), seg((88, 50), (8, 50)), seg((8, 50), (48, 6))]),
        framed((48, 40), extra=[seg((20, 10), (20, 46)), seg((20, 46), (76, 46)), seg((76, 46), (76, 10))]),
        framed((48, 46), extra=[circ((48, 28), 24), circ((48, 28), 12)]),
        framed((0, 0), st='m'),
        framed((48, 28), extra=[obstacle3]),
        framed((40, 28), extra=[box_((30, 20), (50, 36), 5)], st='w'),
        framed((48, 28), extra=[pts_([(30, 20), (31, 22), (60, 30), (47, 28)])]),
        framed((60, 28), extra=[bf_((1, 1), (47, 55), 5)], st='w')]))
    out.append(cell_arm('sh-2', [
        framed((35, 25), extra=[obstacle5], st='w'),
        framed((35, 25), extra=[obstacle3], st='w'),
        framed((48, 28), 7, 7, st='s'),
        framed((48, 28), 7, None, st='m'),
        lambda k: [FR(k, 7), PP(k, (48, 28), 5, 7), PP(k, (48, 28), 0, 7)],
        framed((48, 28), 0, None, st='m'),
        framed((48, 28), 4, None, fc=4, st='m'),
        lambda k: [FR(k, 7), PP(k, (48, 28), 5, 7), PP(k, (48, 28), 6, 7)],
        lambda k: [FR(k, 7), PP(k, (48, 28), 5, 7), PP(k, (48, 28), 6, 5)],
        lambda k: [FR(k, 5), bf_((20, 20), (40, 40), 5)(k), PP(k, (60, 28), 6, 5)],
        framed((20, 28), extra=[seg((48, 0), (48, 56))], st='s'),
        framed((20, 28), extra=[seg((0, 28), (96, 28))], st='s'),
        framed((20, 10), extra=[seg((48, 0), (48, 27)), seg((48, 29), (48, 56))]),
        framed((20, 10), extra=[seg((48, 0), (48, 26)), seg((48, 29), (48, 56))]),
        framed((20, 10), extra=[pts_([(48, y) for y in range(2, 56, 2)])]),
        framed((48, 28), extra=[box_((47, 27), (49, 29))], st='s'),
        framed((48, 28), extra=[box_((46, 26), (50, 30))], st='s'),
        framed((20, 28), extra=[seg((48, 1), (48, 55), 3)], st='m')]))
    # ---- 連結(cn): 4連結か8連結か、1ドット幅の通路
    gapA = [seg((0, 28), (48, 28)), seg((49, 29), (96, 29))]
    gapB = [seg((0, 29), (47, 29)), seg((48, 28), (96, 28))]
    chambers = lambda: [box_((4, 14), (40, 42)), box_((56, 14), (92, 42)), seg((40, 28), (56, 28), 0), seg((41, 27), (55, 27)), seg((41, 29), (55, 29))]
    chambersv = lambda: [box_((20, 4), (76, 24)), box_((20, 32), (76, 52)), seg((48, 24), (48, 32), 0), seg((47, 25), (47, 31)), seg((49, 25), (49, 31))]
    out.append(cell_arm('cn-1', [
        framed((10, 10), extra=[seg((0, 56), (56, 0))], st='w'),
        framed((10, 40), extra=[seg((0, 0), (56, 56))], st='w'),
        framed((10, 10), extra=[seg((0, 56), (96, 0))], st='w'),
        framed((10, 28), extra=[seg((30, 0), (60, 56))], st='w'),
        framed((10, 10), extra=gapA, st='w'),
        framed((10, 10), extra=gapB, st='w'),
        framed((20, 28), extra=[seg((48, 0), (48, 27)), seg((48, 29), (48, 56))], st='m'),
        framed((20, 28), extra=[seg((48, 0), (48, 26)), seg((48, 29), (48, 56))], st='m'),
        framed((21, 1), extra=[seg((20, 1), (75, 56)), seg((22, 1), (77, 56))], st='w'),
        framed((75, 1), extra=[seg((76, 1), (24, 53)), seg((74, 1), (22, 53))], st='w'),
        framed((20, 28), extra=chambers(), st='m'),
        framed((48, 12), extra=chambersv(), st='m'),
        framed((20, 28), extra=[box_((4, 14), (40, 42)), box_((56, 14), (92, 42)), seg((40, 27), (56, 27), 0), seg((40, 28), (56, 28), 0), seg((41, 26), (55, 26)), seg((41, 29), (55, 29))], st='m'),
        framed((48, 28), extra=[box_((47, 27), (49, 29))], st='s'),
        framed((48, 28), extra=[seg((1, 27), (95, 27)), seg((1, 29), (95, 29))], st='m'),
        framed((48, 20), extra=[seg((47, 1), (47, 55)), seg((49, 1), (49, 55))], st='m'),
        framed((20, 28), extra=[seg((2, 27), (40, 27)), seg((2, 29), (38, 29)), seg((38, 29), (38, 52)), seg((40, 27), (40, 52)), seg((38, 52), (40, 52))], st='m'),
        framed((48, 28), extra=[circ((48, 28), 4)], st='m')]))
    # ---- 境界色の判定(bd): 壁(wc)で左右に分けた枠(bc)。壁が境界とみなされれば左だけ塗られ、そうでなければ枠全体
    combos = list(itertools.product(range(1, 8), range(1, 8)))
    for n, chunk in enumerate((combos[:17], combos[17:33], combos[33:])):
        bl = []
        for wc, bc in chunk:
            bl.append(framed((20, 28), 5, bc, extra=[seg((48, 1), (48, 55), wc)], fc=bc, st='s' if wc == bc else 'w'))
        out.append(cell_arm(f'bd-{n+1}', bl))
    # ---- 画面の端・開いた領域(ed)・漏れ(lk)
    out.append(arm('ed-1', PRE + [P((100, 100), 5, 7)], wait=9000))
    edges = [((10, 100), (15, 100)), ((630, 100), (625, 100)), ((320, 8), (320, 10)), ((320, 192), (320, 190)),
             ((2, 2), (6, 3)), ((637, 2), (633, 3)), ((2, 197), (6, 196)), ((637, 197), (633, 196))]
    items = list(PRE)
    for ctr, st_ in edges:
        items += [cm.C(ctr, 30 if ctr[0] not in (2, 637) else 40, 7), P(st_, 5, 7, st='m')]
    out.append(arm('ed-2', items, wait=6000))
    tiny = [lm.L((0, 0), (4, 4), 7, 'b'), lm.L((635, 195), (639, 199), 7, 'b'), lm.L((8, 8), (20, 20), 7, 'b')]
    out.append(arm('ed-3', PRE + tiny + [P(c, 5, 7, probe=True, st='m') for c in
                                        [(-1, 10), (640, 10), (10, 200), (10, -1), (-5, -5), (1000, 1000), (32768, 10), (10, -32769)]]))
    out.append(arm('ed-4', PRE + tiny + [P((2, 2), 5, 7, probe=True), P((637, 197), 5, 7, probe=True), P((14.4, 14.6), 5, 7, probe=True, st='w'),
                                        P((14.5, 14.5), 6, 7, probe=True, st='w'), P((1, 1), 4, 7, s1=True, probe=True),
                                        P((0, 0), 5, 7, probe=True), P((4, 4), 5, 7, probe=True), P((-32768, 100), 5, 7, probe=True)]))
    out.append(arm('lk-1', PRE + [lm.L((0, 0), (639, 199), 7, 'b'), cm.C((320, 100), 60, 7), P((320, 100), 5, None)], wait=9000))
    # ---- 色・引数(co)。小さな枠(90,90)-(120,120)の中で塗る
    small = [lm.L((90, 90), (120, 120), 7, 'b')]
    fv = [(-1, 7), (8, 7), (255, 7), (0.4, 7), (0.5, 7), (1.5, 7), (6.5, 7), ('1e10', 7), ('"a"', 7), (2, 7), (3, 7)]
    out.append(arm('co-1', PRE + small + [P((100, 100), f, b, probe=True, st='m' if isinstance(f, int) else 'w') for f, b in fv]))
    bv = [(5, -1), (5, 8), (5, 255), (5, 0.4), (5, 7.5), (5, '1e10'), (5, '"a"'), (5, ''), (5, 6.5), (5, 7), (3, 0.4)]
    out.append(arm('co-2', PRE + small + [P((100, 100), f, b, probe=True, st='w') for f, b in bv]))
    # ---- LP・STEP(lp)
    out.append(arm('lp-a', PRE + small + [lm.pset(10, 10, 7), P((100, 100), 5, 7, probe=True), P((3, 3), 6, 7, s1=True, probe=True),
                                         P((-3, -3), 4, 7, s1=True, probe=True), P((900, 900), 5, 7, s1=True, probe=True),
                                         P((100, 100), 5, 7, probe=True), P((0, 0), 3, 7, s1=True, probe=True)]))
    # ---- 構文(sx)
    out.append(arm('sx-a', PRE + small + [syn(s) for s in SYN_A]))
    out.append(arm('sx-b', PRE + small + [syn(s) for s in SYN_B]))
    # ---- 白黒(mo)。カラー1ビットの面
    def mono_cells():
        return [framed((48, 28), 5, 7),
                framed((48, 28), 5, 7, fc=3, st='w'),
                framed((48, 28), 0, 7),
                lambda k: [FR(k, 7), PP(k, (48, 28), 5, 7), PP(k, (48, 28), 0, 7)],
                framed((48, 28), 5, 0, st='m'),
                tcell(bytes([0xaa, 0x55]), (30, 25), dx=0, dy=0, w=96, h=56),
                tcell(bytes([0xf0]), (30, 25), dx=0, dy=0, w=96, h=56),
                tcell(bytes([0x80, 0x40, 0x20]), (30, 25), dx=0, dy=0, w=96, h=56),
                framed((48, 28), None, None, st='m'),
                framed((48, 28), 1, None, st='w'),
                framed((48, 28), 7, 7, fc=5, st='w')]
    for tag, sa in (('0', '1,0,0,7'), ('1', '1,0,1,7')):
        out.append(cell_arm(f'mo-{tag}', mono_cells(), pre_items=[lm.screen(sa), lm.cls(3)]))
    # ---- タイル(tl)
    out.append(cell_arm('tl-1', [
        tcell(T_MAN1), tcell(T_MAN2), tcell(T_CHK), tcell(T_4), tcell(T_3), tcell(T_SOLID),
        tcell(T_MAN1+b'Z'), tcell(b'ab'), tcell(T_6), tcell(T_6+b'Q'), tcell(T_Z1), tcell(T_Z2), tcell(T_Z3),
        tcell(T_BD), tcell(T_4+b'zz'), lambda k: [FR(k, 7, 3, 1, 44, 18), PP(k, (25, 11), '""', 7, st='w')]]))
    ph = [(3, 1, 10, 5), (3, 1, 25, 12), (3, 1, 40, 17), (3, 1, 6, 16), (0, 0, 20, 9), (1, 2, 20, 9), (5, 3, 20, 9), (7, 1, 20, 9)]
    out.append(cell_arm('tl-2', [tcell(T_4, (sx, sy), dx=dx, dy=dy) for dx, dy, sx, sy in ph] +
                        [tcell(T_3, (sx, sy), dx=dx, dy=dy) for dx, dy, sx, sy in ph]))
    def tp(data, bg=None, b=7, first=False, st='w'):
        """枠の中でタイルを塗る 1 手(文字列の作り直しと塗り)。"""
        def fn(k):
            out_ = (tile_defs('t$', data) if data is not None else []) + (tile_defs('g$', bg) if bg is not None else [])
            return out_ + [PP(k, (25, 11), None, b, tile=data, bg=bg, st=st)]
        return fn

    def seq(*steps_):
        def fn(k):
            out_ = [FR(k, 7, 3, 1, 44, 18)]
            for s_ in steps_:
                out_ += s_(k)
            return out_
        return fn
    solid = lambda c: (lambda k: [PP(k, (25, 11), c, 7)])
    out.append(cell_arm('tl-3', [
        seq(tp(T_4), tp(T_3)),
        seq(tp(T_4), tp(T_3, bg=T_4)),
        seq(solid(5), tp(T_4)),
        seq(tp(T_4), solid(2)),
        tcell(T_4, b=None, st=None),
        tcell(T_4, bg=T_4, b=None, st=None),
        tcell(T_4, bg=bytes(3)),
        tcell(T_Z3, bg=T_MAN1),
        tcell(T_Z2, bg=bytes(3)),
        tcell(T_MAN1*3),
        tcell(T_MAN1*3, bg=T_MAN1),
        tcell(T_4, bg=b'a'),
        tcell(T_4, bg=T_4+T_4)]))
    # ---- 作業領域(ws): 櫛・点線格子・蛇行路。既定のスタック(512)と CLEAR ,,N の拡大
    def ws(aid, shapes, probes, stack=None, wait=15000, guard=False):
        items = list(PRE)
        for sh_ in shapes:
            items += sh_
        items += probes
        return arm(aid, items, wait=wait, sys_pre=[f'clear ,,{stack}'] if stack else [], guard=guard)
    combs = [(10, 2, 2), (20, 2, 66), (40, 2, 130)]
    out.append(ws('ws-1', [comb_items(n, 2, y) for n, x0, y in combs],
                  [P((3, y+3+50), 5, 7, probe=True, st='w', exp=dict(e=(0, 'w'))) for n, x0, y in combs]))
    combs2 = [(80, 2, 2), (160, 2, 66), (300, 2, 130)]
    for tag, stack in (('2', None), ('2b', 2048), ('2c', 16384)):
        out.append(ws(f'ws-{tag}', [comb_items(n, 2, y) for n, x0, y in combs2],
                      [P((3, y+3+50), 5, 7, probe=True, st='w', exp=dict(e=((7, 'w') if (n >= 160 and stack is None) else (0, 'w')))) for n, x0, y in combs2], stack))
    for tag, stack in (('3', None), ('3b', 8192)):
        out.append(ws(f'ws-{tag}', [dots_items(0, 0, 300, 80), maze_items(0, 100, 300, 40)],
                      [P((1, 1), 5, 7, probe=True, st='w'), P((1, 101), 6, 7, probe=True, st='w')], stack))
    # ---- 追補2: 作業領域が足りなくなる条件を探す腕
    def wsp(pts, errs):
        return [P(c, 5, 7, probe=True, st='w', exp=dict(e=(e, 'w'))) for c, e in zip(pts, errs)]
    cpts = [(3, y+3+50) for n, x0, y in combs]
    for tag, stack, errs in (('6a', 16, (7, 7, 7)), ('6b', 64, (0, 0, 7)), ('6c', 128, (0, 0, 0)), ('6d', 256, (0, 0, 0))):
        out.append(ws(f'ws-{tag}', [comb_items(n, 2, y) for n, x0, y in combs], wsp(cpts, errs), stack, guard=True))
    out.append(ws('ws-6e', [dots_items(0, 0, 300, 80), maze_items(0, 100, 300, 40)], wsp([(1, 1), (1, 101)], (7, 7)), 64, guard=True))
    lat = [dots_items(0, 0, 100, 40), dots_items(110, 0, 200, 80), dots_items(0, 100, 639, 99)]
    for tag, stack, errs in (('4', None, (0, 0, 7)), ('4b', 4096, (0, 0, 0))):
        out.append(ws(f'ws-{tag}', lat, wsp([(1, 1), (111, 1), (1, 101)], errs), stack, wait=150000, guard=True))
    lat2 = [dots_items(0, 0, 100, 40), dots_items(110, 0, 200, 80), comb_items(80, 2, 100)]
    for tag, stack, errs in (('7a', 32000, (0, 0, 0)), ('7b', 60000, (7, 7, 7))):
        out.append(ws(f'ws-{tag}', lat2, wsp([(1, 1), (111, 1), (3, 153)], errs), stack, wait=30000, guard=True))
    # ---- 速さ(sp)。補助の腕
    out += speed_arms()
    return out


SYN = {'paint': (2, 'm'), 'paint(100,100)': (0, 'm'), 'paint(100,100),7': (0, 'm'), 'paint (100,100),7': (0, 'm'),
       'paint(100,100),7,7': (0, 'm'), 'paint(100,100),,7': (0, 'm'), 'paint(100,100),7,': (22, 'w'), 'paint(100,100),': (22, 'w'),
       'paint(100,100),,': None, 'paint 100,100': (2, 'm'), 'paint(100),7': (2, 'm'), 'paint(100,100) 7': (2, 'm'),
       'paint(100,100);7': (2, 'm'), 'paint step(1,1),7': (0, 'm'), 'paint-(5,5)': (2, 'm'), 'paint(100,100),7,7,7': None,
       'paint(100,100),7 7': None, 'paint(100,100),7,7,': None, 'paint(100,100),,7,': None, 'paint(100,100),,,': None,
       'paint(100,100),"abc",7': (0, 'm'), 'paint(100,100),"ab",7': (5, 'm'), 'paint(100,100),"abc"': None,
       'paint(100,100),"abc",,"abc"': None, 'paint(100,100),"abc",7,"abc"': None, 'paint(100,100),"abc",7,': None}
SYN_A = ['paint', 'paint(100,100)', 'paint(100,100),7', 'paint (100,100),7', 'paint(100,100),7,7', 'paint(100,100),,7', 'paint(100,100),7,',
         'paint(100,100),', 'paint(100,100),,', 'paint 100,100', 'paint(100),7', 'paint(100,100) 7', 'paint(100,100);7']
SYN_B = ['paint step(1,1),7', 'paint-(5,5)', 'paint(100,100),7,7,7', 'paint(100,100),7 7', 'paint(100,100),7,7,', 'paint(100,100),,7,',
         'paint(100,100),,,', 'paint(100,100),"abc",7', 'paint(100,100),"ab",7', 'paint(100,100),"abc"', 'paint(100,100),"abc",,"abc"',
         'paint(100,100),"abc",7,"abc"', 'paint(100,100),"abc",7,']
assert set(SYN_A) | set(SYN_B) == set(SYN)


def syn(s):
    return P(None, raw=s, probe=True, exp=dict(e=SYN[s]) if SYN[s] else {})


def speed_arms():
    """所要フレーム数を測る補助の腕。pre は計時の前に実行する準備、prog が計時される。"""
    ops = [('nop', [], []),
           ('bf1', [], ['line(0,0)-(639,199),7,bf']),
           ('ps', [], ['for i=0 to 599:pset(i,100),7:next']),
           ('full', [], ['paint(100,100),7']),
           ('circ', ['circle(320,100),90,7'], ['paint(320,100),5,7']),
           ('box', ['line(0,0)-(639,199),7,b'], ['paint(320,100),5,7']),
           ('comb', ['line(2,2)-(162,57),7,b', 'for i=1 to 79:line(2+2*i,3)-(2+2*i,52),7:next'], ['paint(3,55),5,7']),
           ('maze', ['line(0,0)-(300,80),7,b', 'for i=1 to 39:y=2*i:line(1-2*(i mod 2=0),y)-(299-2*(i mod 2),y),7:next'], ['paint(1,1),5,7']),
           ('tile', ['line(0,0)-(639,199),7,b', 't$=chr$(&h55)+chr$(&h33)+chr$(&h0f)'], ['paint(320,100),t$,7'])]
    return [arm(f'sp-{tag}', [], speed=True, prog=lines, pre=pre, wait=16000 if tag in ('full', 'box', 'tile', 'circ', 'maze', 'comb') else 6000)
            for tag, pre, lines in ops]


# ---------------------------------------------------------------- 予測のモデル
RULES = {'base': {}, 'conn8': dict(conn8=True), 'stopfill': dict(stopfill=True), 'b-subset': dict(border='subset'),
         'b-any': dict(border='any'), 'b-superset': dict(border='superset'), 'tile-start': dict(phase='start'),
         'tile-region': dict(phase='region')}


class Model(cm.Model):
    def __init__(self, rule=None):
        super().__init__()
        self.rule = rule or {}

    def draw_set(self, p1, p2, style=None):
        """線の画素。l4-s9u で確定済みの規則（和が主軸の差以上。cm.LINE_RULE）を使う（事前登録時の器具は lm.PRIMARY=「超える」で、cn-1 の2腕が外れた。結果ノート参照）。"""
        pts = lm.line_pts(p1, p2, **cm.LINE_RULE)
        if style is not None:
            if pts[0] != p1 and pts[-1] == p1:
                pts = pts[::-1]
            pts = [p for k, p in enumerate(pts) if (style >> (15-k % 16)) & 1]
        return pts

    def cv(self, c):
        """画面モードに応じた画素値（白黒は 0/1<<ページ）。"""
        if self.mono:
            return (1 << self.apage) if c else 0
        return c

    def is_border(self, p, bc, fillv):
        v = self.get(p)
        mode = self.rule.get('border', 'exact')
        if mode == 'exact':
            r = v == bc
        elif mode == 'subset':
            r = bc != 0 and (v & bc) == bc
        elif mode == 'any':
            r = (v & bc) != 0
        else:
            r = v != 0 and (v & ~bc) == 0
        return r or (bool(self.rule.get('stopfill')) and v == fillv)

    def flood(self, a, bc, fillv):
        if self.is_border(a, bc, fillv):
            return []
        nb = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        if self.rule.get('conn8'):
            nb += [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        seen = {a}
        st = [a]
        while st:
            x, y = st.pop()
            for dx, dy in nb:
                q = (x+dx, y+dy)
                if q not in seen and screen_has(q) and not self.is_border(q, bc, fillv):
                    seen.add(q)
                    st.append(q)
        return sorted(seen)

    def paint(self, it):
        """返り値 dict(e=(誤り,強さ)|None, lp=(座標,強さ)|None, px=強さ|None)。px は画素の予測の強さ（None は予測なし）。"""
        ex = it['exp']
        if it['raw'] is not None:
            return dict(e=ex.get('e'), lp=None, px=None)
        bad = lambda v: not -32768 <= rnd(v) <= 32767
        x, y = it['ctr']
        if bad(x) or bad(y):
            return dict(e=(6, 'm'), lp=(self.lp, 'w'), px='m')
        a = (rnd(x), rnd(y))
        if it['s1']:
            a = (self.lp[0]+a[0], self.lp[1]+a[1])
        self.lp = a
        lp_ok = (a, 'w')
        pst = it['st']
        err = lambda e, s: dict(e=(e, s), lp=lp_ok, px=s)
        free = dict(e=ex.get('e'), lp=lp_ok, px=None)
        if ex.get('e') and ex['e'][0] != 0:
            return free                            # 作業領域の誤りなど、画素を予測しない腕
        if not screen_has(a):
            return err(5, 'm')
        f, b = it['f'], it['b']
        tile = it['tile']
        if tile is None and isinstance(f, str) and f.startswith('"'):
            tile = f[1:-1].encode()
        elif tile is None and f == '':
            return err(22, 'w')
        fill = None
        if tile is None:
            if f is None:
                fill = self.fg
            elif isinstance(f, str):
                if f == '1e10':
                    return err(6, 'w')
                fill = rnd(float(f))
            else:
                fill = rnd(f)
                if not float(f).is_integer():
                    pst = 'w'
            if not 0 <= fill <= 7:
                return err(5, 'm')
        if b == '':
            return err(22, 'w')
        bcol = None
        if isinstance(b, str):
            if b == '"a"':
                return err(13, 'w')
            if b == '1e10':
                return err(6, 'w')
            b = float(b)
        if b is None:
            bcol = fill                                        # 省略時は領域色
        else:
            bcol = rnd(b)
            if not 0 <= bcol <= 7:
                return err(5, 'm')
            if not float(b).is_integer():
                pst = 'w'
        if tile is not None:
            mono = self.mono
            if (not mono and len(tile) < 3) or (mono and len(tile) < 1):
                return err(5, 'm' if not mono else 'w')
            unit = 1 if mono else 3
            bgpat = (it['bg'] or bytes(unit))[:unit]
            if len(bgpat) < unit:
                return dict(e=None, lp=lp_ok, px=None)
            n = len(tile)//unit
            rows = [tile[unit*r:unit*r+unit] for r in range(n)]
            run = best = 0
            for r in rows:
                run = run+1 if r == bgpat else 0
                best = max(best, run)
            if best >= 3:
                return err(5, 'w')
            if bcol is None:
                return dict(e=(0, 'w'), lp=lp_ok, px=None)
        fillv = None if fill is None else self.cv(fill)
        region = self.flood(a, self.cv(bcol), fillv)
        if tile is None:
            for p in region:
                self.put(p, fill)
        else:
            ph = self.rule.get('phase', 'abs')
            if ph == 'start':
                xo, yo = a
            elif ph == 'region':
                xo, yo = min(p[0] for p in region), min(p[1] for p in region)
            else:
                xo = yo = 0
            for p in region:
                self.put(p, tile_px(tile, self.mono, (p[0]-xo) % 8, (p[1]-yo) % n, n))
        return dict(e=(0, 'm' if tile is None else 'w'), lp=lp_ok, px=pst)


def stmt_of(it):
    if it['op'] == 'P':
        if it['raw'] is not None:
            return it['raw']
        s = 'paint' + (' step' if it['s1'] else '') + f"({num(it['ctr'][0])},{num(it['ctr'][1])})"
        f = 't$' if it['tile'] is not None else it['f']
        gg = 'g$' if it['bg'] is not None else None
        fields = [f, it['b'], gg]
        last = max([i for i, v in enumerate(fields) if v is not None], default=-1)
        if last >= 0:
            s += ',' + ','.join('' if v is None else num(v) for v in fields[:last+1])
        return s
    if it['op'] == 'X':
        return it['stmt']
    return cm.stmt_of(it)


def steps(a, rule=None):
    m = Model(rule)
    out = []
    for i, it in enumerate(a['items']):
        pred = {}
        op = it['op']
        pr = False
        if op == 'P':
            pred = m.paint(it)
            pr = bool(it['probe'])
        elif op == 'C':
            pred = m.circle(it)
        elif op == 'L':
            pred = m.line(it)
        elif op == 'X':
            if it['fn']:
                it['fn'](m)
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
    if a['speed']:
        lines = {5: 'clear ,49151', 6: 'on error goto 900', 7: 'n=0:e=0', 8: 'cls', 10: 'screen 0,0:cls 3'}
        n = 11
        for s in a['pre']:
            lines[n] = s; n += 1
        lines[20] = f'poke {MARK_ADDR},1'
        assert n < 20
        n = 30
        for s in a['prog']:
            lines[n] = s; n += 10
        lines[n] = f'poke {MARK_ADDR},2'; n += 10
        lines[n] = f'print "{PFX}0:";n;",";e;",0;"'; n += 10
        lines[n] = f'print "{SENT}";'; n += 10
        lines[n] = f'goto {n}'
        lines[900] = 'e=err:n=n+1:resume next'
        assert n < 900
    else:
        st, _ = steps(a)
        lines = {2: 'on error goto 900'} if a.get('guard') else {}
        n0 = 3
        for s in a['sys_pre']:
            lines[n0] = s; n0 += 1
        lines.update({5: 'on error goto 900', 6: 'cls'})
        n = 10
        cur = ''
        for it, stmt, pr, i, pred in st:
            if pr:
                if cur:
                    lines[n] = cur; n += 10; cur = ''
                lines[n] = f'e=0:{stmt}:g=e'; n += 10
                lines[n] = 'e=0:x=point(0):y=point(1)'; n += 10
                lines[n] = f'print "{PFX}{i}:";g;",";x;",";y;";"'; n += 10
            else:
                if cur and len(f'{n} {cur}:{stmt}') > 76:
                    lines[n] = cur; n += 10; cur = ''
                cur = f'{cur}:{stmt}' if cur else stmt
        if cur:
            lines[n] = cur; n += 10
        lines[n] = f'print "{SENT}";'; n += 10
        lines[n] = f'goto {n}'
        lines[900] = 'e=err:resume next'
        assert n < 900, (a['id'], n)
    assert all(len(f'{k} {s}') < 80 for k, s in lines.items()), [f'{k} {s}' for k, s in lines.items() if len(f'{k} {s}') >= 80]
    assert all(s.isascii() and s == s.lower() and '@' not in s for s in lines.values()), lines
    return lines


def plan(a):
    return ['new'] + [f'{n} {s}' for n, s in sorted(program_lines(a).items())] + ['cls', ('window',), 'run', ('capture', 'all')]


# ---------------------------------------------------------------- 写しの解析と走らせる
def parse_results(vram):
    if len(vram) != 3000:
        raise ValueError('画面写しの長さが不正')
    joined = b''.join(bytes(vram[r*120:r*120+80]) for r in range(25))
    res = {}
    for m in re.finditer(rb's9w(\d+):([ \x20-\x7e]*?);', joined):
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


def analyze(a, gv, vram, iolog_text, window, img=None, memlog=None):
    obs = dict(arm=a['id'])
    pix, tail, stat = lm.decode_all(gv)
    obs['n'] = len(pix)
    obs['hash'] = lm.pix_hash(pix)
    obs['tail'] = tail
    obs['stat'] = stat
    spans = lm.to_spans(pix)
    obs['spans'] = spans if len(spans) <= SPAN_MAX else None
    res, sent = parse_results(vram)
    obs['res'] = {str(k): v for k, v in sorted(res.items())}
    obs['sent'] = sent
    obs['last'] = g.events(iolog_text, window)['last']
    if a['pix'] and img is not None:
        obs['pix'] = g.pix_stat(img, a['pix'])
    if a['speed']:
        obs['marks'] = cm.marks_summary(cm.parse_marks(memlog or ''))
    return obs


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
    ppm, iolog, vdump, gdump, mlog = work/'shot.ppm', work/'port.txt', work/'vram.bin', work/'gvram.bin', work/'mem.txt'
    args += ['--vram-dump', str(vdump), '--vram-dump-at', str(cap), '--gvram-dump', str(gdump), '--gvram-dump-at', str(cap),
             '--io-log', str(iolog), '--io-log-from-frame', str(window), '--frames', str(cap+100)]
    if a['pix']:
        args += ['--screenshot', str(ppm)]
    if a['speed']:
        args += ['--mem-write-log', str(mlog), '--mem-write-range', f'{MARK_HEX}-{MARK_HEX}', '--mem-write-from-frame', str(window)]
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ, M6FH_LONG_TYPING='1'))
        if proc.returncode or b'untypable' in proc.stderr.lower() or '打てない'.encode() in proc.stderr:
            raise RuntimeError('測定器の実行または打鍵に失敗')
        img = cp.read_ppm(ppm) if a['pix'] else None
        memlog = mlog.read_text(encoding='utf-8', errors='replace') if a['speed'] else None
        return analyze(a, gdump.read_bytes(), vdump.read_bytes(), iolog.read_text(encoding='utf-8', errors='replace'), window, img, memlog)
    finally:
        for p in (ppm, iolog, vdump, gdump, mlog):
            Path(p).unlink(missing_ok=True)
            Path(str(p)+'.info.txt').unlink(missing_ok=True)


def n_probes(a):
    if a['speed']:
        return 1
    return sum(1 for s in steps(a)[0] if s[2])


def valid(obs, a):
    if not isinstance(obs, dict) or obs.get('arm') != a['id'] or 'hash' not in obs:
        return False
    if a['speed']:
        mk = obs.get('marks') or {}
        if not (mk.get('n1') == 1 and mk.get('n2') == 1 and mk.get('frames') is not None and mk['frames'] >= 0):
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
def box_groups(st):
    """箱ごとの (添字の列, 強さ|None)。None は箱内に予測のない塗りがあること。"""
    groups = {}
    for it, stmt, pr, i, pred in st:
        if it['op'] == 'P' and it['raw'] is None and it['box'] is not None:
            groups.setdefault(it['box'], []).append(pred.get('px'))
    out = {}
    for bx, ss in groups.items():
        out[bx] = None if any(s is None for s in ss) else low(*ss)
    return out


def judge(obs, a):
    st, m = steps(a)
    res = {}

    def put(name, got, want, strength):
        res[name] = ('agree:' if got == want else 'differ:') + strength

    r = obs['res']
    for it, stmt, pr, i, pred in st:
        if not pr or it['op'] != 'P':
            continue
        vals = r.get(str(i))
        if vals is None:
            continue
        if pred.get('e') is not None:
            put(f'p{i}_e', vals[0], pred['e'][0], pred['e'][1])
        if pred.get('lp') is not None and pred['lp'][0] is not None:
            put(f'p{i}_lp', tuple(vals[1:3]), pred['lp'][0], pred['lp'][1])
    if a['speed']:
        return res
    if a['id'] == 'base-cls3':
        put('empty', obs['n'], 0, 'm')
        return res
    if a['id'] == 'cal-vis':
        return res
    put('tail', obs['tail'], 0, 's')
    op = lm.obs_pix(obs)
    ps0 = [(it, pred) for it, stmt, pr, i, pred in st if it['op'] == 'P']
    if op is None:
        if ps0 and not any(it['raw'] is not None for it, _ in ps0) and all(p.get('px') is not None for _, p in ps0) and not m.base:
            put('hash', obs['hash'], lm.pix_hash(m.pix), low(*[p['px'] for _, p in ps0]))      # 区間が多すぎて持たない腕は、全画素のハッシュで比べる
        return res
    groups = box_groups(st)
    for bx, sst in groups.items():
        if sst is None:
            continue
        want = {p: c for p, c in m.pix.items() if in_box(p, bx)}
        got = {p: c for p, c in op.items() if in_box(p, bx)}
        put(f'b{bx[0]}_{bx[1]}_px', got, want, sst)
    ps = [(it, pred) for it, stmt, pr, i, pred in st if it['op'] == 'P']
    has_raw = any(it['raw'] is not None for it, _ in ps)
    free = [pred for it, pred in ps if it['box'] is None]
    if not has_raw and not m.base and all(p.get('px') is not None for it, p in ps) and not any(s is None for s in groups.values()):
        strength = low(*[p['px'] for p in free]) if free else 'm'
        want = {p: c for p, c in m.pix.items() if not any(in_box(p, b) for b in groups)}
        got = {p: c for p, c in op.items() if not any(in_box(p, b) for b in groups)}
        put('rest', got, want, strength)
    return res


def cand_report(obs, a):
    """記述: 箱ごとに、観測と一致する候補の規則（的中数には数えない）。{候補: [一致した箱の数, 箱の数]}"""
    op = lm.obs_pix(obs)
    if op is None:
        return {}
    out = {}
    for name, rule in RULES.items():
        _, mm = steps(a, rule)
        groups = box_groups(steps(a, rule)[0])
        hit = tot = 0
        for bx, sst in groups.items():
            if sst is None:
                continue
            tot += 1
            want = {p: c for p, c in mm.pix.items() if in_box(p, bx)}
            got = {p: c for p, c in op.items() if in_box(p, bx)}
            hit += want == got
        out[name] = [hit, tot]
    return out


def calibrated(records):
    by = {r['arm']['id']: r for r in records}
    good = True
    if 'cal-vis' in by:
        r = by['cal-vis']
        o = r['obs'][0] if r['obs'] else {}
        good = good and bool(r['gate'] and o and o['n'] == CAL_N and o['tail'] == 0)
        if o and o.get('pix'):
            good = good and o['pix'][0]['dot'] != o['pix'][0]['ref']
    if 'base-cls3' in by:
        r = by['base-cls3']
        good = good and bool(r['gate'] and r['obs'][0] and r['obs'][0]['n'] == 0)
    return good


def emit(path, records, strict=True):
    known = {a['id']: a for a in arms()}
    for r in records:
        r['gate'] = (r['gate'] and r['arm']['id'] in known and plan(r['arm']) == plan(known[r['arm']['id']]) and len(r['obs']) == 2
                     and all(valid(o, r['arm']) for o in r['obs']) and r['obs'][0] == r['obs'][1])
    cal = calibrated(records) if strict else True
    rows = [(r['arm']['id'], i+1, json.dumps(plan(r['arm'])), json.dumps(r['obs'][i]),
             'pass' if cal and r['gate'] else 'gate_failed',
             json.dumps(judge(r['obs'][0], r['arm'])) if cal and r['gate'] else 'gate_failed',
             int(r['failed'][i])) for r in records for i in range(2)]
    if cal:
        rows.append(('_group', 1, '[]', '{}', 'pass', '{}', 0))
    lm.write_tsv(path, ['arm', 'repeat', 'plan', 'observation', 'gate', 'prediction_judgement', 'failed'], rows)
    return cal and bool(records) and all(r['gate'] for r in records)


def speed_report(measured):
    out = []
    with Path(measured).open(encoding='utf-8', newline='') as stream:
        for r in csv.DictReader(stream, delimiter='\t'):
            if r['repeat'] != '1' or not r['arm'].startswith('sp-'):
                continue
            o = json.loads(r['observation'])
            if o:
                out.append(f"{r['arm']} frames={o['marks']['frames']} n={o['n']} hash={o['hash']} res={o['res']}")
    return '\n'.join(out)


def report(measured):
    arms_by = {a['id']: a for a in arms()}
    with measured.open(encoding='utf-8', newline='') as stream:
        rows = [r for r in csv.DictReader(stream, delimiter='\t') if r['repeat'] == '1']
    lines = []
    for r in rows:
        if r['arm'] == '_group':
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
        lines.append(f"  n={o['n']} hash={o['hash']} tail={o['tail']} res={o['res']} last={o['last']}" + (f" marks={o['marks']}" if 'marks' in o else ''))
        if o.get('pix'):
            lines.append(f"  pix={o['pix']}")
        a = arms_by.get(r['arm'])
        if a and o.get('spans') is not None and not a['speed'] and o['n']:
            cr = cand_report(o, a)
            if cr:
                lines.append('  cand=' + json.dumps(cr))
    return '\n'.join(lines)


def tally(measured):
    """判定項目の強さ別の的中数と外れの一覧。"""
    cnt = {}
    miss = []
    with Path(measured).open(encoding='utf-8', newline='') as stream:
        for r in csv.DictReader(stream, delimiter='\t'):
            if r['repeat'] != '1' or r['arm'] == '_group' or r['gate'] != 'pass':
                continue
            for k, v in json.loads(r['prediction_judgement']).items():
                ok_, s = v.split(':')
                c = cnt.setdefault(s, [0, 0])
                c[1] += 1
                c[0] += ok_ == 'agree'
                if ok_ == 'differ':
                    miss.append(f"{r['arm']}.{k}:{s}")
    return cnt, miss


def describe():
    out = []
    for a in arms():
        if a['speed']:
            pre = ' / '.join(a['pre'])
            out.append(f"- `{a['id']}` (速さ, 待ち+{a['wait']}): " + (f'準備 {pre} → ' if pre else '') + (' / '.join(a['prog']) if a['prog'] else '(空)'))
            continue
        st, m = steps(a)
        prog = ' / '.join(s[1] for s in st if s[1])
        sp = f"[{'; '.join(a['sys_pre'])}] " if a['sys_pre'] else ''
        out.append(f"- `{a['id']}` ({n_probes(a)}印字{', 待ち+%d' % a['wait'] if a['wait'] else ''}): {sp}{prog}")
    return '\n'.join(out)


# ---------------------------------------------------------------- 自己検査
def selftest(work=None):
    if work is not None:
        work.mkdir(parents=True, exist_ok=True)
    known = {a['id']: a for a in arms()}
    assert len(known) == len(arms())
    for a in known.values():
        program_lines(a)
        plan(a)
    # 箱: 箱どうしは重ならない
    for a in known.values():
        bxs = sorted({it['box'] for it in a['items'] if it['op'] == 'P' and it['box']})
        assert all(b1[2] < b2[0] or b2[2] < b1[0] or b1[3] < b2[1] or b2[3] < b1[1] for i, b1 in enumerate(bxs) for b2 in bxs[:i]), a['id']
    # タイルの符号化と復号
    assert tile_bytes([[1, 2, 3, 4, 5, 6, 7, 0]]) == bytes([0b10101010, 0b01100110, 0b00011110])
    assert [tile_px(tile_bytes([[1, 2, 3, 4, 5, 6, 7, 0]]), False, c, 0, 1) for c in range(8)] == [1, 2, 3, 4, 5, 6, 7, 0]
    assert tile_px(bytes([0x80, 0x01]), True, 0, 0, 2) == 1 and tile_px(bytes([0x80, 0x01]), True, 7, 1, 2) == 1 and tile_px(bytes([0x80, 0x01]), True, 0, 1, 2) == 0
    assert [stmt_of(t) for t in tile_defs('t$', bytes(range(7)))] == ['t$=chr$(&h00)+chr$(&h01)+chr$(&h02)+chr$(&h03)+chr$(&h04)', 't$=t$+chr$(&h05)+chr$(&h06)']
    # 文の組み立て
    assert stmt_of(P((1, 2), 5, 7)) == 'paint(1,2),5,7' and stmt_of(P((1, 2))) == 'paint(1,2)' and stmt_of(P((1, 2), None, 7)) == 'paint(1,2),,7'
    assert stmt_of(P((1, 2), 5, '')) == 'paint(1,2),5,' and stmt_of(P((1, 2), '')) == 'paint(1,2),' and stmt_of(P((1, 2), s1=True, f=3)) == 'paint step(1,2),3'
    assert stmt_of(P((1, 2), None, 7, tile=b'abc', bg=b'xyz')) == 'paint(1,2),t$,7,g$'
    # 塗りの規則: 手計算
    def run(items, **rule):
        m = Model(rule)
        preds = []
        for it in items:
            op = it['op']
            if op == 'P':
                preds.append(m.paint(it))
            elif op == 'L':
                m.line(it)
            elif op == 'pset':
                m.pset(it['x'], it['y'], it['c'])
        return m, preds
    box5 = lm.L((10, 10), (14, 14), 7, 'b')
    m, pr = run([box5, P((12, 12), 5, 7)])
    assert len(m.pix) == 16+9 and all(m.pix[(x, y)] == 5 for x in range(11, 14) for y in range(11, 14)) and pr[0]['e'] == (0, 'm') and m.lp == (12, 12)
    m, pr = run([box5, P((10, 10), 5, 7)])                                   # 境界上は何もしない
    assert len(m.pix) == 16 and pr[0]['e'] == (0, 'm')
    m, pr = run([box5, P((12, 12), 5)])                                      # 境界色省略=領域色 5 → 枠(7)は境界でなく外へ漏れて画面全体
    assert len(m.pix) == W*H and all(c == 5 for c in m.pix.values())
    m, pr = run([box5, P((12, 12), 7)])                                      # 領域色 7・省略 → 枠と同じで内側だけ
    assert len(m.pix) == 16+9
    m, pr = run([lm.L((0, 8), (8, 0), 7), P((1, 1), 5, 7)])                  # 斜めの壁は 4連結では越えられない（画面の端と壁で閉じた三角形 36 画素 + 壁 9 画素）
    assert len(m.pix) == 36+9 and all(m.pix[(x, 8-x)] == 7 for x in range(9))
    m8, _ = run([lm.L((0, 8), (8, 0), 7), P((1, 1), 5, 7)], conn8=True)      # 8連結なら壁をすり抜けて画面全体
    assert len(m8.pix) == W*H and m8.pix[(4, 4)] == 7 and m8.pix[(3, 3)] == 5
    m, pr = run([P((-1, 5), 5, 7)]); assert pr[0]['e'] == (5, 'm') and m.lp == (-1, 5) and not m.pix
    m, pr = run([P((32768, 5), 5, 7)]); assert pr[0]['e'] == (6, 'm') and m.lp == (0, 0)
    m, pr = run([box5, P((12, 12), 8, 7)]); assert pr[0]['e'] == (5, 'm') and len(m.pix) == 16
    m, pr = run([box5, P((12, 12), 5, '"a"')]); assert pr[0]['e'][0] == 13
    m, pr = run([box5, P((12, 12), '""', 7)]); assert pr[0]['e'] == (5, 'm') and len(m.pix) == 16
    m, pr = run([box5, P((12, 12), 5, 7), P((12, 12), 0, 7)]); assert len(m.pix) == 16        # 色 0 は消す
    m, pr = run([box5, P((12, 12), 0)]); assert len(m.pix) == 16                                 # 領域色 0・省略 → 開始点が境界色 0 なので何もしない
    # タイル: 絶対位相、2 行のチェッカ
    chk = tile_bytes([[5, 0]*4, [0, 5]*4])
    m, pr = run([box5, P((13, 12), None, 7, tile=chk)])
    assert m.pix[(11, 11)] == 5 and (12, 11) not in m.pix and (11, 12) not in m.pix and m.pix[(12, 12)] == 5      # x%2==y%2 のとき 5（(11,11): 列3,行1 → 偶数列が5 の行0 ではない… 下で検算）
    assert tile_px(chk, False, 3, 1, 2) == 5 and tile_px(chk, False, 4, 0, 2) == 5 and tile_px(chk, False, 4, 1, 2) == 0
    ms, _ = run([box5, P((13, 12), None, 7, tile=chk)], phase='start')
    assert ms.pix != m.pix and len(ms.pix) > 0
    m, pr = run([box5, P((12, 12), None, 7, tile=b'ab')]); assert pr[0]['e'] == (5, 'm')
    m, pr = run([box5, P((12, 12), None, 7, tile=bytes(9))]); assert pr[0]['e'] == (5, 'w')              # 背景(0)の行が3回連続
    m, pr = run([box5, P((12, 12), None, 7, tile=bytes(6))]); assert pr[0]['e'] == (0, 'w')
    m, pr = run([box5, P((12, 12), None, 7, tile=bytes(9), bg=T_MAN1)]); assert pr[0]['e'] == (0, 'w')
    m, pr = run([box5, P((12, 12), None, 7, tile=T_MAN1*3, bg=T_MAN1)]); assert pr[0]['e'] == (5, 'w')
    m, pr = run([box5, P((12, 12), None, None, tile=T_MAN1)]); assert pr[0]['px'] is None
    # 境界色の候補は壁の色で割れる: 壁 7・境界 3 → exact は漏れ、subset は壁
    wall = [lm.L((0, 0), (8, 0), 3), lm.L((0, 8), (8, 8), 3), lm.L((0, 0), (0, 8), 3), lm.L((8, 0), (8, 8), 3), lm.L((4, 1), (4, 7), 7)]
    me, _ = run(wall+[P((2, 4), 5, 3)])
    ms_, _ = run(wall+[P((2, 4), 5, 3)], border='subset')
    assert len(me.pix) == 32+49 and me.pix[(4, 4)] == 5 and len(ms_.pix) == 32+21+7 and ms_.pix[(4, 4)] == 7 and (6, 4) not in ms_.pix
    ring = [lm.L((0, 0), (12, 12), 7, 'b'), lm.L((3, 3), (9, 9), 5, 'b'), P((1, 1), 5, 7)]                 # 領域色の輪の中の空き
    mf, _ = run(ring)
    mp, _ = run(ring, stopfill=True)
    assert (6, 6) in mf.pix and mf.pix[(6, 6)] == 5 and (6, 6) not in mp.pix and len(mf.pix) > len(mp.pix)
    assert Model().draw_set((0, 0), (4, 1)) == [(0, 0), (1, 0), (2, 1), (3, 1), (4, 1)]       # 線の規則は「以上」（cm.LINE_RULE）。「超える」だと cn-1 の2腕が外れた
    # 白黒
    mm = Model(); mm.do_screen('1,0,0,7')
    mm.line(lm.L((10, 10), (14, 14), 3, 'b'))
    mm.paint(P((12, 12), 5, 7))
    assert len(mm.pix) == 25 and all(v == 1 for v in mm.pix.values())
    print('OK 塗りの規則（手計算: 領域・境界上・省略・4連結/8連結・誤り番号・LP・色0・タイル・背景・白黒）', flush=True)
    # 判定の陽性・陰性
    a = known['sh-1']
    st_, mm = steps(a)
    good = dict(arm='sh-1', n=len(mm.pix), hash='x', tail=0, stat=[], spans=lm.to_spans(mm.pix), res={}, sent=1, last={})
    jd = judge(good, a)
    assert all(v.startswith('agree') for v in jd.values()) and 'rest' in jd and len(jd) > 15, jd
    cr = cand_report(good, a)
    assert cr['base'][0] == cr['base'][1] > 10 and cr['conn8'][0] < cr['conn8'][1], cr
    gp = dict(mm.pix)
    cell = sorted(p for p in gp if in_box(p, cell_box(3)))
    gp.pop(cell[40]); gp[(cell[40][0], cell[40][1]+1)] = 7
    jd = judge(dict(good, spans=lm.to_spans(gp)), a)
    assert sum(v.startswith('differ') for v in jd.values()) == 1 and any(k.startswith('b') and v.startswith('differ') for k, v in jd.items()), jd
    assert judge(dict(good, tail=2), a)['tail'].startswith('differ')
    assert judge(dict(good, spans=lm.to_spans({**mm.pix, (635, 100): 7})), a)['rest'].startswith('differ')
    a = known['ed-3']
    st_, mm = steps(a)
    res = {str(i): [pred['e'][0] if pred.get('e') else 0, pred['lp'][0][0], pred['lp'][0][1]] for it, stmt, pr, i, pred in st_ if pr}
    good = dict(arm='ed-3', n=len(mm.pix), hash='x', tail=0, stat=[], spans=lm.to_spans(mm.pix), res=res, sent=1, last={})
    jd = judge(good, a)
    assert all(v.startswith('agree') for v in jd.values()) and len(jd) >= 17, jd
    k0 = next(iter(res))
    assert judge(dict(good, res=dict(res, **{k0: [9, 0, 0]})), a)[f'p{k0}_e'].startswith('differ')
    a = known['sx-a']
    st_, mm = steps(a)
    jd = judge(dict(arm='sx-a', n=0, hash='x', tail=0, stat=[], spans=[], res={str(i): [2, 0, 0] for it, s, pr, i, p in st_ if pr}, sent=1, last={}), a)
    assert any(v == 'agree:m' for v in jd.values()) and any(v.startswith('differ') for v in jd.values()) and 'rest' not in jd
    a = known['bd-1']
    st_, mm = steps(a)
    assert len(mm.pix) > 0 and judge(dict(arm='bd-1', n=0, hash='x', tail=0, stat=[], spans=lm.to_spans(mm.pix), res={}, sent=1, last={}), a)
    print('OK 判定の陽性・陰性（領域の画素・ずれ・範囲外・LP と誤り番号・構文）・候補の区別', flush=True)
    # 印の解析と速さの腕の関門
    assert cm.parse_marks('     1     590  0A12  FF80   01\n     2     640  0A20  FF80   02\n# x\n     3  1  2  FF81  01') == [(590, 1), (640, 2)]
    a = known['sp-nop']
    ok_o = dict(arm='sp-nop', n=0, hash='x', tail=0, stat=[], spans=[], res={'0': [0, 0, 0]}, sent=1, last={}, marks=dict(n1=1, n2=1, frames=3))
    assert valid(ok_o, a)
    assert not valid(dict(ok_o, marks=dict(n1=0, n2=1, frames=None)), a) and not valid(dict(ok_o, marks=dict(n1=1, n2=0, frames=None)), a)
    assert not valid(dict(ok_o, marks=dict(n1=2, n2=1, frames=3)), a) and not valid({k: v for k, v in ok_o.items() if k != 'marks'}, a)
    print('OK 印の解析・速さの腕の関門（開始なし・終了なし・重複・欠落）', flush=True)

    def rec(a_id, o, gate=True):
        return dict(arm=known[a_id], obs=[o, o], failed=[False, False], gate=gate)
    base_o = dict(hash='x', tail=0, stat=[], res={}, sent=1, last={})
    cal_spans = lm.to_spans(steps(known['cal-vis'])[1].pix)
    o_v = dict(base_o, arm='cal-vis', n=CAL_N, spans=cal_spans, pix=[dict(at=[401, 150], dot=['ffffff', 'ffffff'], ref=['000000', '000000'])])
    assert len(steps(known['cal-vis'])[1].pix) == CAL_N
    o_c = dict(base_o, arm='base-cls3', n=0, spans=[])
    assert calibrated([rec('cal-vis', o_v), rec('base-cls3', o_c)])
    assert not calibrated([rec('cal-vis', dict(o_v, n=CAL_N-1))])
    assert not calibrated([rec('cal-vis', dict(o_v, pix=[dict(at=[401, 150], dot=['000000']*2, ref=['000000']*2)]))])
    assert not calibrated([rec('cal-vis', dict(o_v, tail=1))])
    assert not calibrated([rec('base-cls3', dict(o_c, n=1))])
    assert not calibrated([rec('cal-vis', o_v, gate=False)])
    with tempfile.TemporaryDirectory(prefix='l4s9w-emit-', dir=work) as temp:
        out = Path(temp)/'m.tsv'
        assert emit(out, [rec('cal-vis', o_v), rec('base-cls3', o_c)]) and 'gate_failed' not in out.read_text()
        rs2 = [rec('cal-vis', o_v), dict(arm=known['base-cls3'], obs=[o_c, dict(o_c, hash='y')], failed=[False, False], gate=True)]
        assert not emit(out, rs2) and 'gate_failed' in out.read_text()
    print('OK 較正の関門（陰性）・記録の出力・2走不一致の関門落ち', flush=True)
    # 期待値との照合（陽性と陰性）
    with tempfile.TemporaryDirectory(prefix='l4s9w-chk-', dir=work) as temp:
        tdir = Path(temp)
        o1 = dict(o_v, hash='h1')
        o2 = dict(base_o, arm='base-cls3', n=0, spans=[])

        def wr(path, obs_list):
            lm.write_tsv(path, ['arm', 'repeat', 'plan', 'observation', 'gate', 'prediction_judgement', 'failed'],
                         [(o['arm'], i+1, '[]', json.dumps(o), 'pass', '{}', 0) for o in obs_list for i in range(2)])
        wr(tdir/'off.tsv', [o1, o2]); lm.make_expected(tdir/'exp.tsv', tdir/'off.tsv')
        wr(tdir/'same.tsv', [o1, o2]); ok_, bad_ = lm.check(tdir/'exp.tsv', tdir/'same.tsv')
        assert len(ok_) == 2 and not bad_
        sp_ = [list(s) for s in cal_spans]
        sp_[0][1] += 1; sp_[0][2] += 1
        sh = dict(o1, hash='h2', spans=sp_)
        wr(tdir/'shift.tsv', [sh, o2]); ok_, bad_ = lm.check(tdir/'exp.tsv', tdir/'shift.tsv')
        assert ok_ == ['base-cls3'] and 'cal-vis' in bad_ and any(x.startswith('spans:') for x in bad_['cal-vis'])
        wr(tdir/'miss.tsv', [o2]); assert 'cal-vis' in lm.check(tdir/'exp.tsv', tdir/'miss.tsv')[1]
        wr(tdir/'res.tsv', [o1, dict(o2, res={'1': [5, 0, 0]})]); assert 'base-cls3' in lm.check(tdir/'exp.tsv', tdir/'res.tsv')[1]
    print('OK 期待値の作成・照合（陽性、1画素ずれ・欠け・結果行違いの陰性）', flush=True)
    # 自作ROMの対照
    with tempfile.TemporaryDirectory(prefix='l4s9w-selftest-', dir=work) as temp:
        root = Path(temp)
        rom = root/'rom'
        built = subprocess.run([sys.executable, str(kw.REPO/'src/build_main_rom.py'), str(rom), '--work-dir', str(root/'asm')],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert built.returncode == 0, '自作ROM一時ビルド失敗'
        observed = measure(rom, False, [known['base-cls3'], known['sp-nop'], known['lp-a']], root)
        for r in observed:
            assert r['obs'][0] and 'hash' in r['obs'][0] and not any(r['failed']), (r['arm']['id'], r['failed'], r['obs'][0])
            assert r['obs'][0]['tail'] == 0
        assert observed[0]['obs'][0]['n'] == 0
        mk = observed[1]['obs'][0]['marks']
        assert observed[1]['gate'] and mk['n1'] == 1 and mk['n2'] == 1 and 0 <= mk['frames'] < 200, mk
        os.environ['Q88MEASURE_FAULT_CORRUPT_GVRAM_DUMP'] = '1'
        try:
            faulty = run_arm(rom, False, known['base-cls3'], root)
        finally:
            del os.environ['Q88MEASURE_FAULT_CORRUPT_GVRAM_DUMP']
        assert faulty['n'] == 1 and faulty['spans'] == [[1, 7, 7, 2]], faulty['spans']
        print('  自作の現状: sp-nop frames=' + str(mk['frames']) + ' lp-a 結果行=' + json.dumps(observed[2]['obs'][0]['res']), flush=True)
    expected = kw.REPO/'tests/conformance/expected_l4_paint.tsv'
    if expected.exists():
        with expected.open(encoding='utf-8', newline='') as stream:
            want = {r['arm']: json.loads(r['observation']) for r in csv.DictReader(stream, delimiter='\t')}
        assert set(want) == set(known), set(want) ^ set(known)
        with tempfile.TemporaryDirectory(prefix='l4s9w-exp-', dir=work) as temp:
            tdir = Path(temp)
            full = [dict(w, arm=aid, stat=[], last={}, sent=1) for aid, w in sorted(want.items())]
            lm.write_tsv(tdir/'echo.tsv', ['arm', 'repeat', 'plan', 'observation', 'gate', 'prediction_judgement', 'failed'],
                         [(o['arm'], i+1, '[]', json.dumps(o), 'pass', '{}', 0) for o in full for i in range(2)])
            ok_, bad_ = lm.check(expected, tdir/'echo.tsv')
            assert len(ok_) == len(known) and not bad_, bad_
            victim = next(aid for aid in sorted(want) if want[aid]['spans'])
            moved = json.loads(json.dumps(want))
            moved[victim]['spans'][0][1] += 1
            moved[victim]['spans'][0][2] += 1
            lm.write_tsv(tdir/'tamper.tsv', ['arm', 'observation'], [(k, json.dumps(v, separators=(',', ':'))) for k, v in sorted(moved.items())])
            assert moved != want
            ok_, bad_ = lm.check(tdir/'tamper.tsv', tdir/'echo.tsv')
            assert victim in bad_ and len(bad_) == 1, (victim, list(bad_))
            emit(tdir/'own.tsv', [dict(r, gate=r['gate']) for r in observed[:1]], strict=False)
            ok_, bad_ = lm.check(expected, tdir/'own.tsv', only={'base-cls3'})
            assert ok_ == ['base-cls3'] and not bad_, bad_
        print('OK 期待値ファイル（公式観測）との照合: 全腕の一致・1画素ずらしの検出・自作ROMの空画面との一致', flush=True)
    print('OK 自作ROMの対照3腕×2走（グラフィックVRAM写しと印が採れる）・ハーネスの故障注入で写しが変わる', flush=True)
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
    sp = sub.add_parser('speed'); sp.add_argument('--measured', type=Path, required=True)
    tl = sub.add_parser('tally'); tl.add_argument('--measured', type=Path, required=True)
    sub.add_parser('describe')
    e = sub.add_parser('expected'); e.add_argument('--out', type=Path, required=True); e.add_argument('official', type=Path, nargs='+')
    c = sub.add_parser('check'); c.add_argument('--expected', type=Path, required=True); c.add_argument('--measured', type=Path, required=True)
    c.add_argument('--only', default='', help='腕IDのカンマ区切り。空なら期待値の全腕')
    s = sub.add_parser('selftest'); s.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    if args.command == 'selftest':
        return selftest(args.work_dir)
    if args.command == 'expected':
        print(f'期待値 {lm.make_expected(args.out, *args.official)}腕'); return 0
    if args.command == 'check':
        ok, bad = lm.check(args.expected, args.measured, set(x for x in args.only.split(',') if x))
        for aid, d in bad.items():
            print(f'DIFF {aid}: ' + ' / '.join(d))
        print(f'一致 {len(ok)}腕 / 不一致 {len(bad)}腕')
        return 0 if not bad else 1
    if args.command == 'describe':
        print(describe()); return 0
    if args.command == 'report':
        print(report(args.measured)); return 0
    if args.command == 'speed':
        print(speed_report(args.measured)); return 0
    if args.command == 'tally':
        cnt, miss = tally(args.measured)
        print(json.dumps(cnt, sort_keys=True)); print('\n'.join(miss)); return 0
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
