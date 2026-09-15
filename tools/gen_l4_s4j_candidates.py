#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4j_candidates.py — l4-s4j: REP10(tools/l4_rep10.py)とGWの
PRINT出力が異なる打鍵可能な式の候補を探す。EXACTとも異なるものを優先する。
N88想定の書式設定(--single-digits 6 --small-rule len --small-len 7
--fout-algo gw)はEXACT/GW/REP10のどれでも同じにして揃える(FIN=定数の
読み取り方だけを3方式で比較するため、FOUT=桁生成は固定する)。

3グループ:
  (a) 正味の指数が正(10を掛ける側、"e+"): "x-c"(cはxの厳密値に最も
      近い整数、9桁前後になるため倍精度の定数になる)の形。
  (b) 正味の指数が負(10で割る側、"e-"や小数点以下の桁がある定数):
      小さい値になるため6桁のPRINT表示にそのまま最下位ビットの差が
      現れる。"print x"そのままの形(引き算は不要)。
  (c) 単精度どうしの演算だけで差が見える式(倍精度の定数を使わない):
      "x-y"(x,yとも単精度のe指数定数、同程度の桁数・指数)。

測定はしていない。判定には使わない。tools/l4_mbf_oracle_v2.pyは変更して
いない。

使い方:
    python3 tools/gen_l4_s4j_candidates.py > docs/notes/l4-s4j-candidates.tsv
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_rep10 as rep10  # noqa: E402

FMT = dict(single_digits=6, small_rule="len", small_len=7, fout_algo="gw")
MAX_LEN = 70


def _rand_single_lit(rng: random.Random, exp_lo: int, exp_hi: int) -> str:
    ndig = rng.randint(1, 7)
    digits = [rng.choice("0123456789") for _ in range(ndig)]
    if digits[0] == "0" and ndig > 1:
        digits[0] = rng.choice("123456789")
    dotpos = rng.randint(0, ndig)
    if dotpos == 0:
        s = "." + "".join(digits)
    elif dotpos == ndig:
        s = "".join(digits) + "."
    else:
        s = "".join(digits[:dotpos]) + "." + "".join(digits[dotpos:])
    sign = rng.choice(["", "-"])
    exp = rng.randint(exp_lo, exp_hi)
    return f"{sign}{s}e{exp:+d}"


def _preds(expr: str):
    ke, pe = rep10.predict_any(expr, "exact", **FMT)
    kg, pg = rep10.predict_any(expr, "gw", **FMT)
    kr, pr = rep10.predict_rep10(expr, **FMT)
    return (ke, pe), (kg, pg), (kr, pr)


def find_group_a(rng, target, tried_budget):
    """(a) 正の指数側: x-c(cは倍精度の整数)。"""
    rows = []
    seen = set()
    tried = 0
    while len(rows) < target and tried < tried_budget:
        tried += 1
        x = _rand_single_lit(rng, 2, 11)
        try:
            gx = rep10.oracle.parse_literal(x, "gw")
        except Exception:
            continue
        if gx.kind != "single":
            continue
        c = round(gx.exact())
        expr = f"{x}+{-c}" if c < 0 else f"{x}-{c}"
        typed = f"print {expr}"
        if len(typed) > MAX_LEN or typed in seen:
            continue
        try:
            (ke, pe), (kg, pg), (kr, pr) = _preds(expr)
        except Exception:
            continue
        if not (ke == kg == kr == "numeric"):
            continue
        if pg == pr:
            continue
        seen.add(typed)
        rows.append((typed, "a", pe, pg, pr))
    return tried, rows


def find_group_b(rng, target, tried_budget):
    """(b) 負の指数側: print x そのまま。"""
    rows = []
    seen = set()
    tried = 0
    while len(rows) < target and tried < tried_budget:
        tried += 1
        x = _rand_single_lit(rng, -20, -2)
        expr = x
        typed = f"print {expr}"
        if len(typed) > MAX_LEN or typed in seen:
            continue
        try:
            (ke, pe), (kg, pg), (kr, pr) = _preds(expr)
        except Exception:
            continue
        if not (ke == kg == kr == "numeric"):
            continue
        if pg == pr:
            continue
        seen.add(typed)
        rows.append((typed, "b", pe, pg, pr))
    return tried, rows


def find_group_c(rng, target, tried_budget):
    """(c) 単精度どうしの演算だけ: x-y(倍精度の定数を使わない)。"""
    rows = []
    seen = set()
    tried = 0
    while len(rows) < target and tried < tried_budget:
        tried += 1
        x = _rand_single_lit(rng, 2, 11)
        y = _rand_single_lit(rng, 2, 11)
        if y.startswith("-"):
            expr = f"{x}+{y[1:]}"
        else:
            expr = f"{x}-{y}"
        typed = f"print {expr}"
        if len(typed) > MAX_LEN or typed in seen:
            continue
        try:
            (ke, pe), (kg, pg), (kr, pr) = _preds(expr)
        except Exception:
            continue
        if not (ke == kg == kr == "numeric"):
            continue
        if pg == pr:
            continue
        seen.add(typed)
        rows.append((typed, "c", pe, pg, pr))
    return tried, rows


def main() -> int:
    rng_a = random.Random(20260916)
    rng_b = random.Random(20260917)
    rng_c = random.Random(20260918)

    tried_a, rows_a = find_group_a(rng_a, 8, 400000)
    tried_b, rows_b = find_group_b(rng_b, 8, 400000)
    tried_c, rows_c = find_group_c(rng_c, 4, 400000)

    rows = rows_a + rows_b + rows_c
    exact_also_diff = sum(1 for _t, _g, pe, pg, pr in rows if pe != pg and pe != pr)

    print(
        "# l4-s4j 候補: REP10(tools/l4_rep10.py)とGWでPRINT出力が異なる\n"
        "# 打鍵可能な式。書式はEXACT/GW/REP10とも共通\n"
        "# (--single-digits 6 --small-rule len --small-len 7 --fout-algo gw)。\n"
        "# group a=正の指数側(x-c、cは倍精度の整数)、b=負の指数側\n"
        "# (print xそのまま)、c=単精度どうしの演算のみ(倍精度の定数を\n"
        "# 使わない、x-y)。判定には使わない(測定はしていない)。\n#"
    )
    print(
        f"# a: 試行{tried_a}件中{len(rows_a)}件、b: 試行{tried_b}件中{len(rows_b)}件、"
        f"c: 試行{tried_c}件中{len(rows_c)}件。合計{len(rows)}件のうちEXACTとも"
        f"異なるものは{exact_also_diff}件。"
    )
    print("# 生成コマンド: python3 tools/gen_l4_s4j_candidates.py")
    print("typed\tgroup\tEXACT\tGW\tREP10")
    for typed, group, pe, pg, pr in rows:
        print(f'{typed}\t{group}\t"{pe}"\t"{pg}"\t"{pr}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
