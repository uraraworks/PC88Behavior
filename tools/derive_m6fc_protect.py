#!/usr/bin/env python3
"""derive_m6fc_protect.py — m6f-c 追補3（「書き込み禁止」を決めているセクタの
掃引）の測定結果から、docs/notes/m6f-c-addendum3-write-protect-sectors.md
第3節の Q1・Q2・Q3 を機械導出する。

入力の result JSON は tools/measure_m6fc_protect.sh が書く形式:
  {"schema": 1, "runs": [
      {"arm": "P13-00", "sector": "P13", "w": 0, "repetition": 1,
       "markers": [...], "reads": [...], "writes": [...],
       "write_data_count": int, "drive1_read_count": int,
       "drive1_write_count": int}, ...]}

腕名は掃引を表す接頭辞("P13"/"P1")とWの16進2桁を"-"で結んだもの。

Q1 書き込み禁止を外す値: 掃引ごとに、2走とも「目印が er で ERR=61」ではない
Wの集合 Wclear。2走で分類が食い違ったWは run_disagreement に列挙し外す。

Q2 対象のセクタとW*: Wclear13が空でなければ対象は(18,1,13)、W*=min(Wclear13)。
そうでなくWclear1が空でなければ対象は(18,1,1)、W*=min(Wclear1)。
両方空ならprotect_sector_not_found。

Q3（副）: 各Wについて、分類（ERRを含む）と、ドライブ2へのREAD DATA・
WRITE DATAの座標の列を記録する。

公開関数 protect_rule(result) は Q1・Q2 をまとめ、
{"sector": [C,H,R], "w": W} または None（protect_sector_not_found）を返す。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

# 追補3 第2節の表: 掃引名 -> 対象座標。
SWEEP_COORDS: dict[str, tuple[int, int, int]] = {
    "P13": (18, 1, 13),
    "P1": (18, 1, 1),
}
SWEEP_ORDER: tuple[str, ...] = ("P13", "P1")  # Q2の優先順位そのもの(13が先)。
PROTECT_ERR = 61


class InputError(ValueError):
    pass


def _run_tags(run: dict[str, Any]) -> set[str]:
    return {m["tag"] for m in run.get("markers", [])}


def _classify(run: dict[str, Any] | None) -> dict[str, Any]:
    """1走ぶんの分類。tag(ok/ng/er/none)とer時のERR/ERLを返す。"""
    if run is None:
        return {"tag": "none"}
    tags_present = {m["tag"]: m for m in run.get("markers", [])}
    for tag in ("ok", "ng", "er"):
        if tag in tags_present:
            m = tags_present[tag]
            out: dict[str, Any] = {"tag": tag}
            if tag == "er":
                numbers = m.get("numbers", [])
                out["err"] = numbers[0] if len(numbers) >= 1 else None
                out["erl"] = numbers[1] if len(numbers) >= 2 else None
            return out
    return {"tag": "none"}


def _is_protect_blocked(classification: dict[str, Any]) -> bool:
    return classification.get("tag") == "er" and classification.get("err") == PROTECT_ERR


def _runs_by_key(result: dict[str, Any]) -> dict[tuple[str, int, int], dict[str, Any]]:
    out: dict[tuple[str, int, int], dict[str, Any]] = {}
    for r in result.get("runs", []):
        out[(str(r["sector"]), int(r["w"]), int(r["repetition"]))] = r
    return out


def _all_w(result: dict[str, Any], sweep: str) -> list[int]:
    return sorted({int(r["w"]) for r in result.get("runs", []) if str(r["sector"]) == sweep})


# --- Q1: 書き込み禁止を外す値 -------------------------------------------------

def wclear_for_sweep(result: dict[str, Any], sweep: str) -> dict[str, Any]:
    """Q1。掃引sweep("P13"/"P1")ごとのWclear集合。ドライバもこの関数を使ってよい。"""
    runs_by_key = _runs_by_key(result)
    wclear: list[int] = []
    disagreement: list[int] = []
    for w in _all_w(result, sweep):
        r1 = runs_by_key.get((sweep, w, 1))
        r2 = runs_by_key.get((sweep, w, 2))
        if r1 is None or r2 is None:
            continue
        c1, c2 = _classify(r1), _classify(r2)
        blocked1, blocked2 = _is_protect_blocked(c1), _is_protect_blocked(c2)
        if blocked1 != blocked2:
            disagreement.append(w)
            continue
        if not blocked1:
            wclear.append(w)
    out: dict[str, Any] = {"run_disagreement": sorted(disagreement)}
    if not wclear:
        out["status"] = "not_found"
    else:
        out["status"] = "derived"
        out["value"] = sorted(wclear)
    return out


def q1(result: dict[str, Any]) -> dict[str, Any]:
    return {sweep: wclear_for_sweep(result, sweep) for sweep in SWEEP_ORDER}


# --- Q2: 対象のセクタとW* ----------------------------------------------------

def q2(q1_result: dict[str, Any]) -> dict[str, Any]:
    """Q2。Q1の結果からsector/w_starを決める。空欄ならprotect_sector_not_found。"""
    for sweep in SWEEP_ORDER:
        wclear = q1_result.get(sweep, {})
        if wclear.get("status") == "derived" and wclear.get("value"):
            c, h, r = SWEEP_COORDS[sweep]
            return {"status": "derived", "sweep": sweep,
                    "sector": {"c": c, "h": h, "r": r}, "w_star": min(wclear["value"])}
    return {"status": "protect_sector_not_found"}


def protect_rule(result: dict[str, Any]) -> dict[str, Any] | None:
    """公開関数。Q1・Q2をまとめ {"sector": [C,H,R], "w": W} または None を返す。"""
    q1_result = q1(result)
    q2_result = q2(q1_result)
    if q2_result["status"] != "derived":
        return None
    s = q2_result["sector"]
    return {"sector": [s["c"], s["h"], s["r"]], "w": q2_result["w_star"]}


# --- Q3（副）: 分類と入出力座標列 --------------------------------------------

def _coord_seq(coords: list[dict[str, int]]) -> list[dict[str, int]]:
    return [{"c": int(c["c"]), "h": int(c["h"]), "r": int(c["r"])} for c in coords]


def q3(result: dict[str, Any]) -> dict[str, Any]:
    runs_by_key = _runs_by_key(result)
    out: dict[str, Any] = {}
    for sweep in SWEEP_ORDER:
        sweep_out: dict[str, Any] = {}
        for w in _all_w(result, sweep):
            key = f"{w:02X}"
            r1 = runs_by_key.get((sweep, w, 1))
            r2 = runs_by_key.get((sweep, w, 2))
            entry: dict[str, Any] = {}
            for rep, r in ((1, r1), (2, r2)):
                if r is None:
                    entry[f"repetition{rep}"] = {"status": "not_found"}
                    continue
                entry[f"repetition{rep}"] = {
                    "classification": _classify(r),
                    "reads": _coord_seq(r.get("reads", [])),
                    "writes": _coord_seq(r.get("writes", [])),
                }
            sweep_out[key] = entry
        out[sweep] = sweep_out
    return out


# --- 導出の統合 --------------------------------------------------------------

def load_result(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        raise InputError("結果JSONの形式")
    for r in doc["runs"]:
        if not isinstance(r, dict) or "sector" not in r or "w" not in r or "repetition" not in r:
            raise InputError("結果JSONのrun形式")
    return doc


def build(result: dict[str, Any]) -> dict[str, Any]:
    q1_result = q1(result)
    q2_result = q2(q1_result)
    q3_result = q3(result)
    overall = ("m6f_c_protect_sector_derived" if q2_result["status"] == "derived"
               else "protect_sector_not_found")
    return {"schema": 1, "Q1": q1_result, "Q2": q2_result, "Q3": q3_result, "overall": overall}


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
