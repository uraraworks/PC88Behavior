#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4e_posthoc_inputs.py — l4-s4e 用、過去の入力19件へ
GW16/RSTAR/RSTAR_B を当てた事後表(判定には使わない)。

**事後(post hoc)の表であり、判定には使わない。** l4-s4a〜dで既に打って
いる腕への機械的な適用であり、GW16/RSTAR/RSTAR_Bを思いついた後に、
それを立てるのに使ったのと同じデータへ当てはめても仮説の検証には
ならないため(l4-s4a-h6-posthoc.tsvと同じ位置づけ)。l4-s4a〜dの測定結果
ノートは読んでいない。

あわせて、RSTAR_Bの判定に効く「2進の値(MBFの厳密値)が10進の値より
上か下か」を1d-16・2d-16・3d-16・5d-16・9d-16・1d-15・1.5d-15について
示す表を末尾に付けた。

使い方:
    python3 tools/gen_l4_s4e_posthoc_inputs.py > docs/notes/l4-s4e-posthoc-inputs.tsv
"""

import os
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import predict, eval_expr  # noqa: E402

INPUTS = [
    "1#/3",
    "1#/7",
    ".0001#",
    "1d-17",
    "1d-15",
    "1d-16",
    "1.5d-15",
    "1.5d-16",
    ".1234567890123456#",
    "1.234567890123456d-2",
    "1#/3000",
    ".001234567890123456#",
    "1.23456789012345d-3",
    "1.23d-15",
    "1.234d-15",
    "1.2345d-15",
    "1#/300",
    "1#/30",
    "1.5d-14",
]

# (typed, 10進の厳密値をFractionで表したもの)
DIRECTION_CASES = [
    ("1d-16", Fraction(1) * Fraction(10) ** -16),
    ("2d-16", Fraction(2) * Fraction(10) ** -16),
    ("3d-16", Fraction(3) * Fraction(10) ** -16),
    ("5d-16", Fraction(5) * Fraction(10) ** -16),
    ("9d-16", Fraction(9) * Fraction(10) ** -16),
    ("1d-15", Fraction(1) * Fraction(10) ** -15),
    ("1.5d-15", Fraction(15, 10) * Fraction(10) ** -15),
]


def predict_one(body: str, rule: str) -> str:
    _kind, pred, _approx = predict(body, 16, small_rule=rule)
    return pred


def main() -> int:
    print(
        "# 事後(post hoc): l4-s4a〜dの入力へGW16/RSTAR/RSTAR_Bを当てた表。"
        "判定には使わない。"
    )
    print("# 生成コマンド: python3 tools/gen_l4_s4e_posthoc_inputs.py")
    print("typed\tGW16\tRSTAR\tRSTAR_B")
    for typed in INPUTS:
        gw16 = predict_one(typed, "gw")
        rstar = predict_one(typed, "rstar")
        rstar_b = predict_one(typed, "rstar_b")
        print(f'{typed}\t"{gw16}"\t"{rstar}"\t"{rstar_b}"')

    print()
    print(
        "# RSTAR_Bの判定に効く「2進の値(MBFの厳密値)が10進の値より"
        "上か下か」"
    )
    print("typed\tdirection")
    for typed, ideal in DIRECTION_CASES:
        num = eval_expr(typed)
        binv = num.exact()
        diff = binv - ideal
        if diff > 0:
            direction = "above"
        elif diff < 0:
            direction = "below"
        else:
            direction = "exact"
        print(f"{typed}\t{direction}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
