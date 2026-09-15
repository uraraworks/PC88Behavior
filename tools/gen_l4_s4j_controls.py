#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4j_controls.py — l4-s4jの候補(docs/notes/l4-s4j-candidates.tsv)
と同じ形(グループa/b/cそれぞれ)を通るが、EXACT/GW/REP10の3つの予測が
すべて一致する対照を作る。書式設定は候補と同じ
(--single-digits 6 --small-rule len --small-len 7 --fout-algo gw)。

各グループ2個以上、うち少なくとも1個は答えが0でないものを含める。

測定はしていない。判定には使わない。tools/l4_mbf_oracle_v2.pyは変更して
いない。docs/notes/l4-s4j-candidates.tsvは1バイトも変えていない。

使い方:
    python3 tools/gen_l4_s4j_controls.py > docs/notes/l4-s4j-controls.tsv
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_rep10 as rep10  # noqa: E402

FMT = dict(single_digits=6, small_rule="len", small_len=7, fout_algo="gw")
MAX_LEN = 70
PER_GROUP = 3


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
        base = round(gx.exact())
        delta = rng.choice([d for d in range(-6, 7) if d != 0]) if rng.random() < 0.5 else 0
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
        rows.append((typed, "a", pe, pg, pr))
    return tried, rows


def find_group_b(rng, target, tried_budget):
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
        if not (pe == pg == pr):
            continue
        seen.add(typed)
        rows.append((typed, "b", pe, pg, pr))
    return tried, rows


def find_group_c(rng, target, tried_budget):
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
        if not (pe == pg == pr):
            continue
        seen.add(typed)
        rows.append((typed, "c", pe, pg, pr))
    return tried, rows


def main() -> int:
    rng_a = random.Random(31415926)
    rng_b = random.Random(27182818)
    rng_c = random.Random(16180339)

    tried_a, rows_a = find_group_a(rng_a, PER_GROUP, 400000)
    tried_b, rows_b = find_group_b(rng_b, PER_GROUP, 400000)
    tried_c, rows_c = find_group_c(rng_c, PER_GROUP, 400000)

    rows = rows_a + rows_b + rows_c
    nonzero = sum(1 for _t, _g, pe, _pg, _pr in rows if pe.strip() != "0")

    print(
        "# l4-s4j 対照: 候補(docs/notes/l4-s4j-candidates.tsv)と同じ形\n"
        "# (グループa/b/cそれぞれ)を通るが、EXACT/GW/REP10の3方式の予測が\n"
        "# すべて一致する式。書式は候補と同じ(--single-digits 6\n"
        "# --small-rule len --small-len 7 --fout-algo gw)。\n"
        "# 判定には使わない(測定はしていない)。\n#"
    )
    print(
        f"# a: {len(rows_a)}件(試行{tried_a})、b: {len(rows_b)}件(試行{tried_b})、"
        f"c: {len(rows_c)}件(試行{tried_c})。合計{len(rows)}件のうち答えが0でないもの{nonzero}件。"
    )
    print("# 生成コマンド: python3 tools/gen_l4_s4j_controls.py")
    print("typed\tgroup\tEXACT\tGW\tREP10")
    for typed, group, pe, pg, pr in rows:
        print(f'{typed}\t{group}\t"{pe}"\t"{pg}"\t"{pr}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
