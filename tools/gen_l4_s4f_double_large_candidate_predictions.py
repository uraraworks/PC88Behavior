#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4f_double_large_candidate_predictions.py — l4-s4f 用、倍精度の
|v|>=1 側(大きい側)の候補規則(LG16/LG15)ごとの予測表を作る。

候補の定義(N=16で丸め末尾0除去、v=d.ddd×10^E、E>=0。小さい側はRSTARの
まま。tools/l4_mbf_oracle_v2.py の --large-n 参照):
  LG16: E<16 なら固定、それ以外は指数(GW-BASIC本来の規則そのもの。
        docs/notes/l4-gwbasic-fofmt-analysis.md「E<N」)。
  LG15: E<15 なら固定、それ以外は指数。

腕の定義(id・typed)は l4-s4f 担当の腕表と同一(打鍵は変更していない)。
l4-s4f-*preregistration* 等、他担当が並行で書いている文書は読んでいない。

使い方:
    python3 tools/gen_l4_s4f_double_large_candidate_predictions.py > docs/notes/l4-s4f-double-large-candidate-predictions.tsv
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import predict  # noqa: E402

ARMS = [
    ("G1", "print 123456789012345#"),
    ("G2", "print 999999999999999#"),
    ("G3", "print 1234567890123456#"),
    ("G4", "print 9999999999999999#"),
    ("G5", "print 1d15"),
    ("G6", "print 1d14"),
    ("G7", "print 12345678901234.5#"),
    ("G8", "print 123456789012345.6#"),
    ("G9", "print 1d15*10"),
    ("G10", "print 99999999999999995#"),
    ("G11", "print -1234567890123456#"),
]


def predict_one(body: str, large_n: int) -> str:
    _kind, pred, _approx = predict(body, 16, small_rule="rstar", large_n=large_n)
    return pred


def main() -> int:
    print(
        "# 生成コマンド: python3 tools/gen_l4_s4f_double_large_candidate_predictions.py"
    )
    print("id\ttyped\tLG16\tLG15")
    for arm_id, typed in ARMS:
        body = typed
        if body.lower().startswith("print "):
            body = body[len("print "):]
        lg16 = predict_one(body, 16)
        lg15 = predict_one(body, 15)
        print(f'{arm_id}\t{typed}\t"{lg16}"\t"{lg15}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
