#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_oracle_v9_s7a.py — l4-s7a: 単精度四則演算(+-*/)の丸め規則の候補群

l4-s6e/l4-s6f は SIN/COS/TAN の範囲縮約・多項式評価という「超越関数の
中の乗算」を通じてしか単精度乗算の丸めを見ておらず、cos(44)でM8が
M7より悪化するなど、超越関数の結果から丸め方を逆算する手法には限界が
見えた(`docs/notes/l4-s6f-full-single-precision-rounding-results.md`)。
本ファイルは、単精度の四則演算そのものを`print cdbl(a op b)`という
直接の式で測るための候補予測器。超越関数・範囲縮約は一切経由しない。

`tools/l4_mbf_oracle_v2.py`(GwNum・encode_mbf・parse_literal・
print_one等)をそのまま import して使う(二重実装しない)。v2は
「加算・減算・除算(単精度・倍精度)は正しい丸め、単精度乗算だけ
$FMULSの粗い丸め」という結論をGW-BASIC(MIT公開ソース)の命令単位の
読解から得ているが、これは**IBM PC版GW-BASICのソースを読んだ結果**
であり、N88-BASIC(PC-88版)の実際の数値部が同じ丸めを使っている保証は
無い(v7_m7のdocstring既述の懸念と同種)。l4-s7aはこれを公式ROMで
直接検証する。

## 候補(事前登録の(手順1)に対応)

- `even`  : 正しい丸め・偶数丸め(round-half-even)。厳密値をFractionで
  求め、24bit仮数へ1回だけ丸める。v2の`encode_mbf`と同じ規則。
  加算・減算・除算はv2の既定(`gw_binop`)がこれと数学的に等価
  (v2 docstringの2-4番)。乗算については、v7_m7の「範囲縮約の乗算」
  で支持された規則と同じ。
- `away`  : 正しい丸め・0から遠い側(四捨五入寄り、tie相当は常に
  絶対値の大きい側)。`even`とはtie(ちょうど半分)のときだけ違う。
- `trunc` : 切り捨て(0方向、丸めをしない)。
- `coarse8`: ガードバイト方式の粗い丸め — 厳密値をいったん
  (24+8)bit精度へ切り捨て(この時点で下位ビットの情報はスティッキー
  へ畳み込まずに完全に捨てる)、残った8bit(ガードバイト)の上位3bitを
  $ROUNS/$ROUNM(v2の`_rouns_from_guard32`)と同じ規則でtie判定に使う。
  実際の$FMULS(v2の`gw_mul_single`、48bit積の下位16bitをスティッキー
  無しで捨てる)を、乗算以外の演算にも一般化した形の仮説。`even`との
  差は、`coarse8`が「8bit精度に切り捨てた時点でたまたまtie相当に見える
  (masked==0x80)」が実際には切り捨てた下位ビットに非ゼロが残っている
  ため、正しい丸めなら切り上げになるはずの場面で、`coarse8`は
  tie判定(偶数丸め)をしてしまう、という「偽のtie」を作る点。
- `fmuls` (乗算のみ): v2の`gw_mul_single`をそのまま呼ぶ、既存の
  実機$FMULS命令単位モデル(下位16bit破棄、guard byteの粗いtie判定)。
  本ファイルの探索(scratchpad、対象外)では、探索した腕の範囲内では
  常に`coarse8`と一致した(=`coarse8`が`fmuls`の一般化として整合的
  だった)。ただし理論上は破棄幅が8bitではなく16bitなので、探索
  範囲外では違いうる。

## オペランドの読み取り

`tools/l4_mbf_oracle_v2.py`の`parse_literal(text, fin_algo="rep01")`を
使う(l4-s4jのREP01規則、既存予測器)。腕のオペランドは全て`!`サフィックス
付きの7桁以内の10進定数(例`17!`・`0.05!`)。

## 使い方

    python3 tools/l4_mbf_oracle_v9_s7a.py <a> <b> <op>
      例: python3 tools/l4_mbf_oracle_v9_s7a.py '17!' '12.3!' '+'

出力: 候補ごとの (sign:exp_byte:mant) と `print cdbl(a op b)` の
予測される表示文字列(v2の`print_one(..., n88=True)`)。
"""
from __future__ import annotations

import os
import sys
from fractions import Fraction
from typing import Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import l4_mbf_oracle_v2 as v2  # noqa: E402

MBF_SINGLE_BITS = 24


def read_single(text: str) -> Fraction:
    """`!`付き単精度10進定数を REP01 規則で読み、厳密値(Fraction)を返す。"""
    num = v2.parse_literal(text, fin_algo="rep01")
    if num.kind != "single":
        raise ValueError(f"{text!r} は単精度として読めなかった(kind={num.kind})")
    return num.exact()


def _round_half_even(x: Fraction) -> int:
    return v2._round_half_even(x)


def _round_half_away(x: Fraction) -> int:
    n, d = x.numerator, x.denominator
    q, r = divmod(n, d)
    return q if 2 * r < d else q + 1


def _truncate_nonneg(x: Fraction) -> int:
    return x.numerator // x.denominator


def encode_candidate(value: Fraction, nbits: int, rule: str) -> Tuple[int, int, int]:
    """value(厳密値)を候補規則ruleでnbits仮数へ丸め、(sign,exp_byte,mant)を返す。"""
    if value == 0:
        return (0, 0, 0)
    sign = 1 if value < 0 else 0
    av = -value if sign else value
    k = v2._pow2_bracket(av)
    if rule == "even":
        m = _round_half_even(av * Fraction(2) ** (nbits - k))
    elif rule == "away":
        m = _round_half_away(av * Fraction(2) ** (nbits - k))
    elif rule == "trunc":
        m = _truncate_nonneg(av * Fraction(2) ** (nbits - k))
    elif rule == "coarse8":
        w = 8
        ext = av * Fraction(2) ** (nbits + w - k)
        ext_floor = ext.numerator // ext.denominator  # (nbits+w)bit精度へ切り捨て(スティッキー無し)
        candidate = ext_floor >> w
        guard = ext_floor & ((1 << w) - 1)
        masked = guard & 0xE0
        if masked < 0x80:
            m = candidate
        elif masked > 0x80:
            m = candidate + 1
        else:
            m = candidate if candidate % 2 == 0 else candidate + 1
    else:
        raise ValueError(f"unknown rule {rule!r}")
    if m >= (1 << nbits):
        k += 1
        m = 1 << (nbits - 1)
    exp_byte = k + 128
    if exp_byte > 255:
        raise OverflowError("mbf exponent overflow")
    if exp_byte < 1:
        return (0, 0, 0)
    return (sign, exp_byte, m)


def predict_all(a_text: str, b_text: str, op: str) -> Tuple[Fraction, dict]:
    """a_text op b_text の候補ごとの単精度結果を返す。

    戻り値: (exact_fraction, {rule: (sign,exp_byte,mant)})
    """
    av = read_single(a_text)
    bv = read_single(b_text)
    if op == "+":
        exact = av + bv
    elif op == "-":
        exact = av - bv
    elif op == "*":
        exact = av * bv
    elif op == "/":
        exact = av / bv
    else:
        raise ValueError(f"unknown op {op!r}")

    out = {}
    for rule in ("even", "away", "trunc", "coarse8"):
        out[rule] = encode_candidate(exact, MBF_SINGLE_BITS, rule)
    if op == "*":
        an = v2.parse_literal(a_text, fin_algo="rep01")
        bn = v2.parse_literal(b_text, fin_algo="rep01")
        r0 = v2.gw_mul_single(an, bn)
        out["fmuls"] = (r0.sign, r0.exp, r0.mant)
    return exact, out


def cdbl_print_line(bits: Tuple[int, int, int]) -> str:
    """単精度の(sign,exp_byte,mant)を、CDBL()で倍精度化してPRINTした
    ときの表示文字列(先頭・末尾の空白は剥がして返す)にする。"""
    sign, exp_byte, mant = bits
    frac = v2.decode_mbf(sign, exp_byte, mant, MBF_SINGLE_BITS)
    dbl = v2.GwNum.from_fraction(frac, "double")
    line, _approx = v2.print_one(dbl, n88=True)
    return line.strip()


def fmt_bits(bits: Tuple[int, int, int]) -> str:
    return "%d:%02x:%06x" % bits


def main() -> int:
    if len(sys.argv) != 4:
        print(f"使い方: {sys.argv[0]} <a> <b> <op(+-*/)>", file=sys.stderr)
        return 2
    a_text, b_text, op = sys.argv[1], sys.argv[2], sys.argv[3]
    exact, out = predict_all(a_text, b_text, op)
    print(f"exact = {exact} ({float(exact)!r})")
    for rule, bits in out.items():
        print(f"  {rule:8s} {fmt_bits(bits)}  cdbl表示={cdbl_print_line(bits)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
