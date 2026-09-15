#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_s4l_controls_v2.py — l4-s4l対照表の訂正版(v2)を作る。

背景はtools/gen_l4_s4l_candidates_v2.pyと同じ(v1は右辺の定数を1回丸め
〔round-half-away固定〕で読んでいたため、DREP10E/DREP10Aの読み方が
式のすべての定数に一貫して当たっていなかった)。修正後の読み方
(_magnitude_drep10_v2)で対照(4候補すべてが一致するはずの式)を再計算し、
崩れた対照があれば行を対照表から外さずに残し、`still_control`列
(yes/no)で印を付ける(行の入れ替え・削除はしない)。

v1(tools/gen_l4_s4l_controls.py、docs/notes/l4-s4l-controls.tsv)は
1バイトも変えない。行の並び・typed列・group列はv1からそのまま読み込んで
再利用する。

測定はしていない。判定には使わない。tools/l4_mbf_oracle_v2.pyは変更して
いない。

使い方:
    python3 tools/gen_l4_s4l_controls_v2.py > docs/notes/l4-s4l-controls-v2.tsv
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_dmodels as dm  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1_PATH = os.path.join(REPO_ROOT, "docs", "notes", "l4-s4l-controls.tsv")
FMT = dict(single_digits=16, small_rule="rstar", small_len=0, fout_algo="gw")


def _read_v1_rows():
    with open(V1_PATH, encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip() and not ln.startswith("#")]
    header = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        rec = dict(zip(header, ln.split("\t")))
        rows.append((rec["typed"], rec["group"]))
    return rows


def main() -> int:
    rows_v1 = _read_v1_rows()

    computed = []
    for typed, group in rows_v1:
        body = typed[len("print "):]
        _, pe10 = dm.predict_double(body, "drep10e_v2", **FMT)
        _, pa10 = dm.predict_double(body, "drep10a_v2", **FMT)
        _, pe = dm.predict_double(body, "dexact", **FMT)
        _, pr01 = dm.predict_double(body, "drep01", **FMT)
        still = "yes" if len({pe10, pa10, pe, pr01}) == 1 else "no"
        computed.append((typed, group, pe10, pa10, pe, pr01, still))

    broken = sum(1 for *_r, still in computed if still == "no")

    print(
        "# l4-s4l 対照 v2: v1(23ad7ea)は右辺の定数を1回丸め\n"
        "# (round-half-away固定)で読んでいたため作り直した(詳細は\n"
        "# tools/gen_l4_s4l_candidates_v2.py参照)。行の並び・typed/group列は\n"
        "# v1と同じ(v1のtsvから読み込んだ)。崩れた対照(4候補が一致しなく\n"
        "# なった行)は行を外さずに残し、still_control列(yes/no)で印を付けた。\n"
        "# 判定には使わない(測定はしていない)。\n#"
    )
    print(f"# {len(computed)}行中、崩れた対照(still_control=no)は{broken}行。")
    print("# 生成コマンド: python3 tools/gen_l4_s4l_controls_v2.py")
    print("typed\tgroup\tDREP10E\tDREP10A\tDEXACT\tDREP01\tstill_control")
    for typed, group, pe10, pa10, pe, pr01, still in computed:
        print(f'{typed}\t{group}\t"{pe10}"\t"{pa10}"\t"{pe}"\t"{pr01}"\t{still}')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
