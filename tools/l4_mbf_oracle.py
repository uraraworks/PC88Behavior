#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_oracle.py — GW-BASIC 数値部の予測器（M7 / L4 第4段階の事前登録用）

位置づけ: PC88Behavior は「公式 N88 ROM を読まずに測る」プロジェクトである。
本ファイルは公式 ROM を一切参照しない。移植元は Microsoft が 2020-05-21 に
MIT ライセンスで公開した GW-BASIC のソース（コミット
edf82c2ebf6bfe099c2054e0ae125c3efe5769c4）のうち、数値演算を担う
MATH1.ASM / MATH2.ASM（Intel 8086 アセンブリ、Microsoft Binary Format
[MBF] の浮動小数点パック）と、定数の字句処理に触れる GWMAIN.ASM の該当箇所
だけである。読んだのはこの3ファイルの数値関連ラベルのみで、GW-BASIC の
他の部分（画面・ディスク・BASIC文一般等）は読んでいない。

docs/notes/l4-design.md「2. GW-BASIC は数値部だけ移植する」の方針どおり、
トークン番号やインタプリタ構造は一切採らない。本ファイルはあくまで
「PRINT の数値出力を測定より先に予測する」ための道具であり、実装の正解では
ない（docs/notes/l4-mbf-oracle.md 参照。推測で埋めた箇所を区別して列挙）。

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

対応表（このファイルの関数 → MATH1.ASM/MATH2.ASM のラベル）:

  encode_mbf / decode_mbf      $NORMS / $NORMD / $ROUNS ($ROUNM)
                                  (MATH2.ASM 1105-1141, 1764-1807)
                                  正規化とラウンディング（偶数丸め）の
                                  再現。$ROUNS の TSTEVN 分岐（ZF=1 なら
                                  偶数丸め）をそのまま Python の
                                  round-half-to-even で表す。
  mbf4_bytes / mbf8_bytes      $FAC のバイトレイアウト（指数1バイト＋
                                  符号+仮数3or7バイト、符号は仮数最上位
                                  バイトの最上位ビット）。既知定数
                                  （1.0=00 00 00 81 等、MATH1.ASM 冒頭の
                                  $DP01 等の定数群と同型）から復元。
  parse_literal                 $FIN / $FIDIG / $FINEX / $FINFC
                                  (MATH1.ASM 2059-2161, MATH2.ASM 1-181)
                                  数字の逐次累積とinteger→single→double
                                  の昇格しきい値（$FIDIG: BX>=3277 で
                                  single化、FAC>=100万相当でdouble化）、
                                  "."で最低single化、"!"/"#"で強制、
                                  "E"/"e"で単精度強制（既にdoubleなら
                                  そのまま）、"D"/"d"で倍精度強制
                                  ($FINEX 100-110, $FINFC 186)。
                                  小文字 e/d の扱いは $FINCH テーブル
                                  (MATH1.ASM 670-678) が大文字と同じ
                                  ジャンプ先を持つことから直接確認した
                                  （大文字化はしていない）。
  gw_add / gw_sub / gw_mul      FADDS/FSUB/FMULT の入口 (MATH1.ASM
  gw_div                        2415-2430, 2547) と、整数溢れ時の単精度
                                  昇格・"/"の最低単精度昇格
                                  (docs/notes/l4-design.md 段階4の指示
                                  および $FIN の $VALTP 昇格則から类推)。
                                  実際の加算は本ファイルでは「両オペランド
                                  の正確な値を厳密有理数で計算し、結果型の
                                  精度へ1回だけ偶数丸めする」方式で近似する
                                  （$FADDS 内部のガードバイト蓄積を命令列
                                  単位では追っていない。詳細は
                                  docs/notes/l4-mbf-oracle.md）。
  overflow / div-by-zero        $OVFLS / $DIV0S / DOINF (MATH1.ASM
                                  1252-1313)。エラーメッセージを出した後も
                                  実行が止まらず、FAC にその型の最大値
                                  （符号は演算結果ないし被除数の符号）を
                                  代入して処理を継続する、という直接モード
                                  PRINT にとって重要な挙動をここから確認した
                                  （$FLGOV による二重メッセージ抑制、
                                  TRAPER のエラートラップ有無判定は本予測器
                                  の対象外）。
  fout_format                   $FOFMT / $FOTNV / $SIGD (MATH1.ASM
                                  1322-1449, MATH2.ASM 1809-1880)。
                                  有効桁数予算（single=7, double=16。
                                  MATH1.ASM 1338-1341, 1364, 1384 由来）、
                                  指数表記/固定小数点の切替、先頭"0"の
                                  省略、末尾"0"と小数点の省略、指数部の
                                  "E"/"D"記号 (MATH1.ASM 1424-1426) と
                                  符号付き2桁 (MATH1.ASM 1435-1442)。
                                  固定小数点⇔指数表記のしきい値そのもの
                                  (FFM10-FFM30, MATH1.ASM 1338-1399) は
                                  分岐が細かく、命令単位までは追い切れて
                                  いない。本ファイルでは「指数E(値が
                                  d.ddd×10^Eの形のE)が -有効桁数 <
                                  E <= 有効桁数 の範囲なら固定小数点、
                                  それ以外は指数表記」という近似則を採用
                                  している（既知の実例 .1/.01/.001が固定・
                                  1E-10が指数、999999/9999999が固定・
                                  1E10が指数、と矛盾しないことは確認したが、
                                  境界そのものをアセンブリから逐次確認しては
                                  いない。近似・推測として
                                  docs/notes/l4-mbf-oracle.md に明記する）。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# 故障注入（selftest 用）。環境変数 L4_ORACLE_FAULT を立てると丸めや型判定を
# わざと壊す。通常運用では未設定（何も変えない）。
# ---------------------------------------------------------------------------
_FAULT = os.environ.get("L4_ORACLE_FAULT", "")


class GwError(Exception):
    """GW-BASIC のエラー（$OVFLS/$DIV0S 相当）。

    kind: "Overflow" または "Division by zero"（docs/spec/l4-basic.md
    第6.1節のマニュアル表と同じ文言）。
    residual: エラー後も FAC に残る値（続けて PRINT される数値行があれば
    その GwNum）。$FLGOV によりエラー直後の once-only 抑制がある版もあるが、
    本予測器では「そのままエラー後の数値が出力される」($OVFLS/$DIV0S が
    処理を継続する経路、MATH1.ASM 1263-1288)を採用する。
    """

    def __init__(self, kind: str, residual: "GwNum"):
        super().__init__(kind)
        self.kind = kind
        self.residual = residual


# ---------------------------------------------------------------------------
# MBF (Microsoft Binary Format) のバイト表現と厳密有理数への変換
# ---------------------------------------------------------------------------

MBF_SINGLE_BITS = 24  # 隠しビット込みの仮数ビット数（$FAC の 3 バイト分）
MBF_DOUBLE_BITS = 56  # 隠しビット込みの仮数ビット数（$FAC の 7 バイト分）
MBF_SINGLE_DIGITS = 7   # $FOFMT: MATH1.ASM 1338 "print 7 digits"
MBF_DOUBLE_DIGITS = 16  # $FOFMT: MATH1.ASM 1364 "ADD AL,LOW 16D"


def _round_half_even(x: Fraction) -> int:
    """厳密有理数 x を最近接偶数丸めで整数化する。

    $ROUNS (MATH2.ASM 1779-1796) の TSTEVN 分岐（ガードバイトがちょうど
    半分のときだけ偶数丸め）に対応する。故障注入 L4_ORACLE_FAULT=round_up
    で「常に切り上げ」に壊せる（selftest 用）。
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
    # ちょうど半分 -> 偶数丸め
    return q if (q % 2 == 0) else q + 1


def _pow2_bracket(av: Fraction) -> int:
    """av (>0) に対し 2**(k-1) <= av < 2**k となる整数 k を返す。"""
    import math

    est = math.floor(math.log2(av.numerator / av.denominator)) + 1
    while Fraction(2) ** (est - 1) > av:
        est -= 1
    while Fraction(2) ** est <= av:
        est += 1
    return est


def encode_mbf(value: Fraction, nbits: int) -> Tuple[int, int, int]:
    """厳密有理数 value を (sign, exp_byte, mantissa) にパックする。

    exp_byte=0 は 0.0（$ZERO/$DZERO, MATH1.ASM 1465-1478）。
    exp_byte>255 になる場合は GwError("Overflow", ...) を送出元で扱う
    （このヘルパ自体は OverflowError を投げる）。
    指数下限を割り込む場合（アンダーフロー）は、$NORMS の NOR17 /
    $NORMD の NORD50 と同じく静かに 0 を返す（エラーにしない）。
    """
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
        return (0, 0, 0)  # アンダーフロー: 静かに0 (NOR17/NORD50)
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
    mant = frac | 0x800000
    return (sign, exp_byte, mant)


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
    mant = frac | (1 << 55)
    return (sign, exp_byte, mant)


# ---------------------------------------------------------------------------
# GW-BASIC の数値。int(16bit 二の補数) / single(MBF4) / double(MBF8)
# ---------------------------------------------------------------------------


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

    def is_zero(self) -> bool:
        return self.exact() == 0

    def is_negative(self) -> bool:
        if self.kind == "int":
            return self.ivalue < 0
        return self.sign == 1 and self.exp != 0


_KIND_RANK = {"int": 0, "single": 1, "double": 2}


def _max_value(kind: str, sign: int) -> GwNum:
    """DOINF (MATH1.ASM 1290-1313) 相当: その型で表現できる最大値。"""
    nbits = MBF_SINGLE_BITS if kind == "single" else MBF_DOUBLE_BITS
    mant = (1 << nbits) - 1
    exp = 255
    return GwNum(kind, sign=sign, exp=exp, mant=mant)


def _binop_kind(ak: str, bk: str, op: str) -> str:
    if op == "/":
        # "/" は最低でも single (docs/notes/l4-design.md 段階4指示)
        base = "single"
    else:
        base = "int"
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
        # 整数のまま表現できない -> 単精度に昇格して計算し直す
        # ($FIDIG のBX溢れ時のCSIパターンと同種の昇格。MATH1.ASM 2568-2582
        # FLOATR / INEGAD、$FIDIG FFI10 参照)
        forced_single = True

    kind = "single" if forced_single else _binop_kind(a.kind, b.kind, op)
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
            residual = _max_value(kind, sign)
            raise GwError("Division by zero", residual)
        exact = av / bv
    else:
        raise ValueError(f"unknown op {op!r}")

    try:
        return GwNum.from_fraction(exact, kind)
    except OverflowError:
        sign = 1 if exact < 0 else 0
        residual = _max_value(kind, sign)
        raise GwError("Overflow", residual)


def gw_neg(a: GwNum) -> GwNum:
    if a.kind == "int":
        if a.ivalue == -32768:
            raise GwError("Overflow", _max_value("single", 0))
        return GwNum.from_int(-a.ivalue)
    exact = -a.exact()
    return GwNum.from_fraction(exact, a.kind)


# ---------------------------------------------------------------------------
# 定数の字句解析 ($FIN 相当)
# ---------------------------------------------------------------------------


class GwSyntaxError(Exception):
    pass


def parse_literal(text: str) -> GwNum:
    """"[+-]?digits[.digits]?([eEdD][+-]?digits)?[!#]?" を解析する。

    $FIN (MATH1.ASM 2059-2161) と $FIDIG (MATH2.ASM 1-84) の昇格則を
    そのまま模した手続き。数字の連結を厳密整数として蓄積し、
    (1) 整数のまま蓄積できる上限(3277未満のときだけ次の桁を試す。
        結果が32768以上になったら単精度へ昇格。$FIDIG FFI10)
    (2) 単精度は「現在値が100万相当以上ならその桁を足す前に倍精度へ
        昇格」(FI35, MATH2.ASM 71-74; しきい値定数は $DBUFF 比較,
        MATH2.ASM 57-61 由来、実測しやすい "100万" として実装)
    という2段階の昇格をシミュレートしたあと、小数点以下桁数・指数
    ("E"/"e" は単精度強制、"D"/"d" は倍精度強制。$FINEX/$FINFC)・
    強制サフィックス("!"→単精度, "#"→倍精度)を適用する。
    """
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

    # --- $FIDIG 相当の逐次昇格シミュレーション -----------------------
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

    forced_double_by_dot = seen_dot and kind == "int"
    if forced_double_by_dot:
        kind = "single"  # "." は最低単精度 (FN100, $CSI)

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
            kind = "double"  # $FINEX/$FINFC: ZF=1 -> $FD
        else:
            if kind != "double":
                kind = "single"  # $FINEX/$FINFC: ZF=0 -> $FS

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
            # ここには通常到達しない($FIDIGの昇格が先に働くため)
            kind = "single"
        else:
            return GwNum.from_int(iv)

    try:
        num = GwNum.from_fraction(value, kind)
    except OverflowError:
        sign = 1 if value < 0 else 0
        raise GwError("Overflow", _max_value(kind, sign))

    # $CONI2 相当: 単精度でちょうど -32768 になった場合は整数に戻す
    # (FINF, MATH1.ASM 2152-2160)
    if kind == "single" and neg and value == -32768:
        return GwNum.from_int(-32768)
    return num


# ---------------------------------------------------------------------------
# 式評価（本予測器が対象にする範囲: 単項マイナス, + - * /, 括弧なし）
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
    """"print " を除いた式本体を評価する。"""
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
# PRINT の自由形式出力 ($FOFMT / $FOTNV / $SIGD 相当)
# ---------------------------------------------------------------------------


def _decimal_exponent(value: Fraction) -> int:
    """10**(E-1) <= value < 10**E となる整数 E を返す（value>0）。"""
    import math

    est = math.floor(math.log10(value.numerator / value.denominator)) + 1
    while Fraction(10) ** (est - 1) > value:
        est -= 1
    while Fraction(10) ** est <= value:
        est += 1
    return est


def _significant_digits(value: Fraction, ndig: int) -> Tuple[str, int]:
    """value(>0) を ndig 桁の有効数字に丸め、(桁文字列, E) を返す。

    E は value ≈ 0.d1d2...dndig × 10**E の意味（$FOTNV が仮数部を整数へ
    ブラケットしたときに使う指数と同じ向き）。丸めは $ROUNS と同じ
    偶数丸め。
    """
    e = _decimal_exponent(value)
    scaled = value * Fraction(10) ** (ndig - e)
    digits_int = _round_half_even(scaled)
    if digits_int >= 10 ** ndig:
        e += 1
        digits_int //= 10
    s = str(digits_int).rjust(ndig, "0")
    return s, e


def fout_format(num: GwNum) -> str:
    """$FOUT/$FOFMT 相当。数値1個ぶんの本体（符号1桁＋数字列、後置空白
    なし）を返す。符号・後置空白1つは docs/spec/l4-basic.md 第2節の
    規則を呼び出し側で適用する想定なのでここでは付けない。
    """
    if num.kind == "int":
        return str(abs(num.ivalue))

    ndig = MBF_SINGLE_DIGITS if num.kind == "single" else MBF_DOUBLE_DIGITS
    value = num.exact()
    if value == 0:
        return "0"
    av = -value if value < 0 else value

    digits, e = _significant_digits(av, ndig)
    # 末尾0を落とす(有効桁の右側から)。$SIGD 相当。
    trimmed = digits.rstrip("0")
    if trimmed == "":
        trimmed = "0"
    nsig = len(trimmed)

    use_fixed = (-ndig) < e <= ndig  # 近似則。docs/notes/l4-mbf-oracle.md 参照

    if use_fixed:
        if e <= 0:
            body = "." + ("0" * (-e)) + trimmed
        elif e >= nsig:
            body = trimmed + ("0" * (e - nsig))
        else:
            body = trimmed[:e] + "." + trimmed[e:]
        return body
    else:
        mant = trimmed[0]
        if nsig > 1:
            mant += "." + trimmed[1:]
        exp_val = e - 1
        marker = "E" if num.kind == "single" else "D"
        sign_ch = "+" if exp_val >= 0 else "-"
        return f"{mant}{marker}{sign_ch}{abs(exp_val):02d}"


def print_one(num: GwNum) -> str:
    """docs/spec/l4-basic.md 第2節: 数値の前に符号用1桁(正/0は空白、負は
    '-')、後ろに空白1つ。"""
    body = fout_format(num)
    sign = "-" if num.is_negative() else " "
    return f"{sign}{body} "


def predict(typed_print_body: str) -> Tuple[str, str]:
    """"print <expr>" の <expr> 部分を受け取り (kind, predicted) を返す。

    kind: "numeric" | "error"
    predicted: numeric なら print_one() の結果そのもの。
               error なら "<エラー種別>;<続く数値行>"（数値行が無ければ
               エラー種別のみ）。
    """
    try:
        num = eval_expr(typed_print_body)
    except GwError as e:
        residual_line = print_one(e.residual)
        return "error", f"{e.kind};{residual_line}"
    return "numeric", print_one(num)


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        body = arg
        if body.lower().startswith("print "):
            body = body[6:]
        kind, pred = predict(body)
        print(f"{arg!r}\t{kind}\t{pred!r}")
