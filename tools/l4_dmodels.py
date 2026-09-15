#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_dmodels.py — l4-s4k: 倍精度の定数読み取り(FIN)の3候補
(DEXACT/DGW/DREP01)を、tools/l4_mbf_oracle_v2.py とは独立に実装したもの。
段階4b(倍精度の実装)の前に、N88が倍精度の定数をどう読むかを決めるための
候補探し(測定はしていない)。

丸めの前提: l4-s4hで倍精度の丸めの半端(タイ)は出力側で「絶対値の大きい側
(常に切り上げ)」と確定した。本ファイルは読み取り側もこれと同じ規則だと
**仮定**し(未確認、仮定であることをここに明記する)、3候補すべてで
「半分は絶対値の大きい側」(round-half-away、_round_half_away_mag)を使う。
tools/l4_mbf_oracle_v2.py の encode_mbf は偶数丸め(round-half-even)であり、
本ファイルはそれとは意図的に異なる丸め関数を独立に実装している。

## 3候補の定義

- **DEXACT**: 10進の厳密値(acc * 10**net_exp)を、倍精度(56bit仮数)へ
  1回だけround-half-awayで丸める。
- **DGW**: GW-BASICの$FINE/MDPTENの倍精度経路
  (tools/l4_mbf_oracle_v2.pyのfin_algo="gw"の倍精度部分と同じ考え方だが、
  丸めはround-half-away)。10のべき表自体を先に56bitへ丸め、その不正確な
  定数で1回スケーリングしてから、結果をもう一度56bitへ丸める(二段階の
  精度落とし)。
- **DREP01**: l4-s4jの単精度REP01を倍精度へ移したもの。数字を先頭から
  acc=acc*10+dで積み上げて1手ごとに倍精度へ丸め、正味の指数nについて
  n>0なら10をn回、n<0なら倍精度に丸めた0.1を|n|回、1回ずつ掛けて
  1手ごとに倍精度へ丸める。

いずれも対象は倍精度の定数(小数点を除く数字が8桁以上、または`#`付き、
または`d`指数)のみ。本ファイル自体はこの判定を行わず、渡された文字列を
常に倍精度として読む(候補生成側が対象を選ぶ)。

再利用について: tools/l4_mbf_oracle_v2.py から import して使うのは、
FOUT(倍精度の書式生成、fout_format/print_one)と、四則演算の型合成・丸め
(gw_binop/gw_neg、加減算は偶数丸めで正しい丸めと既に確認済みの箇所)、
字句解析のトークナイザ(_tokenize)、GwNumデータ構造、GwError例外——
いずれも3候補間で争っていない共通基盤である。定数の読み取り(丸め方・
積み上げ・指数適用の手順)は本ファイルだけで完結しており、
tools/l4_mbf_oracle_v2.py の parse_literal は一切呼ばない。

測定はしていない。判定には使わない。
"""

from __future__ import annotations

import os
import re
import sys
from fractions import Fraction
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_mbf_oracle_v2 as oracle  # noqa: E402

MBF_DOUBLE_BITS = 56


# ---------------------------------------------------------------------------
# 倍精度への丸め(round-half-away、非負の値だけを受け取る前提)。
# ---------------------------------------------------------------------------


def _bracket(av: Fraction) -> int:
    import math

    est = math.floor(math.log2(av.numerator / av.denominator)) + 1
    while Fraction(2) ** (est - 1) > av:
        est -= 1
    while Fraction(2) ** est <= av:
        est += 1
    return est


def _round_half_away_mag(x: Fraction) -> int:
    n, d = x.numerator, x.denominator
    q, r = divmod(n, d)
    return q if 2 * r < d else q + 1


def _encode_double_away(value: Fraction) -> Tuple[int, int]:
    """非負のFractionを倍精度(56bit仮数)へround-half-awayで丸める。
    戻り値: (exp_byte, mant)。exp_byte>255ならOverflowError。
    """
    if value == 0:
        return (0, 0)
    k = _bracket(value)
    mant_exact = value * Fraction(2) ** (MBF_DOUBLE_BITS - k)
    m = _round_half_away_mag(mant_exact)
    if m >= (1 << MBF_DOUBLE_BITS):
        k += 1
        m = 1 << (MBF_DOUBLE_BITS - 1)
    exp_byte = k + 128
    if exp_byte > 255:
        raise OverflowError("dmodels double overflow")
    if exp_byte < 1:
        return (0, 0)
    return (exp_byte, m)


def _decode_double(exp_byte: int, mant: int) -> Fraction:
    if exp_byte == 0:
        return Fraction(0)
    k = exp_byte - 128
    return Fraction(mant) * Fraction(2) ** (k - MBF_DOUBLE_BITS)


def _round_away_frac(value: Fraction) -> Fraction:
    """非負のFractionを倍精度へ丸めてFractionへ戻す(往復)。"""
    exp_byte, mant = _encode_double_away(value)
    return _decode_double(exp_byte, mant)


_S01_CACHE: Optional[Fraction] = None


def _s01() -> Fraction:
    """倍精度に丸めた0.1(round-half-away)。DREP01の負指数側で使う。"""
    global _S01_CACHE
    if _S01_CACHE is None:
        _S01_CACHE = _round_away_frac(Fraction(1, 10))
    return _S01_CACHE


# ---------------------------------------------------------------------------
# l4-s4l: DREP10(倍精度、負の正味指数を「丸め済み0.1との乗算」ではなく
# 「真の÷10の反復」にした候補)の2変種。round-half-even(DREP10E、
# $ROUND/DDIVがソースで確認されている丸め)とround-half-away(DREP10A、
# l4-s4hの出力側の規則を読み取り側にも当てはめた場合)。
# ---------------------------------------------------------------------------


def _round_half_even_mag(x: Fraction) -> int:
    n, d = x.numerator, x.denominator
    q, r = divmod(n, d)
    twice = 2 * r
    if twice < d:
        return q
    if twice > d:
        return q + 1
    return q if (q % 2 == 0) else q + 1


def _encode_double_even(value: Fraction) -> Tuple[int, int]:
    """非負のFractionを倍精度(56bit仮数)へround-half-evenで丸める。"""
    if value == 0:
        return (0, 0)
    k = _bracket(value)
    mant_exact = value * Fraction(2) ** (MBF_DOUBLE_BITS - k)
    m = _round_half_even_mag(mant_exact)
    if m >= (1 << MBF_DOUBLE_BITS):
        k += 1
        m = 1 << (MBF_DOUBLE_BITS - 1)
    exp_byte = k + 128
    if exp_byte > 255:
        raise OverflowError("dmodels double overflow")
    if exp_byte < 1:
        return (0, 0)
    return (exp_byte, m)


def _round_even_frac(value: Fraction) -> Fraction:
    exp_byte, mant = _encode_double_even(value)
    return _decode_double(exp_byte, mant)


def _round_variant_frac(value: Fraction, variant: str) -> Fraction:
    return _round_even_frac(value) if variant == "even" else _round_away_frac(value)


def _magnitude_drep10(digits: str, net_exp: int, variant: str) -> Fraction:
    """DREP10E(variant="even")/DREP10A(variant="away")共通の本体。
    数字の積み上げは常にround-half-even、かつ$MUL10と$FADDDを別々に
    呼ぶ($FIDIGの構造どおり)ため、桁ごとに「×10を丸める」→「+dを丸める」
    の2回roundする(Codexのdfin_model_search.py accumulate_digits()と
    同じ構造。1回にまとめてroundすると、候補式のx-c形で使う桁数の多い
    定数cで丸め誤差が変わってしまうことを乱数突き合わせで確認したため、
    2回roundに直した)。指数適用の×10/真の÷10だけがvariantで丸め方を
    切り替える。
    """
    acc = Fraction(0)
    for ch in digits or "0":
        acc = _round_even_frac(acc * 10)
        acc = _round_even_frac(acc + int(ch))
    if net_exp > 0:
        for _ in range(net_exp):
            acc = _round_variant_frac(acc * 10, variant)
    elif net_exp < 0:
        for _ in range(-net_exp):
            acc = _round_variant_frac(acc / 10, variant)
    return acc


def _magnitude_drep10e(digits: str, net_exp: int) -> Fraction:
    return _magnitude_drep10(digits, net_exp, "even")


def _magnitude_drep10a(digits: str, net_exp: int) -> Fraction:
    return _magnitude_drep10(digits, net_exp, "away")


# ---------------------------------------------------------------------------
# l4-s4l v2訂正: 親の手検算で、l4-s4l候補表v1(23ad7ea)のDREP10E/DREP10A列が
# 「式の左の定数だけ候補の読み方(even/away)を当て、右の長い整数はaway固定
# (=DREP01/DEXACT/DGWと同じ、l4-s4k以来の既定)で読んでいた」ことが分かった
# (_magnitude_drep10の数字積み上げが_round_even_frac固定だったため)。
# 候補DREP10E/DREP10Aは「N88がすべての定数をどう読むか」の候補なので、
# 式に出てくるどの定数(桁数の多い整数を含む)にも同じ読み方を一貫して
# 当てる必要がある。_magnitude_drep10(v1)はtools/gen_l4_s4l_candidates.py/
# tools/gen_l4_s4l_controls.py(v1)が使い続けるので変更しない
# (v1のtsvを1バイトも変えないため)。v2はここに独立した関数を追加する。
#
# v2の定義: 数字の積み上げは常にround-half-away(DREP01/DEXACT/DGWと同じ
# 既定、l4-s4hの仮定をそのまま踏襲)。指数適用の×10/真の÷10の反復だけが
# DREP10E(even)/DREP10A(away)でわかれる(ここはv1と同じ)。
# ---------------------------------------------------------------------------


def _magnitude_drep10_v2(digits: str, net_exp: int, variant: str) -> Fraction:
    acc = Fraction(0)
    for ch in digits or "0":
        acc = _round_away_frac(acc * 10)
        acc = _round_away_frac(acc + int(ch))
    if net_exp > 0:
        for _ in range(net_exp):
            acc = _round_variant_frac(acc * 10, variant)
    elif net_exp < 0:
        for _ in range(-net_exp):
            acc = _round_variant_frac(acc / 10, variant)
    return acc


def _magnitude_drep10e_v2(digits: str, net_exp: int) -> Fraction:
    return _magnitude_drep10_v2(digits, net_exp, "even")


def _magnitude_drep10a_v2(digits: str, net_exp: int) -> Fraction:
    return _magnitude_drep10_v2(digits, net_exp, "away")


# ---------------------------------------------------------------------------
# 定数の字句解析(倍精度専用の軽量版。符号・桁文字列・小数点以下の桁数・
# 指数だけを取り出す。丸め方自体には関与しない)。
# ---------------------------------------------------------------------------

_LIT_RE = re.compile(r"^([+-]?)(\d*)(?:\.(\d*))?(?:[eEdD]([+-]?\d+))?([!#]?)$")


class DModelLexError(Exception):
    pass


def _lex_raw(text: str):
    m = _LIT_RE.match(text.strip())
    if not m or (not m.group(2) and not m.group(3)):
        raise DModelLexError(f"cannot lex literal {text!r}")
    sign_ch, ip, fp, exp_digits, _suffix = m.groups()
    ip = ip or ""
    fp = fp or ""
    digits = ip + fp
    frac_digits = len(fp)
    exponent = int(exp_digits) if exp_digits else 0
    return sign_ch, digits, frac_digits, exponent


# ---------------------------------------------------------------------------
# 3候補
# ---------------------------------------------------------------------------


def _magnitude_dexact(digits: str, net_exp: int) -> Fraction:
    acc = Fraction(int(digits) if digits else 0)
    exact = acc * (Fraction(10) ** net_exp)
    return _round_away_frac(exact)


def _magnitude_dgw(digits: str, net_exp: int) -> Fraction:
    fac = _round_away_frac(Fraction(int(digits) if digits else 0))
    if net_exp == 0:
        return fac
    pow10 = _round_away_frac(Fraction(10) ** abs(net_exp))
    scaled = fac * pow10 if net_exp > 0 else fac / pow10
    return _round_away_frac(scaled)


def _magnitude_drep01(digits: str, net_exp: int) -> Fraction:
    acc = Fraction(0)
    for ch in digits or "0":
        acc = _round_away_frac(acc * 10 + int(ch))
    if net_exp > 0:
        for _ in range(net_exp):
            acc = _round_away_frac(acc * 10)
    elif net_exp < 0:
        s01 = _s01()
        for _ in range(-net_exp):
            acc = _round_away_frac(acc * s01)
    return acc


_MODELS = {
    "dexact": _magnitude_dexact,
    "dgw": _magnitude_dgw,
    "drep01": _magnitude_drep01,
    "drep10e": _magnitude_drep10e,
    "drep10a": _magnitude_drep10a,
    "drep10e_v2": _magnitude_drep10e_v2,
    "drep10a_v2": _magnitude_drep10a_v2,
}


def parse_double_literal(text: str, model: str) -> "oracle.GwNum":
    """textを常に倍精度の定数として読む(kind判定はしない、呼び出し側が
    対象〔小数点を除く数字8桁以上・#付き・d指数のいずれか〕を選ぶ前提)。
    """
    sign_ch, digits, frac_digits, exponent = _lex_raw(text)
    net_exp = exponent - frac_digits
    fn = _MODELS[model]
    try:
        magnitude = fn(digits, net_exp)
        exp_byte, mant = _encode_double_away(magnitude) if magnitude != 0 else (0, 0)
    except OverflowError:
        sign_bit = 1 if sign_ch == "-" else 0
        raise oracle.GwError("Overflow", oracle._max_value_num("double", sign_bit))
    sign_bit = 1 if sign_ch == "-" else 0
    return oracle.GwNum("double", sign=sign_bit, exp=exp_byte, mant=mant)


# ---------------------------------------------------------------------------
# 式評価(oracle._tokenizeと四則演算gw_binop/gw_negを共通基盤として再利用)。
# ---------------------------------------------------------------------------


def eval_expr_double(expr: str, model: str) -> "oracle.GwNum":
    toks = oracle._tokenize(expr)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def advance():
        t = toks[pos[0]]
        pos[0] += 1
        return t

    def parse_factor():
        t = peek()
        if t is None:
            raise oracle.GwSyntaxError("unexpected end of expression")
        if t == ("op", "-"):
            advance()
            return oracle.gw_neg(parse_factor())
        if t == ("op", "+"):
            advance()
            return parse_factor()
        if t[0] == "num":
            advance()
            return parse_double_literal(t[1], model)
        raise oracle.GwSyntaxError(f"unexpected token {t!r}")

    def parse_term():
        v = parse_factor()
        while True:
            t = peek()
            if t is not None and t[0] == "op" and t[1] in "*/":
                advance()
                rhs = parse_factor()
                v = oracle.gw_binop(v, rhs, t[1])
            else:
                break
        return v

    def parse_add():
        v = parse_term()
        while True:
            t = peek()
            if t is not None and t[0] == "op" and t[1] in "+-":
                advance()
                rhs = parse_term()
                v = oracle.gw_binop(v, rhs, t[1])
            else:
                break
        return v

    v = parse_add()
    if pos[0] != len(toks):
        raise oracle.GwSyntaxError("trailing tokens")
    return v


def predict_double(
    typed_print_body: str,
    model: str,
    single_digits: int = 16,
    small_rule: str = "rstar",
    small_len: int = 0,
    small_emin: int = 0,
    large_n: int = 0,
    fout_algo: str = "gw",
) -> Tuple[str, str]:
    """(kind, printed)。FOUT(桁生成)はoracleのものをそのまま使う。
    既定は16桁・rstar・fout-algo=gw(l4-s4e/l4-s4fで確認済みの倍精度の
    想定設定)。
    """
    try:
        num = eval_expr_double(typed_print_body, model)
    except oracle.GwError as e:
        line, _approx = oracle.print_one(
            e.residual, single_digits, small_rule, small_len, small_emin, large_n, fout_algo
        )
        return "error", f"{e.kind};{line}"
    line, _approx = oracle.print_one(
        num, single_digits, small_rule, small_len, small_emin, large_n, fout_algo
    )
    return "numeric", line


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=("dexact", "dgw", "drep01"), default="dgw")
    ap.add_argument("exprs", nargs="+")
    args = ap.parse_args()
    for arg in args.exprs:
        body = arg
        if body.lower().startswith("print "):
            body = body[6:]
        kind, pred = predict_double(body, args.model)
        print(f"{kind}\t{pred!r}")
