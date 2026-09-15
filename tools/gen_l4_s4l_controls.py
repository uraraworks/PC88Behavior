#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4l_controls.py — l4-s4lの候補(docs/notes/l4-s4l-candidates.tsv)
と同じ経路(グループpos/neg/hash/intdecそれぞれ)を通るが、DREP10E/DREP10A/
DEXACT/DREP01の4方式すべてが一致する対照を作る。書式は候補と同じ
(16桁・rstar・--fout-algo gw)。

各グループ2個以上、うち少なくとも1個は答えが0でないものを含める。
neg(負の指数側)は候補では見分ける式が見つからなかった経路だが、対照は
「4方式が一致する」ことを確かめるものなので、negも問題なく作れる
(むしろ候補で見つからなかったこと自体が「negでは4方式がほぼ常に一致する」
ことの裏付けになる)。

測定はしていない。判定には使わない。tools/l4_mbf_oracle_v2.pyは変更して
いない。docs/notes/l4-s4l-candidates.tsvは1バイトも変えていない。

使い方:
    python3 tools/gen_l4_s4l_controls.py > docs/notes/l4-s4l-controls.tsv
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_dmodels as dm  # noqa: E402

MAX_LEN = 70
FMT = dict(single_digits=16, small_rule="rstar", small_len=0, fout_algo="gw")
PER_GROUP = 3


def _preds(expr: str):
    out = {}
    for model in ("drep10e", "drep10a", "dexact", "drep01"):
        k, p = dm.predict_double(expr, model, **FMT)
        out[model] = (k, p)
    return out


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


def _find_agreeing(rng, gen_literal, group, target, tried_budget):
    rows = []
    seen = set()
    tried = 0
    while len(rows) < target and tried < tried_budget:
        tried += 1
        x = gen_literal(rng)
        try:
            g = dm.parse_double_literal(x, "drep10e")
        except Exception:
            continue
        c = round(g.exact())
        expr = f"{x}+{-c}" if c < 0 else f"{x}-{c}"
        typed = f"print {expr}"
        if len(typed) > MAX_LEN or typed in seen:
            continue
        try:
            p = _preds(expr)
        except Exception:
            continue
        vals = [p[m][1] for m in ("drep10e", "drep10a", "dexact", "drep01")]
        kinds = [p[m][0] for m in ("drep10e", "drep10a", "dexact", "drep01")]
        if not all(k == "numeric" for k in kinds):
            continue
        if len(set(vals)) != 1:
            continue
        seen.add(typed)
        rows.append((typed, group, vals[0]))
    return tried, rows


def main() -> int:
    tried_pos, rows_pos = _find_agreeing(
        random.Random(100), lambda r: _rand_double_lit(r, 2, 20), "pos", PER_GROUP, 20000
    )
    tried_neg, rows_neg = _find_agreeing(
        random.Random(200), lambda r: _rand_double_lit(r, -30, -2), "neg", PER_GROUP, 20000
    )
    tried_hash, rows_hash = _find_agreeing(random.Random(300), _rand_hash_lit, "hash", PER_GROUP, 20000)
    tried_intdec, rows_intdec = _find_agreeing(
        random.Random(400), _rand_intdec_lit, "intdec", PER_GROUP, 20000
    )

    rows = rows_pos + rows_neg + rows_hash + rows_intdec
    nonzero = sum(1 for _t, _g, v in rows if v.strip() != "0")

    print(
        "# l4-s4l 対照: 候補(docs/notes/l4-s4l-candidates.tsv)と同じ経路\n"
        "# (グループpos/neg/hash/intdecそれぞれ)を通るが、DREP10E/DREP10A/\n"
        "# DEXACT/DREP01の4方式すべての予測が一致する式。書式は候補と同じ\n"
        "# (16桁・rstar・--fout-algo gw)。判定には使わない\n"
        "# (測定はしていない)。\n#"
    )
    print(
        f"# pos: {len(rows_pos)}件(試行{tried_pos})、neg: {len(rows_neg)}件(試行{tried_neg})、"
        f"hash: {len(rows_hash)}件(試行{tried_hash})、intdec: {len(rows_intdec)}件(試行{tried_intdec})。"
        f"合計{len(rows)}件のうち答えが0でないもの{nonzero}件。"
    )
    print("# 生成コマンド: python3 tools/gen_l4_s4l_controls.py")
    print("typed\tgroup\tDREP10E\tDREP10A\tDEXACT\tDREP01")
    for typed, group, v in rows:
        print(f'{typed}\t{group}\t"{v}"\t"{v}"\t"{v}"\t"{v}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
