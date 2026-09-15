#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_fin_candidates.py — 単精度の定数読み取り(FIN)が「厳密値→
1回丸め(EXACT)」か「GW-BASICの手順=倍精度を経由して$CSDで丸める(GW)」
かをPRINTの出力で見分けられる、打鍵可能な式の候補を探す。

背景: tools/l4_mbf_oracle_v2.py の parse_literal(fin_algo="gw") は、
コミットde9e12eで「単精度でも指数が非0なら必ず倍精度(56bit)を経由し、
最後に$CSD(csd_narrow、タイを作らない特殊丸め)で単精度へ戻す」という
実際のMDPTEN手順どおりに修正された(修正前は厳密値を直接24bit丸めしており、
二重丸めのタイ潰しを再現していなかった)。この修正により、EXACTとGWで
最下位ビットが食い違う単精度の打鍵可能な定数が実在するようになった
(docs/notes/l4-mbf-oracle.md「FINの近似の有無」節、修正前は単精度0件と
書かれていた記述の訂正)。

探索方法:
1. 符号・小数点位置・指数(-20〜+20)をランダムに振った単精度の
   打鍵可能な定数(小数点を除いて1〜7桁、"e"指数付き)を生成する。
2. parse_literal(text, "exact") と parse_literal(text, "gw") の
   MBF単精度エンコード(符号・指数バイト・仮数)を比較し、食い違う
   定数xを見つける。
3. xの厳密値に最も近い整数cを求め、"x-c"(cが負なら"x+(-c)")という
   引き算の式を作る。cは整数なので net_exp=0 となりfin_algoの影響を
   受けず、EXACTとGWの差はxの1ULPの差だけがx-cの残差にそのまま出る
   (残差は小さい数としてPRINTの6桁表示に拡大される)。
4. N88想定の書式設定(単精度6桁・LEN7・fout-algo gw/exact)でPRINTの
   出力文字列を計算し、EXACTとGWで実際に異なるものだけを候補として残す。

打鍵の制約: 英字は小文字、1行70文字以内、"print"で始まる直接モードの
1行。乗除算の括弧は予測器(tools/l4_mbf_oracle_v2.py)が括弧を実装して
いないため使わない(x-c の形だけで残差が6桁表示に収まることを確認した
うえで採用した)。

測定はしていない。判定には使わない。

使い方:
    python3 tools/gen_l4_fin_candidates.py > docs/notes/l4-fin-exact-vs-gw-candidates.tsv
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.l4_mbf_oracle_v2 import parse_literal, predict  # noqa: E402

SEED = 20260915
MAX_TRIALS = 400000
MAX_ROWS = 20

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
    exp = rng.randint(-20, 20)
    return f"{sign}{s}e{exp:+d}"


def find_candidates():
    rng = random.Random(SEED)
    rows = []
    seen = set()
    tried = 0
    literal_diffs = 0
    while len(rows) < MAX_ROWS and tried < MAX_TRIALS:
        tried += 1
        x = _rand_literal(rng)
        try:
            ex = parse_literal(x, "exact")
            gx = parse_literal(x, "gw")
        except Exception:
            continue
        if ex.kind != "single" or gx.kind != "single":
            continue
        if _encode(ex) == _encode(gx):
            continue
        literal_diffs += 1

        c = round(ex.exact())
        expr = f"{x}+{-c}" if c < 0 else f"{x}-{c}"
        typed = f"print {expr}"
        if len(typed) > 70 or typed in seen:
            continue

        try:
            k1, p1, _ = predict(expr, **PRINT_KW_EXACT)
            k2, p2, _ = predict(expr, **PRINT_KW_GW)
        except Exception:
            continue
        if k1 != "numeric" or k2 != "numeric" or p1 == p2:
            continue

        seen.add(typed)
        rows.append((typed, p1, p2))

    return tried, literal_diffs, rows


def main() -> int:
    tried, literal_diffs, rows = find_candidates()

    print(
        "# 単精度の打鍵可能な定数(小数点を除いて1-7桁、e指数-20〜+20)を\n"
        "# 乱数で探し、tools/l4_mbf_oracle_v2.py の parse_literal で\n"
        "# fin_algo=\"exact\"(厳密値を1回丸め)とfin_algo=\"gw\"(倍精度経由+\n"
        "# $CSD、コミットde9e12eで修正済み)が食い違う定数xを見つけたうえで、\n"
        "# x-round(x)という引き算の式でPRINT出力(単精度6桁・LEN7・\n"
        "# --fout-algo gw/exact)に差が出るものだけを候補として残した。\n"
        "# 判定には使わない(測定はしていない)。\n#"
    )
    print(f"# 試行{tried}件中、定数xの時点でEXACT/GWが食い違ったのは{literal_diffs}件。")
    print(f"# そのうちPRINT出力まで差が出た式を{len(rows)}件、先頭から採用した。")
    print("# 生成コマンド: python3 tools/gen_l4_fin_candidates.py")
    print("typed\texact\tgw")
    for typed, e, g in rows:
        print(f'{typed}\t"{e}"\t"{g}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
