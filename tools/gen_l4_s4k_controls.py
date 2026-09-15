#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4k_controls.py — l4-s4kの候補(docs/notes/l4-s4k-candidates.tsv)
と同じ形(グループpos/neg/hash/intdecそれぞれ)を通るが、DEXACT/DGW/DREP01
の3方式の予測がすべて一致する対照を作る。書式は候補と同じ
(16桁・rstar・--fout-algo gw)。

各グループ2個以上、うち少なくとも1個は答えが0でないものを含める。

測定はしていない。判定には使わない。tools/l4_mbf_oracle_v2.pyは変更して
いない。docs/notes/l4-s4k-candidates.tsvは1バイトも変えていない。

使い方:
    python3 tools/gen_l4_s4k_controls.py > docs/notes/l4-s4k-controls.tsv
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_dmodels as dm  # noqa: E402

MAX_LEN = 70
PER_GROUP = 3


def _rand_double_lit(rng: random.Random, exp_lo: int, exp_hi: int) -> str:
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
    return f"{sign}{s}e{exp:+d}"


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


def _find_via_subtraction(rng, gen_literal, group, target, tried_budget, jitter=True):
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
        base = round(gw.exact())
        delta = 0
        if jitter and rng.random() < 0.6:
            delta = rng.choice([d for d in range(-4, 5) if d != 0])
        c = base + delta
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
        if not (pe == pg == pr):
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
        if not (pe == pg == pr):
            continue
        seen.add(typed)
        rows.append((typed, "neg", pe, pg, pr))
    return tried, rows


def find_group_hash(rng, target, tried_budget):
    return _find_via_subtraction(rng, _rand_hash_lit, "hash", target, tried_budget)


def find_group_intdec(rng, target, tried_budget):
    return _find_via_subtraction(rng, _rand_intdec_lit, "intdec", target, tried_budget)


def main() -> int:
    rng_a = random.Random(31415926)
    rng_b = random.Random(27182818)
    rng_c = random.Random(16180339)
    rng_d = random.Random(14142135)

    tried_a, rows_a = find_group_pos(rng_a, PER_GROUP, 400000)
    tried_b, rows_b = find_group_neg(rng_b, PER_GROUP, 400000)
    tried_c, rows_c = find_group_hash(rng_c, PER_GROUP, 400000)
    tried_d, rows_d = find_group_intdec(rng_d, PER_GROUP, 400000)

    rows = rows_a + rows_b + rows_c + rows_d
    nonzero = sum(1 for _t, _g, pe, _pg, _pr in rows if pe.strip() != "0")

    print(
        "# l4-s4k 対照: 候補(docs/notes/l4-s4k-candidates.tsv)と同じ形\n"
        "# (グループpos/neg/hash/intdecそれぞれ)を通るが、DEXACT/DGW/DREP01\n"
        "# の3方式の予測がすべて一致する式。書式は候補と同じ\n"
        "# (16桁・rstar・--fout-algo gw)。判定には使わない\n"
        "# (測定はしていない)。\n#"
    )
    print(
        f"# pos: {len(rows_a)}件(試行{tried_a})、neg: {len(rows_b)}件(試行{tried_b})、"
        f"hash: {len(rows_c)}件(試行{tried_c})、intdec: {len(rows_d)}件(試行{tried_d})。"
        f"合計{len(rows)}件のうち答えが0でないもの{nonzero}件。"
    )
    print("# 生成コマンド: python3 tools/gen_l4_s4k_controls.py")
    print("typed\tgroup\tDEXACT\tDGW\tDREP01")
    for typed, group, pe, pg, pr in rows:
        print(f'{typed}\t{group}\t"{pe}"\t"{pg}"\t"{pr}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
