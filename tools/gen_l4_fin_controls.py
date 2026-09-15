#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_fin_controls.py — l4-s4i の候補
(docs/notes/l4-fin-exact-vs-gw-candidates.tsv)と**同じ形**(単精度の
"e"指数付き定数 - 倍精度の定数、同程度の桁数・指数)を通るが、
EXACT("厳密値を1回丸め")とGW("倍精度を経由して$CSDで丸める")の予測が
**一致する**対照の式を作る。

背景: 候補の式(例 "print 1.7e+10-16999999488")は、単精度の定数を
式の中でいったん倍精度へ広げてから倍精度の定数(大きい整数リテラルは
tools/l4_mbf_oracle_v2.py の parse_literal が桁数でkindを
"double"へ昇格させる)と引き算する、という型が混ざる経路を通る。
この経路自体はN88でまだ測っていないため、候補の式がEXACT/GWの
どちらの予測とも一致しなかった場合に、原因が定数の読み取り
(fin_algo)なのか型が混ざる経路(この昇格・引き算そのもの)なのかを
候補の表だけでは区別できない。対照はこの区別のために、同じ経路を
通るが定数xの時点でEXACT/GWが食い違わない(parse_literalのエンコード
が一致する)組み合わせだけを選び、期待どおりEXACT/GWの予測が一致する
ことを確認して載せる。

構成:
- xは候補と同じ生成規則(符号・小数点位置・"e"指数を+2〜+11の範囲で
  ランダム、小数点を除いて1〜7桁)。
- xのMBF単精度エンコードがEXACT/GWで一致するものだけを採用する
  (食い違うものは候補側の役目なのでここでは使わない)。
- c(引く側の倍精度整数定数)はxの厳密値に最も近い整数base=round(x)を
  基準に、"base+delta"(deltaは-8〜+8の非0整数、絶対値10^6以上を保つ)
  を使う。delta=0の組はx-c=0(候補で言う「食い違わなければ0になる」
  側)、delta!=0の組はx-c!=0(引き算そのものが効く側)になる——どちらも
  xがEXACT/GWで一致する限り、EXACT側の予測とGW側の予測は自明に一致する
  はずで、それを実際にpredict()で確認したものだけを載せる。

測定はしていない。判定には使わない。予測器tools/l4_mbf_oracle_v2.pyは
変更していない。

使い方:
    python3 tools/gen_l4_fin_controls.py > docs/notes/l4-fin-controls.tsv
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import parse_literal, predict  # noqa: E402

SEED = 1618033988
MAX_TRIALS = 400000
TARGET_ZERO = 3
TARGET_NONZERO = 5
DELTA_RANGE = range(-8, 9)
MIN_MAGNITUDE = 10**6

PRINT_KW_EXACT = dict(single_digits=6, small_rule="len", small_len=7, fout_algo="exact")
PRINT_KW_GW = dict(single_digits=6, small_rule="len", small_len=7, fout_algo="gw")


def _encode(num):
    return (num.sign, num.exp, num.mant)


def _rand_literal(rng: random.Random) -> str:
    ndig = rng.randint(1, 7)
    digits = [rng.choice("0123456789") for _ in range(ndig)]
    if digits[0] == "0" and ndig > 1:
        digits[0] = rng.choice("123456789")
    dotpos = rng.randint(0, ndig)
    if dotpos == 0:
        s = "." + "".join(digits)
    elif dotpos == ndig:
        s = "".join(digits) + "."
    else:
        s = "".join(digits[:dotpos]) + "." + "".join(digits[dotpos:])
    sign = rng.choice(["", "-"])
    exp = rng.randint(2, 11)  # 候補と同程度の指数域(+2〜+11)に絞る
    return f"{sign}{s}e+{exp}"


def find_controls():
    rng = random.Random(SEED)
    rows = []
    seen = set()
    tried = 0
    zero_count = 0
    nonzero_count = 0
    nondelta_choices = [d for d in DELTA_RANGE if d != 0]
    while len(rows) < TARGET_ZERO + TARGET_NONZERO and tried < MAX_TRIALS:
        tried += 1
        x = _rand_literal(rng)
        try:
            ex = parse_literal(x, "exact")
            gx = parse_literal(x, "gw")
        except Exception:
            continue
        if ex.kind != "single" or gx.kind != "single":
            continue
        if _encode(ex) != _encode(gx):
            continue  # 対照: xの時点で食い違うものは候補側の役目なので使わない

        base = round(ex.exact())
        if abs(base) < MIN_MAGNITUDE:
            continue

        want_nonzero = nonzero_count < TARGET_NONZERO
        if want_nonzero:
            delta = rng.choice(nondelta_choices)
        else:
            if zero_count >= TARGET_ZERO:
                continue
            delta = 0
        c = base + delta

        expr = f"{x}+{-c}" if c < 0 else f"{x}-{c}"
        typed = f"print {expr}"
        if len(typed) > 70 or typed in seen:
            continue

        try:
            k1, p1, _ = predict(expr, **PRINT_KW_EXACT)
            k2, p2, _ = predict(expr, **PRINT_KW_GW)
        except Exception:
            continue
        if k1 != "numeric" or k2 != "numeric" or p1 != p2:
            continue  # 対照はEXACT/GWが一致するものだけを載せる

        is_zero = p1.strip() == "0"
        if want_nonzero and is_zero:
            continue
        if (not want_nonzero) and not is_zero:
            continue

        seen.add(typed)
        rows.append((typed, p1, p2))
        if is_zero:
            zero_count += 1
        else:
            nonzero_count += 1

    return tried, rows, zero_count, nonzero_count


def main() -> int:
    tried, rows, zero_count, nonzero_count = find_controls()

    print(
        "# 対照: 候補(docs/notes/l4-fin-exact-vs-gw-candidates.tsv)と同じ経路\n"
        "# (単精度のe指数定数-倍精度の定数、同程度の桁数・指数)を通るが、\n"
        "# 定数xの時点でfin_algo=\"exact\"/\"gw\"が食い違わないため、\n"
        "# EXACTとGWの予測が一致する式。判定には使わない(測定はしていない)。\n#"
    )
    print(
        f"# {len(rows)}件({nonzero_count}件は答えが0でない=引き算そのものが"
        f"効く側、{zero_count}件は答えが0)。試行{tried}件。"
    )
    print("# 生成コマンド: python3 tools/gen_l4_fin_controls.py")
    print("typed\texact\tgw")
    for typed, e, g in rows:
        print(f'{typed}\t"{e}"\t"{g}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
