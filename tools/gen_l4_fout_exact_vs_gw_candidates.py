#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_fout_exact_vs_gw_candidates.py — N88想定の設定(単精度6桁・
LEN7、倍精度RSTAR・LG16)で --fout-algo exact と --fout-algo gw が
食い違う打鍵可能な10進定数を乱数で探し、
docs/notes/l4-fout-exact-vs-gw-candidates.tsv を作る。

単精度は一様乱数(符号+小数点込みで数字最大7桁)を60000件、倍精度は
同じ方法(#付き、数字最大16桁、明示指数なし)を200000件試す。単精度は
見つかり次第20件で打ち切る。倍精度は(過去の実行で)0件だったため、
0件ならその旨をコメントに書く(判定には使わない)。

使い方:
    python3 tools/gen_l4_fout_exact_vs_gw_candidates.py > docs/notes/l4-fout-exact-vs-gw-candidates.tsv
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import predict  # noqa: E402

SINGLE_SEED = 12345
DOUBLE_SEED = 54321
SINGLE_TRIALS = 60000
DOUBLE_TRIALS = 200000
MAX_ROWS = 20


def rand_literal(max_digits: int, suffix: str, rng: random.Random) -> str:
    ndig = rng.randint(1, max_digits)
    digits = "".join(rng.choice("0123456789") for _ in range(ndig))
    dp = rng.randint(0, ndig)
    s = digits[:dp] + ("." + digits[dp:] if dp < ndig else "")
    if s in ("", "."):
        s = "0"
    sign = rng.choice(["", "-"])
    return sign + s + suffix


def find_diffs(max_digits, suffix, kind, single_digits, trials, seed, max_rows):
    rng = random.Random(seed)
    rows = []
    for _ in range(trials):
        lit = rand_literal(max_digits, suffix, rng)
        try:
            _, e, _ = predict(lit, single_digits, "rstar", 0, 0, 0, "exact")
            _, g, _ = predict(lit, single_digits, "rstar", 0, 0, 0, "gw")
        except Exception:
            continue
        if e != g:
            rows.append((lit, kind, e, g))
            if len(rows) >= max_rows:
                break
    return rows


def main() -> int:
    single_rows = find_diffs(7, "", "single", 6, SINGLE_TRIALS, SINGLE_SEED, MAX_ROWS)
    double_rows = find_diffs(16, "#", "double", 6, DOUBLE_TRIALS, DOUBLE_SEED, MAX_ROWS)

    print(
        "# N88想定の設定(単精度6桁・LEN7、倍精度RSTAR・LG16)で、\n"
        "# tools/l4_mbf_oracle_v2.py --fout-algo exact と --fout-algo gw が\n"
        "# 食い違う「打鍵できる10進定数」を乱数で探した候補。判定には使わない\n"
        "# (測定はしていない。詳細はdocs/notes/l4-mbf-oracle.md「FOUTのexactと\n"
        "# gwの違い」参照)。\n#"
    )
    print(
        f"# 単精度: 一様乱数({SINGLE_TRIALS}件試行)で{len(single_rows)}件見つかった。"
    )
    if double_rows:
        print(f"# 倍精度: 一様乱数({DOUBLE_TRIALS}件試行)で{len(double_rows)}件見つかった。")
    else:
        print(f"# 倍精度: 一様乱数({DOUBLE_TRIALS}件試行)で0件だった。")
    print("# 生成コマンド: python3 tools/gen_l4_fout_exact_vs_gw_candidates.py")
    print("typed\ttype\texact\tgw")
    for typed, kind, e, g in single_rows + double_rows:
        print(f'{typed}\t{kind}\t"{e}"\t"{g}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
