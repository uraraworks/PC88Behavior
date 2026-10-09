#!/usr/bin/env python3
"""l4-s9v: CIRCLE 文（円・楕円・円弧・扇形）と、描画の速さ（補助の腕）を測る器具。

画面本文は扱わない。採るのは次の数値・記号だけ。ここで「描いた」と言うのは、こちらの打ち込んだプログラムが描かせた画素だけ。
 (1) グラフィックVRAM 3 プレーンの全画素（ハーネス --gvram-dump）を (x,y,色) に復号したもの。連続した同色を (y,x0,x1,色) の区間に畳む。
     復号は l4_line_measure と同じ（80 バイト/ライン、MSB が左、B=1・R=2・G=4）。生バイトは採取後に消し、コミットしない。
 (2) こちらのプログラムが印字した結果行 `s9v<番号>:誤り,LP-X,LP-Y;`（テキストVRAM写しから）。
 (3) 制御ポートの最後の値。
 (4) 速さの腕だけ: プログラムが利用者領域の1バイトへ書いた開始の印(1)と終了の印(2)のフレーム番号（--mem-write-log）。差が所要フレーム。
 (5) --screenshot の PPM から、描いた画素（cal-vis だけ）。
事前登録は docs/notes/l4-s9v-circle-preregistration.md。
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import struct
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

WORK = kw.REPO.parent / 'tmp/s9v-work'
SENT = 's9vz'
PFX = 's9v'
W, H = lm.W, lm.H
SPAN_MAX = lm.SPAN_MAX
VISIBLE = (401, 150)
MARK_ADDR = 65408            # 0xFF80。clear ,49151 で確保した利用者領域のうちテキストVRAMの外で、グラフィックの描画が触らない位置
MARK_HEX = 'FF80'
rnd = lm.rnd
screen_has = lm.screen_has
in_box = lm.in_box
num = lm.num
DEFAULT_RATIO = 0.5          # マニュアル: 640x200 の省略値


def f32(v):
    try:
        return struct.unpack('f', struct.pack('f', v))[0]
    except (OverflowError, struct.error):
        return math.inf if v > 0 else -math.inf


# ---------------------------------------------------------------- 円の画素を生む規則（候補）
# 資料: GW-BASIC の公開ソース ADVGRP.ASM の 445〜840 行（CIRCLE 本体・アルゴリズムの注釈・CPLOT8/CPLOT4・SCALE・CGTCNT）。コードは転載しない。
def circle_offsets(r, half=1):
    """(a,b) の列。half は半分にするときの前置き（1＝切り上げ、0＝切り捨て）。2r を半径に取り、Y が偶数のときだけ ((X+1)/2,(Y+1)/2) を打ち、Y>=X で止める。
    毎歩 和 += 2Y+1、Y を進める前に 和>=0 なら 和 -= 2X-1 して X を1減らす。"""
    X, Y, S = 2*r, 0, 0
    out = []
    while True:
        if Y % 2 == 0:
            out.append(((X+half) >> 1, (Y+half) >> 1))
            if Y >= X:
                break
        S += 1+2*Y
        if S >= 0:
            S -= 2*X-1
            X -= 1
        Y += 1
    return out


def aspect_of(ratio, trunc=False):
    """(aspect整数, X を縮めるか)。ratio<=1 は Y を ratio 倍、>1 は X を 1/ratio 倍。負は None。"""
    f = math.floor if trunc else rnd
    if ratio <= 1:                      # 負の比率もここへ来る（256 倍した負の整数のまま。scale が下位バイトと上位バイトで扱う）
        return f(f32(ratio)*256), False
    return f(f32(1/f32(ratio))*256), True


def scale(v, a, add=128):
    """aspect 整数 a（256 倍した 16 ビット）による掛け算。下位バイトが 0 なら、上位バイトが 0 以外で素通し・0 で 0 倍、
    それ以外は下位バイトだけで (v×下位+add)>>8。負の比率（-0.5 → 下位 0x80）が絶対値のように見えるのはこのため（観測 el-4）。"""
    lo, hi = a & 0xFF, (a >> 8) & 0xFF
    if lo == 0:
        return v if hi else 0
    return (v*lo+add) >> 8


def ang_count(v, n):
    """角(ラジアン)→点数。(frac, 点数)。|v|/(2π) が1を超えたら None（誤り）。"""
    frac = f32(f32(abs(v))*f32(0.15915494))
    if frac > 1:
        return None
    return rnd(f32(frac*f32(8*n)))


def decide(c, sc, ec, plotf, lf):
    """点数 c の点を打つか: 'plot' / 'line'（中心へ線）/ None。"""
    if c == sc:
        return 'line' if lf & 1 else 'plot'
    if sc > c:
        return 'plot' if plotf else None
    if c == ec:
        return 'line' if lf & 0x80 else 'plot'
    if ec > c:
        return None if plotf else 'plot'
    return 'plot' if plotf else None


# 扇形の線は LINE と同じ規則。l4-s9u の観測（仕様 l4-graphics 第3版 9.2）で「和が主軸の差以上」と確定済み。
# 事前登録時の器具は lm.PRIMARY（予測時の「超える」）をそのまま使っていて外れた（結果ノート参照）。
LINE_RULE = dict(init='floor', cmp='>=', start='gw')


def circle_points(cx, cy, r, ratio, start=None, end=None, half=1, add=128, trunc=False):
    """CIRCLE の予測画素列（画面外を含む）。start/end は角(ラジアン)か None。負の角は中心へ線。誤りなら ValueError(5)。
    負の比率は 256 倍した負の整数のまま掛け算に渡る。"""
    asp = aspect_of(ratio, trunc)
    if asp is None:
        return None
    a_, swap = asp
    n = rnd(f32(r*0.7071068))
    sc, ec, lf = 0, 0xFFFF, 0
    if start is not None:
        sc = ang_count(start, n)
        if sc is None:
            raise ValueError(5)
        if start < 0:
            lf |= 1
    if end is not None:
        ec = ang_count(end, n)
        if ec is None:
            raise ValueError(5)
        if end < 0:
            lf |= 0x80
    if ec >= sc:
        plotf = 0
    else:
        sc, ec = ec, sc
        plotf = 0xFF
        lf = ((lf & 1) << 7) | ((lf >> 7) & 1)
    out = []
    lines = []
    for a, b in circle_offsets(r, half):
        sa, sb = scale(a, a_, add), scale(b, a_, add)
        if not swap:
            octs = [(a, -sb, b), (b, -sa, 2*n-b), (-b, -sa, 2*n+b), (-a, -sb, 4*n-b),
                    (-a, sb, 4*n+b), (-b, sa, 6*n-b), (b, sa, 6*n+b), (a, sb, 8*n-b)]
        else:
            octs = [(sa, -b, b), (sb, -a, 2*n-b), (-sb, -a, 2*n+b), (-sa, -b, 4*n-b),
                    (-sa, b, 4*n+b), (-sb, a, 6*n-b), (sb, a, 6*n+b), (sa, b, 8*n-b)]
        for dx, dy, c in octs:
            d = decide(c & 0xFFFF, sc, ec, plotf, lf)
            if d == 'plot':
                out.append((cx+dx, cy+dy))
            elif d == 'line':
                lines.append(((cx+dx, cy+dy), (cx, cy)))
    pts = list(out)
    for p, q in lines:
        if screen_has(p) and screen_has(q):
            pts += lm.line_pts(p, q, **LINE_RULE)
        else:
            pts += lm.clip_recompute(p, q, LINE_RULE)
    return pts


# 記述用の別候補（判定には使わず、観測と一致するものを報告するだけ）
def circle_trig(cx, cy, r, ratio):
    """角度を刻む方式: 密に刻んだ角の (r cosθ, ratio·r sinθ) を四捨五入して集める（ratio>1 は垂直半径 r）。"""
    out = set()
    steps = max(64, 16*r)
    rx, ry = (r, r*ratio) if ratio <= 1 else (r/ratio, r)
    for k in range(steps):
        t = 2*math.pi*k/steps
        out.add((cx+rnd(rx*math.cos(t)), cy+rnd(ry*math.sin(t))))
    return out


CIRCLE_CANDS = {'gw': {}, 'half-down': dict(half=0), 'scale-floor': dict(add=0), 'aspect-trunc': dict(trunc=True)}


def cand_report(obs, a):
    """記述: 単独の全円（円弧でない・全部が画面内）のセルごとに、観測と一致する候補。"""
    op = lm.obs_pix(obs)
    if op is None:
        return {}
    out = {}
    st, _ = steps(a)
    for it, stmt, pr, i, pred in st:
        if it['op'] != 'C' or it['raw'] is not None or it['box'] is None or pred.get('pts') is None or not pred.get('pts') or pred.get('arc'):
            continue
        if not all(screen_has(q) for q in pred['pts']):
            continue
        got = {p for p in op if in_box(p, it['box'])}
        names = []
        for name, kw_ in CIRCLE_CANDS.items():
            if {q for q in circle_points(pred['a'][0], pred['a'][1], pred['r'], pred['ratio'], **kw_)} == got:
                names.append(name)
        if circle_trig(pred['a'][0], pred['a'][1], pred['r'], pred['ratio']) == got:
            names.append('trig')
        out[i] = dict(r=pred['r'], ratio=pred['ratio'], n=len(got), match=names)
    return out


# ---------------------------------------------------------------- 項目
def C(ctr, r, c=None, s=None, e=None, ratio=None, s1=False, box=None, probe=False, exp=None, raw=None):
    """CIRCLE 文。c＝色、s＝開始角、e＝終了角、ratio＝比率（None は省略、'' はコンマだけ）。"""
    return dict(op='C', ctr=ctr, r=r, c=c, s=s, e=e, ratio=ratio, s1=s1, box=box, probe=probe, exp=exp or {}, raw=raw)


def arm(aid, items, pix=None, group=None, wait=0, speed=False, prog=None):
    return dict(id=aid, items=items, pix=pix or [], group=group or aid.split('-')[0], wait=wait, speed=speed, prog=prog)


PRE = [lm.screen('0,0'), lm.cls(3)]
cell_xy, cell_box = lm.cell_xy, lm.cell_box


def ccenter(k):
    ox, oy = cell_xy(k)
    return ox+48, oy+28


def ccells(params, **common):
    """params の各要素（dict: r と任意の c,s,e,ratio,probe,exp）を別のセルの中心に置く。最大 18。"""
    assert len(params) <= lm.CELL_COLS*lm.CELL_ROWS
    out = []
    for k, p in enumerate(params):
        q = dict(common); q.update(p)
        out.append(C(ccenter(k), box=cell_box(k), **q))
    return out


def rs(vals, **kw_):
    return [dict(r=v, **kw_) for v in vals]


def arms():
    out = [arm('base-cls3', [lm.cls(3)]),
           arm('cal-vis', PRE + [C((400, 150), 1, 7, ratio=1)], pix=[VISIBLE])]
    out.append(arm('ci-1', PRE + ccells(rs(range(0, 18)), c=7)))
    out.append(arm('ci-2', PRE + ccells(rs(range(18, 36)), c=7)))
    out.append(arm('ci-b1', PRE + [C((100, 100), 45, 7)]))
    out.append(arm('ci-b2', PRE + [C((320, 100), 90, 7)]))
    out.append(arm('ci-b3', PRE + [C((320, 100), 150, 7)]))
    out.append(arm('ci-b4', PRE + [C((320, 100), 300, 7)], wait=2000))
    # ---- はみ出し（cp）
    out.append(arm('cp-ed', PRE + [C((10, 10), 30, 7), C((629, 10), 30, 7), C((10, 189), 30, 7), C((629, 189), 30, 7)]))
    out.append(arm('cp-ou', PRE + [C((-10, 100), 30, 7), C((650, 100), 30, 7), C((320, -5), 40, 7), C((320, 205), 40, 7),
                                   C((-20, -20), 40, 7), C((660, 220), 60, 7), C((-100, 100), 30, 7)]))
    out.append(arm('cp-bg', PRE + [C((320, 100), 2000, 7), C((0, 0), 700, 7), C((639, 199), 500, 7)], wait=6000))
    # ---- 半径の値（co）
    rv = [-1, -0.4, 0.4, 0.5, 1.5, 2.5, 10.4, 10.5, 10.6, '"a"', '1e10', -0.5, 0, 1, 2, 3, '', '1e-10']
    out.append(arm('co-r', PRE + ccells([dict(r=v, probe=True) for v in rv], c=7)))
    rg = [C((32768, 100), 10, 7, probe=True), C((-32769, 100), 10, 7, probe=True), C((100, 100), 32768, 7, probe=True),
          C((100, 100), 65535, 7, probe=True), C((100, 100), 32767, 7, probe=True), C((-32768, 100), 10, 7, probe=True),
          C((10, 100), 70000, 7, probe=True), C((1e10, 100), 10, 7, probe=True), C((100, 100), -32768, 7, probe=True),
          C((32767, 32767), 10, 7, probe=True)]
    out.append(arm('co-rg', PRE + rg, wait=9000))
    # ---- 楕円（el）。ratio<=1 は r が水平半径、>1 は r が垂直半径
    out.append(arm('el-1', PRE + ccells([dict(r=30, ratio=v) for v in
                                         [0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 2, 3, 5]], c=7)))
    out.append(arm('el-2', PRE + ccells([dict(r=48, ratio=v) for v in
                                         [0.5, 0.6, 0.64, 0.4, 0.3, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.004, 0.003, 0.002, 0.001, 0, 1e-4, 1e-10]], c=7)))
    out.append(arm('el-3', PRE + ccells([dict(r=30, ratio=v) for v in
                                         [4, 6, 8, 10, 16, 32, 64, 100, 128, 200, 255, 256, 257, 500, 1000, 10000, 100000, 1e10]], c=7)))
    out.append(arm('el-4', PRE + ccells([dict(r=20, ratio=v, probe=True) for v in
                                         [-0.5, -1, -0.001, -2, -100, '"a"', '', '1e38', '1e-38', '0.5,1']], c=7)))
    out.append(arm('el-5', PRE + ccells([dict(r=50, ratio=v) for v in
                                         [0.49, 0.4961, 0.498, 0.4981, 0.5, 0.5016, 0.5020, 0.5023, 0.5039, 0.505, 0.51, 0.52]], c=7)))
    out.append(arm('el-6', PRE + ccells([dict(r=v, ratio=0.5) for v in [3, 4, 5, 6, 7, 8, 9, 10, 13, 16, 20, 25, 33, 40, 45, 50]], c=7)))
    # ---- 既定の比率（df）。省略と明示の比較
    dfp = []
    for r in (10, 20, 30):
        dfp += [dict(r=r), dict(r=r, ratio=0.5), dict(r=r, ratio=1), dict(r=r, ratio=0.4), dict(r=r, ratio=0.6)]
    dfp += [dict(r=5), dict(r=5, ratio=0.5), dict(r=5, ratio=1)]
    out.append(arm('df-1', PRE + ccells(dfp, c=7)))
    # ---- 円弧・扇形（ar）。比率1を明示して角度→画素だけを見る
    PI2, PI, PI32, PI4 = 1.5708, 3.14159, 4.71239, 6.28318
    q1 = [(0, PI2), (PI2, PI), (PI, PI32), (PI32, PI4), (0, 0.7854), (0.7854, PI2), (0, PI), (PI, PI4), (0.5, 1), (1, 2), (2, 3), (3, 4),
          (4, 5), (5, 6), (0.1, 0.2), (0, PI4), (0, 0), (1, 1)]
    out.append(arm('ar-1', PRE + ccells([dict(r=28, s=a, e=b, ratio=1) for a, b in q1], c=7)))
    q2 = [(PI2, 0), (3, 1), (6, 3), (PI4, 0.1), (5, 4.9), (PI, 0), (0.1, 0), (-0.5, 1), (0.5, -1), (-0.5, -1), (-1, -2), (-3, -4),
          (-PI2, -PI), (-1e-4, 1), (0, -1), (-1, 0), (-PI4, -0.1), (-PI, -PI4)]
    out.append(arm('ar-2', PRE + ccells([dict(r=28, s=a, e=b, ratio=1) for a, b in q2], c=7)))
    out.append(arm('ar-3', PRE + ccells([dict(r=28, s=a, e=b) for a, b in q1[:8] + q2[7:12] + q2[12:15] + [(0.5, 1), (1, 2)]], c=7)))
    ang = [0.1, 0.3, 0.6, 0.7, 0.78, 0.7854, 0.79, 0.8, 1.0, 1.4, 1.5, 1.57, 1.5708, 1.58, 2.0, 2.35, 3.0, 3.5]
    out.append(arm('ar-4', PRE + ccells([dict(r=28, s=0, e=v, ratio=1) for v in ang], c=7)))
    out.append(arm('ar-5', PRE + ccells([dict(r=50, s=0, e=v, ratio=0.5) for v in ang], c=7)))
    out.append(arm('ar-6', PRE + ccells([dict(r=12, s=0, e=v, ratio=1) for v in ang], c=7)))
    out.append(arm('ar-7', PRE + ccells([dict(r=28, s=-0.1, e=-v, ratio=1) for v in ang], c=7)))
    ae = [(PI4, 0), (6.2832, 0), (6.3, 0), (7, 0), (-PI4, 0), (-6.2832, 0), (-7, 0), (100, 0), (0, 6.2832), (0, -6.2832), (0, 7), (0, 1e10),
          ('"a"', 0), (0, '"a"'), (PI4, PI4), (-PI4, -PI4), (6.28319, 0), (0, 6.28319)]
    out.append(arm('ar-e', PRE + ccells([dict(r=20, s=a, e=b, ratio=1, probe=True) for a, b in ae], c=7)))
    # ---- 色（cl）
    out.append(arm('cl-1', PRE + ccells([dict(r=12, c=c) for c in range(8)] + [dict(r=12, c=c, ratio=1) for c in range(8)])))
    cs = [-1, 8, 255, '"a"', 1.5, 0.5, '1e10', 0.4, 6.5, '']
    out.append(arm('cl-2', PRE + ccells([dict(r=12, c=c, probe=True) for c in cs])))
    out.append(arm('cl-4', PRE + [C((30, 20), 12), lm.color(f=3), C((70, 20), 12), lm.text('color 5'), C((110, 20), 12), lm.color(f=0),
                                  C((150, 20), 12), lm.color(f=6), C((190, 20), 12, s=0, e=1), lm.color(f=7), lm.color(b=2),
                                  C((230, 20), 12)]))
    out.append(arm('cl-5', PRE + [lm.color(b=3), lm.cls(3), C((100, 60), 40, 7), C((100, 60), 20, 0), C((100, 60), 10, 5, s=0, e=3),
                                  C((250, 60), 40, 7), C((250, 60), 40, 0), C((400, 60), 30, 6), C((400, 60), 10, 0, s=-1, e=-4)]))
    # ---- 最終参照点・STEP（lp）
    out.append(arm('lp-a', PRE + [lm.pset(10, 10, 7), C((100, 100), 20, 7, probe=True), C((30, 10), 5, 7, s1=True, probe=True),
                                  C((50, 50), 8, 7, probe=True), lm.L(None, (200, 50), 7, probe=True),
                                  C((-5, -5), 6, 7, s1=True, probe=True), C((0, 0), 6, 7, s1=True, probe=True),
                                  C((300, 100), 0, 7, probe=True)]))
    lpb = []
    for k, (ctr, r, c, s, e, ra) in enumerate([((100, 100), -1, 7, None, None, None), ((110, 100), 10, 8, None, None, None),
                                               ((120, 100), 10, 7, 7, None, None), ((130, 100), 10, 7, 0, 7, None),
                                               ((140, 100), 10, 7, 0, 1, '"a"'), ((32768, 100), 10, 7, None, None, None),
                                               ((150, 32768), 10, 7, None, None, None), ((160, 100), '"a"', 7, None, None, None),
                                               ((170, 100), 10, '"a"', None, None, None), ((180, 100), 1e10, 7, None, None, None)]):
        lpb += [lm.pset(10+k, 10, 7), C(ctr, r, c, s, e, ra, probe=True)]
    out.append(arm('lp-b', PRE + lpb))
    # ---- 白黒（mo）
    mp = [dict(r=12, c=5), dict(r=12, c=3), dict(r=12, c=0), dict(r=12, c=1, ratio=1), dict(r=20, c=7, s=0, e=3), dict(r=20, c=7, s=-1, e=-3),
          dict(r=16, c=2, ratio=2)]
    for tag, sa in (('0', '1,0,0,7'), ('1', '1,0,1,7')):
        out.append(arm(f'mo-{tag}', [lm.screen(sa), lm.cls(3)] + ccells(mp)))
    # ---- 構文（sx）
    out.append(arm('sx-a', PRE + [syn(s) for s in SYN_A]))
    out.append(arm('sx-b', PRE + [syn(s) for s in SYN_B]))
    # ---- 速さ（sp）。補助の腕
    out += speed_arms()
    return out


SYN = {'circle': (2, 'm'), 'circle(100,100)': (2, 'm'), 'circle(100,100),': (22, 'w'), 'circle(100,100),10': (0, 'm'),
       'circle (100,100),10': (0, 'm'), 'circle(100,100),10,': (22, 'w'), 'circle(100,100),10,,': None, 'circle(100,100),10,7,,': None,
       'circle(100,100),10,7,0,': None, 'circle 100,100,10': (2, 'm'), 'circle(100),10': (2, 'm'), 'circle(100,100) 10': (2, 'm'),
       'circle(100,100);10': (2, 'm'), 'circle step(5,5),10': (0, 'm'), 'circle-(5,5),10': (2, 'm'),
       'circle(100,100),10,7,0,1,0.5,1': (2, 'm'), 'circle(100,100),10,7,0,1,0.5,': None, 'circle(100,100),10,,,,0.5': (0, 'w'),
       'circle(100,100),10,7,,,': None, 'circle(100,100),10,7,,1': (0, 'w'), 'circle(100,100),10,7,1': (0, 'm'),
       'circle(100,100),10,,1,2': (0, 'w'), 'circle(100,100),10,7,0,1,0.5': (0, 'm'), 'circle(100,100),10,,,,': None,
       'circle(100,100),10;7': (2, 'm'), 'circle(100,100),10 7': (0, 'w'), 'circle(100,100),,7': None, 'circle(100,100),10,7,0,1,,': None}
SYN_A = ['circle', 'circle(100,100)', 'circle(100,100),', 'circle(100,100),10', 'circle (100,100),10', 'circle(100,100),10,',
         'circle(100,100),10,,', 'circle(100,100),10,7,,', 'circle(100,100),10,7,0,', 'circle 100,100,10', 'circle(100),10',
         'circle(100,100) 10', 'circle(100,100);10']
SYN_B = ['circle step(5,5),10', 'circle-(5,5),10', 'circle(100,100),10,7,0,1,0.5,1', 'circle(100,100),10,7,0,1,0.5,',
         'circle(100,100),10,,,,0.5', 'circle(100,100),10,7,,,', 'circle(100,100),10,7,,1', 'circle(100,100),10,7,1',
         'circle(100,100),10,,1,2', 'circle(100,100),10,7,0,1,0.5', 'circle(100,100),10,,,,', 'circle(100,100),10;7',
         'circle(100,100),10 7', 'circle(100,100),,7', 'circle(100,100),10,7,0,1,,']
assert set(SYN_A) | set(SYN_B) == set(SYN)


def syn(s):
    return C(None, None, raw=s, probe=True, exp=dict(e=SYN[s]) if SYN[s] else {})


def speed_arms():
    """所要フレーム数を測る補助の腕。開始の印(1)と終了の印(2)を利用者領域の1バイトへ POKE し、その書き込みのフレーム差を採る。
    比較のため、画素の結果（最終画面のハッシュ・画素数）と誤りの数も採る。"""
    ops = [('nop', []),
           ('bf1', ['line(0,0)-(639,199),7,bf']),
           ('bf10', ['for i=1 to 10:line(0,0)-(639,199),7,bf:next']),
           ('diag', ['for i=0 to 639:line(i,0)-(639-i,199),7:next']),
           ('c100', ['for i=1 to 100:circle(320,100),90,7:next']),
           ('c10', ['for i=1 to 100:circle(320,100),10,7:next']),
           ('ps', ['for i=0 to 599:pset(i,100),7:next'])]
    return [arm(f'sp-{tag}', [], speed=True, prog=lines, wait=16000 if tag in ('diag', 'c100') else 6000) for tag, lines in ops]


# ---------------------------------------------------------------- 予測のモデル
RANK = {'s': 3, 'm': 2, 'w': 1}
low = lm.low


class Model(lm.Model):
    def circle(self, it):
        """返り値 dict(e=(誤り,強さ)|None, lp=(座標,強さ)|None, px=強さ|None, pts=画素列|None, ...)。"""
        ex = it['exp']
        if it['raw'] is not None:
            return dict(e=ex.get('e'), lp=None, px=None, pts=[])
        bad = lambda v: not -32768 <= rnd(v) <= 32767
        x, y = it['ctr']
        if bad(x) or bad(y):
            return dict(e=(6, 'm'), lp=(self.lp, 'w'), px='m', pts=[])
        a = (rnd(x), rnd(y))
        if it['s1']:
            a = (self.lp[0]+a[0], self.lp[1]+a[1])
        self.lp = a
        lp_ok = (a, 'm')
        err = lambda e, st: dict(e=(e, st), lp=lp_ok, px=st, pts=[])
        r = it['r']
        if r == '':
            return err(2, 'w') if any(v is not None for v in (it['c'], it['s'], it['e'], it['ratio'])) else err(22, 'w')
        if r == '"a"':
            return err(13, 'm')
        if isinstance(r, str):
            r = float(r)
        if r < 0:
            return err(5, 'w')                  # 符号は丸める前に見る（観測: -0.4・-0.5 も ERR 5）
        rr = rnd(r)
        if rr > 32767:
            return err(6, 'w')
        c = it['c']
        cst = 'm'
        if c is None:
            cc = self.fg
        elif c == '':
            return err(22, 'w')
        elif isinstance(c, str):
            return err(13, 'm') if c == '"a"' else err(6, 'w')
        else:
            cc = rnd(c)
            cst = 's' if float(c).is_integer() else 'w'
            if not 0 <= cc <= 7:
                return err(5, 'm')
        angs = []
        for v in (it['s'], it['e']):
            if v is None:
                angs.append(None)
            elif v == '':
                return err(22, 'w')
            elif isinstance(v, str):
                if v == '"a"':
                    return err(13, 'm')
                angs.append(float(v))
            else:
                angs.append(v)
        for v in angs:
            if v is not None and f32(f32(abs(v))*f32(0.15915494)) > 1:
                return err(5, 'm')
        ra = it['ratio']
        dflt = ra is None
        if ra == '':
            return err(22, 'w')
        if isinstance(ra, str):
            if ra == '"a"':
                return err(13, 'm')
            try:
                ra = float(ra)
            except ValueError:
                return err(2, 'w')
        if dflt:
            ra = DEFAULT_RATIO
        if abs(ra) > 1e38 or (0 < ra < 1e-37):
            return dict(e=None, lp=lp_ok, px=None, pts=None)
        pts = circle_points(a[0], a[1], rr, ra, angs[0], angs[1])
        for q in pts:
            self.put(q, cc)
        sst = 'w'
        if rr == 0 and angs == [None, None]:
            sst = 'm'
        if cst == 'w':
            sst = 'w'
        return dict(e=(0, 's'), lp=lp_ok, px=sst, pts=pts, a=a, r=rr, plain=(angs == [None, None] and not dflt and ra == 1) or
                    (angs == [None, None] and dflt), ratio=ra, arc=angs != [None, None], dflt=dflt)


def stmt_of(it):
    if it['op'] == 'C':
        if it['raw'] is not None:
            return it['raw']
        s = 'circle' + (' step' if it['s1'] else '') + f"({num(it['ctr'][0])},{num(it['ctr'][1])}),{num(it['r'])}"
        fields = [it['c'], it['s'], it['e'], it['ratio']]
        last = max([i for i, f in enumerate(fields) if f is not None], default=-1)
        if last >= 0:
            s += ',' + ','.join('' if f is None else num(f) for f in fields[:last+1])
        return s
    return lm.stmt_of(it)


def steps(a):
    m = Model()
    out = []
    for i, it in enumerate(a['items']):
        pred = {}
        op = it['op']
        pr = False
        if op == 'C':
            pred = m.circle(it)
            pr = bool(it['probe'])
        elif op == 'L':
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
    if a['speed']:
        lines = {5: 'clear ,49151', 6: 'on error goto 900', 7: 'n=0:e=0', 8: 'cls', 10: 'screen 0,0:cls 3', 20: f'poke {MARK_ADDR},1'}
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
        lines = {5: 'on error goto 900', 6: 'cls'}
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
        assert n < 900, a['id']
    assert all(len(f'{k} {s}') < 80 for k, s in lines.items()), [f'{k} {s}' for k, s in lines.items() if len(f'{k} {s}') >= 80]
    assert all(s.isascii() and s == s.lower() and '@' not in s for s in lines.values()), lines
    return lines


def plan(a):
    return ['new'] + [f'{n} {s}' for n, s in sorted(program_lines(a).items())] + ['cls', ('window',), 'run', ('capture', 'all')]


# ---------------------------------------------------------------- 写しの解析
def parse_results(vram):
    if len(vram) != 3000:
        raise ValueError('画面写しの長さが不正')
    joined = b''.join(bytes(vram[r*120:r*120+80]) for r in range(25))
    res = {}
    for m in re.finditer(rb's9v(\d+):([ \x20-\x7e]*?);', joined):
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


def parse_marks(text):
    """開始の印(1)・終了の印(2)のフレーム番号の列。(書き込み順の (フレーム, 値) 列)。"""
    out = []
    for line in text.splitlines():
        m = re.fullmatch(rf'\s*\d+\s+(\d+)\s+[0-9A-F]+\s+{MARK_HEX}\s+([0-9A-F]+)\s*', line)
        if m:
            out.append((int(m[1]), int(m[2], 16)))
    return out


def marks_summary(ms):
    s = [f for f, v in ms if v == 1]
    e = [f for f, v in ms if v == 2]
    return dict(n1=len(s), n2=len(e), frames=(e[0]-s[0]) if len(s) == 1 and len(e) == 1 else None)


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
        obs['marks'] = marks_summary(parse_marks(memlog or ''))
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
def bbox(pts):
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), max(xs), min(ys), max(ys))


def sym_ok(got, ctr):
    return all(((2*ctr[0]-x, y) in got and (x, 2*ctr[1]-y) in got) for x, y in got)


def judge(obs, a):
    st, m = steps(a)
    res = {}

    def put(name, got, want, strength):
        res[name] = ('agree:' if got == want else 'differ:') + strength

    r = obs['res']
    for it, stmt, pr, i, pred in st:
        if not pr or it['op'] not in ('C', 'L'):
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
    if op is None:
        return res
    boxes = []
    for it, stmt, pr, i, pred in st:
        if it['op'] != 'C' or it['raw'] is not None or it['box'] is None:
            continue
        boxes.append(it['box'])
        sst = pred.get('px')
        if not sst or pred.get('pts') is None:
            continue
        bx = it['box']
        want = {p: c for p, c in m.pix.items() if in_box(p, bx)}
        got = {p: c for p, c in op.items() if in_box(p, bx)}
        put(f'c{i}_px', got, want, sst)
        inside = pred['pts'] and all(screen_has(q) for q in pred['pts'])
        if pred['pts'] and inside and not (it['c'] is not None and not isinstance(it['c'], str) and rnd(it['c']) == 0):
            put(f'c{i}_bbox', bbox(got), bbox(pred['pts']), 'm')
            if not pred['arc']:
                put(f'c{i}_sym', sym_ok(set(got), pred['a']), True, 'm')
    items = [(it, pred) for it, stmt, pr, i, pred in st if it['op'] in ('C', 'L')]
    has_raw = any(it['raw'] is not None for it, _ in items)
    free = [pred for it, pred in items if it['box'] is None]
    if not has_raw and not m.base and all(p.get('pts') is not None for p in free):
        strength = low(*[p.get('px') for p in free if p.get('px')]) if any(p.get('px') for p in free) else 'm'
        want = {p: c for p, c in m.pix.items() if not any(in_box(p, b) for b in boxes)}
        got = {p: c for p, c in op.items() if not any(in_box(p, b) for b in boxes)}
        if free or boxes or not boxes:
            put('rest', got, want, strength)
    return res


def cell_sets(obs, a):
    op = lm.obs_pix(obs)
    if op is None:
        return None
    return [lm.rel_set(op, it['box'], (it['box'][0]+3+48, it['box'][1]+3+28)) for it in a['items'] if it['op'] == 'C' and it['box']]


def group_judges(records):
    by = {r['arm']['id']: r['obs'][0] for r in records if r['gate'] and r['obs'][0]}
    out = {}
    o = by.get('df-1')
    if o:
        a = next(x for x in arms() if x['id'] == 'df-1')
        cs = cell_sets(o, a)
        if cs:
            # 3 つの半径 × (省略,0.5,1,0.4,0.6) と、半径5の (省略,0.5,1)
            out['default_is_half'] = ('agree:' if all(cs[k] == cs[k+1] for k in (0, 5, 10, 15)) else 'differ:') + 'm'
    return out


def calibrated(records):
    by = {r['arm']['id']: r for r in records}
    good = True
    if 'cal-vis' in by:
        r = by['cal-vis']
        o = r['obs'][0] if r['obs'] else {}
        good = good and bool(r['gate'] and o and o['n'] == 4 and o['tail'] == 0)
        if o and o.get('pix'):
            good = good and o['pix'][0]['dot'] != o['pix'][0]['ref']
    if 'base-cls3' in by:
        r = by['base-cls3']
        good = good and bool(r['gate'] and r['obs'][0] and r['obs'][0]['n'] == 0)
    return good


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
    lm.write_tsv(path, ['arm', 'repeat', 'plan', 'observation', 'gate', 'prediction_judgement', 'failed'], rows)
    return cal and bool(records) and all(r['gate'] for r in records)


# ---------------------------------------------------------------- 公式観測の期待値と照合（l4_line_measure の汎用部を使う）
def comparable(obs):
    """公式と自作で比べる数値。速さの腕のフレーム数は比べない（器材と実装で変わるのが当然。別に報告する）。"""
    if not obs:
        return None
    return lm.comparable(obs)


lm_comparable = lm.comparable


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
        lines.append(f"  n={o['n']} hash={o['hash']} tail={o['tail']} res={o['res']} last={o['last']}" + (f" marks={o['marks']}" if 'marks' in o else ''))
        if o.get('pix'):
            lines.append(f"  pix={o['pix']}")
        a = arms_by.get(r['arm'])
        if a and o.get('spans') is not None and not a['speed']:
            for i, c in cand_report(o, a).items():
                lines.append(f"  cand[{i}] r={c['r']} ratio={c['ratio']} n={c['n']} match={c['match']}")
    return '\n'.join(lines)


def describe():
    out = []
    for a in arms():
        if a['speed']:
            out.append(f"- `{a['id']}` (速さ, 待ち+{a['wait']}): " + ' / '.join(a['prog']) if a['prog'] else f"- `{a['id']}` (速さ, 待ち+{a['wait']}): (空)")
            continue
        st, m = steps(a)
        prog = ' / '.join(s[1] for s in st if s[1])
        out.append(f"- `{a['id']}` ({n_probes(a)}印字{', 待ち+%d' % a['wait'] if a['wait'] else ''}): {prog}")
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
    # 箱: 各セルの円は自分の箱に収まり、箱どうしは重ならない。ただし既定の比率を測る腕（df）と大きい比率の腕は箱を超えない設計かを確かめる
    for a in known.values():
        bxs = [it['box'] for it in a['items'] if it['op'] == 'C' and it['box']]
        if len(bxs) > 1:
            assert all(b1[2] < b2[0] or b2[2] < b1[0] or b1[3] < b2[1] or b2[3] < b1[1] for i, b1 in enumerate(bxs) for b2 in bxs[:i]), a['id']
        for it in a['items']:
            if it['op'] == 'C' and it['box'] and it['raw'] is None:
                pr_ = Model().circle(it)
                assert pr_['pts'] is None or all(in_box(q, it['box']) for q in pr_['pts']) or a['id'] in ('el-4', 'lp-b'), (a['id'], it, [q for q in pr_['pts'] if not in_box(q, it['box'])][:3])
    # 円の規則: 手計算
    assert circle_offsets(0) == [(0, 0)] and circle_offsets(1) == [(1, 0), (0, 1)] and circle_offsets(2) == [(2, 0), (2, 1), (1, 2)]
    p2 = set(circle_points(0, 0, 2, 1))
    assert p2 == {(2, 0), (-2, 0), (0, 2), (0, -2), (2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)}, sorted(p2)
    assert set(circle_points(5, 5, 0, 0.5)) == {(5, 5)} and set(circle_points(5, 5, 1, 1)) == {(6, 5), (4, 5), (5, 6), (5, 4)}
    for r in (3, 7, 10, 28):
        ps = set(circle_points(0, 0, r, 1))
        assert all((-x, y) in ps and (x, -y) in ps and (y, x) in ps for x, y in ps) and (r, 0) in ps and (0, r) in ps
        assert max(x for x, y in ps) == r and max(y for x, y in ps) == r
    assert scale(10, 128) == 5 and scale(11, 128) == 6 and scale(10, 256) == 10 and scale(10, 0) == 0 and scale(3, 128) == 2
    assert aspect_of(0.5) == (128, False) and aspect_of(2) == (128, True) and aspect_of(1) == (256, False) and aspect_of(-1) == (-256, False) and aspect_of(-0.5) == (-128, False)
    ph = set(circle_points(0, 0, 40, 0.5))
    assert max(x for x, y in ph) == 40 and max(y for x, y in ph) == 20 and (0, 20) in ph and (40, 0) in ph
    pv = set(circle_points(0, 0, 40, 2))                     # >1: 半径は垂直方向、水平は半分
    assert max(y for x, y in pv) == 40 and max(x for x, y in pv) == 20
    # 点数と角: r=28 → 1/8 周あたり 20 点、π/2 は 40 点
    assert rnd(f32(28*0.7071068)) == 20 and ang_count(1.5708, 20) == 40 and ang_count(-3.14159, 20) == 80 and ang_count(6.3, 20) is None
    assert decide(5, 5, 9, 0, 0) == 'plot' and decide(5, 5, 9, 0, 1) == 'line' and decide(9, 5, 9, 0, 0x80) == 'line' and decide(10, 5, 9, 0, 0) is None
    assert decide(2, 5, 9, 0xFF, 0) == 'plot' and decide(7, 5, 9, 0xFF, 0) is None and decide(10, 5, 9, 0xFF, 0) == 'plot' and decide(2, 5, 9, 0, 0) is None
    # 第1象限だけの円弧
    arc = set(circle_points(0, 0, 28, 1, 0, 1.5708))
    assert arc and all(x >= 0 and y <= 0 for x, y in arc) and (28, 0) in arc and (0, -28) in arc and (0, 28) not in arc and (-28, 0) not in arc
    full = set(circle_points(0, 0, 28, 1))
    q = [set(circle_points(0, 0, 28, 1, s, e)) for s, e in ((0, 1.5708), (1.5708, 3.14159), (3.14159, 4.71239), (4.71239, 6.28318))]
    assert set().union(*q) == full and not any(q[i] & q[j] - {(0, -28), (0, 28), (28, 0), (-28, 0)} for i in range(4) for j in range(i))
    # 逆順は「間」でなく「外側」: 0→1.5708 の補集合に境界を足したもの
    inv = set(circle_points(0, 0, 28, 1, 1.5708, 0))
    assert inv | arc == full and (-28, 0) in inv and (28, 0) in inv
    # 負の角は中心への線
    sec = set(circle_points(100, 100, 28, 1, -0.5, -1))
    assert (100, 100) in sec and len(sec) > len(set(circle_points(100, 100, 28, 1, 0.5, 1))) + 20
    for bad_ in ((7, None), (None, -7), (6.3, 0)):
        try:
            circle_points(0, 0, 28, 1, *bad_); assert False
        except ValueError:
            pass
    assert LINE_RULE['cmp'] == '>=' and lm.line_pts((0, 0), (4, 1), **LINE_RULE) == [(0, 0), (1, 0), (2, 1), (3, 1), (4, 1)]   # 扇形の線は「以上」
    sec2 = set(circle_points(160, 96, 28, 1, -0.5, 1))                 # 公式の ar-2 の1セルで (184,84) が立ち (184,83) は立たない。「超える」の線だと逆になる
    assert (184, 84) in sec2 and (184, 83) not in sec2
    print('OK 円の規則（手計算・対称・半径・比率・点数と角・円弧・逆順・扇形・角の誤り）', flush=True)
    # 文の組み立て
    assert stmt_of(C((1, 2), 3)) == 'circle(1,2),3' and stmt_of(C((1, 2), 3, 7)) == 'circle(1,2),3,7'
    assert stmt_of(C((1, 2), 3, None, 0.5, 1, 0.25)) == 'circle(1,2),3,,0.5,1,0.25' and stmt_of(C((1, 2), 3, s1=True)) == 'circle step(1,2),3'
    assert stmt_of(C((1, 2), 3, 7, None, None, 1)) == 'circle(1,2),3,7,,,1' and stmt_of(C((1, 2), '')) == 'circle(1,2),'
    # モデルの手計算
    m = Model()
    p = m.circle(C((10, 10), 1, 7, ratio=1))
    assert p['e'] == (0, 's') and p['lp'] == ((10, 10), 'm') and m.pix == {(11, 10): 7, (9, 10): 7, (10, 11): 7, (10, 9): 7}
    p = m.circle(C((50, 50), -1, 7)); assert p['e'] == (5, 'w') and m.lp == (50, 50)
    p = m.circle(C((50, 50), 5, 9)); assert p['e'] == (5, 'm')
    p = m.circle(C((50, 50), 5, 7, 7)); assert p['e'] == (5, 'm')
    p = m.circle(C((32768, 5), 5, 7)); assert p['e'] == (6, 'm') and m.lp == (50, 50)
    ca = set(circle_points(0, 0, 20, -0.5)); assert ca == set(circle_points(0, 0, 20, 0.5)) and set(circle_points(0, 0, 20, -2)) == set(circle_points(0, 0, 20, 1))     # 観測 el-4
    assert set(circle_points(0, 0, 20, -0.001)) == set(circle_points(0, 0, 20, 0))
    m = Model(); m.lp = (100, 100)
    m.circle(C((-5, -5), 0, 7, s1=True)); assert m.lp == (95, 95) and m.pix == {(95, 95): 7}
    m = Model(); m.circle(C((10, 10), 5, 7, ratio=1)); m.circle(C((10, 10), 5, 0, ratio=1)); assert m.pix == {}
    print('OK モデル（手計算: 円・誤り番号・LP・STEP・色0の消去）と文の組み立て', flush=True)
    # 判定の陽性・陰性
    a = known['el-1']
    st_, mm = steps(a)
    good = dict(arm='el-1', n=len(mm.pix), hash='x', tail=0, stat=[], spans=lm.to_spans(mm.pix), res={}, sent=1, last={})
    jd = judge(good, a)
    assert all(v.startswith('agree') for v in jd.values()) and 'rest' in jd and len(jd) > 20, jd
    gp = dict(mm.pix)
    cell = sorted(p for p in gp if in_box(p, cell_box(3)))
    gp.pop(cell[5]); gp[(cell[5][0], cell[5][1]+1)] = 7
    jd = judge(dict(good, spans=lm.to_spans(gp)), a)
    assert jd['c5_px'].startswith('differ') and not any(v.startswith('differ') for k, v in jd.items() if not k.startswith('c5_'))
    assert judge(dict(good, tail=2), a)['tail'].startswith('differ')
    assert judge(dict(good, spans=lm.to_spans({**mm.pix, (635, 100): 7})), a)['rest'].startswith('differ')
    a = known['lp-b']
    st_, mm = steps(a)
    res = {str(i): [pred['e'][0] if pred.get('e') else 0, pred['lp'][0][0], pred['lp'][0][1]] for it, stmt, pr, i, pred in st_ if pr}
    good = dict(arm='lp-b', n=len(mm.pix), hash='x', tail=0, stat=[], spans=lm.to_spans(mm.pix), res=res, sent=1, last={})
    jd = judge(good, a)
    assert all(v.startswith('agree') for v in jd.values()) and len(jd) >= 20, jd
    k0 = next(iter(res))
    assert judge(dict(good, res=dict(res, **{k0: [9, 0, 0]})), a)[f'p{k0}_e'].startswith('differ')
    a = known['sx-a']
    st_, mm = steps(a)
    jd = judge(dict(arm='sx-a', n=0, hash='x', tail=0, stat=[], spans=[], res={str(i): [2, 0, 0] for it, s, pr, i, p in st_ if pr}, sent=1, last={}), a)
    assert any(v == 'agree:m' for v in jd.values()) and any(v.startswith('differ') for v in jd.values()) and 'rest' not in jd
    # 候補は区別できる（単独の円を並べた腕で、候補どうしの画素集合が割れる）。観測が gw と同じなら gw が一致の筆頭に出る
    a = known['el-5']
    st_, mm = steps(a)
    sets_ = [tuple(sorted(circle_points(ccenter(0)[0], ccenter(0)[1], 50, ra, **kw_))) for ra in (0.49, 0.5016, 0.5039) for kw_ in CIRCLE_CANDS.values()]
    assert len(set(sets_)) >= 6, len(set(sets_))
    cr = cand_report(dict(arm='el-5', spans=lm.to_spans(mm.pix)), a)
    assert cr and all('gw' in c['match'] for c in cr.values()) and any(len(c['match']) == 1 for c in cr.values())
    bad_pix = {k: v for k, v in mm.pix.items() if k != sorted(p for p in mm.pix if in_box(p, cell_box(0)))[7]}
    cr2 = cand_report(dict(arm='el-5', spans=lm.to_spans(bad_pix)), a)
    assert 'gw' not in next(iter(cr2.values()))['match']
    print('OK 判定の陽性・陰性（円の画素・ずれ・範囲外・LP と誤り番号・構文）・候補の区別', flush=True)
    # 印の解析と速さの腕の関門（陰性対照つき）
    assert parse_marks('     1     590  0A12  FF80   01\n     2     640  0A20  FF80   02\n# x\n     3  1  2  FF81  01') == [(590, 1), (640, 2)]
    assert marks_summary([(590, 1), (640, 2)]) == dict(n1=1, n2=1, frames=50)
    a = known['sp-nop']
    ok_o = dict(arm='sp-nop', n=0, hash='x', tail=0, stat=[], spans=[], res={'0': [0, 0, 0]}, sent=1, last={}, marks=dict(n1=1, n2=1, frames=3))
    assert valid(ok_o, a)
    assert not valid(dict(ok_o, marks=dict(n1=0, n2=1, frames=None)), a) and not valid(dict(ok_o, marks=dict(n1=1, n2=0, frames=None)), a)
    assert not valid(dict(ok_o, marks=dict(n1=2, n2=1, frames=3)), a) and not valid({k: v for k, v in ok_o.items() if k != 'marks'}, a)
    print('OK 印の解析・速さの腕の関門（開始なし・終了なし・重複・欠落）', flush=True)
    # 較正の関門と emit
    def rec(a_id, o, gate=True):
        return dict(arm=known[a_id], obs=[o, o], failed=[False, False], gate=gate)
    base_o = dict(hash='x', tail=0, stat=[], res={}, sent=1, last={})
    o_v = dict(base_o, arm='cal-vis', n=4, spans=[[149, 400, 400, 7], [150, 399, 399, 7], [150, 401, 401, 7], [151, 400, 400, 7]],
               pix=[dict(at=[401, 150], dot=['ffffff', 'ffffff'], ref=['000000', '000000'])])
    o_c = dict(base_o, arm='base-cls3', n=0, spans=[])
    assert calibrated([rec('cal-vis', o_v), rec('base-cls3', o_c)])
    assert not calibrated([rec('cal-vis', dict(o_v, n=3))])
    assert not calibrated([rec('cal-vis', dict(o_v, pix=[dict(at=[401, 150], dot=['000000']*2, ref=['000000']*2)]))])
    assert not calibrated([rec('cal-vis', dict(o_v, tail=1))])
    assert not calibrated([rec('base-cls3', dict(o_c, n=1))])
    assert not calibrated([rec('cal-vis', o_v, gate=False)])
    with tempfile.TemporaryDirectory(prefix='l4s9v-emit-', dir=work) as temp:
        out = Path(temp)/'m.tsv'
        assert emit(out, [rec('cal-vis', o_v), rec('base-cls3', o_c)]) and 'gate_failed' not in out.read_text()
        rs2 = [rec('cal-vis', o_v), dict(arm=known['base-cls3'], obs=[o_c, dict(o_c, hash='y')], failed=[False, False], gate=True)]
        assert not emit(out, rs2) and 'gate_failed' in out.read_text()
    print('OK 較正の関門（陰性）・記録の出力・2走不一致の関門落ち', flush=True)
    # 期待値との照合（陽性と陰性）
    with tempfile.TemporaryDirectory(prefix='l4s9v-chk-', dir=work) as temp:
        tdir = Path(temp)
        o1 = dict(o_v, hash='h1')
        o2 = dict(base_o, arm='base-cls3', n=0, spans=[])
        def wr(path, obs_list):
            lm.write_tsv(path, ['arm', 'repeat', 'plan', 'observation', 'gate', 'prediction_judgement', 'failed'],
                         [(o['arm'], i+1, '[]', json.dumps(o), 'pass', '{}', 0) for o in obs_list for i in range(2)])
        wr(tdir/'off.tsv', [o1, o2]); lm.make_expected(tdir/'exp.tsv', tdir/'off.tsv')
        wr(tdir/'same.tsv', [o1, o2]); ok_, bad_ = lm.check(tdir/'exp.tsv', tdir/'same.tsv')
        assert len(ok_) == 2 and not bad_
        sh = dict(o1, hash='h2', spans=[[149, 400, 400, 7], [150, 399, 399, 7], [150, 402, 402, 7], [151, 400, 400, 7]])
        wr(tdir/'shift.tsv', [sh, o2]); ok_, bad_ = lm.check(tdir/'exp.tsv', tdir/'shift.tsv')
        assert ok_ == ['base-cls3'] and 'cal-vis' in bad_ and any(x.startswith('spans:') for x in bad_['cal-vis'])
        wr(tdir/'miss.tsv', [o2]); assert 'cal-vis' in lm.check(tdir/'exp.tsv', tdir/'miss.tsv')[1]
        wr(tdir/'res.tsv', [o1, dict(o2, res={'1': [5, 0, 0]})]); assert 'base-cls3' in lm.check(tdir/'exp.tsv', tdir/'res.tsv')[1]
        tampered = (tdir/'exp.tsv').read_text().replace('[150,401,401,7]', '[150,402,402,7]')
        assert tampered != (tdir/'exp.tsv').read_text()
        (tdir/'exp2.tsv').write_text(tampered)
        assert 'cal-vis' in lm.check(tdir/'exp2.tsv', tdir/'same.tsv')[1]
    print('OK 期待値の作成・照合（陽性、1画素ずれ・欠け・結果行違いの陰性）', flush=True)
    # 自作ROMの対照: 器具が走り、グラフィックVRAMの写しと印が採れる。故障注入で写しが変わる
    with tempfile.TemporaryDirectory(prefix='l4s9v-selftest-', dir=work) as temp:
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
    # 公式観測の期待値ファイル（コミット済み）との照合: 期待値の腕は器具の腕と一致し、期待値どおりの観測は全腕一致、
    # 1画素ずらすと不一致、自作ROMの現測定（base-cls3）は期待値と一致する
    expected = kw.REPO/'tests/conformance/expected_l4_circle.tsv'
    if expected.exists():
        with expected.open(encoding='utf-8', newline='') as stream:
            want = {r['arm']: json.loads(r['observation']) for r in csv.DictReader(stream, delimiter='\t')}
        assert set(want) == set(known), set(want) ^ set(known)
        with tempfile.TemporaryDirectory(prefix='l4s9v-exp-', dir=work) as temp:
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
