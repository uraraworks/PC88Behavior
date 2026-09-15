#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4h_double_tie_predictions.py — l4-s4h 用、倍精度でちょうど
半分(タイ)になる値の予測表を作る。

l4-s4g で単精度の半端は GW(絶対値の大きい側、常に切り上げ)が唯一残った
(コミット `e637eca`)。倍精度は乱数探しで候補0件だったが、16桁の整数に
`.5` を付けた定数なら2進でちょうど表せて(MBF倍精度は56bit仮数を持ち、
16桁の整数部(~51-52bit)+`.5`(1bit)は余裕で収まる)、16桁への丸めが
ちょうど半分になるはず、という仮説をここで確かめる。

腕(id・typed)は l4-s4h 担当の腕表と同一(打鍵は変更していない)。
exact_binary列は、FIN(倍精度、既定のexact手順。丸め誤差があっても
値そのものは変わらないため--fout-algoの違いは無関係)で得たMBFの値が
10進の意図した値とちょうど一致するか(2進で正確に表せたか)を表す。

EXACT列は`--fout-algo exact`(偶数丸め)、GW列は`--fout-algo gw`
(常に切り上げ)。どちらも倍精度の書式はN88想定の設定(16桁・LG16・RSTAR)
で統一している。

使い方:
    python3 tools/gen_l4_s4h_double_tie_predictions.py > docs/notes/l4-s4h-double-tie-predictions.tsv
"""

import os
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import predict, eval_expr  # noqa: E402

ARMS = [
    ("H1", "print 1234567890123456.5#", Fraction(12345678901234565, 10)),
    ("H2", "print 1234567890123457.5#", Fraction(12345678901234575, 10)),
    ("H3", "print 2000000000000000.5#", Fraction(20000000000000005, 10)),
    ("H4", "print -1234567890123456.5#", Fraction(-12345678901234565, 10)),
    ("H5", "print 3333333333333333.5#", Fraction(33333333333333335, 10)),
    ("H6", "print 9007199254740992.5#", Fraction(90071992547409925, 10)),
    ("H7", "print 1234567890123456#+.5", Fraction(12345678901234565, 10)),
    ("H8", "print 1234567890123456.4#", Fraction(12345678901234564, 10)),
    ("H9", "print 1234567890123456.6#", Fraction(12345678901234566, 10)),
]


def body_of(typed: str) -> str:
    b = typed
    if b.lower().startswith("print "):
        b = b[len("print "):]
    return b


def main() -> int:
    print("# 生成コマンド: python3 tools/gen_l4_s4h_double_tie_predictions.py")
    print("id\ttyped\texact_binary\tEXACT\tGW")
    for arm_id, typed, target in ARMS:
        body = body_of(typed)
        num = eval_expr(body, "exact")
        exact_binary = "yes" if num.exact() == target else "no"
        _, ex, _ = predict(body, 16, "rstar", 0, 0, 16, "exact")
        _, gw, _ = predict(body, 16, "rstar", 0, 0, 16, "gw")
        print(f'{arm_id}\t{typed}\t{exact_binary}\t"{ex}"\t"{gw}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
