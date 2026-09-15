#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4l_candidates_v2.py — l4-s4l候補表の訂正版(v2)を作る。

親の手検算で、v1(docs/notes/l4-s4l-candidates.tsv、コミット23ad7ea)の
DREP10E/DREP10A列に食い違いがあると分かった: v1は式の左の定数だけに
候補の読み方(even/away)を当て、右辺の長い整数(x-c形のcのような、
16桁を超える整数)はDREP01/DEXACT/DGWと同じ既定(round-half-away固定)で
積み上げていた(tools/l4_dmodels.py の _magnitude_drep10 が数字の積み上げ
を_round_even_frac固定にしていたため)。候補DREP10E/DREP10Aは「N88が
すべての定数をどう読むか」の候補なので、式に出てくるどの定数にも同じ
読み方を一貫して当てる必要がある。

修正した読み方(_magnitude_drep10_v2、tools/l4_dmodels.py): 数字の積み上げ
は常にround-half-away(DREP01/DEXACT/DGWと同じ既定を踏襲)、指数適用の
×10/真の÷10の反復だけがDREP10E(even)/DREP10A(away)でわかれる(ここは
v1と同じ)。DEXACT/DREP01はもともと式のどの定数にも同じ候補を一貫して
当てていた(l4-s4kのDEXACT/DGW/DREP01と同じ実装をそのまま再利用していた
ため)ので、v2でも値は変えていない(念のため再計算はする)。

v1(tools/gen_l4_s4l_candidates.py、docs/notes/l4-s4l-candidates.tsv)は
1バイトも変えない。行の並び・typed列・group列・source列はv1から
そのまま読み込んで再利用する(順序を変えない)。

測定はしていない。判定には使わない。tools/l4_mbf_oracle_v2.pyは変更して
いない。

使い方:
    python3 tools/gen_l4_s4l_candidates_v2.py > docs/notes/l4-s4l-candidates-v2.tsv
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_dmodels as dm  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1_PATH = os.path.join(REPO_ROOT, "docs", "notes", "l4-s4l-candidates.tsv")
FMT = dict(single_digits=16, small_rule="rstar", small_len=0, fout_algo="gw")


def _read_v1_rows():
    with open(V1_PATH, encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip() and not ln.startswith("#")]
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        rec = dict(zip(header, ln.split("\t")))
        rows.append((rec["typed"], rec["group"], rec["source"]))
    return rows


def main() -> int:
    rows_v1 = _read_v1_rows()

    computed = []
    for typed, group, source in rows_v1:
        body = typed[len("print "):]
        _, pe10 = dm.predict_double(body, "drep10e_v2", **FMT)
        _, pa10 = dm.predict_double(body, "drep10a_v2", **FMT)
        _, pe = dm.predict_double(body, "dexact", **FMT)
        _, pr01 = dm.predict_double(body, "drep01", **FMT)
        computed.append((typed, group, source, pe10, pa10, pe, pr01))

    still_diff = sum(1 for *_r, pe10, pa10, _pe, _pr01 in computed if pe10 != pa10)
    no_longer_diff = len(computed) - still_diff

    print(
        "# l4-s4l 候補 v2: v1(23ad7ea)は右辺の定数(x-c形のcのような桁数の\n"
        "# 多い整数)を1回丸め(DEXACT/DREP01と同じround-half-away固定)で\n"
        "# 読んでおり、候補DREP10E/DREP10Aの読み方(even/away)を左の定数に\n"
        "# しか当てていなかったため作り直した。修正後は式のすべての定数に\n"
        "# 同じ候補の読み方を一貫して当てる\n"
        "# (_magnitude_drep10_v2、数字の積み上げは常にround-half-awayで\n"
        "# 統一、指数適用の×10/真の÷10の反復だけがeven/awayでわかれる)。\n"
        "# 行の並び・typed/group/source列はv1と同じ(v1のtsvから読み込んだ)。\n"
        "# 判定には使わない(測定はしていない)。\n#"
    )
    print(
        f"# {len(computed)}行中、DREP10E/DREP10Aがv2でも分かれているのは"
        f"{still_diff}行、分かれなくなった(=もう見分けられない)のは"
        f"{no_longer_diff}行。"
    )
    print("# 生成コマンド: python3 tools/gen_l4_s4l_candidates_v2.py")
    print("typed\tgroup\tsource\tDREP10E\tDREP10A\tDEXACT\tDREP01")
    for typed, group, source, pe10, pa10, pe, pr01 in computed:
        print(f'{typed}\t{group}\t{source}\t"{pe10}"\t"{pa10}"\t"{pe}"\t"{pr01}"')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
