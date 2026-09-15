#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4d_double_candidate_predictions.py — l4-s4d 用、倍精度の
|v|<1 側の切替の候補規則(LE17/LE18)ごとの予測表を作る。

候補の定義(大きい側・単精度は現行のまま。倍精度 N=16 で有効数字に丸め
末尾0を落とし v=d.ddd×10^E、E<0、len=(-E-1)+有効桁数。Eは定義どおりの
標準的な指数——l4-s4cでS0列が内部指数e(=E+1)を使って定義と1つずれた
教訓(docs/notes/l4-mbf-oracle.md「l4-s4c: S0列の食い違いとその原因」)を
踏まえ、tools/l4_mbf_oracle_v2.pyの"lene"はEへ変換してから比較している):
  LE17: len<=17 かつ E>=-15 なら固定、それ以外は指数。
  LE18: len<=18 かつ E>=-15 なら固定、それ以外は指数。

腕の定義(id・typed)は l4-s4d 担当の腕表(s4d-arms.tsv)と同一(打鍵は
変更していない)。l4-s4d-*preregistration* 等、他担当が並行で書いている
文書・docs/spec/ は読んでいない。

使い方:
    python3 tools/gen_l4_s4d_double_candidate_predictions.py > docs/notes/l4-s4d-double-candidate-predictions.tsv
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import predict  # noqa: E402

ARMS = [
    ("M1", "double_small", "print .001234567890123456#"),
    ("M2", "double_small", "print 1.23456789012345d-3"),
    ("M3", "double_small", "print 1.23d-15"),
    ("M4", "double_small", "print 1.234d-15"),
    ("M5", "double_small", "print 1.2345d-15"),
    ("M6", "double_small", "print 1#/300"),
    ("M7", "double_small", "print 1#/30"),
    ("M8", "double_small", "print 1.5d-14"),
    ("M9", "double_small", "print -1.23d-15"),
    ("M10", "double_small", "print -.001234567890123456#"),
]

SMALL_EMIN = -15


def predict_one(body: str, t: int) -> str:
    _kind, pred, _approx = predict(body, 16, small_rule="lene", small_len=t, small_emin=SMALL_EMIN)
    return pred


def main() -> int:
    print("# 生成コマンド: python3 tools/gen_l4_s4d_double_candidate_predictions.py")
    print("id\ttyped\tLE17\tLE18")
    for arm_id, _group, typed in ARMS:
        body = typed
        if body.lower().startswith("print "):
            body = body[len("print "):]
        le17 = predict_one(body, 17)
        le18 = predict_one(body, 18)
        print(f'{arm_id}\t{typed}\t"{le17}"\t"{le18}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
