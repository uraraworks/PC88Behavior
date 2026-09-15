#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4c_candidate_predictions.py — l4-s4c 用、|v|<1 の固定⇔指数
切替の候補規則(S0/LEN7/LEN8/LEN9/LEN16)ごとの予測表を作る。

l4-s4a/l4-s4b の測定で単精度の有効桁数は6桁と確定した(H6)。一方、
|v|<1側の切替規則は対称近似(S0)では説明できなかったため、候補を機械的に
列挙して並べ、測定で消す(l4-s4c)。本表はどれかの候補を「正しい」と
仮定して作った盲検の予測ではなく、各候補規則をそのまま適用した機械的な
帰結であり、l4-s4a/l4-s4bの測定結果ノートは読まずに作っている。

候補の定義(大きい側はいずれも現行の規則のまま。tools/l4_mbf_oracle_v2.py
の fout_format()/_small_side_fixed() 参照):
  S0    : 対称近似則。固定 iff E > -N (N=単精度6・倍精度16、H6確定分)。
  LEN(T): 固定表記の小数点より右の文字数(先頭の0を含む)がT以下なら固定。
  単精度の候補: S0・LEN7・LEN8・LEN9。倍精度の候補: S0・LEN16。

腕の定義(id・typed)は l4-s4c 担当の腕表(s4c-arms.tsv)と同一(打鍵は
変更していない)。l4-s4c-*preregistration* 等、他担当が並行で書いている
文書は読んでいない。

使い方:
    python3 tools/gen_l4_s4c_candidate_predictions.py > docs/notes/l4-s4c-candidate-predictions.tsv
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import predict, eval_expr  # noqa: E402

ARMS = [
    ("K1", "single_small", "print 1e-8"),
    ("K2", "single_small", "print 1e-9"),
    ("K3", "single_small", "print 1.5e-6"),
    ("K4", "single_small", "print 1.5e-7"),
    ("K5", "single_small", "print 1.23e-6"),
    ("K6", "single_small", "print 1.23456e-2"),
    ("K7", "single_small", "print 1.23456e-3"),
    ("K8", "single_small", "print 1.2345e-3"),
    ("K9", "single_small", "print 1.2e-6"),
    ("K10", "single_small", "print -1e-7"),
    ("K11", "single_small", "print -1.5e-7"),
    ("K12", "single_small", "print 1/3000"),
    ("K13", "single_small", "print 1/300000"),
    ("L1", "double_small", "print 1d-15"),
    ("L2", "double_small", "print 1d-16"),
    ("L3", "double_small", "print 1.5d-15"),
    ("L4", "double_small", "print 1.5d-16"),
    ("L5", "double_small", "print .1234567890123456#"),
    ("L6", "double_small", "print 1.234567890123456d-2"),
    ("L7", "double_small", "print 1#/3000"),
]

SINGLE_CANDIDATES = ["S0", "LEN7", "LEN8", "LEN9"]
DOUBLE_CANDIDATES = ["S0", "LEN16"]

# 単精度の有効桁数はH6(l4-s4a/l4-s4bの測定)で6桁と確定済み。ここではその
# 確定値を固定して使い、|v|<1側の切替規則(small_rule/small_len)だけを
# 候補ごとに振る。倍精度は常に16桁(--single-digitsの影響を受けない)。
SINGLE_DIGITS_H6 = 6


def predict_one(body: str, rule: str) -> str:
    if rule == "S0":
        _kind, pred, _approx = predict(body, SINGLE_DIGITS_H6, small_rule="sym")
    else:
        t = int(rule[len("LEN"):])
        _kind, pred, _approx = predict(
            body, SINGLE_DIGITS_H6, small_rule="len", small_len=t
        )
    return pred


def main() -> int:
    print("# 生成コマンド: python3 tools/gen_l4_s4c_candidate_predictions.py")
    print("id\ttyped\ttype\tS0\tLEN7\tLEN8\tLEN9\tLEN16")
    for arm_id, _group, typed in ARMS:
        body = typed
        if body.lower().startswith("print "):
            body = body[len("print "):]
        num = eval_expr(body)
        kind = num.kind  # "single" or "double" (このファイルの腕はintにならない)
        s0 = f'"{predict_one(body, "S0")}"'
        if kind == "single":
            len7 = f'"{predict_one(body, "LEN7")}"'
            len8 = f'"{predict_one(body, "LEN8")}"'
            len9 = f'"{predict_one(body, "LEN9")}"'
            len16 = "-"
        elif kind == "double":
            len7 = len8 = len9 = "-"
            len16 = f'"{predict_one(body, "LEN16")}"'
        else:
            raise AssertionError(f"unexpected kind {kind!r} for {typed!r}")
        row = [arm_id, typed, kind, s0, len7, len8, len9, len16]
        print("\t".join(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
