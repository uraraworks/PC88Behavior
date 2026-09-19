#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s6a_predictions.py — tools/l4_mbf_oracle_v3.py を使って
docs/notes/l4-s6a-gwbasic-predictions.tsv を生成する。

腕の定義(id・group・typed)はここに固定する(事前登録の一部)。
1関数呼び出し(引数は数値リテラル1個)の直接モードPRINTのみを対象にする。

使い方:
    python3 tools/gen_l4_s6a_predictions.py > docs/notes/l4-s6a-gwbasic-predictions.tsv
"""

import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v3 import predict_fn  # noqa: E402

# (id, group, typed) — typed は "print fn(arg)\n" の形。
ARMS = [
    # --- SQR群(S) ---
    ("S1", "sqr_irrational", "print sqr(2)"),
    ("S2", "sqr_irrational", "print sqr(3)"),
    ("S3", "sqr_irrational", "print sqr(.5)"),
    ("S4", "sqr_irrational", "print sqr(123456)"),
    ("S5", "sqr_double", "print sqr(2#)"),
    ("S6", "sqr_double", "print sqr(1000000#)"),
    ("S7", "sqr_error", "print sqr(-1)"),
    # --- SIN群(N) ---
    ("N1", "sin_irrational", "print sin(1)"),
    ("N2", "sin_irrational", "print sin(.5)"),
    ("N3", "sin_irrational", "print sin(-1)"),
    ("N4", "sin_large", "print sin(100)"),
    ("N5", "sin_double", "print sin(1#)"),
    ("N6", "sin_near2pi", "print sin(6.283185)"),
    ("N7", "sin_large", "print sin(1000000)"),
    # --- COS群(C) ---
    ("C1", "cos_irrational", "print cos(.5)"),
    ("C2", "cos_irrational", "print cos(1)"),
    ("C3", "cos_irrational", "print cos(-1)"),
    ("C4", "cos_large", "print cos(100)"),
    # --- TAN群(T) ---
    ("T1", "tan_irrational", "print tan(1)"),
    ("T2", "tan_irrational", "print tan(.5)"),
    ("T3", "tan_irrational", "print tan(-1)"),
    ("T4", "tan_large", "print tan(100)"),
    # --- ATN群(A) ---
    ("A1", "atn_irrational", "print atn(1)"),
    ("A2", "atn_irrational", "print atn(-1)"),
    ("A3", "atn_large", "print atn(100)"),
    ("A4", "atn_small", "print atn(.001)"),
    ("A5", "atn_double", "print atn(1#)"),
    ("A6", "atn_irrational", "print atn(.5)"),
    # --- EXP群(E) ---
    ("E1", "exp_irrational", "print exp(1)"),
    ("E2", "exp_irrational", "print exp(-1)"),
    ("E3", "exp_irrational", "print exp(.5)"),
    ("E4", "exp_irrational", "print exp(10)"),
    ("E5", "exp_double", "print exp(1#)"),
    ("E6", "exp_overflow", "print exp(100)"),
    ("E7", "exp_irrational", "print exp(.1)"),
    # --- LOG群(L) ---
    ("L1", "log_irrational", "print log(2)"),
    ("L2", "log_irrational", "print log(.5)"),
    ("L3", "log_irrational", "print log(100)"),
    ("L4", "log_double", "print log(2#)"),
    ("L5", "log_error", "print log(0)"),
    ("L6", "log_error", "print log(-1)"),
    ("L7", "log_irrational", "print log(10)"),
]

FN_ARG_RE = re.compile(r"^print\s+(sqr|sin|cos|tan|atn|exp|log)\(([^)]*)\)$", re.IGNORECASE)


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    oracle_path = os.path.join(here, "l4_mbf_oracle_v3.py")
    digest = hashlib.sha256(open(oracle_path, "rb").read()).hexdigest()

    print(f"# 生成元: tools/l4_mbf_oracle_v3.py sha256={digest}")
    print("# 生成コマンド: python3 tools/gen_l4_s6a_predictions.py")
    print("id\tgroup\ttyped\tkind\tpredicted\tapprox")
    for arm_id, group, typed in ARMS:
        m = FN_ARG_RE.match(typed.strip())
        if not m:
            raise ValueError(f"unrecognized arm typed string: {typed!r}")
        fname, arg = m.group(1), m.group(2)
        kind, pred, approx = predict_fn(fname, arg)
        print(f"{arm_id}\t{group}\t{typed}\\n\t{kind}\t\"{pred}\"\t{int(approx)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
