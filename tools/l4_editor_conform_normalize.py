#!/usr/bin/env python3
"""PC88Behavior: l4-c6 スクリーンエディタ適合 — 正規化・比較道具。

`tools/l4_editor_conform_record.py`の生出力(JSON、座標・文字コードを
含む)を、腕ごとに「nonblank_count・sha256」だけに正規化する。
ファンクションキー表示行(公式row19)・自作の状態表示行(row20-24)は
編集キーの挙動そのものではないため正規化時に除外する(l4-c5の
`l4_program_conform_record.py`が最下行を除外するのと同じ作法)。

`tools/l4_editor_conform_record.py`のimport元(単一の出所)。二重実装
しない。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import l4_editor_conform_record as R  # noqa: E402

MID = list(R.MID_ARMS)
BOUNDARY = list(R.BOUNDARY_ARMS)
S1G = list(R.S1G_ARMS)
ARM_ORDER = MID + BOUNDARY + S1G

STATUS_ROWS_OFFICIAL = {19}
STATUS_ROWS_SELF = {20, 21, 22, 23, 24}


def _norm_cells(cells: list[dict], status_rows: set[int]) -> list[dict]:
    out = [c for c in cells if c["row0"] not in status_rows]
    out.sort(key=lambda c: (c["row0"], c["col0"]))
    return out


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def normalize_arm(name: str, entry: dict, status_rows: set[int]) -> dict:
    if entry.get("rc") != 0:
        return {"nonblank_count": -1, "sha256": "", "error": entry.get("err_tail", "")}
    if name in MID:
        q1 = _norm_cells(entry["q1"], status_rows)
        q3 = _norm_cells(entry["q3"], status_rows)
        return {"nonblank_count": len(q1) + len(q3), "sha256": _sha({"q1": q1, "q3": q3})}
    if name in BOUNDARY:
        md = _norm_cells(entry["mark_diff"], status_rows)
        return {"nonblank_count": len(md), "sha256": _sha(md)}
    if name in S1G:
        rows = entry["new_row_sigs"]
        if not rows:
            return {"nonblank_count": 0, "sha256": _sha(None)}
        out_row = min(rows, key=lambda r: int(r))
        sig = rows[out_row]
        return {"nonblank_count": sig["nonblank_count"], "sha256": sig["row_sha256"]}
    raise ValueError(f"未知の腕: {name}")


def normalize_all(raw: dict, status_rows: set[int]) -> dict:
    return {name: normalize_arm(name, entry, status_rows) for name, entry in raw.items()}


def load_expected_tsv(path: str) -> dict:
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            name, nb, sha = parts
            out[name] = {"nonblank_count": int(nb), "sha256": sha}
    return out


def write_expected_tsv(path: str, normalized: dict) -> None:
    lines = [
        "# l4-c6 スクリーンエディタ適合の場面 — 期待値（tools/conform_l3_editor.sh が読む）",
        "#",
        "# 値そのもの（文字コード・画面本文）は一切含まない。腕ごとの",
        "# nonblank_count・sha256のみ（CLAUDE.md禁止事項4、expected_l4_echo.tsv等と",
        "# 同じ作法）。sha256は tools/l4_editor_conform_record.py の出力を",
        "# tools/l4_editor_conform_normalize.py が正規化した後のハッシュ",
        "# （ファンクションキー表示行〈公式row19〉・自作の状態表示行〈row20-24〉は",
        "# 正規化時に除外済み）。",
        "# 事前登録: docs/spec/l3-main.md 第16・17節（l4-s1f・l4-s1g）。",
        "# 公式ROM(PC88_REF_ROM_DIR経由)で採取する(tools/conform_l3_editor.sh --record)。",
        "#",
        "# arm\tnonblank_count\tsha256",
    ]
    for name in ARM_ORDER:
        e = normalized.get(name, {"nonblank_count": -1, "sha256": ""})
        lines.append(f"{name}\t{e['nonblank_count']}\t{e['sha256']}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-json", required=True, help="l4_editor_conform_record.pyの出力")
    ap.add_argument("--status-rows", choices=["official", "self"], required=True)
    ap.add_argument("--expected-tsv", help="比較対象の期待値TSV")
    ap.add_argument("--write-expected", action="store_true", help="期待値TSVを書き出す(--expected-tsvへ)")
    args = ap.parse_args()

    raw = json.load(open(args.raw_json, encoding="utf-8"))
    status_rows = STATUS_ROWS_OFFICIAL if args.status_rows == "official" else STATUS_ROWS_SELF
    normalized = normalize_all(raw, status_rows)

    if args.write_expected:
        assert args.expected_tsv
        write_expected_tsv(args.expected_tsv, normalized)
        print(f"[l4_editor_conform_normalize] {len(normalized)}腕 -> {args.expected_tsv}")
        return 0

    if args.expected_tsv:
        expected = load_expected_tsv(args.expected_tsv)
        match, mismatch, missing = [], [], []
        for name in ARM_ORDER:
            if name not in expected:
                missing.append(name)
                continue
            got = normalized.get(name, {})
            exp = expected[name]
            if got.get("nonblank_count") == exp["nonblank_count"] and got.get("sha256") == exp["sha256"]:
                match.append(name)
            else:
                mismatch.append(name)
        print(json.dumps({"match": match, "mismatch": mismatch, "missing_in_normalized": missing},
                          ensure_ascii=False, indent=2))
        return 0 if not mismatch and not missing else 1

    print(json.dumps(normalized, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
