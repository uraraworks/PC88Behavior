#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_oracle_v8_m8.py — 候補M8(単精度の乗算を段階的にすべて正しい
丸めへ広げる)

l4-s6e(`docs/notes/l4-s6e-single-precision-multiply-rounding-results.md`)
で候補M7(範囲縮約の乗算だけ正しい丸め)は62腕中50腕(81%)・新規21腕中
17腕(81%)で完全一致したが、残り4腕(COSの±1〜2ULP、TANへ伝播)が
残った。本ファイルはCOS/SIN内の**他の単精度乗算**(多項式評価の
Horner乗算・偶関数変形の自乗)も正しい丸めに広げた場合にこれが直るか
を段階的に確かめる。

## 段階の設計(根拠)

`tools/l4_mbf_oracle_v2.py`のdocstring(v1→v2の変更点)によれば:

- 単精度乗算($FMULS)だけが「正しい丸めではない」(l4-s6eで確認・
  修正対象)。
- 加算・減算(単精度・倍精度とも)は**正しい丸めと確認済み**
  (位置合わせシフトでSTビットを保持するため)。
- 除算(単精度・倍精度とも)も**正しい丸めと確認済み**($SDIVがKnuthの
  Algorithm Dでスティッキービットを明示的に立てるため)。

つまり、加算・除算は元から正しい丸めなので、「段階を分けて広げる」
対象は**単精度乗算だけ**であり、SIN/COS/TANの計算で単精度乗算が
現れる箇所は以下の2箇所に限られる(範囲縮約の乗算を除く):

1. `$POLY`/`$POLYX`(多項式Horner評価)の各ステップの乗算(`gw_binop
   (acc, x, "*")`)。
2. `$POLYX`の偶関数変形`x^2`を作る自乗(`gw_binop(x, x, "*")`)。

よって段階は以下の2つで尽きる(3段階目「加算・除算も正しい丸めに
広げる」は、v2の確認済み事実によりM7・段階2と数学的に同じになるため、
別実装はしない。理由をそのまま結果ノートに書く):

- **段階1(=M7)**: 範囲縮約の乗算だけ正しい丸め。多項式評価は元の
  粗い丸め(`v3`のまま)。`tools/l4_mbf_oracle_v7_m7.py`を再利用。
- **段階2(M8)**: 範囲縮約の乗算に加え、多項式評価(Horner・自乗)の
  乗算も正しい丸めにする。
- **段階3**: 加算・除算も正しい丸めにする、という広げ方は、v2の
  確認済み事実(加算・除算は元から正しい丸め)により段階2と同一になる
  ため実装しない。

係数(SINCN等)の当てはめは行っていない。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import l4_mbf_oracle_v3 as v3  # noqa: E402
import l4_mbf_oracle_v5_m5 as m5  # noqa: E402
import l4_mbf_oracle_v7_m7 as m7  # noqa: E402
from tools.l4_mbf_oracle_v2 import GwNum, encode_mbf, force_to_single, gw_binop, gw_neg  # noqa: E402


def _correct_mul(a: GwNum, b: GwNum) -> GwNum:
    """正しい丸め(厳密積→1回round-half-even)の乗算(単精度・倍精度とも
    対応、resultのkindは大きい方に合わせるv2の_binop_kindには依らず、
    本ファイルでは単精度どうしの乗算にしか使わないためkind="single"
    固定でよい)。"""
    exact = a.exact() * b.exact()
    sign, exp, mant = encode_mbf(exact, 24)
    return GwNum("single", sign=sign, exp=exp, mant=mant)


def _poly_eval_correct(x: GwNum, coeffs) -> GwNum:
    """v3.poly_evalと同型だが、乗算だけ_correct_mulに差し替える。
    加算はgw_binop(v2で正しい丸めと確認済み)のまま。"""
    acc = coeffs[0]
    for c in coeffs[1:]:
        acc = _correct_mul(acc, x)
        acc = gw_binop(c, acc, "+")
    return acc


def _polyx_eval_correct(x: GwNum, coeffs) -> GwNum:
    x2 = _correct_mul(x, x)
    p = _poly_eval_correct(x2, coeffs)
    return _correct_mul(p, x)


def _sin_core_m8(frac_turns: GwNum, outer_neg: bool) -> GwNum:
    """m5._sin_core_singleと同型だが、多項式評価をpolyx_eval_correctに
    差し替える。範囲縮約後の量子化(quad,floor,sub)はいずれも乗算では
    ない(2の整数乗の厳密演算・加減算)ため、そのままm5と同一。"""
    quad = GwNum.from_fraction(frac_turns.exact() * 4, "single")
    q_num = m5._floor_single(quad)
    q = int(q_num.exact()) % 4
    sub = gw_neg(gw_binop(q_num, quad, "-"))
    if q in (1, 3):
        sub = gw_binop(m5.ONE_SINGLE, sub, "-")
    reduced_sp = GwNum.from_fraction(sub.exact() / 4, "single")
    if reduced_sp.exp != 0 and reduced_sp.exp < 0o164:
        result = _correct_mul(reduced_sp, v3.TWO_PI)
    else:
        result = _polyx_eval_correct(reduced_sp, v3.SINCN)
    if q in (2, 3):
        result = gw_neg(result)
    if outer_neg:
        result = gw_neg(result)
    return result


def sin_impl(x: GwNum) -> GwNum:
    """範囲縮約はM7(乗算を正しい丸め)、多項式評価も正しい丸め(段階2)。"""
    if x.exp != 0 and x.exp < 0o167:
        return x
    neg = x.is_negative()
    xx = gw_neg(x) if neg else x
    frac = m7._rr_reduce_single_m7(xx)
    return _sin_core_m8(frac, neg)


def cos_impl(x: GwNum) -> GwNum:
    """M6・M7と同じ構造(角度領域でπ/2を単精度加算しSINをやり直す)。
    加算はv2で正しい丸めと確認済みのため変更なし。"""
    a = gw_binop(x, v3.PI2, "+")
    a = force_to_single(a)
    return sin_impl(a)


def tan_impl(x: GwNum) -> GwNum:
    """除算はv2で正しい丸めと確認済みのため変更なし(M0/M5/M6/M7と同一)。"""
    s = sin_impl(x)
    c = cos_impl(x)
    return gw_binop(s, c, "/")
