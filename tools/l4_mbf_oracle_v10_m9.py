#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_oracle_v10_m9.py — 候補M9(M6の手順 + 超越関数内部の単精度演算
(乗算・加算・減算・除算すべて)をaway丸めにする)

l4-s7a/l4-s7b(`docs/notes/l4-s7a-single-precision-arithmetic-rounding-
results.md`・`docs/notes/l4-s7b-integer-only-rounding-results.md`)で、
整数オペランドのみを使った単精度の加減乗除は**すべて正しい丸め・
ちょうど半分はround-half-away(0から遠い側)**と確定した(`even`は
40腕中0腕的中、`away`は40腕中40腕的中)。

一方M8(`tools/l4_mbf_oracle_v8_m8.py`)はSIN/COS/TAN内部の単精度乗算を
「厳密積→round-half-even」で正しい丸めにしている。l4-s7bの確定事実と
食い違う可能性があるので、M8の構造はそのままに、丸めだけを
round-half-away に差し替えた候補がM9である。

## 対象(超越関数内部の単精度演算すべて)

- SIN/COS/TAN: 範囲縮約の乗算(x×1/(2π))・多項式評価(Horner乗算・
  加算・偶関数変形の自乗)・COS用のπ/2単精度加算・TAN用の除算。
  範囲縮約内の減算(quad-q、1-sub)も対象に含める。
- ATN: 1/xの除算・(x+√3)の加算・(x√3-1)/(x+√3)の除算・多項式評価・
  π/6の加算・π/2の減算。
- EXP: x*log2(e)の乗算・y-Nyの減算・多項式評価(POLY、$POLYXではない)・
  2^Nyとの乗算。
- LOG: 多項式評価・P/Qの除算・e_float+pqの加算・log2x*ln2の乗算。
- SQR: GW-BASICの実装手順(ニュートン法の反復)は未特定なので、
  `tools/l4_mbf_oracle_v3.py`のsqr_implと同じ高精度近似のまま、
  最終の単精度への丸め1回だけをawayに差し替える(演算列そのものは
  未特定のため「すべての単精度演算」という前提が適用できない旨を
  結果ノートに明記する)。

丸め方式以外(範囲縮約の構造・多項式係数・分岐条件)はM8/v3から変更しない。
係数(SINCN等)の当てはめは行っていない。
"""
from __future__ import annotations

import math
import os
import sys
from fractions import Fraction
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import l4_mbf_oracle_v3 as v3  # noqa: E402
import l4_mbf_oracle_v5_m5 as m5  # noqa: E402
import l4_mbf_oracle_v7_m7 as m7  # noqa: E402
import l4_mbf_oracle_v8_m8 as m8  # noqa: E402
from tools.l4_mbf_oracle_v2 import (  # noqa: E402
    GwNum,
    GwError,
    MBF_DOUBLE_BITS,
    MBF_SINGLE_BITS,
    _pow2_bracket,
    _round_half_away_mag,
    force_to_single,
    gw_neg,
)


# ---------------------------------------------------------------------------
# away丸め版のencode/binop/correct_mul/poly_eval
# (l4_mbf_oracle_v2.pyの_round_half_away_mag・_encode_single_away/
# _encode_double_awayと同型だが、公開されている単精度専用の
# _encode_single_awayではなく、single/doubleどちらでも使えるよう
# 汎用のnbits版として書き直す。丸め規則そのものはv2から変更しない)
# ---------------------------------------------------------------------------


def _encode_mbf_away(value: Fraction, nbits: int) -> Tuple[int, int, int]:
    if value == 0:
        return (0, 0, 0)
    sign = 1 if value < 0 else 0
    av = -value if sign else value
    k = _pow2_bracket(av)
    mexact = av * Fraction(2) ** (nbits - k)
    m = _round_half_away_mag(mexact)
    if m >= (1 << nbits):
        k += 1
        m = 1 << (nbits - 1)
    exp_byte = k + 128
    if exp_byte > 255:
        raise OverflowError("mbf exponent overflow (away)")
    if exp_byte < 1:
        return (0, 0, 0)
    return (sign, exp_byte, m)


def from_fraction_away(value: Fraction, kind: str) -> GwNum:
    nbits = MBF_SINGLE_BITS if kind == "single" else MBF_DOUBLE_BITS
    sign, exp, mant = _encode_mbf_away(value, nbits)
    return GwNum(kind, sign=sign, exp=exp, mant=mant)


def _binop_kind_away(ak: str, bk: str, op: str) -> str:
    rank = {"int": 0, "single": 1, "double": 2}
    base = "single" if op == "/" else "int"
    return max([ak, bk, base], key=lambda k: rank[k])


def away_binop(a: GwNum, b: GwNum, op: str) -> GwNum:
    """gw_binop(v2)と同型だが、丸めをround-half-awayに差し替える。
    整数どうしの+-*は元から厳密(丸め不要)なので分岐はv2のまま流用する。
    """
    if op in "+-*" and a.kind == "int" and b.kind == "int":
        if op == "+":
            r = a.ivalue + b.ivalue
        elif op == "-":
            r = a.ivalue - b.ivalue
        else:
            r = a.ivalue * b.ivalue
        if -32768 <= r <= 32767:
            return GwNum.from_int(r)

    kind = _binop_kind_away(a.kind, b.kind, op)
    av = a.exact()
    bv = b.exact()
    if op == "+":
        exact = av + bv
    elif op == "-":
        exact = av - bv
    elif op == "*":
        exact = av * bv
    elif op == "/":
        if bv == 0:
            sign = 1 if av < 0 else 0
            raise GwError("Division by zero", GwNum(kind, sign=sign, exp=255, mant=(1 << 24) - 1))
        exact = av / bv
    else:
        raise ValueError(op)
    try:
        return from_fraction_away(exact, kind)
    except OverflowError:
        sign = 1 if exact < 0 else 0
        raise GwError("Overflow", GwNum(kind, sign=sign, exp=255, mant=(1 << 24) - 1))


def _correct_mul_away(a: GwNum, b: GwNum) -> GwNum:
    """正しい丸め(厳密積→1回round-half-away)の単精度乗算。M8の
    _correct_mulのaway版。"""
    exact = a.exact() * b.exact()
    sign, exp, mant = _encode_mbf_away(exact, 24)
    return GwNum("single", sign=sign, exp=exp, mant=mant)


def _poly_eval_away(x: GwNum, coeffs: List[GwNum]) -> GwNum:
    acc = coeffs[0]
    for c in coeffs[1:]:
        acc = _correct_mul_away(acc, x)
        acc = away_binop(c, acc, "+")
    return acc


def _polyx_eval_away(x: GwNum, coeffs: List[GwNum]) -> GwNum:
    x2 = _correct_mul_away(x, x)
    p = _poly_eval_away(x2, coeffs)
    return _correct_mul_away(p, x)


# ---------------------------------------------------------------------------
# SIN/COS/TAN — M8と同じ構造(単精度の範囲縮約 + 多項式評価も乗算を
# 正しい丸めに広げた段階2)だが、丸め方式をaway化する。
# ---------------------------------------------------------------------------


def _rr_reduce_single_m9(x_single: GwNum) -> GwNum:
    y = _correct_mul_away(x_single, m5.IN2PI_SINGLE)
    n = m5._floor_single(y)
    diff = away_binop(n, y, "-")
    return gw_neg(diff)


def _sin_core_m9(frac_turns: GwNum, outer_neg: bool) -> GwNum:
    quad = GwNum.from_fraction(frac_turns.exact() * 4, "single")  # 2の整数乗の厳密演算
    q_num = m5._floor_single(quad)
    q = int(q_num.exact()) % 4
    sub = gw_neg(away_binop(q_num, quad, "-"))
    if q in (1, 3):
        sub = away_binop(m5.ONE_SINGLE, sub, "-")
    reduced_sp = GwNum.from_fraction(sub.exact() / 4, "single")  # 2の整数乗の厳密演算
    if reduced_sp.exp != 0 and reduced_sp.exp < 0o164:
        result = _correct_mul_away(reduced_sp, v3.TWO_PI)
    else:
        result = _polyx_eval_away(reduced_sp, v3.SINCN)
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
    frac = _rr_reduce_single_m9(xx)
    return _sin_core_m9(frac, neg)


def cos_impl(x: GwNum) -> GwNum:
    a = away_binop(x, v3.PI2, "+")
    a = force_to_single(a)  # $CSD、tie理論上到達しないためv2のまま(丸め方式の対象外)
    return sin_impl(a)


def tan_impl(x: GwNum) -> GwNum:
    s = sin_impl(x)
    c = cos_impl(x)
    return away_binop(s, c, "/")


# ---------------------------------------------------------------------------
# ATN — v3.atn_implと同じ構造、演算をすべてaway化。
# ---------------------------------------------------------------------------


def atn_impl(x: GwNum) -> GwNum:
    neg = x.is_negative()
    xx = gw_neg(x) if neg else x
    need_pi2 = xx.exp != 0 and xx.exp >= 0o201
    if need_pi2:
        xx = away_binop(v3.ONE_S, xx, "/")
    need_pi6 = xx.exact() > v3.TAN_PI12.exact()
    if need_pi6:
        xps = away_binop(xx, v3.SQRT3, "+")
        num = _poly_eval_away(xx, v3.ATNC1)
        xx = away_binop(num, xps, "/")
    result = _polyx_eval_away(xx, v3.ATNC2)
    if need_pi6:
        result = away_binop(v3.PI6, result, "+")
    if need_pi2:
        result = away_binop(v3.PI2, result, "-")
    if neg:
        result = gw_neg(result)
    return result


# ---------------------------------------------------------------------------
# EXP — v3.exp_implと同じ構造、演算をすべてaway化。
# ---------------------------------------------------------------------------


def exp_impl(x: GwNum) -> GwNum:
    y = away_binop(x, v3.LOG2E, "*")
    if y.exp != 0 and y.exp >= 0o210:
        if y.is_negative():
            return from_fraction_away(Fraction(0), "single")
        raise GwError("Overflow", v3._max_single(0))
    if y.exp == 0 or y.exp < 0o150:
        return from_fraction_away(Fraction(1), "single")
    ny = math.floor(y.exact())
    ny_num = from_fraction_away(Fraction(ny), "single")
    frac = away_binop(y, ny_num, "-")
    poly_result = _poly_eval_away(frac, v3.EXPCN)
    exp2 = ny + 129
    if exp2 > 255:
        raise GwError("Overflow", v3._max_single(0))
    if exp2 < 1:
        return from_fraction_away(Fraction(0), "single")
    two_pow_ny = GwNum("single", sign=0, exp=exp2, mant=0x800000)
    return away_binop(poly_result, two_pow_ny, "*")


# ---------------------------------------------------------------------------
# LOG — v3.log_implと同じ構造、演算をすべてaway化。
# ---------------------------------------------------------------------------


def log_impl(x: GwNum) -> GwNum:
    if x.exp == 0 or x.is_negative():
        raise GwError("IllegalFunctionCall", from_fraction_away(Fraction(0), "single"))
    if x.exact() == Fraction(1):
        return from_fraction_away(Fraction(0), "single")
    e_raw = x.exp - 128
    m = GwNum("single", sign=0, exp=128, mant=x.mant)
    p = _poly_eval_away(m, v3.LOGP)
    q = _poly_eval_away(m, v3.LOGQ)
    pq = away_binop(p, q, "/")
    e_float = from_fraction_away(Fraction(e_raw), "single")
    log2x = away_binop(e_float, pq, "+")
    return away_binop(log2x, v3.LN2, "*")


# ---------------------------------------------------------------------------
# SQR — GW-BASICの反復手順は未特定(v3のdocstring参照)なので、v3と同じ
# 高精度近似のまま、最終丸め1回だけをawayに差し替える。「内部演算すべて」
# という前提が成り立たない旨は結果ノート側に明記する。
# ---------------------------------------------------------------------------


def sqr_impl(x: GwNum) -> GwNum:
    if x.exp == 0:
        return from_fraction_away(Fraction(0), "single")
    if x.is_negative():
        raise GwError("IllegalFunctionCall", from_fraction_away(Fraction(0), "single"))
    approx = v3._high_precision_sqrt(x.exact())
    return from_fraction_away(approx, "single")


FUNCS = {
    "sqr": (sqr_impl, True),
    "sin": (sin_impl, False),
    "cos": (cos_impl, False),
    "tan": (tan_impl, False),
    "atn": (atn_impl, False),
    "exp": (exp_impl, False),
    "log": (log_impl, False),
}


def predict_fn(fname: str, arg_literal: str):
    """v3.predict_fnと同じ入出力・同じ構造(引数は常に単精度に強制する)。
    差分は参照するFUNCSテーブルがM9(away丸め)である点だけ。"""
    fname = fname.lower()
    if fname not in FUNCS:
        raise ValueError(f"unknown function: {fname}")
    fn, always_approx = FUNCS[fname]
    try:
        arg_num = v3.parse_literal(arg_literal)
        arg_single = force_to_single(arg_num)
        result = fn(arg_single)
    except GwError as e:
        line, approx = v3.print_one(e.residual, n88=True)
        return "error", f"{e.kind};{line}", approx
    line, approx = v3.print_one(result, n88=True)
    return "numeric", line, approx or always_approx
