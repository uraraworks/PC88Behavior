#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4e_double_candidate_predictions.py — l4-s4e 用、倍精度の
|v|<1 側の候補規則(GW16/RSTAR/RSTAR_B)ごとの予測表を作る。

候補の定義(N=16で有効数字に丸め末尾0を落とし v=d.ddd×10^E、E<0、
k=-E-1、sは丸め後の有効桁数。docs/notes/l4-gwbasic-fofmt-analysis.md
(Codexが GW-BASIC ソースのみから導出)の結論をそのまま実装した
tools/l4_mbf_oracle_v2.py の --small-rule 参照):
  GW16   : k+s<=16 なら固定(=GW-BASIC本来の規則そのもの)。
  RSTAR  : k<=1、または(k+s<=16 かつ k<=14)なら固定。
  RSTAR_B: k'<=1、または k'+s<=16 なら固定。k'は丸める前の2進の値
           (MBFの厳密値)の10進指数E'=floor(log10|v|)から計算する
           (k'=-E'-1)。表示する数字sは丸め後の値のまま。

腕の定義(id・typed)は l4-s4e 担当の腕表(s4e-arms.tsv)と同一(打鍵は
変更していない)。l4-s4e-*preregistration* 等、他担当が並行で書いている
文書は読んでいない。

使い方:
    python3 tools/gen_l4_s4e_double_candidate_predictions.py > docs/notes/l4-s4e-double-candidate-predictions.tsv
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import predict  # noqa: E402

ARMS = [
    ("Q1", "k1_long", "print 1#/70"),
    ("Q2", "k1_long", "print .09876543210987654#"),
    ("Q3", "k1_long", "print .01000000000000001#"),
    ("Q4", "k1_long", "print 1#/7/10"),
    ("Q5", "k1_long", "print -1#/70"),
    ("Q6", "k15_short", "print 2d-16"),
    ("Q7", "k15_short", "print 5d-16"),
    ("Q8", "k15_short", "print 9d-16"),
    ("Q9", "k15_short", "print 3d-16"),
    ("Q10", "mid_len16", "print 1.2345678901234d-3"),
    ("Q11", "mid_len16", "print 1.1d-15"),
    ("Q12", "mid_len16", "print 1.12d-14"),
    ("Q13", "mid_len17", "print 1.123d-14"),
    ("Q14", "mid_len17", "print 1#/700"),
]


def predict_one(body: str, rule: str) -> str:
    _kind, pred, _approx = predict(body, 16, small_rule=rule)
    return pred


def main() -> int:
    print("# 生成コマンド: python3 tools/gen_l4_s4e_double_candidate_predictions.py")
    print("id\ttyped\tGW16\tRSTAR\tRSTAR_B")
    for arm_id, _group, typed in ARMS:
        body = typed
        if body.lower().startswith("print "):
            body = body[len("print "):]
        gw16 = predict_one(body, "gw")
        rstar = predict_one(body, "rstar")
        rstar_b = predict_one(body, "rstar_b")
        print(f'{arm_id}\t{typed}\t"{gw16}"\t"{rstar}"\t"{rstar_b}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
