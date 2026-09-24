#!/usr/bin/env python3
"""derive_m6fc_boot.py — m6f-c 追補1（起動用セクタの一様値の掃引）の
測定結果から、docs/notes/m6f-c-addendum1-boot-sector-sweep.md 第3節の
B1・B2を導出する。

入力の result JSON は tools/measure_m6fc_boot.sh が書く形式:
  {"schema": 1, "runs": [
      {"arm": "BX-00", "x": 0, "repetition": 1, "markers": [...],
       "reads": [{"c":..,"h":..,"r":..}, ...], "read_001_count": int,
       "write_data_count": int}, ...]}

B1 起動できる値: 2走とも `ZQbt` が出た X の集合 Xboot。空でなければ derived
（集合を記録）、空なら not_found。2走で食い違った X は run_disagreement に
列挙し Xboot から外す。

B2（副）: 各 X について、刺激の前後を通じた READ DATA の (C,H,R) の
初出順の列の先頭4個と、(0,0,1) を読んだ回数を記録する。

X\\* = Xboot の最小値。公開関数 boot_fill_star(result) はこれを返す
（Xbootが導出できなければ None）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BOOT_COORD = (0, 0, 1)


class InputError(ValueError):
    pass


def _run_tags(run: dict[str, Any]) -> set[str]:
    return {m["tag"] for m in run.get("markers", [])}


def _has_bt(run: dict[str, Any] | None) -> bool:
    return run is not None and "bt" in _run_tags(run)


def _runs_by_key(result: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for r in result.get("runs", []):
        out[(int(r["x"]), int(r["repetition"]))] = r
    return out


def _all_x(result: dict[str, Any]) -> list[int]:
    return sorted({int(r["x"]) for r in result.get("runs", [])})


# --- B1: 起動できる値 --------------------------------------------------------

def boot_capable_values(result: dict[str, Any]) -> dict[str, Any]:
    """B1。ドライバもこの関数を使ってよい。"""
    runs_by_key = _runs_by_key(result)
    xboot: list[int] = []
    disagreement: list[int] = []
    for x in _all_x(result):
        r1, r2 = runs_by_key.get((x, 1)), runs_by_key.get((x, 2))
        if r1 is None or r2 is None:
            continue
        b1, b2 = _has_bt(r1), _has_bt(r2)
        if b1 != b2:
            disagreement.append(x)
            continue
        if b1:
            xboot.append(x)
    out: dict[str, Any] = {"run_disagreement": sorted(disagreement)}
    if not xboot:
        out["status"] = "not_found"
    else:
        out["status"] = "derived"
        out["value"] = sorted(xboot)
    return out


def boot_fill_star(result: dict[str, Any]) -> int | None:
    """X\\* = Xbootの最小値。derivedでなければNone。"""
    b1 = boot_capable_values(result)
    if b1["status"] != "derived":
        return None
    return min(b1["value"])


# --- B2（副）: 次の読み込み --------------------------------------------------

def _read_summary(run: dict[str, Any]) -> dict[str, Any]:
    seen: list[dict[str, int]] = []
    seen_keys: set[tuple[int, int, int]] = set()
    boot_reads = 0
    for coord in run.get("reads", []):
        key = (int(coord["c"]), int(coord["h"]), int(coord["r"]))
        if key == BOOT_COORD:
            boot_reads += 1
        if key not in seen_keys:
            seen_keys.add(key)
            seen.append({"c": key[0], "h": key[1], "r": key[2]})
    return {"first4": seen[:4], "boot_sector_read_count": boot_reads}


def next_read(result: dict[str, Any]) -> dict[str, Any]:
    """B2。Xごとに2走を比べ、一致すればderived、食い違えばambiguousで両走を残す。"""
    runs_by_key = _runs_by_key(result)
    out: dict[str, Any] = {}
    for x in _all_x(result):
        r1, r2 = runs_by_key.get((x, 1)), runs_by_key.get((x, 2))
        key = f"{x:02X}"
        if r1 is None or r2 is None:
            out[key] = {"status": "not_found", "candidate_count": 0}
            continue
        s1, s2 = _read_summary(r1), _read_summary(r2)
        if s1 == s2:
            out[key] = {"status": "derived", **s1}
        else:
            out[key] = {"status": "ambiguous", "run1": s1, "run2": s2}
    return out


# --- 導出の統合 --------------------------------------------------------------

def load_result(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        raise InputError("結果JSONの形式")
    for r in doc["runs"]:
        if not isinstance(r, dict) or "x" not in r or "repetition" not in r:
            raise InputError("結果JSONのrun形式")
    return doc


def build(result: dict[str, Any]) -> dict[str, Any]:
    b1 = boot_capable_values(result)
    b2 = next_read(result)
    x_star = min(b1["value"]) if b1["status"] == "derived" else None
    overall = "m6f_c_boot_addendum1_ok" if b1["status"] == "derived" else "not_found"
    return {"schema": 1, "B1": b1, "B2": b2, "x_star": x_star, "overall": overall}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        result = load_result(args.result)
        body = build(result)
        digest = hashlib.sha256(args.result.read_bytes()).hexdigest()
        body["input_sha256"] = digest
        text = json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
