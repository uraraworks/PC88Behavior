#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4k_candidates.py — l4-s4k: 倍精度の定数読み取り3候補
(DEXACT/DGW/DREP01、tools/l4_dmodels.py)のPRINT出力が異なる打鍵可能な
式の候補を探す。書式は16桁・rstar・--fout-algo gw(l4-s4e/l4-s4fで確認
済みの倍精度の想定設定)で3候補とも共通にする。

4グループ:
  (a) pos    正味の指数が正(×10側)。"x-c"(cはxの厳密値に最も近い整数)。
  (b) neg    正味の指数が負(×0.1側)。"print x"そのまま。
  (c) hash   `#`付きで小数点以下の桁がある定数。"x-c"の形。
  (d) intdec 小数点を除く数字が8桁以上の整数に小数部を足した形。
             "x-c"の形。

測定はしていない。判定には使わない。tools/l4_mbf_oracle_v2.pyは変更して
いない。

使い方:
    python3 tools/gen_l4_s4k_candidates.py > docs/notes/l4-s4k-candidates.tsv
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_dmodels as dm  # noqa: E402

MAX_LEN = 70
TARGET_PER_GROUP = 6


def _rand_double_lit(rng: random.Random, exp_lo: int, exp_hi: int, suffix: str = "") -> str:
    ndig = rng.randint(8, 16)
    digits = [rng.choice("0123456789") for _ in range(ndig)]
    if digits[0] == "0":
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
    return f"{sign}{s}e{exp:+d}{suffix}"


def _rand_hash_lit(rng: random.Random) -> str:
    nint = rng.randint(1, 8)
    nfrac = rng.randint(1, 8)
    int_digits = "".join(rng.choice("0123456789") for _ in range(nint))
    int_digits = rng.choice("123456789") + int_digits[1:]
    frac_digits = "".join(rng.choice("0123456789") for _ in range(nfrac))
    sign = rng.choice(["", "-"])
    return f"{sign}{int_digits}.{frac_digits}#"


def _rand_intdec_lit(rng: random.Random) -> str:
    nint = rng.randint(8, 16)
    int_digits = "".join(rng.choice("0123456789") for _ in range(nint))
    int_digits = rng.choice("123456789") + int_digits[1:]
    nfrac = rng.randint(1, 4)
    frac_digits = "".join(rng.choice("0123456789") for _ in range(nfrac))
    sign = rng.choice(["", "-"])
    return f"{sign}{int_digits}.{frac_digits}"


def _preds(expr: str):
    ke, pe = dm.predict_double(expr, "dexact")
    kg, pg = dm.predict_double(expr, "dgw")
    kr, pr = dm.predict_double(expr, "drep01")
    return (ke, pe), (kg, pg), (kr, pr)


def _find_via_subtraction(rng, gen_literal, group, target, tried_budget):
    rows = []
    seen = set()
    tried = 0
    while len(rows) < target and tried < tried_budget:
        tried += 1
        x = gen_literal(rng)
        try:
            gw = dm.parse_double_literal(x, "dgw")
        except Exception:
            continue
        c = round(gw.exact())
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
        rows.append((typed, group, pe, pg, pr))
    return tried, rows


def find_group_pos(rng, target, tried_budget):
    return _find_via_subtraction(rng, lambda r: _rand_double_lit(r, 2, 20), "pos", target, tried_budget)


def find_group_neg(rng, target, tried_budget):
    rows = []
    seen = set()
    tried = 0
    while len(rows) < target and tried < tried_budget:
        tried += 1
        x = _rand_double_lit(rng, -40, -2)
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
        rows.append((typed, "neg", pe, pg, pr))
    return tried, rows


def find_group_hash(rng, target, tried_budget):
    return _find_via_subtraction(rng, _rand_hash_lit, "hash", target, tried_budget)


def find_group_intdec(rng, target, tried_budget):
    return _find_via_subtraction(rng, _rand_intdec_lit, "intdec", target, tried_budget)


def main() -> int:
    rng_a = random.Random(20260916)
    rng_b = random.Random(20260917)
    rng_c = random.Random(20260918)
    rng_d = random.Random(20260919)

    tried_a, rows_a = find_group_pos(rng_a, TARGET_PER_GROUP, 400000)
    tried_b, rows_b = find_group_neg(rng_b, TARGET_PER_GROUP, 400000)
    tried_c, rows_c = find_group_hash(rng_c, TARGET_PER_GROUP, 400000)
    tried_d, rows_d = find_group_intdec(rng_d, TARGET_PER_GROUP, 400000)

    rows = rows_a + rows_b + rows_c + rows_d
    exact_also_diff = sum(1 for _t, _g, pe, pg, pr in rows if pe != pg and pe != pr)

    print(
        "# l4-s4k 候補: 倍精度の定数読み取り3候補(DEXACT/DGW/DREP01、\n"
        "# tools/l4_dmodels.py)でPRINT出力が異なる打鍵可能な式。書式は\n"
        "# 3候補とも共通(16桁・rstar・--fout-algo gw)。丸めは読み取り側も\n"
        "# 出力側(l4-s4h)と同じ「半分は絶対値の大きい側」と仮定(未確認)。\n"
        "# group: pos=正の指数側(x-c)、neg=負の指数側(print xそのまま)、\n"
        "# hash=#付き小数、intdec=8桁以上の整数+小数(いずれもx-c)。\n"
        "# 判定には使わない(測定はしていない)。\n#"
    )
    print(
        f"# pos: 試行{tried_a}件中{len(rows_a)}件、neg: 試行{tried_b}件中{len(rows_b)}件、"
        f"hash: 試行{tried_c}件中{len(rows_c)}件、intdec: 試行{tried_d}件中{len(rows_d)}件。"
        f"合計{len(rows)}件のうちDEXACTとも異なるものは{exact_also_diff}件。"
    )
    print("# 生成コマンド: python3 tools/gen_l4_s4k_candidates.py")
    print("typed\tgroup\tDEXACT\tDGW\tDREP01")
    for typed, group, pe, pg, pr in rows:
        print(f'{typed}\t{group}\t"{pe}"\t"{pg}"\t"{pr}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
