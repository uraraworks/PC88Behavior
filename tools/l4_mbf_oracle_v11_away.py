#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""l4_mbf_oracle_v11_away.py — 単精度四則演算(+-*/)の「正しい丸め・
away」予測器、薄い版。

## 位置づけ（親からの指摘への対応）

`docs/spec/l4-basic.md`5.3a節（`l4-s7a`/`l4-s7b`、`docs/notes/
l4-s7b-integer-only-rounding-results.md`）で、単精度の加減乗除は
「厳密値を1回だけ正しく丸める・タイ(丁度半分)はaway(0から遠い側)」と
確定し、`src/l4_basic/mbf_single.asm`のMBF_ADD/MBF_SUB/MBF_MUL/MBF_DIV
もこの規則に直した（`759de46`）。ところが`tools/l4_mbf_conform.py`
（Z80実照合、`tools/l4_mbf_z80_selftest.sh`から呼ばれる）は比較相手に
`tools/l4_mbf_oracle_v2.py`の`gw_binop`（add/sub/divは厳密値1回丸め・
**偶数**タイ、mulは$FMULSの粗いROUNS再現）を使い続けていたため、
実装を直した後もN=400照合でadd/sub/mul不一致（16/8/14件、いずれも
タイまたは粗い丸めの差）が出るようになっていた。

本モジュールは、その比較相手を「correct-rounding・awayタイブレーク」
へ切り替えるための薄い予測器。`tools/l4_mbf_oracle_v2.py`の
`_encode_single_away`（REP01用に先行実装済み、`round_half_away_mag`の
24bit版。`tools/l4_mbf_oracle_v9_s7a.py`の`away`候補と数学的に同一）
をそのまま呼ぶ（二重実装しない）。**v2自体（`gw_binop`・
`gw_mul_single`・偶数丸めの`encode_mbf`）は一切変更していない** —
REP01・FIN/FOUT・整数変換・倍精度(dadd/dsub/dmul/ddiv等)の期待値は
引き続きv2をそのまま使う。

## tools/l4_mbf_conform.py側の切り替え内容

`expected_binop(op, a, b)`（add/sub/mul/divの期待値。呼び出し元は
`compare()`のelse分岐、この4演算専用）の実装を、本モジュールの
`expected_binop_away`に差し替えた。整数変換(itos/itod/stod/dtos)・
FIN/FOUT(fin/dfin/fout/dfout)・倍精度(dadd/dsub/dmul/ddiv/dcmp/dneg)・
cmp/negの期待値関数は変更していない（従来どおりv2を直接使う）。

## 故障注入との関係

`tools/l4_mbf_conform.py`の`--fault`（`load_mbf_src`、`src/l4_basic/
mbf_single.asmへANDやNOPでパッチを当てて故障注入する既存の仕組み）は
**予測器ではなく実装(Z80コード)側の故障注入**なので、本モジュールの
新設とは独立。ただし旧経路（偶数丸め・粗いROUNS再現）を前提にした
故障注入点は、実装をaway丸めへ直した後は踏まれない箇所があり得る。
それらは`src/l4_basic/mbf_single.asm`側の対応する行（`_add_round`の
awayタイブレーク分岐・`MBF_MUL`の`WK_MUL_ROUNDMODE=1`固定経路・
`MBF_DIV`が共有する`_add_round`）に付け直す
（`tools/l4_mbf_conform.py`の`load_mbf_src`のfault名・パッチ箇所を
参照）。
"""
from __future__ import annotations

import pathlib
import sys
from fractions import Fraction
from typing import Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import l4_mbf_oracle_v2 as oracle  # noqa: E402


def _encode_away_nonneg(av: Fraction) -> Tuple[int, int]:
    """非負のFractionを単精度(24bit仮数)へaway(半分は絶対値の大きい側)
    で丸める。v2の`_encode_single_away`をそのまま呼ぶ(二重実装しない)。
    戻り値: (exp_byte, mant)。exp_byte>255ならOverflowErrorを投げる
    (v2と同じ契約)。
    """
    return oracle._encode_single_away(av)  # noqa: SLF001 (同一プロジェクトの薄いラッパ)


def encode_single_away(value: Fraction) -> "oracle.GwNum":
    """厳密値(Fraction、符号つき)を単精度away丸めのoracle.GwNumへ。
    exp_byte>255ならOverflowErrorをそのまま伝播する(呼び出し側で
    oracle.GwErrorへ変換する)。
    """
    if value == 0:
        return oracle.GwNum("single", sign=0, exp=0, mant=0)
    sign = 1 if value < 0 else 0
    av = -value if sign else value
    exp_byte, mant = _encode_away_nonneg(av)
    return oracle.GwNum("single", sign=sign, exp=exp_byte, mant=mant)


def expected_binop_away(op: str, a: "oracle.GwNum", b: "oracle.GwNum") -> "oracle.GwNum":
    """単精度add/sub/mul/divを、厳密値を1回だけawayタイブレークで丸めて
    返す。`docs/spec/l4-basic.md`5.3a節・`src/l4_basic/mbf_single.asm`の
    `_add_round`(ADD/SUB/DIV共通)・`MBF_MUL`(既定でaway、
    `MBF_MUL_HALFUP`と同一経路)と同じ規則。

    エラー(オーバーフロー・0除算)は`oracle.GwError`(v2の`gw_binop`と
    同じ例外型・残差値の作り方)で通知する。呼び出し元
    (`tools/l4_mbf_conform.py`の`expected_binop`)の例外処理はv2版から
    変更不要。
    """
    if a.kind != "single" or b.kind != "single":
        raise ValueError(
            "l4_mbf_oracle_v11_away.expected_binop_away は単精度専用 "
            f"(a.kind={a.kind!r}, b.kind={b.kind!r})。倍精度はv2のまま。"
        )
    av, bv = a.exact(), b.exact()
    if op == "+":
        exact = av + bv
    elif op == "-":
        exact = av - bv
    elif op == "*":
        exact = av * bv
    elif op == "/":
        if bv == 0:
            sign = 1 if av < 0 else 0
            raise oracle.GwError("Division by zero", oracle._max_value_num("single", sign))
        exact = av / bv
    else:
        raise ValueError(f"unknown op {op!r}")
    try:
        return encode_single_away(exact)
    except OverflowError:
        sign = 1 if exact < 0 else 0
        raise oracle.GwError("Overflow", oracle._max_value_num("single", sign))
