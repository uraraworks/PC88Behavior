#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4c_candidate_predictions_v2.py — l4-s4c 候補規則の予測 v2。

v1(コミット0936808、tools/gen_l4_s4c_candidate_predictions.py)のS0列は
l4-s4c事前登録の定義「S0: -N<E で固定」（v = d.ddd×10^E、E<0）と
食い違っていた。原因はtools/l4_mbf_oracle_v2.pyの"sym"が使っていた内部
指数`e`（`_significant_digits()`が返す、v≈d1.d2d3…×10^(e-1)の意味）と、
事前登録の定義が使う標準的な`E`（v=d.ddd×10^E、E=e-1）がちょうど1ずれて
おり、旧"sym"が`e>-N`（標準Eで書くと`E>-N-1`）を計算していたため。
詳細はdocs/notes/l4-mbf-oracle.md「l4-s4c: S0列の食い違い」参照。

v2は新しい候補`--small-rule sym-def`（`E>-N`を文字どおり計算する）で
S0列を作り直した。**LEN列はv1と同一である**（LENは先頭0の個数と有効桁数
から直接計算しており、e/Eのずれの影響を受けないため。selftestで確認）。
**v1のファイル(l4-s4c-candidate-predictions.tsv)は1バイトも変えていない
(このスクリプトは新しいファイルへ書くだけ)。**

腕の定義はv1と同一(打鍵は変更していない)。l4-s4c-*preregistration*等、
他担当が並行で書いている文書は読んでいない。

使い方:
    python3 tools/gen_l4_s4c_candidate_predictions_v2.py > docs/notes/l4-s4c-candidate-predictions-v2.tsv
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

SINGLE_DIGITS_H6 = 6


def predict_one(body: str, rule: str) -> str:
    if rule == "S0":
        _kind, pred, _approx = predict(body, SINGLE_DIGITS_H6, small_rule="sym-def")
    else:
        t = int(rule[len("LEN"):])
        _kind, pred, _approx = predict(
            body, SINGLE_DIGITS_H6, small_rule="len", small_len=t
        )
    return pred


def main() -> int:
    print(
        "# v1(0936808)のS0列は定義と食い違っていたため作り直した。"
        "LEN列はv1と同一。"
    )
    print("# 生成コマンド: python3 tools/gen_l4_s4c_candidate_predictions_v2.py")
    print("id\ttyped\ttype\tS0\tLEN7\tLEN8\tLEN9\tLEN16")
    for arm_id, _group, typed in ARMS:
        body = typed
        if body.lower().startswith("print "):
            body = body[len("print "):]
        num = eval_expr(body)
        kind = num.kind
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
