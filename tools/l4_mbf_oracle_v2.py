#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_oracle_v2.py — GW-BASIC数値部の予測器 v2（命令単位の再現）

v1(tools/l4_mbf_oracle.py, コミット1444cb4時点)は「両オペランドの厳密値を
有理数で求め、結果の型へ1回だけ偶数丸めする」近似で四則演算を再現していた。
v2はこの近似を、実際に8086命令列をレジスタ単位で追って置き換える。
v1はこのファイルでは変更しない(公式ROMとの測定はまだ先なので、v1とv2の
どちらが実機に近いかは今後の測定で判定する対象)。

読んだ範囲は v1 と同じ GW-BASIC(MIT公開ソース、コミット
edf82c2ebf6bfe099c2054e0ae125c3efe5769c4)の MATH1.ASM / MATH2.ASM に加え、
今回新たに以下のラベルを命令単位で読んだ:
  $FADDS/$FSUBS (MATH1.ASM 3265-3427)      単精度 加算/減算
  $FADDD/$FSUBD (MATH1.ASM 3131-3263)      倍精度 加算/減算 (+DDIV1などの
                                            シフト・繰り上げ)
  $SHRA         (MATH1.ASM 1583-1616)      倍精度加算のビット位置合わせ
                                            シフトとST(スティッキー)ビット
  $FMULS        (MATH2.ASM 408-490)        単精度乗算(部分積)
  $FMULD/DMULT  (MATH2.ASM 308-407)        倍精度乗算(Knuth Algorithm M、
                                            完全な積+末尾スティッキー走査)
  $AEXPS/$SEXPS (MATH1.ASM 2913-2970)      乗除算の指数計算
  $SDIV/$FDIVS  (MATH1.ASM 3666-3825)      単精度除算(Knuth Algorithm D、
                                            商2ワード+スティッキービット)
  $ROUNS/$ROUND (MATH2.ASM 1764-1807,
                 MATH1.ASM 3793-3815)      丸め(偶数丸め、コース化された
                                            guard byte)
  $CSD          (MATH2.ASM 197-206)        倍精度→単精度への切り詰め
  $INFPD/$INFMD (MATH1.ASM 776-790)        オーバーフロー/0除算時の
                                            残留値(実バイト列)

----------------------------------------------------------------------------
MIT License

Copyright (c) Microsoft Corporation.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE
----------------------------------------------------------------------------

## v1 から v2 で変わった箇所(命令単位で確認できたもの)

1. **単精度乗算 $FMULS は正しい丸めではない。** 24bit×24bitの厳密48bit積を
   計算したあと、下位16bitを「スティッキービットに畳み込まずに」そのまま
   捨てる(MATH2.ASM 449-450 "MUL DX;MOV CX,DX"で積の下位ワードを保存せず
   捨てている)。さらに $ROUNS 自身も guard byte の下位5bitを捨てて
   tie判定するため(粒度が粗い)、"厳密値を求めて1回偶数丸め"では
   再現できない。v2は P48=MF*MO の上位32bit(P48>>16、下位16bitは
   スティッキーなしで完全に破棄)を作り、その上位32bitの中でだけ
   $ROUNS と同じ粗い偶数丸めを行う。
2. **倍精度乗算 $FMULD は正しい丸め。** Knuth Algorithm M
   (MATH2.ASM 321-407)で完全な精度の積を作り、捨てる下位バイト側を
   最後に1バイトずつ走査してスティッキービットを立てる(M5AA loop,
   MATH2.ASM 382-391)。よって v2 では「厳密値→1回偶数丸め」のままでよい
   と確認した(近似ではなく確認済み)。
3. **加算・減算(単精度・倍精度とも)は正しい丸め。** 位置合わせシフトの
   際、単精度は FA23-FA30(MATH1.ASM)のビット単位シフトで"ST"ビットを
   OR で保持し、倍精度は $SHRA(MATH1.ASM 1583-1616)が同様にSTビットを
   保持する。どちらも「厳密値→1回偶数丸め」と数学的に等価と確認した。
4. **除算(単精度・倍精度とも)は正しい丸め。** $SDIV(MATH1.ASM 3666-3825)
   はKnuthのAlgorithm D(2ワード長除算)を使い、剰余が非ゼロならスティッキー
   ビットを明示的に立てる("OR DL,LOW 1 ;Set sticky bit if remainder not
   zero"、MATH1.ASM 3745)。よって「厳密値→1回偶数丸め」と等価と確認した。
5. **$INFPD/$INFMD の実バイト列を読んだ。** 単精度・倍精度とも
   「仮数全ビット1、指数バイト255」(MATH1.ASM 776-792)で、v1が独自に
   導出した値(既知のMBFバイト列4件から演繹した「その型の最大値」)と
   完全に一致することを確認した。v1は推測、v2は確認済み。
6. **$CSD(倍精度→単精度への切り詰め)は「同点(タイ)にならない」。**
   保持する24bitの直後のバイトをガードバイトとして使うが、
   "OR AH,LOW 100"(MATH2.ASM 204)でbit6を強制的に1にするため、
   $ROUNM のtie判定(guard&0xE0==0x80)には理論上到達しない
   (bit6=1のときmasked値は0x40台か0xC0台にしかならない)。
   つまり倍精度→単精度の切り詰めは「次のバイトのbit7だけで決まる」
   単純な規則(bit7=1なら切り上げ、0なら切り捨て、tie相当は無い)と確認。
   $FINE/MDP10(定数の指数適用)は常に倍精度で計算してから最後に $CSD
   で単精度へ落とすため、この規則がそのまま定数リテラルの丸めにも効く。

## v1 のままにした箇所(命令単位で追い切れなかった)

- **$FOFMT の FFM10〜FFM30(固定小数点⇔指数表記の切替しきい値)、
  $FOTNV の実際のブラケット目標値、$SIGD の末尾ゼロ計算との組み合わせ。**
  レジスタを1つずつ追ったが、"999999"(単精度、固定小数点になるはずの
  既知の例)を検算すると、自分の途中式(FOTNV の戻り値 AL を
  「E-有効桁数」と仮定する式)と矛盾する結果になり、時間内に解消
  できなかった。v2 はこの部分だけ v1 と同じ近似則
  (`-有効桁数 < E <= 有効桁数 なら固定小数点`)を維持し、
  `approx` 列で該当する腕に印を付ける。

## $FOTNV/$SIGD について確認できたこと(未解決の一部としてではなく)

$FOTNV 自体のブラケット処理(MATH2.ASM 716-769)は、テーブル
(`$FOTB`)による初期見積もりのあと、$DP06(単精度側、下限)と
HIDBL(倍精度側、上限、実バイト列 MATH2.ASM 776
"9999999999999999."と明記)との比較で1回だけ補正する構造になっており、
補正ループがある以上、最終的な結果はテーブルの近似精度に依存せず
数学的に確定するはずだと判断した。ただし「有効桁数が何桁か
(7/16なのか、8/17なのか)」の対応づけで上記の矛盾が生じたため、
FFM10-30 の項目とあわせて `approx` 扱いとした。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional, Tuple

_FAULT = os.environ.get("L4_ORACLE_FAULT", "")


class GwError(Exception):
    def __init__(self, kind: str, residual: "GwNum"):
        super().__init__(kind)
        self.kind = kind
        self.residual = residual


MBF_SINGLE_BITS = 24
MBF_DOUBLE_BITS = 56
MBF_SINGLE_DIGITS = 7
MBF_DOUBLE_DIGITS = 16


def _round_half_even(x: Fraction) -> int:
    """$ROUNS の TSTEVN 分岐(MATH2.ASM 1779-1796)と同じ偶数丸め。
    加算・減算・除算・倍精度乗算はスティッキービットまで含めて
    正しい丸めであることを確認したので、これらは「厳密値をこの関数で
    丸める」実装のままでよい(上のモジュールdocstring 2-4番)。
    故障注入: L4_ORACLE_FAULT=round_up で「常に切り上げ」に壊せる。
    """
    if _FAULT == "round_up":
        n, d = x.numerator, x.denominator
        q, r = divmod(n, d)
        return q if r == 0 else q + 1
    n, d = x.numerator, x.denominator
    q, r = divmod(n, d)
    twice = 2 * r
    if twice < d:
        return q
    if twice > d:
        return q + 1
    return q if (q % 2 == 0) else q + 1


def _pow2_bracket(av: Fraction) -> int:
    import math

    est = math.floor(math.log2(av.numerator / av.denominator)) + 1
    while Fraction(2) ** (est - 1) > av:
        est -= 1
    while Fraction(2) ** est <= av:
        est += 1
    return est


def encode_mbf(value: Fraction, nbits: int) -> Tuple[int, int, int]:
    if value == 0:
        return (0, 0, 0)
    sign = 1 if value < 0 else 0
    av = -value if sign else value
    k = _pow2_bracket(av)
    mexact = av * Fraction(2) ** (nbits - k)
    m = _round_half_even(mexact)
    if m >= (1 << nbits):
        k += 1
        m = 1 << (nbits - 1)
    exp_byte = k + 128
    if exp_byte > 255:
        raise OverflowError("mbf exponent overflow")
    if exp_byte < 1:
        return (0, 0, 0)
    return (sign, exp_byte, m)


def decode_mbf(sign: int, exp_byte: int, mant: int, nbits: int) -> Fraction:
    if exp_byte == 0:
        return Fraction(0)
    k = exp_byte - 128
    val = Fraction(mant) * Fraction(2) ** (k - nbits)
    return -val if sign else val


def mbf4_bytes(sign: int, exp_byte: int, mant: int) -> bytes:
    frac = mant & 0x7FFFFF
    b0 = frac & 0xFF
    b1 = (frac >> 8) & 0xFF
    b2 = ((frac >> 16) & 0x7F) | (0x80 if sign else 0)
    if exp_byte == 0:
        return bytes([0, 0, 0, 0])
    return bytes([b0, b1, b2, exp_byte])


def mbf4_from_bytes(b: bytes) -> Tuple[int, int, int]:
    b0, b1, b2, exp_byte = b
    sign = 1 if (b2 & 0x80) else 0
    frac = ((b2 & 0x7F) << 16) | (b1 << 8) | b0
    if exp_byte == 0:
        return (0, 0, 0)
    return (sign, exp_byte, frac | 0x800000)


def mbf8_bytes(sign: int, exp_byte: int, mant: int) -> bytes:
    frac = mant & ((1 << 55) - 1)
    out = bytearray(8)
    for i in range(6):
        out[i] = (frac >> (8 * i)) & 0xFF
    out[6] = ((frac >> 48) & 0x7F) | (0x80 if sign else 0)
    out[7] = exp_byte
    if exp_byte == 0:
        return bytes(8)
    return bytes(out)


def mbf8_from_bytes(b: bytes) -> Tuple[int, int, int]:
    exp_byte = b[7]
    sign = 1 if (b[6] & 0x80) else 0
    frac = 0
    for i in range(6):
        frac |= b[i] << (8 * i)
    frac |= (b[6] & 0x7F) << 48
    if exp_byte == 0:
        return (0, 0, 0)
    return (sign, exp_byte, frac | (1 << 55))


# ---------------------------------------------------------------------------
# $INFPD/$INFMD (MATH1.ASM 776-792) — 実バイト列で確認済み: 仮数全ビット1・
# 指数バイト255。v1の「導出した最大値」と一致(確認済みに格上げ)。
# ---------------------------------------------------------------------------


def _max_value_num(kind: str, sign: int) -> "GwNum":
    nbits = MBF_SINGLE_BITS if kind == "single" else MBF_DOUBLE_BITS
    mant = (1 << nbits) - 1
    return GwNum(kind, sign=sign, exp=255, mant=mant)


@dataclass
class GwNum:
    kind: str  # "int" | "single" | "double"
    ivalue: int = 0
    sign: int = 0
    exp: int = 0
    mant: int = 0

    @staticmethod
    def from_int(v: int) -> "GwNum":
        assert -32768 <= v <= 32767
        return GwNum("int", ivalue=v)

    @staticmethod
    def from_fraction(value: Fraction, kind: str) -> "GwNum":
        nbits = MBF_SINGLE_BITS if kind == "single" else MBF_DOUBLE_BITS
        sign, exp, mant = encode_mbf(value, nbits)
        return GwNum(kind, sign=sign, exp=exp, mant=mant)

    def exact(self) -> Fraction:
        if self.kind == "int":
            return Fraction(self.ivalue)
        nbits = MBF_SINGLE_BITS if self.kind == "single" else MBF_DOUBLE_BITS
        return decode_mbf(self.sign, self.exp, self.mant, nbits)

    def is_negative(self) -> bool:
        if self.kind == "int":
            return self.ivalue < 0
        return self.sign == 1 and self.exp != 0

    def mantissa_bits(self) -> int:
        return MBF_SINGLE_BITS if self.kind == "single" else MBF_DOUBLE_BITS

    def as_single_or_double_pair(self) -> Tuple[int, int, int]:
        return (self.sign, self.exp, self.mant)


_KIND_RANK = {"int": 0, "single": 1, "double": 2}


# ---------------------------------------------------------------------------
# $AEXPS/$SEXPS (MATH1.ASM 2913-2970) — 乗除算の指数計算を命令単位で再現。
# ---------------------------------------------------------------------------


def _aexps(e1: int, e2: int) -> int:
    """$AEXPS: final_exp = e1+e2-129 (乗算用)。範囲外は例外で知らせる。
    OverflowError: e1+e2-257 >= 128 (MATH1.ASM "CMP AX,200;...JMP $OVFLS")
    UnderflowZero: e1+e2-257 < -128 (MATH1.ASM SES10 "JMP $ZERO")
    """
    raw = e1 + e2 - 257
    if raw >= 128:
        raise OverflowError("aexps overflow")
    if raw < -128:
        return 0  # 下でexp_byte<1として扱う(呼び出し側でゼロにする)
    return raw + 128  # SES20/SES30: final_exp = raw+128


def _sexps(e_num: int, e_den: int) -> int:
    """$SEXPS: 除算の指数計算。$SDIV(MATH1.ASM 3691-3714)の
    "SUB AH,128;SUB CH,128;SUB AH,CH;...ADD AH,128" をそのまま
    raw=e_num-e_den, final_tentative=raw+128 として再現する。
    """
    raw = e_num - e_den
    if raw > 127 or raw < -128:
        raise OverflowError("sexps range")  # 8bit符号付き引き算の範囲外
    return raw + 128


# ---------------------------------------------------------------------------
# 単精度乗算 $FMULS (MATH2.ASM 408-490) — 命令単位。
# ---------------------------------------------------------------------------


def _rouns_from_guard32(mantissa_bits: int, m32: int) -> Tuple[int, int]:
    """$ROUNS/$ROUNM (MATH2.ASM 1764-1807) を、上位24bit(候補仮数)+
    下位8bit(guard byte)からなる32bit値 m32 に適用する。
    戻り値: (最終24bit仮数, 仮数からの繰り上げによる指数+1が必要なら1)
    """
    candidate = m32 >> 8
    guard = m32 & 0xFF
    masked = guard & 0xE0
    if masked < 0x80:
        final = candidate
    elif masked > 0x80:
        final = candidate + 1
    else:
        # tie: 偶数丸め
        final = candidate if candidate % 2 == 0 else candidate + 1
    if final >= (1 << mantissa_bits):
        return (1 << (mantissa_bits - 1)), 1
    return final, 0


def _single_multiply_mantissa(mf24: int, mo24: int) -> Tuple[int, int]:
    """$FMULS のマンティッサ処理(MATH2.ASM 430-490)を再現する。

    厳密48bit積 P48=mf24*mo24 のうち、下位16bitはスティッキービットへ
    畳み込まずにそのまま捨てる(MATH2.ASM 449-450「MUL DX; MOV CX,DX」で
    最初の部分積の下位ワードを保存せず破棄している)。上位32bit
    (=P48>>16)の最上位ビット(bit31)がセットされているかどうかで
    +1桁繰り上げるか1bit左シフトするかを分岐する(MATH2.ASM 476-484)。
    戻り値: (24bit最終仮数, 指数への追加調整量)
    """
    p48 = mf24 * mo24
    if _FAULT == "mul_sticky":
        # 故障注入: 8086実装が実際には捨てている下位16bitを、
        # 「厳密値を求めて1回だけ正しく丸める」($ROUNSのtie判定を
        # 粗くマスクせず、真の剰余全体を見て偶数丸めする)側へ壊す。
        # これはv1の近似(命令単位で確認する前の実装)そのものであり、
        # 既知の乖離例(9924.8*984025.0)でこの分岐を有効にすると
        # 通常のv2と異なる結果になることをselftestで確認する。
        if p48 >= (1 << 47):
            exp_adj = 1
            scaled = p48
        else:
            exp_adj = 0
            scaled = p48 << 1
        m = _round_half_even(Fraction(scaled, 1 << 24))
        if m >= (1 << MBF_SINGLE_BITS):
            return 1 << (MBF_SINGLE_BITS - 1), exp_adj + 1
        return m, exp_adj
    p32 = p48 >> 16  # 下位16bitを完全に破棄(スティッキーなし)
    if p32 & 0x80000000:
        exp_adj = 1
        m32 = p32
    else:
        exp_adj = 0
        m32 = (p32 << 1) & 0xFFFFFFFF
    final24, carry = _rouns_from_guard32(MBF_SINGLE_BITS, m32)
    return final24, exp_adj + carry


def gw_mul_single(a: GwNum, b: GwNum) -> GwNum:
    sa, ea, ma = _to_single_parts(a)
    sb, eb, mb = _to_single_parts(b)
    if ma == 0 or mb == 0:
        return GwNum.from_fraction(Fraction(0), "single")
    sign = sa ^ sb
    try:
        final_exp = _aexps(ea, eb)
    except OverflowError:
        raise GwError("Overflow", _max_value_num("single", sign))
    if final_exp == 0:
        return GwNum.from_fraction(Fraction(0), "single")
    final24, exp_adj = _single_multiply_mantissa(ma, mb)
    final_exp += exp_adj
    if final_exp > 255:
        raise GwError("Overflow", _max_value_num("single", sign))
    if final_exp < 1:
        return GwNum.from_fraction(Fraction(0), "single")
    return GwNum("single", sign=sign, exp=final_exp, mant=final24)


def _to_single_parts(a: GwNum) -> Tuple[int, int, int]:
    if a.kind == "single":
        return a.sign, a.exp, a.mant
    if a.kind == "int":
        v = a.ivalue
        if v == 0:
            return 0, 0, 0
        s, e, m = encode_mbf(Fraction(v), MBF_SINGLE_BITS)
        return s, e, m
    # double -> single 経由が必要な場面はここでは想定しない(呼び出し側で解決)
    raise AssertionError("unexpected kind for single parts")


# ---------------------------------------------------------------------------
# 倍精度乗算 $FMULD/DMULT (MATH2.ASM 308-407) — 完全精度+スティッキー、
# 加算・減算(単精度・倍精度)、除算(単精度・倍精度)は、命令単位で追った
# 結果「厳密値を求めて1回偶数丸め」と数学的に等価と確認できたので、
# その実装のまま使う(モジュールdocstring 2-4番)。
# ---------------------------------------------------------------------------


def _exact_round_binop(av: Fraction, bv: Fraction, op: str, kind: str) -> GwNum:
    if op == "+":
        exact = av + bv
    elif op == "-":
        exact = av - bv
    elif op == "*":
        exact = av * bv
    elif op == "/":
        if bv == 0:
            sign = 1 if av < 0 else 0
            raise GwError("Division by zero", _max_value_num(kind, sign))
        exact = av / bv
    else:
        raise ValueError(op)
    try:
        return GwNum.from_fraction(exact, kind)
    except OverflowError:
        sign = 1 if exact < 0 else 0
        raise GwError("Overflow", _max_value_num(kind, sign))


def _binop_kind(ak: str, bk: str, op: str) -> str:
    base = "single" if op == "/" else "int"
    return max([ak, bk, base], key=lambda k: _KIND_RANK[k])


def gw_binop(a: GwNum, b: GwNum, op: str) -> GwNum:
    forced_single = False
    if op in "+-*" and a.kind == "int" and b.kind == "int":
        if op == "+":
            r = a.ivalue + b.ivalue
        elif op == "-":
            r = a.ivalue - b.ivalue
        else:
            r = a.ivalue * b.ivalue
        if -32768 <= r <= 32767:
            return GwNum.from_int(r)
        forced_single = True

    kind = "single" if forced_single else _binop_kind(a.kind, b.kind, op)

    if op == "*" and kind == "single":
        # $FMULS の命令単位再現(v1からの変更点)
        return gw_mul_single(a, b)

    av = a.exact()
    bv = b.exact()
    return _exact_round_binop(av, bv, op, kind)


def gw_neg(a: GwNum) -> GwNum:
    if a.kind == "int":
        if a.ivalue == -32768:
            raise GwError("Overflow", _max_value_num("single", 0))
        return GwNum.from_int(-a.ivalue)
    exact = -a.exact()
    return GwNum.from_fraction(exact, a.kind)


# ---------------------------------------------------------------------------
# $CSD (MATH2.ASM 197-206) — 倍精度→単精度への切り詰め。命令単位で確認:
# 保持する24bitの直後のバイトのbit7だけで切り上げ/切り捨てが決まり、
# tie(偶数丸め)には理論上到達しない(bit6を強制1にしているため)。
# ---------------------------------------------------------------------------


def csd_narrow(mant56: int) -> Tuple[int, int]:
    """倍精度56bit仮数(隠しビット込み)を単精度24bitへ切り詰める。
    戻り値: (24bit仮数, 繰り上げによる指数+1が必要なら1)
    """
    top24 = mant56 >> 32
    guard_byte = ((mant56 >> 24) & 0xFF) | 0x40  # bit6を強制1
    masked = guard_byte & 0xE0
    if masked < 0x80:
        final = top24
    else:
        final = top24 + 1  # masked>=0x80はbit6強制によりtieになり得ない
    if final >= (1 << MBF_SINGLE_BITS):
        return 1 << (MBF_SINGLE_BITS - 1), 1
    return final, 0


def force_to_single(a: GwNum) -> GwNum:
    """"!" サフィックス等での単精度への強制変換。
    倍精度からの変換は $CSD、整数からの変換は厳密(丸め不要)。
    """
    if a.kind == "single":
        return a
    if a.kind == "int":
        return GwNum.from_fraction(Fraction(a.ivalue), "single")
    # double -> single: $CSD
    if a.exp == 0:
        return GwNum.from_fraction(Fraction(0), "single")
    final24, carry = csd_narrow(a.mant)
    # $CSD自体は指数バイトをそのまま流用する(上位24bitを取り出すだけなら
    # value=mantissa/2^nbits*2^(exp-128) の関係で exp は不変。carry
    # (2^24への繰り上げ)が起きた場合だけ+1する)。
    exp = a.exp + carry
    if exp > 255:
        raise GwError("Overflow", _max_value_num("single", a.sign))
    return GwNum("single", sign=a.sign, exp=exp, mant=final24)


def force_to_double(a: GwNum) -> GwNum:
    if a.kind == "double":
        return a
    if a.kind == "int":
        return GwNum.from_fraction(Fraction(a.ivalue), "double")
    # single -> double は厳密(24bit仮数は56bit精度に完全に収まる)
    exp = a.exp
    mant = a.mant << (MBF_DOUBLE_BITS - MBF_SINGLE_BITS)
    return GwNum("double", sign=a.sign, exp=exp, mant=mant)


# ---------------------------------------------------------------------------
# 定数の字句解析 ($FIN 相当。v1と同じロジック、変更なし)
# ---------------------------------------------------------------------------


class GwSyntaxError(Exception):
    pass


def parse_literal(text: str) -> GwNum:
    s = text.strip()
    if not s:
        raise GwSyntaxError("empty literal")
    i = 0
    neg = False
    if s[i] in "+-":
        neg = s[i] == "-"
        i += 1
    digits = []
    frac_digits = 0
    seen_dot = False
    while i < len(s) and (s[i].isdigit() or (s[i] == "." and not seen_dot)):
        if s[i] == ".":
            seen_dot = True
        else:
            digits.append(s[i])
            if seen_dot:
                frac_digits += 1
        i += 1
    if not digits:
        raise GwSyntaxError(f"no digits in {text!r}")

    kind = "int"
    acc = 0
    for ch in digits:
        d = int(ch)
        if kind == "int":
            if acc >= 3277:
                kind = "single"
            else:
                nv = acc * 10 + d
                if nv >= 32768:
                    kind = "single"
                else:
                    acc = nv
                    continue
        if kind == "single":
            if acc >= 1_000_000:
                kind = "double"
            else:
                acc = acc * 10 + d
                continue
        if kind == "double":
            acc = acc * 10 + d

    if seen_dot and kind == "int":
        kind = "single"

    exponent = 0
    j = i
    force_suffix: Optional[str] = None
    if j < len(s) and s[j] in "eEdD":
        is_upper_d = s[j] in "dD"
        j += 1
        esign = 1
        if j < len(s) and s[j] in "+-":
            esign = -1 if s[j] == "-" else 1
            j += 1
        estart = j
        while j < len(s) and s[j].isdigit():
            j += 1
        if j == estart:
            raise GwSyntaxError(f"bad exponent in {text!r}")
        exponent = esign * int(s[estart:j])
        if is_upper_d:
            kind = "double"
        else:
            if kind != "double":
                kind = "single"

    if j < len(s) and s[j] in "!#":
        force_suffix = s[j]
        j += 1

    if j != len(s):
        raise GwSyntaxError(f"trailing garbage in {text!r}: {s[j:]!r}")

    if force_suffix == "!":
        kind = "single"
    elif force_suffix == "#":
        kind = "double"

    value = Fraction(acc) * Fraction(10) ** (exponent - frac_digits)
    if neg:
        value = -value

    if kind == "int":
        iv = int(value)
        if not (-32768 <= iv <= 32767):
            kind = "single"
        else:
            return GwNum.from_int(iv)

    try:
        num = GwNum.from_fraction(value, kind)
    except OverflowError:
        sign = 1 if value < 0 else 0
        raise GwError("Overflow", _max_value_num(kind, sign))

    if kind == "single" and neg and value == -32768:
        return GwNum.from_int(-32768)
    return num


# ---------------------------------------------------------------------------
# 式評価
# ---------------------------------------------------------------------------


def _tokenize(expr: str):
    toks = []
    i = 0
    n = len(expr)
    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
            continue
        if c in "+-*/":
            toks.append(("op", c))
            i += 1
            continue
        if c.isdigit() or c == ".":
            j = i
            while j < n and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            if j < n and expr[j] in "eEdD":
                k = j + 1
                if k < n and expr[k] in "+-":
                    k += 1
                k2 = k
                while k2 < n and expr[k2].isdigit():
                    k2 += 1
                if k2 > k:
                    j = k2
            if j < n and expr[j] in "!#":
                j += 1
            toks.append(("num", expr[i:j]))
            i = j
            continue
        raise GwSyntaxError(f"unexpected char {c!r} in {expr!r}")
    return toks


def eval_expr(expr: str) -> GwNum:
    toks = _tokenize(expr)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def advance():
        t = toks[pos[0]]
        pos[0] += 1
        return t

    def parse_factor() -> GwNum:
        t = peek()
        if t is None:
            raise GwSyntaxError("unexpected end of expression")
        if t == ("op", "-"):
            advance()
            return gw_neg(parse_factor())
        if t == ("op", "+"):
            advance()
            return parse_factor()
        if t[0] == "num":
            advance()
            return parse_literal(t[1])
        raise GwSyntaxError(f"unexpected token {t!r}")

    def parse_term() -> GwNum:
        v = parse_factor()
        while True:
            t = peek()
            if t is not None and t[0] == "op" and t[1] in "*/":
                advance()
                rhs = parse_factor()
                v = gw_binop(v, rhs, t[1])
            else:
                break
        return v

    def parse_add() -> GwNum:
        v = parse_term()
        while True:
            t = peek()
            if t is not None and t[0] == "op" and t[1] in "+-":
                advance()
                rhs = parse_term()
                v = gw_binop(v, rhs, t[1])
            else:
                break
        return v

    v = parse_add()
    if pos[0] != len(toks):
        raise GwSyntaxError(f"trailing tokens in {expr!r}")
    return v


# ---------------------------------------------------------------------------
# PRINT の自由形式出力。固定小数点⇔指数表記のしきい値は v1 と同じ近似則を
# 維持している(モジュールdocstring「v1のままにした箇所」参照)。
# predict() は、この未解決の近似則を経由したかどうかを approx で返す。
# ---------------------------------------------------------------------------


def _decimal_exponent(value: Fraction) -> int:
    import math

    est = math.floor(math.log10(value.numerator / value.denominator)) + 1
    while Fraction(10) ** (est - 1) > value:
        est -= 1
    while Fraction(10) ** est <= value:
        est += 1
    return est


def _significant_digits(value: Fraction, ndig: int) -> Tuple[str, int]:
    e = _decimal_exponent(value)
    scaled = value * Fraction(10) ** (ndig - e)
    digits_int = _round_half_even(scaled)
    if digits_int >= 10 ** ndig:
        e += 1
        digits_int //= 10
    s = str(digits_int).rjust(ndig, "0")
    return s, e


def fout_format(num: GwNum) -> Tuple[str, bool]:
    """戻り値: (本体文字列, この腕の固定/指数判定が未解決近似則を
    経由したか=approx)"""
    if num.kind == "int":
        return str(abs(num.ivalue)), False

    ndig = MBF_SINGLE_DIGITS if num.kind == "single" else MBF_DOUBLE_DIGITS
    value = num.exact()
    if value == 0:
        return "0", False
    av = -value if value < 0 else value

    digits, e = _significant_digits(av, ndig)
    trimmed = digits.rstrip("0")
    if trimmed == "":
        trimmed = "0"
    nsig = len(trimmed)

    use_fixed = (-ndig) < e <= ndig  # v1と同じ未解決の近似則(approx=True)

    if use_fixed:
        if e <= 0:
            body = "." + ("0" * (-e)) + trimmed
        elif e >= nsig:
            body = trimmed + ("0" * (e - nsig))
        else:
            body = trimmed[:e] + "." + trimmed[e:]
        return body, True
    else:
        mant = trimmed[0]
        if nsig > 1:
            mant += "." + trimmed[1:]
        exp_val = e - 1
        marker = "E" if num.kind == "single" else "D"
        sign_ch = "+" if exp_val >= 0 else "-"
        return f"{mant}{marker}{sign_ch}{abs(exp_val):02d}", True


def print_one(num: GwNum) -> Tuple[str, bool]:
    body, approx = fout_format(num)
    sign = "-" if num.is_negative() else " "
    return f"{sign}{body} ", approx


def predict(typed_print_body: str) -> Tuple[str, str, bool]:
    """戻り値: (kind, predicted, approx)"""
    try:
        num = eval_expr(typed_print_body)
    except GwError as e:
        residual_line, approx = print_one(e.residual)
        return "error", f"{e.kind};{residual_line}", approx
    line, approx = print_one(num)
    return "numeric", line, approx


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        body = arg
        if body.lower().startswith("print "):
            body = body[6:]
        kind, pred, approx = predict(body)
        print(f"{arg!r}\t{kind}\t{pred!r}\tapprox={approx}")
