#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4a_h6_posthoc.py — l4-s4a の既存32腕を、仮説H6(単精度6桁)で
再予測したもの。

**事後(post hoc)の表であり、判定には使わない。** H6はl4-s4aの観測結果
から立てた仮説であり、l4-s4aの32腕自体はH6を思いつく前に打った腕
なので、この表でH6が「当たる」かどうかを見ても仮説の検証にはならない
(仮説を立てた後に、それを立てるのに使ったのと同じデータに当てはめて
「合っている」と言っているだけになるため)。判定は l4-s4b の23腕
(tools/gen_l4_s4b_h6_predictions.py)で行う。

腕の定義は tools/gen_l4_s4a_predictions_v2.py と同一(打鍵文字列・id・
groupとも変更していない)。

使い方:
    python3 tools/gen_l4_s4a_h6_posthoc.py > docs/notes/l4-s4a-h6-posthoc.tsv
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import predict  # noqa: E402

SINGLE_DIGITS_H6 = 6

ARMS = [
    ("F1", "decimal", "print 1.5"),
    ("F2", "decimal", "print .5"),
    ("F3", "decimal", "print -.5"),
    ("F4", "decimal", "print 0.25"),
    ("F5", "decimal", "print 123.456"),
    ("D1", "digits", "print 1/3"),
    ("D2", "digits", "print 2/3"),
    ("D3", "digits", "print 10/3"),
    ("D4", "digits", "print 1234567.8"),
    ("D5", "digits", "print 12345678"),
    ("E1", "exp_large", "print 999999"),
    ("E2", "exp_large", "print 9999999"),
    ("E3", "exp_large", "print 10000000"),
    ("E4", "exp_large", "print 1e10"),
    ("E5", "exp_large", "print -1.5e+20"),
    ("S1", "exp_small", "print .1"),
    ("S2", "exp_small", "print .01"),
    ("S3", "exp_small", "print .001"),
    ("S4", "exp_small", "print 1e-10"),
    ("P1", "promote", "print 40000"),
    ("P2", "promote", "print 30000+30000"),
    ("P3", "promote", "print -32768-1"),
    ("P4", "promote", "print 200*200"),
    ("P5", "promote", "print 7/2"),
    ("W1", "double", "print 1#/3"),
    ("W2", "double", "print 1d10"),
    ("W3", "double", "print 12345678901234#"),
    ("W4", "double", "print 1/3#"),
    ("R1", "error_view", "print .1+.2"),
    ("R2", "error_view", "print 1/3*3"),
    ("X1", "out_of_range", "print 1e38*10"),
    ("X2", "out_of_range", "print 1/0"),
]


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    oracle_path = os.path.join(here, "l4_mbf_oracle_v2.py")
    digest = hashlib.sha256(open(oracle_path, "rb").read()).hexdigest()

    print(f"# 生成元: tools/l4_mbf_oracle_v2.py sha256={digest}")
    print(
        "# 生成コマンド: python3 tools/gen_l4_s4a_h6_posthoc.py "
        f"(内部で predict(expr, single_digits={SINGLE_DIGITS_H6}) を使用。"
        "CLI等価: python3 tools/l4_mbf_oracle_v2.py --single-digits 6 <expr>)"
    )
    print(
        "# 事後(post hoc): H6はl4-s4aの観測から立てた仮説。"
        "この表は判定に使わない。"
    )
    print("id\ttyped\tkind\tpredicted\tapprox")
    for arm_id, _group, typed in ARMS:
        body = typed
        if body.lower().startswith("print "):
            body = body[len("print "):]
        kind, pred, approx = predict(body, SINGLE_DIGITS_H6)
        print(f"{arm_id}\t{typed}\t{kind}\t\"{pred}\"\t{int(approx)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
