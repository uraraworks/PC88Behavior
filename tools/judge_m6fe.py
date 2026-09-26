#!/usr/bin/env python3
"""derive_m6fe.py の出力を独立再判定し、m6f-e の判定名だけを返す。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import predict_m6fe as predictor  # noqa: E402
import derive_m6fe as derive  # noqa: E402


FIXED_OVERALL = {
    "gate_failed", "inconclusive_order", "inconclusive_extra_lines",
    "inconclusive_empty", "inconclusive_overflow", "inconclusive_no_candidate",
    "inconclusive_multiple_candidates",
}
SHA_RE = re.compile(r"[0-9a-f]{64}")
ERROR_RE = re.compile(r"files_error_err_(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])")


class InputError(ValueError):
    pass


def _recompute(doc: dict[str, Any]) -> str:
    required = {"format", "overall", "gates", "candidates", "first_empty_arm", "aux",
                "structure", "fkey_unchanged", "extra_lines_absent", "input_sha256"}
    if set(doc) != required or doc.get("format") != "m6fe-derived-v1":
        raise InputError("導出形式")
    gates = doc["gates"]
    if (not isinstance(gates, dict) or set(gates) != {"G9", "G10", "G11", "G12", "G13"}
            or any(not isinstance(v, bool) for v in gates.values())):
        raise InputError("関門形式")
    candidates = doc["candidates"]
    valid = set(predictor.candidate_ids())
    if (not isinstance(candidates, list) or len(candidates) != len(set(candidates))
            or any(value not in valid for value in candidates)):
        raise InputError("候補集合")
    if doc["first_empty_arm"] is not None and doc["first_empty_arm"] not in predictor.LAYOUT_ARMS:
        raise InputError("初回全滅腕")
    aux = doc["aux"]
    if not isinstance(aux, dict) or set(aux) != {"order", "empty", "overflow", "drive", "expression", "no_media", "errors"}:
        raise InputError("補助判定形式")
    errors = aux["errors"]
    if not isinstance(errors, dict) or set(errors) != {"E-0", "E-3", "E-str"}:
        raise InputError("E腕形式")
    for value in errors.values():
        parse_values = {f"files_error_parse_{number}" for number in derive.PARSE_CLASSES}
        if (value != "inconclusive_error" and value not in parse_values
                and not (isinstance(value, str) and ERROR_RE.fullmatch(value))):
            raise InputError("E腕判定")
    fixed_aux = {
        "order": derive.ORDER_VALUES, "empty": derive.EMPTY_VALUES,
        "overflow": derive.OVERFLOW_VALUES, "drive": derive.DRIVE_VALUES,
        "expression": derive.EXPR_VALUES,
    }
    if any(aux[key] not in values for key, values in fixed_aux.items()):
        raise InputError("補助判定値")
    no_media = aux["no_media"]
    if (no_media not in derive.NO_MEDIA_VALUES
            and not (isinstance(no_media, str) and re.fullmatch(
                r"files_no_media_error_(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])",
                no_media))):
        raise InputError("未挿入判定値")
    if not isinstance(doc["fkey_unchanged"], bool) or not isinstance(doc["extra_lines_absent"], bool):
        raise InputError("画面補助形式")
    if not isinstance(doc["input_sha256"], str) or not SHA_RE.fullmatch(doc["input_sha256"]):
        raise InputError("入力SHA形式")
    structure = doc["structure"]
    if not isinstance(structure, dict) or structure.get("classification") not in (
            "char_count_uninformative", "char_count_informative"):
        raise InputError("構造導出形式")
    if structure["classification"] == "char_count_uninformative":
        if set(structure) != {"classification"}:
            raise InputError("構造導出列")
    else:
        expected_structure = {"classification", "rows_per_count", "row_count_pattern",
                              "w1", "l4_first_minus_w1", "l5_first_minus_w1",
                              "entry_width", "name_length"}
        if set(structure) != expected_structure:
            raise InputError("構造導出列")
        if structure["rows_per_count"] not in ("K=5", "K=4", "K>=6", "rows_per_count_other"):
            raise InputError("構造導出値")
        if structure["entry_width"] not in ("fixed_width_cell", "content_width", "entry_width_other"):
            raise InputError("構造導出値")
        if structure["name_length"] not in ("width_depends_on_name_length", "width_fixed_per_entry"):
            raise InputError("構造導出値")
        pattern = structure["row_count_pattern"]
        if (not isinstance(pattern, list) or len(pattern) != 3
                or any(not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 25 for v in pattern)):
            raise InputError("構造導出数値")
        for key in ("w1", "l4_first_minus_w1", "l5_first_minus_w1"):
            value = structure[key]
            if value is not None and (not isinstance(value, int) or isinstance(value, bool)
                                      or not -80 <= value <= 80):
                raise InputError("構造導出数値")
    if not all(gates.values()):
        return "gate_failed"
    if aux["order"] != "directory_order_skips_deleted":
        return "inconclusive_order"
    if aux["empty"] != "empty_has_no_entry_rows":
        return "inconclusive_empty"
    if aux["overflow"] != "scrolls_to_tail":
        return "inconclusive_overflow"
    if not doc["extra_lines_absent"] or not doc["fkey_unchanged"]:
        return "inconclusive_extra_lines"
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return "inconclusive_no_candidate"
    return "inconclusive_multiple_candidates"


def _judgments(doc: dict[str, Any], overall: str) -> list[str]:
    aux = doc["aux"]
    values = [overall, aux["order"], aux["empty"], aux["overflow"], aux["drive"],
              aux["expression"], aux["no_media"]]
    values.extend(aux["errors"][arm] for arm in ("E-0", "E-3", "E-str"))
    return values


def _emit(overall: str, judgments: list[str], digest: str) -> None:
    print(json.dumps({"overall": overall, "judgments": judgments, "sha256": digest},
                     ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--derived", required=True, type=Path)
    args = ap.parse_args()
    digest = hashlib.sha256()
    try:
        raw = args.derived.read_bytes()
        digest.update(raw)
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise InputError("導出形式")
        overall = _recompute(doc)
        if doc["overall"] != overall or (overall not in FIXED_OVERALL and overall not in predictor.candidate_ids()):
            raise InputError("overall不一致")
        _emit(overall, _judgments(doc, overall), digest.hexdigest())
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, InputError, ValueError):
        _emit("gate_failed", ["gate_failed"], digest.hexdigest())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
