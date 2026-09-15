#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_rep10.py — l4-s4i の実測に事後で当てたところ全28腕を再現したという
3つ目の候補 REP10 を、tools/l4_mbf_oracle_v2.py とは独立に実装したもの。

REP10 の定義(親からの指示をそのまま実装した):
    10進の数字を先頭から1つずつ acc=acc*10+d で積み上げ、1手ごとに
    単精度(24bit仮数)へ丸める。そのあと指数の分だけ(小数点以下の桁数を
    差し引いた正味の指数nについて)n>0ならacc*10、n<0ならacc/10を1回ずつ
    繰り返し、1手ごとに単精度へ丸める。丸めは「半分は絶対値の大きい側」
    (ちょうど半分なら切り上げ)。符号は最後に付ける(=積み上げ・指数適用
    は常に非負の絶対値で行う)。

単体の検算(親の指示どおり):
    "5.1e+10" は digits="51"(net_exp=9)から acc=51(丸め不要)→
    ×10を9回、毎回単精度へ丸め直すと 51000004608 になる
    (tools/l4_rep10_selftest.py で確認)。EXACT/GWの51000000512とは
    別の値になる。

独立性について: 単精度への丸め手続き(_round_half_up_mag/
_round_single_rep10/rep10_single_value)は本ファイルだけで完結しており、
tools/l4_mbf_oracle_v2.py の parse_literal(fin_algo="exact"/"gw")は
一切呼ばない。同モジュールから再利用しているのは以下の、FIN(定数読み取り)
そのものとは無関係な共通基盤だけ:
- 定数のkind(int/single/double)判定は _classify_kind() として本ファイルに
  再実装した(oracle.parse_literalの判定規則の文書化された部分をなぞった
  もので、値の丸め方自体には触れない)。
- 四則演算の型合成・丸め(gw_binop/gw_neg)、オーバーフロー/ゼロ除算の
  例外(GwError)、字句解析のトークナイザ(_tokenize)、PRINT出力の桁生成
  (fout_format/print_one)は oracle からそのまま import して使う
  (これらはFINの候補間で争っていない箇所であり、指示の「importしてFOUT
  等を使うのは可」の範囲)。

測定はしていない。判定には使わない。
"""

from __future__ import annotations

import os
import re
import sys
from fractions import Fraction
from typing import Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_mbf_oracle_v2 as oracle  # noqa: E402

MBF_SINGLE_BITS = 24


# ---------------------------------------------------------------------------
# 単精度への丸め(REP10専用、「半分は絶対値の大きい側」= 常に切り上げ)。
# 値は常に非負(符号は呼び出し側で最後に付ける)。
# ---------------------------------------------------------------------------


def _bracket(av: Fraction) -> int:
    """av を 2^(k-1) <= av < 2^k に収める最小の k を返す。"""
    import math

    est = math.floor(math.log2(av.numerator / av.denominator)) + 1
    while Fraction(2) ** (est - 1) > av:
        est -= 1
    while Fraction(2) ** est <= av:
        est += 1
    return est


def _round_half_up_mag(x: Fraction) -> int:
    """半分は絶対値の大きい側(x>=0前提なので常に切り上げ側)に丸める。"""
    n, d = x.numerator, x.denominator
    q, r = divmod(n, d)
    return q if 2 * r < d else q + 1


def _round_single_rep10(value: Fraction) -> Tuple[int, int]:
    """非負のFractionを単精度(24bit仮数)へ丸める。戻り値: (exp_byte, mant)。
    exp_byte>255ならOverflowErrorを投げる(MBF単精度の指数バイト上限)。
    """
    if value == 0:
        return (0, 0)
    k = _bracket(value)
    mant_exact = value * Fraction(2) ** (MBF_SINGLE_BITS - k)
    m = _round_half_up_mag(mant_exact)
    if m >= (1 << MBF_SINGLE_BITS):
        k += 1
        m = 1 << (MBF_SINGLE_BITS - 1)
    exp_byte = k + 128
    if exp_byte > 255:
        raise OverflowError("rep10 single overflow")
    if exp_byte < 1:
        return (0, 0)
    return (exp_byte, m)


def _decode_single(exp_byte: int, mant: int) -> Fraction:
    if exp_byte == 0:
        return Fraction(0)
    k = exp_byte - 128
    return Fraction(mant) * Fraction(2) ** (k - MBF_SINGLE_BITS)


# ---------------------------------------------------------------------------
# 定数の字句解析(REP10専用の軽量版)。桁文字列・小数点以下の桁数・指数だけ
# を取り出す(丸め方自体には関与しない、純粋な字句解析)。
# ---------------------------------------------------------------------------

_LIT_RE = re.compile(
    r"^([+-]?)(\d*)(?:\.(\d*))?(?:([eEdD])([+-]?\d+))?([!#]?)$"
)


class Rep10LexError(Exception):
    pass


def _lex_raw(text: str):
    m = _LIT_RE.match(text.strip())
    if not m or (not m.group(2) and not m.group(3)):
        raise Rep10LexError(f"cannot lex literal {text!r}")
    sign_ch, ip, fp, exp_marker, exp_digits, suffix = m.groups()
    ip = ip or ""
    fp = fp or ""
    digits = ip + fp
    frac_digits = len(fp)
    exponent = int(exp_digits) if exp_digits else 0
    has_dot = "." in text
    return sign_ch, digits, frac_digits, exponent, exp_marker, suffix, has_dot


def _classify_kind(digits: str, has_dot: bool, exp_marker, suffix) -> str:
    """oracle.parse_literalのkind判定(int->single->double昇格規則)を、
    値の丸め方には触れずに判定だけ独立に再実装したもの
    (docs/notes/l4-mbf-oracle.md「確認できたこと」4-5番と同じ規則)。"""
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
    if has_dot and kind == "int":
        kind = "single"
    if exp_marker:
        if exp_marker in "dD":
            kind = "double"
        else:
            if kind != "double":
                kind = "single"
    if suffix == "!":
        kind = "single"
    elif suffix == "#":
        kind = "double"
    return kind


def rep10_single_value(text: str) -> Tuple[int, int, int]:
    """REP10手順で単精度エンコード(sign, exp_byte, mant)を返す。
    text は kind=="single" と分かっている定数のみを渡す前提。
    """
    sign_ch, digits, frac_digits, exponent, _exp_marker, _suffix, _has_dot = _lex_raw(text)
    if digits == "":
        digits = "0"
    net_exp = exponent - frac_digits

    val = Fraction(0)
    exp_byte, mant = 0, 0
    for ch in digits:
        d = int(ch)
        val = val * 10 + d
        exp_byte, mant = _round_single_rep10(val)
        val = _decode_single(exp_byte, mant)

    if net_exp > 0:
        for _ in range(net_exp):
            val = val * 10
            exp_byte, mant = _round_single_rep10(val)
            val = _decode_single(exp_byte, mant)
    elif net_exp < 0:
        for _ in range(-net_exp):
            val = val / 10
            exp_byte, mant = _round_single_rep10(val)
            val = _decode_single(exp_byte, mant)

    sign_bit = 1 if sign_ch == "-" else 0
    return sign_bit, exp_byte, mant


def rep10_parse_literal(text: str) -> "oracle.GwNum":
    """REP10版のparse_literal相当。kindがsingleのときだけ独自手順で
    値を作り直す。int/doubleはREP10の対象外(定義上、単精度の定数読み取り
    にしか関与しない)なのでoracle.parse_literal(fin_algo="exact")の結果を
    そのまま使う(値そのものは争っていない箇所)。
    """
    sign_ch, digits, frac_digits, exponent, exp_marker, suffix, has_dot = _lex_raw(text)
    kind = _classify_kind(digits, has_dot, exp_marker, suffix)

    if kind != "single":
        return oracle.parse_literal(text, "exact")

    try:
        sign_bit, exp_byte, mant = rep10_single_value(text)
    except OverflowError:
        sign_bit = 1 if sign_ch == "-" else 0
        raise oracle.GwError("Overflow", oracle._max_value_num("single", sign_bit))

    num = oracle.GwNum("single", sign=sign_bit, exp=exp_byte, mant=mant)
    if sign_ch == "-" and num.exact() == -32768:
        return oracle.GwNum.from_int(-32768)
    return num


# ---------------------------------------------------------------------------
# 式評価(oracle._tokenizeと四則演算gw_binop/gw_negは共通基盤として再利用。
# 数値リテラルの読み取りだけrep10_parse_literalに差し替える)。
# ---------------------------------------------------------------------------


def rep10_eval_expr(expr: str) -> "oracle.GwNum":
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
            return rep10_parse_literal(t[1])
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


def predict_rep10(
    typed_print_body: str,
    single_digits: int = 6,
    small_rule: str = "len",
    small_len: int = 7,
    small_emin: int = 0,
    large_n: int = 0,
    fout_algo: str = "gw",
) -> Tuple[str, str]:
    """oracle.predict()と同じ形の戻り値(kind, printed)。FOUTの桁生成
    (fout_format/print_one)はoracleのものをそのまま使う(FINの候補間で
    争っていない箇所)。
    """
    try:
        num = rep10_eval_expr(typed_print_body)
    except oracle.GwError as e:
        line, _approx = oracle.print_one(
            e.residual, single_digits, small_rule, small_len, small_emin, large_n, fout_algo
        )
        return "error", f"{e.kind};{line}"
    line, _approx = oracle.print_one(
        num, single_digits, small_rule, small_len, small_emin, large_n, fout_algo
    )
    return "numeric", line


# ---------------------------------------------------------------------------
# REP01(l4-s4j) — l4-s4jでもno_survivorとなったREP10に続き、親から指示
# された3つ目の候補。正味の指数が負のとき、REP10のように真の÷10を
# 反復するのではなく、単精度に丸めた0.1(S01)を1回ずつ掛けて毎回単精度へ
# 丸め直す(正の指数側はREP10と同じ×10の反復)。出所は親から渡された
# scratchpadのfin-model-search.md/fin_model_search.py(Codex gpt-5.6-sol
# がGW-BASIC edf82c2のMATH1.ASM/MATH2.ASMとl4-s4i/l4-s4jの実測値から
# 事後で導出。詳細はdocs/notes/l4-fin-model-search.md参照)。
#
# tools/l4_mbf_oracle_v2.py の parse_literal(fin_algo="rep01")とは別に、
# ここでも_round_single_rep10(round_half_away、REP10と同じ丸め関数)を
# 使って独立に実装し、tools/l4_mbf_oracle_v2_selftest.shで両者が乱数
# 1万件でバイト一致することを検査する。
# ---------------------------------------------------------------------------

_REP01_S01_CACHE: Optional[Tuple[int, int]] = None


def _rep01_s01() -> Tuple[int, int]:
    global _REP01_S01_CACHE
    if _REP01_S01_CACHE is None:
        _REP01_S01_CACHE = _round_single_rep10(Fraction(1, 10))
    return _REP01_S01_CACHE


def rep01_single_value(text: str) -> Tuple[int, int, int]:
    """REP01手順で単精度エンコード(sign, exp_byte, mant)を返す。
    text は kind=="single" と分かっている定数のみを渡す前提。
    """
    sign_ch, digits, frac_digits, exponent, _exp_marker, _suffix, _has_dot = _lex_raw(text)
    if digits == "":
        digits = "0"
    net_exp = exponent - frac_digits

    val = Fraction(0)
    exp_byte, mant = 0, 0
    for ch in digits:
        d = int(ch)
        val = val * 10 + d
        exp_byte, mant = _round_single_rep10(val)
        val = _decode_single(exp_byte, mant)

    if net_exp > 0:
        for _ in range(net_exp):
            val = val * 10
            exp_byte, mant = _round_single_rep10(val)
            val = _decode_single(exp_byte, mant)
    elif net_exp < 0:
        s01_exp, s01_mant = _rep01_s01()
        s01 = _decode_single(s01_exp, s01_mant)
        for _ in range(-net_exp):
            val = val * s01
            exp_byte, mant = _round_single_rep10(val)
            val = _decode_single(exp_byte, mant)

    sign_bit = 1 if sign_ch == "-" else 0
    return sign_bit, exp_byte, mant


def rep01_parse_literal(text: str) -> "oracle.GwNum":
    sign_ch, digits, frac_digits, exponent, exp_marker, suffix, has_dot = _lex_raw(text)
    kind = _classify_kind(digits, has_dot, exp_marker, suffix)
    if kind != "single":
        return oracle.parse_literal(text, "exact")
    try:
        sign_bit, exp_byte, mant = rep01_single_value(text)
    except OverflowError:
        sign_bit = 1 if sign_ch == "-" else 0
        raise oracle.GwError("Overflow", oracle._max_value_num("single", sign_bit))
    num = oracle.GwNum("single", sign=sign_bit, exp=exp_byte, mant=mant)
    if sign_ch == "-" and num.exact() == -32768:
        return oracle.GwNum.from_int(-32768)
    return num


def rep01_eval_expr(expr: str) -> "oracle.GwNum":
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
            return rep01_parse_literal(t[1])
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


def predict_rep01(
    typed_print_body: str,
    single_digits: int = 6,
    small_rule: str = "len",
    small_len: int = 7,
    small_emin: int = 0,
    large_n: int = 0,
    fout_algo: str = "gw",
) -> Tuple[str, str]:
    try:
        num = rep01_eval_expr(typed_print_body)
    except oracle.GwError as e:
        line, _approx = oracle.print_one(
            e.residual, single_digits, small_rule, small_len, small_emin, large_n, fout_algo
        )
        return "error", f"{e.kind};{line}"
    line, _approx = oracle.print_one(
        num, single_digits, small_rule, small_len, small_emin, large_n, fout_algo
    )
    return "numeric", line


def predict_any(
    typed_print_body: str,
    fin_algo: str,
    single_digits: int = 6,
    small_rule: str = "len",
    small_len: int = 7,
    small_emin: int = 0,
    large_n: int = 0,
    fout_algo: str = "gw",
) -> Tuple[str, str]:
    """fin_algo in {"exact","gw"} の予測を、FOUT(桁生成)側は常に指定の
    fout_algo(既定"gw")で揃えて計算する。oracle.predict()はfin_algoを
    fout_algoに連動させてしまう(fout_algo="gw"のとき自動的にfin_algo も
    "gw")ため、ここでは oracle.eval_expr()/print_one() を直接呼んで
    FINとFOUTを独立に選べるようにする(REP10とそろえて3方式を同じFOUT
    設定で比較するため)。
    """
    try:
        num = oracle.eval_expr(typed_print_body, fin_algo)
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
    ap.add_argument("exprs", nargs="+")
    args = ap.parse_args()
    for arg in args.exprs:
        body = arg
        if body.lower().startswith("print "):
            body = body[6:]
        kind, pred = predict_rep10(body)
        print(f"{kind}\t{pred!r}")
