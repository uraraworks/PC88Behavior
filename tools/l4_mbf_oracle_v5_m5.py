#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_oracle_v5_m5.py — 候補M5(SIN/COS/TANの範囲縮約を単精度で行う旧形)

l4-s6b(`docs/notes/l4-s6b-transcendental-precision-results.md`「訂正」
節)で、A05(`SIN(6.283185)`)の公式出力`-3.745070387140004D-07`が
`-2π×2^-24`(=単精度1ULP×2π)にきわめて近いという観察から、親が立てた
候補。x×(1/2π)を**単精度で**丸め、その小数部が単精度の量子化グリッド
(2^-24刻み)に乗った結果と読める。

`tools/l4_mbf_oracle_v3.py`(v3)は範囲縮約(RR/RR1/RR2/RR3)を倍精度で
行う(GW-BASIC MATH1.ASMのコメント"Changed COS to double precision
range reduction 24-JUN-82/NGT"が示す、1982年6月**以後**の形)。M5は
その変更が無かった場合の旧形、すなわち**範囲縮約の乗算・整数部の
除去・象限処理を単精度のまま行う**手順を再現する。

## GWソース上のどこを単精度に戻すか(根拠)

`MATH1.ASM`(コミット`edf82c2e`)1036-1073行を再読した。倍精度化されて
いる箇所は次の3命令列:

1. `RR`: `CALL $CDS`(スタック側の単精度argを倍精度へ変換)→
   `CALL $FMULD`(倍精度乗算、IN2PIとの積)。
2. `RR3`: `CALL $DINT`(倍精度INT)。
3. `RR2`: `CALL $FSUBD`→`JMP $NEG`(倍精度減算)。

これらはいずれも「同じ位置の単精度命令(`$CDS`を経由しない、`$FMULS`・
`$INT`・`$FSUBS`)に置き換える」という最小の形で旧形に戻せる。旧版の
GW-BASICソース自体は現存しない(l4-s6b-source-reread-and-selfcheck.md
参照、MIT公開リポジトリはコミット1個のみ)ため、**この置き換え以上の
推測(旧版が実際に使っていた命令の並び・追加の丸め等)はしない**。
係数(SINCN等の多項式係数)は測定値から当てはめず、v3と同一のものを
そのまま使う。

## 単精度IN2PIについて

GWソースには単精度版1/(2π)定数は存在しない。M5では、v3が使う倍精度
IN2PI(MATH1.ASM 892-899の`$IN2PI`)を`force_to_single`(=$CSD相当、
正しい丸めであることはv2 docstringで確認済み)で単精度へ丸めたものを
使う。これは「同じ定数を単精度演算で使う」という最小差分の解釈であり、
独自に係数を作っていない。

$SIN10の早期リターン判定・SINCN等の多項式係数・TANのSIN/COS除算・
ATN等はv3から変更しない(範囲縮約だけを差し替える)。
"""
from __future__ import annotations

import os
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import l4_mbf_oracle_v3 as v3  # noqa: E402
from tools.l4_mbf_oracle_v2 import (  # noqa: E402
    GwNum,
    force_to_single,
    gw_binop,
    gw_neg,
)

# 単精度に丸めたIN2PI ($CSDで倍精度→単精度、正しい丸め)。
IN2PI_SINGLE = force_to_single(v3.IN2PI)

# 単精度の1.0 (DP00相当だが単精度)。
ONE_SINGLE = GwNum.from_fraction(Fraction(1), "single")


def _floor_single(x: GwNum) -> GwNum:
    """$INT相当(単精度)。既に単精度に丸められた値の厳密floorを取り、
    単精度へ再エンコードする(整数値なので丸め不要)。"""
    import math

    v = x.exact()
    fl = Fraction(math.floor(v))
    return GwNum.from_fraction(fl, "single")


def _frac_part_single(y: GwNum) -> GwNum:
    """RR2相当(単精度): $FSUBS(n-y)の後$NEG(y-n)。"""
    n = _floor_single(y)
    diff = gw_binop(n, y, "-")  # $FSUBS: (ARG=n)-(FAC=y)
    return gw_neg(diff)


def _rr_reduce_single(x_single: GwNum) -> GwNum:
    """RR/RR1相当(単精度): $CDSを経由せず、単精度のxをそのまま単精度
    IN2PIと$FMULS(単精度乗算、粗い丸め)で掛ける。"""
    y = gw_binop(x_single, IN2PI_SINGLE, "*")  # $FMULS
    return _frac_part_single(y)


def _sin_core_single(frac_turns: GwNum, outer_neg: bool) -> GwNum:
    """v3の_sin_coreと同型だが、全段を単精度で行う(reduced_spへの
    force_to_singleは既に単精度なので恒等)。"""
    quad = GwNum.from_fraction(frac_turns.exact() * 4, "single")  # FAC*4(厳密、2の整数乗)
    q_num = _floor_single(quad)
    q = int(q_num.exact()) % 4
    sub = gw_neg(gw_binop(q_num, quad, "-"))  # quad - q (単精度$FSUBS)
    if q in (1, 3):
        sub = gw_binop(ONE_SINGLE, sub, "-")  # 1 - sub (単精度$FSUBS)
    reduced_sp = GwNum.from_fraction(sub.exact() / 4, "single")  # 厳密(2の整数乗)
    if reduced_sp.exp != 0 and reduced_sp.exp < 0o164:
        result = gw_binop(reduced_sp, v3.TWO_PI, "*")
    else:
        result = v3.polyx_eval(reduced_sp, v3.SINCN)
    if q in (2, 3):
        result = gw_neg(result)
    if outer_neg:
        result = gw_neg(result)
    return result


def sin_impl(x: GwNum) -> GwNum:
    if x.exp != 0 and x.exp < 0o167:
        return x
    neg = x.is_negative()
    xx = gw_neg(x) if neg else x
    frac = _rr_reduce_single(xx)
    return _sin_core_single(frac, neg)


def cos_impl(x: GwNum) -> GwNum:
    xx = gw_neg(x) if x.is_negative() else x
    frac = _rr_reduce_single(xx)
    quarter_single = GwNum.from_fraction(Fraction(1, 4), "single")
    frac2 = gw_binop(quarter_single, frac, "+")  # $FADDS
    frac3 = _frac_part_single(frac2) if frac2.exact() >= 1 else frac2
    return _sin_core_single(frac3, False)


def tan_impl(x: GwNum) -> GwNum:
    s = sin_impl(x)
    c = cos_impl(x)
    return gw_binop(s, c, "/")  # $FDIVS: sin/cos (v3と同一、不変更)
