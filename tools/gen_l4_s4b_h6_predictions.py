#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4b_h6_predictions.py — 仮説H6(単精度は6桁で出力し、6桁を
超えると指数表記になる。GW-BASICは7桁)による l4-s4b 23腕の出力予測。

tools/l4_mbf_oracle_v2.py の --single-digits 相当(predict(expr, 6))を
使い、単精度の有効桁数だけを6へ差し替える。倍精度は常に16桁のまま
(l4-s4b の C1-C6 は倍精度の腕なので、この差し替えの影響を受けない)。

腕の定義(id・typed)は l4-s4b 事前登録担当の腕表と同一(打鍵文字列は
変更していない)。l4-s4b-*-preregistration* 等、他担当が並行で書いている
文書は読んでいない。

使い方:
    python3 tools/gen_l4_s4b_h6_predictions.py > docs/notes/l4-s4b-h6-predictions.tsv
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import predict  # noqa: E402

SINGLE_DIGITS_H6 = 6

ARMS = [
    ("A1", "single_digits", "print 1234567"),
    ("A2", "single_digits", "print 123456"),
    ("A3", "single_digits", "print 1/7"),
    ("A4", "single_digits", "print 100000*10"),
    ("A5", "single_digits", "print 1e6"),
    ("A6", "single_digits", "print 1e5"),
    ("A7", "single_digits", "print 999999.5"),
    ("A8", "single_digits", "print 2/3*1000"),
    ("A9", "single_digits", "print 12345.678!"),
    ("A10", "single_digits", "print 1234567!"),
    ("A11", "single_digits", "print -1/3"),
    ("B1", "single_small", "print .0001"),
    ("B2", "single_small", "print .00001"),
    ("B3", "single_small", "print .000001"),
    ("B4", "single_small", "print 1e-7"),
    ("B5", "single_small", "print 1.5e-5"),
    ("B6", "single_small", "print 123456e-10"),
    ("C1", "double", "print 1#/7"),
    ("C2", "double", "print 1d16"),
    ("C3", "double", "print 1d17"),
    ("C4", "double", "print 12345678901234567#"),
    ("C5", "double", "print .0001#"),
    ("C6", "double", "print 1d-17"),
]


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    oracle_path = os.path.join(here, "l4_mbf_oracle_v2.py")
    digest = hashlib.sha256(open(oracle_path, "rb").read()).hexdigest()

    print(f"# 生成元: tools/l4_mbf_oracle_v2.py sha256={digest}")
    print(
        "# 生成コマンド: python3 tools/gen_l4_s4b_h6_predictions.py "
        f"(内部で predict(expr, single_digits={SINGLE_DIGITS_H6}) を使用。"
        "CLI等価: python3 tools/l4_mbf_oracle_v2.py --single-digits 6 <expr>)"
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
