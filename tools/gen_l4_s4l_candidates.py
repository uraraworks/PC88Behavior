#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4l_candidates.py — l4-s4l: 倍精度の定数読み取り新候補DREP10の
2変種(DREP10E=round-half-even、DREP10A=round-half-away、
tools/l4_dmodels.py)のPRINT出力が異なる打鍵可能な式の候補を探す。
参照としてDEXACT・DREP01(l4-s4kで実装済み)も併記する。書式は4候補とも
共通(16桁・rstar・--fout-algo gw)。

DREP10E/DREP10Aの違いは、正味の指数nを適用する×10(n>0)・真の÷10(n<0)の
反復の丸め方だけ(digit積み上げは常にround-half-even)。

グループ:
  (a) pos    正味の指数が正(×10側)。"x-c"の形。Codex(gpt-5.6-sol、
             docs/notes/l4-dfin-model-search.md)が見分ける式として提示した
             5本を含む(該当行はsource=codex、他はsource=own)。
  (b) neg    正味の指数が負(÷10側)。**見分ける式が見つからなかった。**
             理由はノート(docs/notes/l4-s4l-double-drep10-variants.md)参照。
  (c) hash   `#`付きで小数点以下の桁があり、かつ明示指数(e+)で正味指数を
             正にした定数。"x-c"の形。
  (d) intdec 小数点を除く数字が8桁以上の整数に小数部を足し、かつ明示指数
             (e+)で正味指数を正にした定数。"x-c"の形。

(c)(d)はいずれも「正味指数が正」にしないとDREP10E/DREP10Aの食い違いが
実質的に見つからなかった(グループ(b)と同じ理由、ノート参照)ため、
task定義の形(#付き小数・8桁以上の整数+小数)に明示指数を足して正味指数を
正にしている。

測定はしていない。判定には使わない。tools/l4_mbf_oracle_v2.pyは変更して
いない。

使い方:
    python3 tools/gen_l4_s4l_candidates.py > docs/notes/l4-s4l-candidates.tsv
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_dmodels as dm  # noqa: E402

MAX_LEN = 70
FMT = dict(single_digits=16, small_rule="rstar", small_len=0, fout_algo="gw")

# Codex(gpt-5.6-sol)がdocs/notes/l4-dfin-model-search.mdの分析で示した、
# DREP10E/DREP10Aを見分ける5本(出所: scratchpadのdfin-model-search.md
# 「残る同値候補と判別式」節。GW-BASIC edf82c2のソースとl4-s4kの実測から
# 事後で導出した予測であり、測定はしていない)。
CODEX_EXPRS = [
    "8937451488973898e+7-89374514889738978066432",
    "2950953187928057e+7-29509531879280569483264",
    "4944140467464335e+8-494414046746433520926720",
    "7096509499740639e+4-70965094997406390272",
    "4953814120086905e+2-495381412008690496",
]


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


def _rand_hash_pos_lit(rng: random.Random) -> str:
    # #付き小数、明示指数(e+)で正味指数を正にする
    nint = rng.randint(1, 6)
    nfrac = rng.randint(1, 6)
    int_digits = "".join(rng.choice("0123456789") for _ in range(nint))
    int_digits = rng.choice("123456789") + int_digits[1:]
    frac_digits = "".join(rng.choice("0123456789") for _ in range(nfrac))
    k = nfrac + rng.randint(1, 12)
    sign = rng.choice(["", "-"])
    return f"{sign}{int_digits}.{frac_digits}e+{k}#"


def _rand_intdec_pos_lit(rng: random.Random) -> str:
    # 8桁以上の整数+小数、明示指数(e+)で正味指数を正にする
    nint = rng.randint(8, 14)
    int_digits = "".join(rng.choice("0123456789") for _ in range(nint))
    int_digits = rng.choice("123456789") + int_digits[1:]
    nfrac = rng.randint(1, 4)
    frac_digits = "".join(rng.choice("0123456789") for _ in range(nfrac))
    k = nfrac + rng.randint(1, 10)
    sign = rng.choice(["", "-"])
    return f"{sign}{int_digits}.{frac_digits}e+{k}"


def _find_via_subtraction(rng, gen_literal, group, source, target, tried_budget, seen):
    rows = []
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
        if not all(p[m][0] == "numeric" for m in ("drep10e", "drep10a", "dexact", "drep01")):
            continue
        if p["drep10e"][1] == p["drep10a"][1]:
            continue
        seen.add(typed)
        rows.append((typed, group, source, p["dexact"][1], p["drep01"][1], p["drep10e"][1], p["drep10a"][1]))
    return tried, rows


def main() -> int:
    seen = set()
    rows = []

    # (a) pos: Codexの5本(source=codex)
    for body in CODEX_EXPRS:
        typed = f"print {body}"
        seen.add(typed)
        p = _preds(body)
        rows.append((typed, "pos", "codex", p["dexact"][1], p["drep01"][1], p["drep10e"][1], p["drep10a"][1]))

    # (a) pos: 自前で探した3本(source=own)
    tried_pos, rows_pos = _find_via_subtraction(
        random.Random(20260916), lambda r: _rand_double_lit(r, 2, 20), "pos", "own", 3, 400000, seen
    )
    rows.extend(rows_pos)

    # (c) hash
    tried_hash, rows_hash = _find_via_subtraction(
        random.Random(20260917), _rand_hash_pos_lit, "hash", "own", 4, 400000, seen
    )
    rows.extend(rows_hash)

    # (d) intdec
    tried_intdec, rows_intdec = _find_via_subtraction(
        random.Random(20260918), _rand_intdec_pos_lit, "intdec", "own", 4, 400000, seen
    )
    rows.extend(rows_intdec)

    exact_also_diff = sum(
        1 for _t, _g, _s, pe, pr01, pe10, pa10 in rows if pe != pe10 and pe != pa10
    )

    print(
        "# l4-s4l 候補: 倍精度の定数読み取りDREP10の2変種\n"
        "# (DREP10E=round-half-even/DREP10A=round-half-away、\n"
        "# tools/l4_dmodels.py)でPRINT出力が異なる打鍵可能な式。参照として\n"
        "# DEXACT・DREP01(l4-s4k)も併記。書式は4候補とも共通\n"
        "# (16桁・rstar・--fout-algo gw)。\n"
        "# group: pos=正の指数側(x-c、Codexの5本を含む)、hash=#付き小数+\n"
        "# 明示指数(正味指数を正にした)、intdec=8桁以上の整数+小数+明示指数\n"
        "# (同じく正味指数を正にした)。\n"
        "# neg(負の指数側、真の÷10)は見分ける式が見つからなかった\n"
        "# (docs/notes/l4-s4l-double-drep10-variants.md参照)。\n"
        "# source: own=本探索で見つけた式、codex=Codexが分析で示した式。\n"
        "# 判定には使わない(測定はしていない)。\n#"
    )
    print(
        f"# pos: Codex5件+own{len(rows_pos)}件(試行{tried_pos})、"
        f"hash: {len(rows_hash)}件(試行{tried_hash})、"
        f"intdec: {len(rows_intdec)}件(試行{tried_intdec})。"
        f"合計{len(rows)}件のうちDEXACTとも異なるものは{exact_also_diff}件。"
    )
    print("# 生成コマンド: python3 tools/gen_l4_s4l_candidates.py")
    print("typed\tgroup\tsource\tDREP10E\tDREP10A\tDEXACT\tDREP01")
    for typed, group, source, pe, pr01, pe10, pa10 in rows:
        print(f'{typed}\t{group}\t{source}\t"{pe10}"\t"{pa10}"\t"{pe}"\t"{pr01}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
