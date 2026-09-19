#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_oracle_v7_m7.py — 候補M7(範囲縮約の単精度乗算だけ正しい丸めにする)

l4-s6d(`docs/notes/l4-s6d-cos-via-shifted-sin-results.md`)で候補M6が
記録済み62腕中44腕(71%)で一致したが、D22(`sin(99999)`)・D09/D10
(`cos(200)`/`tan(200)`)等で大きな外れが残った。親の事後検算により、
これらの外れは「範囲縮約の手順」ではなく「単精度定数1/(2π)の値、または
単精度乗算の丸め」のどちらかにあると指摘され、本ファイルで両方を
検算して原因を確定した。

## 検算結果(根拠)

1. **単精度定数(1/(2π)・π/2)のビットは、πから直接求めた最近接丸め
   (round-half-even)の単精度値と完全に一致した。** `tools/l4_mbf_
   oracle_v5_m5.py`の`IN2PI_SINGLE`(`force_to_single(v3.IN2PI)`)・
   `tools/l4_mbf_oracle_v3.py`の`PI2`のいずれも、独立に計算した
   「πの高精度値から求めた1/(2π)・π/2を単精度へ正しく丸めた値」と
   仮数までビット一致した。**定数は原因ではない。**
2. **`SIN(99999)`の範囲縮約の最初の乗算(`x×IN2PI_SINGLE`)で、
   v2の`gw_binop`(GW-BASICの`$FMULS`の粗い丸め、48bit積の下位16bitを
   スティッキーに畳み込まずに捨てる、`l4_mbf_oracle_v2.py`docstring
   の既知の課題)による結果と、厳密積を1回だけ正しく丸めた結果が
   **仮数で1違った**(`0xf8ad56`対`0xf8ad57`)。正しい丸めの方が真値
   (πの高精度値から計算したx/(2π))に近かった(誤差0.000193対
   0.001170)。この1ULPの差が、後続の「大きな整数部を引く」処理で
   増幅され、最終的な観測された52108ULPの食い違いにつながったと
   考えられる。**単精度乗算の丸めが原因である。**

よってM7は、**範囲縮約の乗算(`x×IN2PI_SINGLE`、$FMULS相当)だけを
正しい丸め(厳密積→1回round-half-even)に差し替える**。それ以外
(多項式評価の乗算・加減算・除算)はM5・M6のまま変更しない。GW-BASIC
自身の$FMULSが粗い丸めであること自体はv2で命令単位に確認済みの事実
だが、N88(旧式の単精度範囲縮約を持つと推定される版)の$FMULSが、
IBM PC版と同じ粗い丸めだったという保証は無い。この乗算1箇所に限り
「粗い丸めではなく正しい丸めだった」という候補として立てる。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import l4_mbf_oracle_v3 as v3  # noqa: E402
import l4_mbf_oracle_v5_m5 as m5  # noqa: E402
import l4_mbf_oracle_v6_m6 as m6  # noqa: E402
from tools.l4_mbf_oracle_v2 import GwNum, encode_mbf, force_to_single, gw_binop, gw_neg  # noqa: E402


def _correct_mul_single(a: GwNum, b: GwNum) -> GwNum:
    """正しい丸め(厳密積→1回round-half-even)の単精度乗算。"""
    exact = a.exact() * b.exact()
    sign, exp, mant = encode_mbf(exact, 24)
    return GwNum("single", sign=sign, exp=exp, mant=mant)


def _rr_reduce_single_m7(x_single: GwNum) -> GwNum:
    """M5の_rr_reduce_singleと同じ構造だが、$FMULS相当の乗算だけ
    正しい丸めに差し替える。"""
    y = _correct_mul_single(x_single, m5.IN2PI_SINGLE)
    return m5._frac_part_single(y)


def sin_impl(x: GwNum) -> GwNum:
    if x.exp != 0 and x.exp < 0o167:
        return x
    neg = x.is_negative()
    xx = gw_neg(x) if neg else x
    frac = _rr_reduce_single_m7(xx)
    return m5._sin_core_single(frac, neg)


def cos_impl(x: GwNum) -> GwNum:
    """M6と同じ構造(角度領域でπ/2を単精度加算しSINをやり直す)。
    SIN側の範囲縮約だけがM7の正しい丸めに変わる。"""
    a = gw_binop(x, v3.PI2, "+")
    a = force_to_single(a)
    return sin_impl(a)


def tan_impl(x: GwNum) -> GwNum:
    s = sin_impl(x)
    c = cos_impl(x)
    return gw_binop(s, c, "/")
