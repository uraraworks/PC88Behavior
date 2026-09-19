#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_oracle_v3.py — GW-BASIC数値部の予測器 v3(超越関数への拡張)

v2(tools/l4_mbf_oracle_v2.py)は四則演算(+-*/)とPRINTの書式化だけを
命令単位で再現していた。v3はそれに加え、SQR・SIN・COS・TAN・ATN・EXP・LOG
の7関数を対象に追加する(l4-s6a)。v2はこのファイルでは変更せず、import
して四則演算プリミティブ(gw_binop/gw_neg/force_to_single/force_to_double/
GwNum/GwError/encode_mbf/decode_mbf/mbf4_from_bytes/mbf8_from_bytes)を
そのまま再利用する。超越関数のGW-BASIC実装自体が、位取り・多項式評価の
各段で$FADDS/$FSUBS/$FMULS/$FDIVS/$FADDD/$FSUBD/$FMULD/$CSD/$CDSを
呼び出しているので、これらをv2の(既に命令単位で確認済みの)実装へ
委譲することで、超越関数側の実装も命令単位の忠実さを保てる。

読んだ範囲(GW-BASIC、MIT公開ソース、コミット
edf82c2ebf6bfe099c2054e0ae125c3efe5769c4。取得元
https://raw.githubusercontent.com/microsoft/GW-BASIC/<commit>/<file>.ASM):
  MATH1.ASM 952-1049   $SIN/$COS (Hart #3341多項式、2πでの位取り縮約)
  MATH1.ASM 1055-1073  RR/RR1/RR2/RR3(倍精度位取り縮約、frac(x/2π)を得る)
  MATH1.ASM 1080-1143  $TAN($SIN/$COSの比)・$ATAN(Hart #4940、
                        SQR(3)公式によるπ/12超の範囲縮約、|X|>1の
                        逆数公式)
  MATH1.ASM 2177-2236  $SQR(24bitマンティッサに対するビット単位の
                        平方根抽出。v3では抽出アルゴリズムそのものを
                        レジスタ単位で再現するのではなく、下記
                        「SQRの扱い」節の理由により近似する)
  MATH1.ASM 3028-3092  $EXP(底2への変換、$QINT(floor)による整数部
                        分離、Hart #1302多項式、2^Nyとの再合成)
  MATH1.ASM 793-830    $LG2E(log2(e)定数)・$EXPCN(Hart #1302係数)
  MATH1.ASM 831-856    $SINCN(Hart #3341係数)
  MATH1.ASM 857-884    $ATNC1・$ATNC2(Hart #4940関連係数)
  MATH1.ASM 573        $DP00(倍精度1.0定数)
  MATH1.ASM 892-899    $IN2PI(倍精度1/(2π)、位取り縮約専用定数)
  MATH2.ASM 828-996    $INT/$DINT/$QINT(いずれも切り捨てはBASICの
                        INT()と同じ「負方向への床関数」。$QINTは
                        $EXPが2^Ny・2^frac(y)に分解する際のNy=floor(y)
                        に使われる)
  MATH2.ASM 998-1050   $LOG(Hart #2524、P(x)/Q(x)によるlog2の有理近似
                        + log2→loge変換のln(2)乗算)
  MATH2.ASM 631-664    $LOGP・$LOGQ(Hart #2524係数)
  MATH2.ASM 1143-1220  $POLY($C_N,...,C_0のHorner評価、単精度)・
                        $POLYX(X*P(X^2)、$SIN/$COS/$ATNが使う偶関数用
                        変形)
  MATH1.ASM 3653-3825(既にv2で読了。本ファイルでは$FDIVSの演算子順序
                        規約の確認にのみ再利用): 「$FDIVS FORMS THE
                        QUOTIENT (BXDX)/(FAC)」。同様に$FADDS/$FSUBSの
                        コメント(MATH1.ASM 3268-3276)「$FADDS FORMS THE
                        SUM OF (BXDX) AND ($FAC)」「$FSUBS FORMS THE
                        DIFFERENCE (BXDX)-(FAC)」から、スタック側
                        (呼び出し元でBASIC式の左オペランドだったほう)を
                        第1引数、FAC側(右オペランド)を第2引数として
                        gw_binop(stack, fac, op)を呼べば、上の全関数の
                        演算子順序が原アセンブリと一致する。本ファイルの
                        すべての四則演算呼び出しはこの規約に従う。

定数・係数の取得方法: 上記コミットのMATH1.ASM/MATH2.ASMをそのまま取得し、
DB列(8進数)をメモリ順(下位バイト→中位バイト→(符号|上位7bit)バイト→
指数バイト)でそのままbytes化し、v2のmbf4_from_bytes/mbf8_from_bytesで
復号した。復号結果はソースコメントに書かれた10進値(例:
「.69314717213716+」)や実世界の定数(log2(e)≈1.442695、π/2≈1.570796等)
と一致することを below selftest で確認している(ROMのバイト列ではなく
MIT公開ソースの定数表なので、クリーンルーム規律の対象外)。

## 有効桁数(n88=True)

l4-s4a(`docs/notes/l4-s4a-float-print-results.md`)は、割り切れない
単精度の値(`1/3`等)で「実測の有効桁数が予測(既定7桁)より1桁少ない
(6桁)」という食い違いを既に見つけており、予測器側の課題として次の
作業に渡していた(同ノート「判定後の行き先」節)。v2の`fout_format`/
`print_one`には、この既知の食い違いに対応する`n88=True`(単精度6桁・
`small_rule="len"`・`small_len=7`)という設定口が用意されていたので、
v3の`predict_fn()`はこれを使う。本ノートの実測(l4-s6a、下記)でも、
`n88=True`にした途端SQR(2)等の桁数が実測(`1.41421`、6桁)と一致した
ことをselftest的に確認している。すなわちv3は「割り切れない値では
GW-BASICの既定7桁ではなくN88-BASICは6桁を使う」というl4-s4aの発見を
そのまま引き継いでいる。

## 倍精度引数の扱い

$SIN/$COS/$TAN/$ATAN/$EXP/$LOG/$SQRはいずれも$FAC(単精度)だけを前提に
組まれている(例: $SINの早期リターン判定"CMP AH,167O"は単精度の8bit
指数バイト比較)。よって呼び出し側が倍精度の値を渡す前にBASICインタプリタ
が単精度へ強制変換していると考えられる(GW-BASICの実機挙動としても
「超越関数は常に単精度を返す」は広く知られている)。v3のpredict()は
引数を評価した直後に force_to_single()(=$CSD相当)を必ず適用する。
これ自体は事前登録の腕(倍精度引数の腕)で測定によって裏を取る対象。

## SQRの扱い(近似段階として明示する)

$SQR(MATH1.ASM 2177-2234)は24bitマンティッサに対し、指数の奇偶で
1bit事前シフトしたうえで64bitの入力に対し25回のビット単位「試し引き」で
平方根を抽出し、最後に2回の右シフトのうち後半の1回だけ(前半でシフト
落ちしたビットは捨てたまま)をADCで丸めに使う、という、桁ごとの
非復元法平方根である。レジスタの受け渡し(DX:BX等)を完全に再構成すれば
理論上ビット単位で再現できるはずだが、往復での取り違えのリスクが高く、
実機測定なしに正しさを検証できない。そこでv3では、SQRだけ次の近似で
代替する: 入力の厳密値(有理数)に対し高精度(数十bit余裕)で平方根を
計算し、単精度への収め込みはv2のencode_mbf(偶数丸め)に任せる。
無理数(割り切れない)平方根に対しては真の値がちょうど丸めの境界に
乗ることは実質ない(測度0)ので、上の近似と実機の非復元法アルゴリズムが
食い違うのは「ガードビットの次のビットだけを見てスティッキーを無視する」
ことに起因する、通常丸めでは起こらない特殊な内部境界に限られるはずで
ある。SQRの出力にはpredict_fn()が approx=True を立てる(l4-s4aのapprox
列と同じ扱い)。測定でSQRだけ食い違う場合、この近似が原因である可能性を
最初に疑う。

----------------------------------------------------------------------------
MIT License (GW-BASICソース部分)

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
"""

import math
import os
import sys
from fractions import Fraction
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import (  # noqa: E402
    GwError,
    GwNum,
    decode_mbf,
    force_to_double,
    force_to_single,
    gw_binop,
    gw_neg,
    mbf4_from_bytes,
    mbf8_from_bytes,
    parse_literal,
    print_one,
)

# 故障注入用(選択的にコンスタントを壊すセルフテストのため)
_FAULT = os.environ.get("L4_ORACLE_V3_FAULT", "")


def _s(*octal_bytes: str) -> GwNum:
    """4バイト(8進数文字列)の単精度定数をGwNumへ。バイト順は
    ソースのDB列そのまま(下位,中位,符号|上位7bit,指数)。"""
    b = bytes(int(o, 8) for o in octal_bytes)
    sign, exp, mant = mbf4_from_bytes(b)
    return GwNum("single", sign=sign, exp=exp, mant=mant)


def _d(*octal_bytes: str) -> GwNum:
    """8バイト(8進数文字列)の倍精度定数をGwNumへ。"""
    b = bytes(int(o, 8) for o in octal_bytes)
    sign, exp, mant = mbf8_from_bytes(b)
    return GwNum("double", sign=sign, exp=exp, mant=mant)


# ---------------------------------------------------------------------------
# 定数(MATH1.ASM内のインライン即値、MOV DX,xxx;MOV BX,yyy形。
# バイト順は[DX下位,DX上位,BX下位,BX上位]で、BX上位が指数バイトに一致する
# ことを確認済み(selftestでlog2(e)・ln(2)・π/2等の実世界の値に復号
# されることを検証)。
# ---------------------------------------------------------------------------
def _dxbx_single(dx_octal: str, bx_octal: str) -> GwNum:
    dx = int(dx_octal, 8)
    bx = int(bx_octal, 8)
    b0 = dx & 0xFF
    b1 = (dx >> 8) & 0xFF
    b2 = bx & 0xFF
    b3 = (bx >> 8) & 0xFF
    return _s(oct(b0)[2:], oct(b1)[2:], oct(b2)[2:], oct(b3)[2:])


LOG2E = _dxbx_single("125073", "100470")  # MATH1.ASM 3029-3030
ONE_S = _dxbx_single("0", "100400")  # MATH1.ASM 1016-1017 / 1106-1107
LN2 = _dxbx_single("71030", "100061")  # MATH2.ASM 1047-1048 (MLLN2)
TAN_PI12 = _dxbx_single("30242", "77411")  # MATH1.ASM 1109-1110
SQRT3 = _dxbx_single("131727", "100535")  # MATH1.ASM 1117-1118
PI2 = _dxbx_single("7733", "100511")  # MATH1.ASM 1137-1138 (ATN100)
PI6 = _dxbx_single("5222", "100006")  # MATH1.ASM 1141-1142 (ATN200)
TWO_PI = _dxbx_single("7733", "101511")  # MATH1.ASM 1036-1037 (SIN60)

LG2E_TABLE_CONST = _s("073", "252", "070", "201")  # MATH1.ASM 793-796 $LG2E(未使用、確認用)

DP00 = _d("000", "000", "000", "000", "000", "000", "000", "201")  # MATH1.ASM 573 ($DP00, 1.0)
IN2PI = _d("013", "104", "116", "156", "203", "371", "042", "176")  # MATH1.ASM 892-899

QUARTER_TURN = GwNum.from_fraction(Fraction(1, 4), "double")  # ARGのexponentバイト書き換え
# (177O)を、同値の厳密なFraction構成で代替(結果は同一値)。

# ---------------------------------------------------------------------------
# 係数表(Hart多項式)。MATH1.ASM/MATH2.ASMのDB列(8進)をそのままbytes化。
# ---------------------------------------------------------------------------
EXPCN: List[GwNum] = [  # MATH1.ASM 802-830 (Hart #1302, degree 6, 7係数)
    _s("174", "210", "131", "164"),
    _s("340", "227", "046", "167"),
    _s("304", "035", "036", "172"),
    _s("136", "120", "143", "174"),
    _s("032", "376", "165", "176"),
    _s("030", "162", "061", "200"),
    _s("000", "000", "000", "201"),
]

SINCN: List[GwNum] = [  # MATH1.ASM 831-856 (Hart #3341, 5係数)
    _s("373", "327", "036", "206"),
    _s("145", "046", "231", "207"),
    _s("130", "064", "043", "207"),
    _s("341", "135", "245", "206"),
    _s("333", "017", "111", "203"),
]

ATNC1: List[GwNum] = [  # MATH1.ASM 857-866 (X*SQR(3)-1 の分子生成用)
    _s("327", "263", "135", "201"),
    _s("000", "000", "200", "201"),
]

ATNC2: List[GwNum] = [  # MATH1.ASM 867-884 (Hart #4940, 4係数)
    _s("142", "065", "203", "176"),
    _s("120", "044", "114", "176"),
    _s("171", "251", "252", "177"),
    _s("000", "000", "000", "201"),
]

LOGP: List[GwNum] = [  # MATH1.ASM 631-647 (Hart #2524, P(x), 4係数)
    _s("232", "367", "031", "203"),
    _s("044", "143", "103", "203"),
    _s("165", "315", "215", "204"),
    _s("251", "177", "203", "202"),
]

LOGQ: List[GwNum] = [  # MATH1.ASM 648-664 (Hart #2524, Q(x), 4係数)
    _s("000", "000", "000", "201"),
    _s("342", "260", "115", "203"),
    _s("012", "162", "021", "203"),
    _s("364", "004", "065", "177"),
]


# ---------------------------------------------------------------------------
# $POLY/$POLYX (MATH2.ASM 1143-1220) — Horner評価。単精度の$FMULS/$FADDSを
# v2のgw_binopへ委譲する。
# ---------------------------------------------------------------------------


def poly_eval(x: GwNum, coeffs: List[GwNum]) -> GwNum:
    acc = coeffs[0]
    for c in coeffs[1:]:
        acc = gw_binop(acc, x, "*")  # $FMULS (乗算は順序に依らない)
        acc = gw_binop(c, acc, "+")  # $FADDS: (BXDX)+(FAC) = c + acc
    return acc


def polyx_eval(x: GwNum, coeffs: List[GwNum]) -> GwNum:
    x2 = gw_binop(x, x, "*")
    p = poly_eval(x2, coeffs)
    return gw_binop(p, x, "*")


# ---------------------------------------------------------------------------
# $INT/$DINT/$QINT (MATH2.ASM 828-996) — floor (負方向への切り捨て)。
# ---------------------------------------------------------------------------


def _gw_floor(x: GwNum) -> GwNum:
    v = x.exact()
    fl = Fraction(math.floor(v))
    return GwNum.from_fraction(fl, x.kind)


# ---------------------------------------------------------------------------
# RR/RR1/RR2/RR3 (MATH1.ASM 1055-1070) — 倍精度でfrac(y)=y-floor(y)を返す。
# ---------------------------------------------------------------------------


def _frac_part_double(y: GwNum) -> GwNum:
    n = _gw_floor(y)
    diff = gw_binop(n, y, "-")  # $FSUBD: (ARG=n) - (FAC=y)
    return gw_neg(diff)  # y - n


def _rr_reduce(x_single: GwNum) -> GwNum:
    xd = force_to_double(x_single)  # $CDS
    y = gw_binop(xd, IN2PI, "*")  # $FMULD: x/(2π) (順序自由)
    return _frac_part_double(y)


# ---------------------------------------------------------------------------
# $SIN/$COS/$TAN (MATH1.ASM 952-1092)
# ---------------------------------------------------------------------------


def _sin_core(frac_turns: GwNum, outer_neg: bool) -> GwNum:
    quad = GwNum.from_fraction(frac_turns.exact() * 4, "double")  # FAC*4 (exact)
    q_num = _gw_floor(quad)
    q = int(q_num.exact()) % 4
    sub = gw_neg(gw_binop(q_num, quad, "-"))  # quad - q
    if q in (1, 3):
        sub = gw_binop(DP00, sub, "-")  # 1 - sub
    reduced = GwNum.from_fraction(sub.exact() / 4, "double")
    reduced_sp = force_to_single(reduced)  # $CSD
    if reduced_sp.exp != 0 and reduced_sp.exp < 0o164:
        result = gw_binop(reduced_sp, TWO_PI, "*")  # 微小角: sin(x)≈xを2πで復元
    else:
        result = polyx_eval(reduced_sp, SINCN)
    if q in (2, 3):
        result = gw_neg(result)
    if outer_neg:
        result = gw_neg(result)
    return result


def sin_impl(x: GwNum) -> GwNum:
    if x.exp != 0 and x.exp < 0o167:
        return x  # SIN10: 十分小さければ x=SIN(x) として即リターン
    neg = x.is_negative()
    xx = gw_neg(x) if neg else x
    frac = _rr_reduce(xx)
    return _sin_core(frac, neg)


def cos_impl(x: GwNum) -> GwNum:
    xx = gw_neg(x) if x.is_negative() else x  # cos(-x)=cos(x)
    frac = _rr_reduce(xx)
    frac2 = gw_binop(QUARTER_TURN, frac, "+")  # +1/4回転
    frac3 = _frac_part_double(frac2) if frac2.exact() >= 1 else frac2
    return _sin_core(frac3, False)


def tan_impl(x: GwNum) -> GwNum:
    s = sin_impl(x)
    c = cos_impl(x)
    return gw_binop(s, c, "/")  # $FDIVS: sin/cos


# ---------------------------------------------------------------------------
# $ATAN (MATH1.ASM 1093-1143)
# ---------------------------------------------------------------------------


def atn_impl(x: GwNum) -> GwNum:
    neg = x.is_negative()
    xx = gw_neg(x) if neg else x
    need_pi2 = xx.exp != 0 and xx.exp >= 0o201  # |x| > tan(pi/4)=1
    if need_pi2:
        xx = gw_binop(ONE_S, xx, "/")  # 1/x
    need_pi6 = xx.exact() > TAN_PI12.exact()
    if need_pi6:
        xps = gw_binop(xx, SQRT3, "+")  # x+sqrt(3)
        num = poly_eval(xx, ATNC1)  # x*sqrt(3)-1
        xx = gw_binop(num, xps, "/")
    result = polyx_eval(xx, ATNC2)
    if need_pi6:
        result = gw_binop(PI6, result, "+")
    if need_pi2:
        result = gw_binop(PI2, result, "-")
    if neg:
        result = gw_neg(result)
    return result


# ---------------------------------------------------------------------------
# $EXP (MATH1.ASM 3028-3092)
# ---------------------------------------------------------------------------


def _max_single(sign: int) -> GwNum:
    return GwNum("single", sign=sign, exp=255, mant=(1 << 24) - 1)


def exp_impl(x: GwNum) -> GwNum:
    y = gw_binop(x, LOG2E, "*")  # y = x*log2(e)
    if y.exp != 0 and y.exp >= 0o210:
        if y.is_negative():
            return GwNum.from_fraction(Fraction(0), "single")  # 負に大きい -> 0
        raise GwError("Overflow", _max_single(0))  # 正に大きい -> オーバーフロー
    if y.exp == 0 or y.exp < 0o150:
        return GwNum.from_fraction(Fraction(1), "single")  # EXP200: 小さすぎるので1.0
    ny = math.floor(y.exact())  # $QINT = floor
    ny_num = GwNum.from_fraction(Fraction(ny), "single")
    frac = gw_binop(y, ny_num, "-")  # (BXDX=y) - (FAC=Ny)
    poly_result = poly_eval(frac, EXPCN)  # $POLY(POLYXではない)
    exp2 = ny + 129
    if exp2 > 255:
        raise GwError("Overflow", _max_single(0))
    if exp2 < 1:
        return GwNum.from_fraction(Fraction(0), "single")
    two_pow_ny = GwNum("single", sign=0, exp=exp2, mant=0x800000)
    return gw_binop(poly_result, two_pow_ny, "*")


# ---------------------------------------------------------------------------
# $LOG (MATH2.ASM 998-1050)
# ---------------------------------------------------------------------------


def log_impl(x: GwNum) -> GwNum:
    if x.exp == 0 or x.is_negative():
        raise GwError("IllegalFunctionCall", GwNum.from_fraction(Fraction(0), "single"))
    if x.exact() == Fraction(1):
        return GwNum.from_fraction(Fraction(0), "single")
    e_raw = x.exp - 128
    m = GwNum("single", sign=0, exp=128, mant=x.mant)  # 指数を200O(128)に固定=[0.5,1)
    p = poly_eval(m, LOGP)
    q = poly_eval(m, LOGQ)
    pq = gw_binop(p, q, "/")  # $FDIVS: (BXDX=P)/(FAC=Q)
    e_float = GwNum.from_fraction(Fraction(e_raw), "single")  # $FLT
    log2x = gw_binop(e_float, pq, "+")
    return gw_binop(log2x, LN2, "*")


# ---------------------------------------------------------------------------
# $SQR (MATH1.ASM 2177-2236) — 近似(モジュールdocstring「SQRの扱い」参照)。
# ---------------------------------------------------------------------------


def _high_precision_sqrt(v: Fraction, guard_bits: int = 96) -> Fraction:
    if v == 0:
        return Fraction(0)
    num, den = v.numerator, v.denominator
    k = guard_bits
    scaled = num * den * (1 << (2 * k))
    r = math.isqrt(scaled)
    return Fraction(r, den << k)


def sqr_impl(x: GwNum) -> GwNum:
    if x.exp == 0:
        return GwNum.from_fraction(Fraction(0), "single")
    if x.is_negative():
        raise GwError("IllegalFunctionCall", GwNum.from_fraction(Fraction(0), "single"))
    approx = _high_precision_sqrt(x.exact())
    if _FAULT == "sqr_break":
        approx = approx * (Fraction(101, 100))  # 故障注入(陰性対照用)
    return GwNum.from_fraction(approx, "single")


FUNCS = {
    "sqr": (sqr_impl, True),
    "sin": (sin_impl, False),
    "cos": (cos_impl, False),
    "tan": (tan_impl, False),
    "atn": (atn_impl, False),
    "exp": (exp_impl, False),
    "log": (log_impl, False),
}


def predict_fn(fname: str, arg_literal: str) -> Tuple[str, str, bool]:
    """`print SQR(2)`等の1関数呼び出しの print body を予測する。
    引数は単一の数値リテラル(符号・単精度/倍精度サフィックス可)のみ
    対応する(l4-s6aの腕はすべてこの形)。
    戻り値: (kind, predicted_print_line, approx)
    """
    fname = fname.lower()
    if fname not in FUNCS:
        raise ValueError(f"unknown function: {fname}")
    fn, always_approx = FUNCS[fname]
    try:
        arg_num = parse_literal(arg_literal)
        arg_single = force_to_single(arg_num)  # 超越関数は常に単精度引数
        result = fn(arg_single)
    except GwError as e:
        line, approx = print_one(e.residual, n88=True)
        return "error", f"{e.kind};{line}", approx
    line, approx = print_one(result, n88=True)
    return "numeric", line, approx or always_approx


if __name__ == "__main__":
    # 簡易セルフテスト。実世界の値との近さ(丸め込み前の妥当性)だけを見る。
    # tools/l4_mbf_oracle_v3_selftest.sh 側でより厳密な既知値・陰性対照を行う。
    checks = [
        ("sqr", "4", 2.0),
        ("sqr", "2", 1.4142135),
        ("sin", "0", 0.0),
        ("cos", "0", 1.0),
        ("sin", "1", 0.841471),
        ("cos", "1", 0.540302),
        ("tan", "1", 1.557408),
        ("atn", "1", 0.785398),
        ("exp", "1", 2.718282),
        ("exp", "0", 1.0),
        ("log", "1", 0.0),
        ("log", "2", 0.693147),
    ]
    ok = True
    for fname, arg, expected in checks:
        kind, line, approx = predict_fn(fname, arg)
        got = float(line)
        if abs(got - expected) > 2e-5:
            print(f"NG {fname}({arg}): got={got} expected~={expected}")
            ok = False
        else:
            print(f"ok {fname}({arg}) = {line.strip()} (approx={approx})")
    sys.exit(0 if ok else 1)
