#!/usr/bin/env python3
"""m6f-b の18個の疎なD88差分から、事前登録 E1〜E8 を機械導出する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from derive_m6fa import (DiffView, InputError, Pos, Sector, _find, _pos_dict,
                         _sector_dict, _sector_values, _unique, parse_diff)

ARMS = tuple(f"G{i}" for i in range(9))
DERIVATIONS = tuple(f"E{i}" for i in range(1, 9))
DIRECTORY: Sector = (18, 1, 3)
U = b"QZ7A"
L = b"qz7a"
U_B = b"QZ7B"
L_B = b"qz7b"
U_LONG = b"QZ7ABC"
L_LONG = b"qz7abc"
U_PROGRAM = b"QZ7E"
L_PROGRAM = b"qz7e"
CASE_JUDGMENTS = (
    "case_stored_as_given", "case_folded_to_lower",
    "case_folded_to_upper", "case_other",
)
STATUSES = ("derived", "ambiguous", "not_found")


def _result(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    values = _unique(candidates)
    count = len(values)
    out: dict[str, Any] = {
        "status": "not_found" if count == 0 else "derived" if count == 1 else "ambiguous",
        "candidate_count": count,
    }
    if count == 1:
        out["value"] = values[0]
    return out


def _hits(view: DiffView, needles: tuple[bytes, ...]) -> list[Pos]:
    return sorted({pos for needle in needles for pos in _find(view, needle, {DIRECTORY})})


def _case(view: DiffView) -> tuple[str, list[Pos]]:
    upper = _find(view, U, {DIRECTORY})
    lower = _find(view, L, {DIRECTORY})
    if upper and lower:
        return "both", sorted(set(upper + lower))
    if upper:
        return "U", upper
    if lower:
        return "L", lower
    return "none", []


def _changed_range_starts(view: DiffView) -> set[Pos]:
    offsets = sorted(pos[3] for pos in view.new if pos[:3] == DIRECTORY)
    starts = {offset for index, offset in enumerate(offsets)
              if index == 0 or offsets[index - 1] + 1 != offset}
    return {(*DIRECTORY, offset) for offset in starts}


def _name_field_candidates(view: DiffView, names: tuple[bytes, ...],
                           allowed: set[Pos] | None = None) -> list[tuple[Pos, int]]:
    result: list[tuple[Pos, int]] = []
    for name in names:
        for start in _find(view, name, {DIRECTORY}):
            if allowed is not None and start not in allowed:
                continue
            length = len(name)
            while view.new.get((*DIRECTORY, start[3] + length)) == 0x20:
                length += 1
            result.append((start, length))
    return result


def derive_repetition(views: dict[str, DiffView]) -> dict[str, dict[str, Any]]:
    if set(views) != set(ARMS):
        raise InputError("腕の不足または余分")
    g1, g2, g3, g4, g5, g6, g7, g8 = (views[f"G{i}"] for i in range(1, 9))

    # E1: S内の疎な新値列で U/L の連続出現を腕ごとに分類する。
    cases: dict[str, str] = {}
    case_hits: dict[str, list[Pos]] = {}
    for arm, view in (("G1", g1), ("G2", g2), ("G3", g3)):
        cases[arm], case_hits[arm] = _case(view)
    triple = (cases["G1"], cases["G2"], cases["G3"])
    if triple == ("U", "L", "L"):
        case_judgment = "case_stored_as_given"
    elif triple == ("L", "L", "L"):
        case_judgment = "case_folded_to_lower"
    elif triple == ("U", "U", "U"):
        case_judgment = "case_folded_to_upper"
    else:
        case_judgment = "case_other"
    e1 = {"status": case_judgment, "candidate_count": 1,
          "value": {"G1": cases["G1"], "G2": cases["G2"], "G3": cases["G3"]}}

    # E2: G1で見つけた U/L の位置が、S内の変更区間の先頭と一致すること。
    starts = _changed_range_starts(g1)
    e2_positions = [pos for pos in case_hits["G1"] if pos in starts]
    e2 = _result([{"position": _pos_dict(pos)} for pos in e2_positions])

    # E3: G4の2名がそれぞれちょうど1か所なら、その位置差を採る。
    first = _hits(g4, (U, L))
    second = _hits(g4, (U_B, L_B))
    if len(first) == len(second) == 1 and second[0][3] > first[0][3]:
        e3 = _result([{"entry_length": second[0][3] - first[0][3]}])
    elif first and second:
        e3 = {"status": "ambiguous", "candidate_count": max(2, len(first) * len(second))}
    else:
        e3 = {"status": "not_found", "candidate_count": 0}

    # E4: 4文字名/6文字名に続く0x20を含む最長連続長が同じ場合だけ採る。
    allowed = set(e2_positions)
    short_fields = _name_field_candidates(g1, (U, L), allowed)
    long_fields = _name_field_candidates(g6, (U_LONG, L_LONG))
    e4_values = [{"name_field_length": a_length, "padding_value": "20"}
                 for _a_pos, a_length in short_fields
                 for _b_pos, b_length in long_fields if a_length == b_length]
    e4 = _result(e4_values)

    # E5: G1/G5の最終値を、相手側で開示された一様旧値だけで補って比較する。
    lengths: list[int] = []
    if e3["status"] == "derived":
        lengths = [int(e3["value"]["entry_length"])]
    elif e3["status"] == "not_found" and e4["status"] == "derived":
        lengths = [int(e4["value"]["name_field_length"]) + 2]
    e5_values: list[dict[str, Any]] = []
    for start in e2_positions:
        for length in lengths:
            for offset in range(start[3], min(256, start[3] + length)):
                pos = (*DIRECTORY, offset)
                value1 = g1.new.get(pos, g5.old.get(pos))
                value5 = g5.new.get(pos, g1.old.get(pos))
                if value1 is not None and value5 is not None and value1 != value5:
                    e5_values.append({"position": _pos_dict(pos), "value": f"{value5:02X}"})
    e5 = _result(e5_values)

    # E6: Sのセクタ単位一様旧値。変更済みだが非開示なら理由を固定する。
    if DIRECTORY in g1.old_uniform:
        e6 = _result([{"unused_entry_value": f"{g1.old_uniform[DIRECTORY]:02X}"}])
    else:
        e6 = {"status": "not_found", "candidate_count": 0}
        if DIRECTORY in g1.changed_counts:
            e6["reason"] = "old_values_withheld"

    # E7: S以外でG1/G2/G3の位置・新値が完全一致し、G7の変更数が多いセクタ。
    common = set(g1.changed_counts) & set(g2.changed_counts) & set(g3.changed_counts)
    e7_sectors = [sector for sector in sorted(common) if sector != DIRECTORY
                  and _sector_values(g1, sector) == _sector_values(g2, sector)
                  == _sector_values(g3, sector)
                  and g7.changed_counts.get(sector, 0) > g1.changed_counts[sector]]
    if e7_sectors:
        e7 = {"status": "derived", "candidate_count": len(e7_sectors),
              "value": {"sectors": [_sector_dict(sector) for sector in e7_sectors]}}
    else:
        e7 = {"status": "not_found", "candidate_count": 0}

    # E8: G1/G8それぞれで名前欄直後に実際に書かれた新値を記録する。
    e8_values: list[dict[str, Any]] = []
    if e4["status"] == "derived":
        field_length = int(e4["value"]["name_field_length"])
        program_hits = _hits(g8, (U_PROGRAM, L_PROGRAM))
        for data_pos in e2_positions:
            data_value = g1.new.get((*DIRECTORY, data_pos[3] + field_length))
            for program_pos in program_hits:
                program_value = g8.new.get((*DIRECTORY, program_pos[3] + field_length))
                if data_value is not None and program_value is not None:
                    e8_values.append({"data_value": f"{data_value:02X}",
                                      "program_value": f"{program_value:02X}"})
    e8 = _result(e8_values)
    return {"E1": e1, "E2": e2, "E3": e3, "E4": e4,
            "E5": e5, "E6": e6, "E7": e7, "E8": e8}


def _key(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def consensus(name: str, first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    if name == "E1":
        if first.get("status") not in CASE_JUDGMENTS or second.get("status") not in CASE_JUDGMENTS:
            raise InputError("E1導出結果の形式")
        if first["status"] == second["status"] and _key(first.get("value")) == _key(second.get("value")):
            return first
        return {"status": "ambiguous", "candidate_count": 2}
    for item in (first, second):
        if item.get("status") not in STATUSES or type(item.get("candidate_count")) is not int:
            raise InputError("導出結果の形式")
    if first["status"] == second["status"] == "derived" \
            and _key(first.get("value")) == _key(second.get("value")):
        return first
    if first["status"] == second["status"] == "not_found" \
            and first.get("reason") == second.get("reason"):
        return first
    return {"status": "ambiguous",
            "candidate_count": max(2, int(first["candidate_count"]), int(second["candidate_count"]))}


def load_all(raw_dir: Path) -> tuple[list[dict[str, object]], dict[str, dict[str, Any]], str]:
    digest = hashlib.sha256()
    runs: list[dict[str, object]] = []
    for repetition in (1, 2):
        views = {}
        for arm in ARMS:
            path = raw_dir / f"{arm}-r{repetition}.diff.json"
            raw = path.read_bytes()
            digest.update(f"{arm}:{repetition}\n".encode("ascii") + raw)
            views[arm] = parse_diff(json.loads(raw))
        runs.append({"repetition": repetition, "derivations": derive_repetition(views)})
    first = runs[0]["derivations"]
    second = runs[1]["derivations"]
    assert isinstance(first, dict) and isinstance(second, dict)
    combined = {name: consensus(name, first[name], second[name]) for name in DERIVATIONS}
    return runs, combined, digest.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        runs, derivations, digest = load_all(args.raw_dir)
        body = json.dumps({"schema": 1, "runs": runs, "derivations": derivations,
                           "input_sha256": digest},
                          ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        if args.output:
            args.output.write_text(body, encoding="utf-8")
        else:
            sys.stdout.write(body)
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
