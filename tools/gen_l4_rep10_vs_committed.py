#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen_l4_rep10_vs_committed.py — l4-s4j: 既存の予測表(単精度の定数を
含む腕)について、FINをREP10(tools/l4_rep10.py)にしたときの予測を、
コミット済みの予測文字列と機械的に突き合わせる。

対象の表(すべて予測表・候補表で、測定結果ノートは読んでいない):
- docs/notes/l4-s4a-gwbasic-predictions.tsv (v1)
- docs/notes/l4-s4a-gwbasic-predictions-v2.tsv (v2)
- docs/notes/l4-s4b-h6-predictions.tsv
- docs/notes/l4-s4c-candidate-predictions-v2.tsv (LEN7列のみ、type=single)
- docs/notes/l4-fout-exact-vs-gw-candidates.tsv (type=single、exact/gw列)
- docs/notes/l4-fin-exact-vs-gw-candidates.tsv (exact/gw列)
- docs/notes/l4-fin-controls.tsv (exact/gw列)

倍精度の定数だけの腕(単精度の定数を1つも含まない腕)は対象外。腕の関連性は
typed列をトークナイズし(oracle._tokenizeを再利用)、各数値トークンを
tools/l4_rep10.py の _classify_kind でkind判定して、1つでもkind=="single"
のトークンがあれば対象にする(判定そのものはREP10とは無関係な共通基盤)。

REP10側の予測は常にN88想定の書式設定(--single-digits 6 --small-rule len
--small-len 7 --fout-algo gw)で統一する。committed側は各表に元から入って
いる文字列をそのまま使うため、表ごとに生成時の書式設定が異なる(v1/v2は
single_digits=7既定、s4bはsym既定、s4c以外はrstar等)。**このため
committed列とrep10列の食い違いには、REP10仮説そのものの違いだけでなく
書式設定の違いに由来するものが混ざりうる。仕分け(照合)は親が行う。**

測定はしていない。判定には使わない。tools/l4_mbf_oracle_v2.pyは変更して
いない。committed側の各表は1バイトも変えていない。

使い方:
    python3 tools/gen_l4_rep10_vs_committed.py > docs/notes/l4-rep10-vs-committed-predictions.tsv
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import l4_mbf_oracle_v2 as oracle  # noqa: E402
from tools import l4_rep10 as rep10  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TABLES = [
    {
        "name": "l4-s4a-gwbasic-predictions",
        "path": "docs/notes/l4-s4a-gwbasic-predictions.tsv",
        "id_col": "id",
        "typed_col": "typed",
        "type_col": None,
        "committed_cols": ["predicted"],
    },
    {
        "name": "l4-s4a-gwbasic-predictions-v2",
        "path": "docs/notes/l4-s4a-gwbasic-predictions-v2.tsv",
        "id_col": "id",
        "typed_col": "typed",
        "type_col": None,
        "committed_cols": ["predicted"],
    },
    {
        "name": "l4-s4b-h6-predictions",
        "path": "docs/notes/l4-s4b-h6-predictions.tsv",
        "id_col": "id",
        "typed_col": "typed",
        "type_col": None,
        "committed_cols": ["predicted"],
    },
    {
        "name": "l4-s4c-candidate-predictions-v2",
        "path": "docs/notes/l4-s4c-candidate-predictions-v2.tsv",
        "id_col": "id",
        "typed_col": "typed",
        "type_col": "type",
        "committed_cols": ["LEN7"],
    },
    {
        "name": "l4-fout-exact-vs-gw-candidates",
        "path": "docs/notes/l4-fout-exact-vs-gw-candidates.tsv",
        "id_col": None,
        "typed_col": "typed",
        "type_col": "type",
        "committed_cols": ["exact", "gw"],
    },
    {
        "name": "l4-fin-exact-vs-gw-candidates",
        "path": "docs/notes/l4-fin-exact-vs-gw-candidates.tsv",
        "id_col": None,
        "typed_col": "typed",
        "type_col": None,
        "committed_cols": ["exact", "gw"],
    },
    {
        "name": "l4-fin-controls",
        "path": "docs/notes/l4-fin-controls.tsv",
        "id_col": None,
        "typed_col": "typed",
        "type_col": None,
        "committed_cols": ["exact", "gw"],
    },
]


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _read_tsv(path: str):
    rows = []
    header = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            if header is None:
                header = fields
                continue
            rows.append(dict(zip(header, fields)))
    return rows


def _row_has_single_literal(typed: str) -> bool:
    body = typed
    if body.lower().startswith("print "):
        body = body[6:]
    try:
        toks = oracle._tokenize(body)
    except Exception:
        return False
    for kind_tok, val in toks:
        if kind_tok != "num":
            continue
        try:
            _sign_ch, digits, _fd, _exp, exp_marker, suffix, has_dot = rep10._lex_raw(val)
        except rep10.Rep10LexError:
            continue
        k = rep10._classify_kind(digits, has_dot, exp_marker, suffix)
        if k == "single":
            return True
    return False


def main() -> int:
    out_rows = []
    scanned = 0
    relevant = 0
    for table in TABLES:
        path = os.path.join(REPO_ROOT, table["path"])
        rows = _read_tsv(path)
        for row in rows:
            typed = row.get(table["typed_col"], "")
            if not typed:
                continue
            scanned += 1
            if table["type_col"] is not None:
                if row.get(table["type_col"]) != "single":
                    continue
            else:
                if not _row_has_single_literal(typed):
                    continue
            relevant += 1

            body = typed
            if body.lower().startswith("print "):
                body = body[6:]
            try:
                _k, rep10_pred = rep10.predict_rep10(body)
            except Exception as e:
                rep10_pred = f"<REP10-EXC:{e}>"

            row_id = row.get(table["id_col"], "") if table["id_col"] else ""
            id_or_typed = row_id if row_id else typed

            for col in table["committed_cols"]:
                if col not in row:
                    continue
                committed_raw = _strip_quotes(row[col])
                if committed_raw in ("-", ""):
                    continue
                if committed_raw != rep10_pred:
                    out_rows.append(
                        (f"{table['name']}/{col}", id_or_typed, committed_raw, rep10_pred)
                    )

    print(
        "# l4-s4j: 既存の予測表(単精度の定数を含む腕)について、FINを\n"
        "# REP10にしたときの予測(--single-digits 6 --small-rule len\n"
        "# --small-len 7 --fout-algo gw)を、コミット済みの予測文字列と\n"
        "# 機械的に突き合わせた差分。倍精度の定数だけの腕は対象外。\n"
        "# committed列は表ごとに元の生成時の書式設定が異なる(v1/v2は\n"
        "# single_digits=7既定、s4bはsym既定、fout候補はrstar等)ため、\n"
        "# ここに出る差分にはREP10仮説そのものの違いだけでなく書式設定の\n"
        "# 違いに由来するものが混ざりうる。仕分け(照合)は親が行う。\n"
        "# 判定には使わない(測定はしていない)。\n#"
    )
    print(f"# 走査した腕(単精度以外含む){scanned}件のうち単精度の定数を含む腕{relevant}件を比較、差分{len(out_rows)}件。")
    print("# 生成コマンド: python3 tools/gen_l4_rep10_vs_committed.py")
    print("table\tid_or_typed\tcommitted\trep10")
    for table_col, id_or_typed, committed, rep10_pred in out_rows:
        print(f'{table_col}\t{id_or_typed}\t"{committed}"\t"{rep10_pred}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
