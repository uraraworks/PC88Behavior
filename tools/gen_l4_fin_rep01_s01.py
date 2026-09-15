#!/usr/bin/env python3
"""gen_l4_fin_rep01_s01.py — REP01(docs/spec/l4-basic.md 5.1.1節)が使う
「単精度に丸めた0.1」の定数バイト列を、tools/l4_mbf_oracle_v2.py の
_encode_single_away(丸めは半分は絶対値の大きい側=round_half_away)と
同じ計算で独立に求める。src/l4_basic/mbf_single.asm の
FIN_SET_OPB_S01 に書くバイト列は、本スクリプトの出力をそのまま
転記したものであり、手計算・手入力はしていない
(90cb054で10のべき乗テーブルの手入力に転記ミスが複数あった教訓)。

実行: python3 tools/gen_l4_fin_rep01_s01.py
"""
from fractions import Fraction
import math


def pow2_bracket(av: Fraction) -> int:
    est = math.floor(math.log2(av.numerator / av.denominator)) + 1
    while Fraction(2) ** (est - 1) > av:
        est -= 1
    while Fraction(2) ** est <= av:
        est += 1
    return est


def round_half_away_mag(x: Fraction) -> int:
    """半分は絶対値の大きい側(xは常に非負なので常に切り上げ側)。"""
    n, d = x.numerator, x.denominator
    q, r = divmod(n, d)
    return q if 2 * r < d else q + 1


def encode_single_away(value: Fraction):
    if value == 0:
        return (0, 0)
    k = pow2_bracket(value)
    mant_exact = value * Fraction(2) ** (24 - k)
    m = round_half_away_mag(mant_exact)
    if m >= (1 << 24):
        k += 1
        m = 1 << 23
    exp_byte = k + 128
    return exp_byte, m


def main() -> None:
    exp_byte, mant = encode_single_away(Fraction(1, 10))
    frac = mant & 0x7FFFFF
    b0 = frac & 0xFF
    b1 = (frac >> 8) & 0xFF
    b2 = (frac >> 16) & 0x7F  # sign=0(正)
    b3 = exp_byte
    val = Fraction(mant) * Fraction(2) ** (exp_byte - 128 - 24)
    print(f"exp_byte={exp_byte} mant=0x{mant:06X}")
    print(f"db 0x{b0:02x}, 0x{b1:02x}, 0x{b2:02x}, 0x{b3:02x}  ; 単精度0.1(round_half_away)")
    print(f"検算: float(value)={float(val)!r}")


if __name__ == "__main__":
    main()
