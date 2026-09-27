#!/usr/bin/env python3
"""judge_m6ff.py — m6f-f の測定結果(result JSON, tools/measure_m6ff.sh の出力)
から、事前登録第6節の判定を出す。

読むのは各runの entry_fields(名前キー付き、bytes9_15の7値)だけで、
本体セクタの中身・割り当て表は見ない(そもそも measure_m6ff.sh がそこまで
しか記録していない)。

腕ごと:
  - 2走が一致し、名前どおりのエントリが見つかった → {"status":"type_byte","value":"0xNN"}
  - 見つかったが2走で bytes9_15 が食い違う → {"status":"inconclusive"}
  - どちらの走もエントリが見つからない → {"status":"no_entry"}
  - abort(3回とも失敗)のまま記録された走がある → {"status":"gate_failed"}

F-II(bytes11_15、0始まりindex2..6=1始まり12〜16バイト目=事前登録の「11〜15
バイト目」)は、type_byteが求まった腕だけを対象に、全腕で0xFFのままなら
"bytes11_15_unchanged"、そうでなければ変わった腕・位置・値を記録する。

G5: F-Sの種別バイトが0x80、F-Dが0x00でなければ control_failed=true。
G6: F-0のentry_fieldsに、5つの名前のどれかが見つかったら g6_ok=false。
G7: 各runのdrive1_sha_okがTrueでなければ control_failed=true
    (measure_m6ff.shがG7不成立時はgate_failedで止まる設計だが、
    結果JSONを直接与えられた場合の二重チェックとして持つ)。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

NAMED_ARMS = {"F-S": "qzs", "F-A": "qza", "F-P": "qzp", "F-B": "qzb", "F-D": "qzd"}
ALL_ARMS = ("F-S", "F-A", "F-P", "F-B", "F-D", "F-0")
NEGATIVE_NAMES = ("qzs", "qza", "qzp", "qzb", "qzd")
TYPE_BYTE_INDEX = 0  # bytes9_15[0] = 名前欄直後(offset9)
BYTES_11_15_INDEXES = (2, 3, 4, 5, 6)  # offsets 11..15


class InputError(ValueError):
    pass


def load_result(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list):
        raise InputError("結果JSONの形式")
    return doc


def _reps(runs: list[dict[str, Any]], arm: str) -> list[dict[str, Any] | None]:
    by_rep = {r.get("repetition"): r for r in runs if r.get("arm") == arm}
    return [by_rep.get(1), by_rep.get(2)]


def _named_fields(run: dict[str, Any] | None, name: str) -> dict[str, Any] | None:
    if run is None or run.get("abort"):
        return None
    ef = run.get("entry_fields")
    if not isinstance(ef, dict):
        return None
    return ef.get(name)


def judge_arm(runs: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    reps = _reps(runs, arm)
    if any(r is None for r in reps):
        return {"status": "gate_failed", "reason": "run_missing"}
    if any(r.get("abort") for r in reps):
        return {"status": "gate_failed", "reason": "abort"}
    name = NAMED_ARMS[arm]
    f1, f2 = _named_fields(reps[0], name), _named_fields(reps[1], name)
    if f1 is None and f2 is None:
        return {"status": "no_entry"}
    if f1 is None or f2 is None:
        return {"status": "inconclusive"}
    b1, b2 = f1.get("bytes9_15"), f2.get("bytes9_15")
    if not isinstance(b1, list) or not isinstance(b2, list) or b1 != b2:
        return {"status": "inconclusive"}
    return {"status": "type_byte", "value": f"0x{b1[TYPE_BYTE_INDEX]:02X}", "bytes9_15": b1}


def judge_f0(runs: list[dict[str, Any]]) -> dict[str, Any]:
    reps = _reps(runs, "F-0")
    if any(r is None or r.get("abort") for r in reps):
        return {"g6_ok": False, "reason": "run_missing_or_abort"}
    found: list[str] = []
    for r in reps:
        ef = r.get("entry_fields")
        if not isinstance(ef, dict):
            found.append("entry_fields_missing")
            continue
        for name in NEGATIVE_NAMES:
            if ef.get(name) is not None:
                found.append(name)
    return {"g6_ok": (len(found) == 0), "found": sorted(set(found))}


def judge_bytes11_15(arm_results: dict[str, Any]) -> dict[str, Any]:
    vary: list[dict[str, Any]] = []
    for arm, res in arm_results.items():
        if res.get("status") != "type_byte":
            continue
        bytes9_15 = res["bytes9_15"]
        for idx in BYTES_11_15_INDEXES:
            value = bytes9_15[idx]
            if value != 0xFF:
                vary.append({"arm": arm, "index_offset": idx + 9, "value": f"0x{value:02X}"})
    if vary:
        return {"status": "bytes11_15_vary", "detail": vary}
    return {"status": "bytes11_15_unchanged"}


def judge_g7(runs: list[dict[str, Any]]) -> bool:
    return all(r.get("drive1_sha_ok") is True for r in runs if not r.get("abort"))


def judge(doc: dict[str, Any]) -> dict[str, Any]:
    runs = doc["runs"]
    arm_results = {arm: judge_arm(runs, arm) for arm in NAMED_ARMS}
    f0 = judge_f0(runs)
    bytes11_15 = judge_bytes11_15(arm_results)
    g7_ok = judge_g7(runs)

    g5_ok = True
    fs = arm_results.get("F-S", {})
    fd = arm_results.get("F-D", {})
    if fs.get("status") == "type_byte" and fs.get("value") != "0x80":
        g5_ok = False
    if fd.get("status") == "type_byte" and fd.get("value") != "0x00":
        g5_ok = False
    if fs.get("status") != "type_byte" or fd.get("status") != "type_byte":
        g5_ok = False

    control_failed = (not g5_ok) or (not g7_ok)

    return {
        "schema": 1,
        "arms": {**arm_results, "F-0": f0},
        "bytes11_15": bytes11_15,
        "g5_ok": g5_ok,
        "g6_ok": f0.get("g6_ok", False),
        "g7_ok": g7_ok,
        "control_failed": control_failed,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result", required=True, type=Path)
    args = ap.parse_args()
    try:
        doc = load_result(args.result)
        body = judge(doc)
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, KeyError) as exc:
        print(json.dumps({"schema": 1, "status": "gate_failed", "reason": str(exc)},
                          sort_keys=True, separators=(",", ":")))
        return 2
    print(json.dumps(body, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
