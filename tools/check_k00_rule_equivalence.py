#!/usr/bin/env python3
"""m7bxの記号化20標本でK00の5候補規則が同じA/Bを返すことを検査する。

入力にデータポート値は含まれない。条件名、観測列A/B、リセットepoch内通番、
直前run記号、履歴フラグだけを扱う。候補同士が1件でも食い違う、または観測列と
食い違う場合は終了コード1とし、将来の標本追加で等価性が崩れたことを表に出す。
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

RULES = {
    "epoch内通番": lambda r: "A" if int(r["epoch_ordinal"]) == 1 else "B",
    "直前run": lambda r: "B" if r["previous_kind"] == "K05" else "A",
    "SPECIFY履歴": lambda r: "B" if r["specify_done"] == "1" else "A",
    "READ完走履歴": lambda r: "B" if r["read_done"] == "1" else "A",
    "FDC完了履歴": lambda r: "B" if r["fdc_done"] == "1" else "A",
}
REQUIRED = {
    "condition", "variant", "epoch_ordinal", "previous_kind",
    "specify_done", "read_done", "fdc_done",
}


def load(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if reader.fieldnames is None or set(reader.fieldnames) != REQUIRED:
            raise ValueError("列定義が期待と異なる")
        rows = list(reader)
    if not rows:
        raise ValueError("標本が0件")
    for i, row in enumerate(rows, 1):
        if row["variant"] not in {"A", "B"}:
            raise ValueError(f"標本{i}: variantがA/B以外")
        if row["epoch_ordinal"] not in {"1", "2"}:
            raise ValueError(f"標本{i}: epoch通番が範囲外")
        for key in ("specify_done", "read_done", "fdc_done"):
            if row[key] not in {"0", "1"}:
                raise ValueError(f"標本{i}: {key}が0/1以外")
    return rows


def check(rows: list[dict[str, str]]) -> tuple[list[str], bool]:
    lines = [f"K00記号標本: {len(rows)}件"]
    predictions = {name: [fn(row) for row in rows] for name, fn in RULES.items()}
    ok = True
    for name, values in predictions.items():
        mismatches = sum(value != row["variant"] for value, row in zip(values, rows))
        lines.append(f"{name}: 観測列との不一致{mismatches}件")
        ok &= mismatches == 0
    names = list(RULES)
    disagreement_rows = 0
    for i in range(len(rows)):
        if len({predictions[name][i] for name in names}) != 1:
            disagreement_rows += 1
    lines.append(f"5規則間の不一致標本: {disagreement_rows}件")
    ok &= disagreement_rows == 0
    lines.append("判定: " + ("等価" if ok else "非等価"))
    return lines, ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("table", type=Path)
    args = ap.parse_args()
    try:
        rows = load(args.table)
        lines, ok = check(rows)
    except (OSError, ValueError) as ex:
        print(f"検査不能: {ex}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
