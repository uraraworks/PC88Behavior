#!/usr/bin/env python3
"""m6f-e の候補集合 C、補助判定、文字数だけの構造を導出する。

入力 JSON (m6fe-observations-v1) は走行ドライバが作る本文なしの正規化結果。
各 run は screen/late_screen の全体署名、entry_lines（入力待ち行・ファンクション
キー行を除いたエントリ行署名）、input_wait、reference_unchanged、
output_audit_clean、g13 の3陰性対照を持つ。E腕の entry_lines は ERR 数値行を
表し、parse_class は登録時に拒否された場合だけ指定する。

自由記述欄は持たず、入力値を例外や出力へ反射しない。
"""
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


ALL_ARMS = ("L0", "L1", "L4", "L5", "L6", "L11", "L96",
            "D-omit", "D-1", "D-2", "D-expr", "E-0", "E-3", "E-str", "N-wait")
LAYOUT_ARMS = predictor.LAYOUT_ARMS
ERROR_ARMS = ("E-0", "E-3", "E-str")
SHA_RE = re.compile(r"[0-9a-f]{64}")
PARSE_CLASSES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
                 18, 19, 20, 21, 22, 23, 26, 27, 29, 30, 31, 32, 33, 50, 51,
                 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 64, 65, 68, 69,
                 70, 71, 72, 73)

ORDER_VALUES = ("directory_order_skips_deleted", "order_other")
EMPTY_VALUES = ("empty_has_no_entry_rows", "empty_other")
OVERFLOW_VALUES = ("scrolls_to_tail", "page_wait", "truncates", "overflow_other")
DRIVE_VALUES = ("default_is_1_explicit_1_2", "drive1_served_from_cache", "drive_selection_other")
EXPR_VALUES = ("drive_expression_accepted", "drive_literal_only", "drive_expression_other")
NO_MEDIA_VALUES = ("files_no_media_waits_for_media", "files_no_media_stuck", "inconclusive_no_media")


class InputError(ValueError):
    """不正入力。入力由来の値はメッセージへ含めない。"""


def _keys(value: Any, allowed: set[str], required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or not required <= set(value) or not set(value) <= allowed:
        raise InputError("許可リスト外フィールド")
    return value


def _uint(value: Any, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise InputError("整数範囲")
    return value


def _sha(value: Any) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise InputError("SHA形式")
    return value


def _summary(value: Any) -> tuple[int, int, str]:
    item = _keys(value, {"line_count", "char_count", "sha256"},
                 {"line_count", "char_count", "sha256"})
    return _uint(item["line_count"], 25), _uint(item["char_count"], 2000), _sha(item["sha256"])


def _lines(value: Any) -> tuple[tuple[int, int, str], ...]:
    if not isinstance(value, list):
        raise InputError("行一覧形式")
    out = []
    seen = set()
    for raw in value:
        item = _keys(raw, {"physical_row", "char_count", "sha256"},
                     {"physical_row", "char_count", "sha256"})
        row = _uint(item["physical_row"], 24)
        if row in seen:
            raise InputError("行番号重複")
        seen.add(row)
        out.append((row, _uint(item["char_count"], 80), _sha(item["sha256"])))
    if [item[0] for item in out] != sorted(seen):
        raise InputError("行順序")
    return tuple(out)


def _parse_class(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value not in PARSE_CLASSES:
        raise InputError("parse分類形式")
    return value


def _run(value: Any) -> dict[str, Any]:
    allowed = {"screen", "late_screen", "entry_lines", "input_wait",
               "reference_unchanged", "output_audit_clean", "g13", "parse_class",
               "fkey_unchanged", "extra_lines_absent"}
    required = allowed - {"parse_class"}
    item = _keys(value, allowed, required)
    for key in ("input_wait", "reference_unchanged", "output_audit_clean",
                "fkey_unchanged", "extra_lines_absent"):
        if not isinstance(item[key], bool):
            raise InputError("真偽値形式")
    g13 = _keys(item["g13"], {"line_sha", "char_count", "physical_row"},
                {"line_sha", "char_count", "physical_row"})
    if any(not isinstance(v, bool) for v in g13.values()):
        raise InputError("G13形式")
    return {
        "screen": _summary(item["screen"]),
        "late_screen": _summary(item["late_screen"]),
        "entry_lines": _lines(item["entry_lines"]),
        "input_wait": item["input_wait"],
        "reference_unchanged": item["reference_unchanged"],
        "output_audit_clean": item["output_audit_clean"],
        "fkey_unchanged": item["fkey_unchanged"],
        "extra_lines_absent": item["extra_lines_absent"],
        "g13": dict(g13),
        "parse_class": _parse_class(item.get("parse_class")),
    }


def _aux(value: Any) -> dict[str, str]:
    item = _keys(value, {"order", "empty", "overflow", "drive", "expression", "no_media"},
                 {"order", "empty", "overflow", "drive", "expression", "no_media"})
    choices = {"order": ORDER_VALUES, "empty": EMPTY_VALUES, "overflow": OVERFLOW_VALUES,
               "drive": DRIVE_VALUES, "expression": EXPR_VALUES}
    if any(item[key] not in values for key, values in choices.items()):
        raise InputError("補助判定値")
    no_media = item["no_media"]
    if (no_media not in NO_MEDIA_VALUES
            and not (isinstance(no_media, str) and re.fullmatch(r"files_no_media_error_(?:[0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])", no_media))):
        raise InputError("未挿入判定値")
    return dict(item)


def load_observations(path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str], str]:
    try:
        raw = path.read_bytes()
        doc = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError("観測入力読取") from exc
    root = _keys(doc, {"format", "arms", "aux"}, {"format", "arms", "aux"})
    if root["format"] != "m6fe-observations-v1" or not isinstance(root["arms"], dict):
        raise InputError("観測入力形式")
    if set(root["arms"]) != set(ALL_ARMS):
        raise InputError("腕一覧")
    arms: dict[str, list[dict[str, Any]]] = {}
    for arm in ALL_ARMS:
        runs = root["arms"][arm]
        if not isinstance(runs, list) or len(runs) != 2:
            raise InputError("2走形式")
        arms[arm] = [_run(run) for run in runs]
    return arms, _aux(root["aux"]), hashlib.sha256(raw).hexdigest()


def load_candidates(path: Path) -> dict[tuple[str, str], tuple[tuple[int, int, str], ...]]:
    try:
        raw_lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise InputError("候補表読取") from exc
    header = "record\tcandidate_id\tarm\tphysical_row\tchar_count\tsha256"
    if not raw_lines or raw_lines[0] != header:
        raise InputError("候補表ヘッダ")
    rows: dict[tuple[str, str], list[tuple[int, int, str]]] = {}
    summaries: dict[tuple[str, str], tuple[int, str]] = {}
    valid_ids = set(predictor.candidate_ids())
    for raw in raw_lines[1:]:
        fields = raw.split("\t")
        if len(fields) != 6:
            raise InputError("候補表列")
        record, candidate, arm, row_text, count_text, digest = fields
        if candidate not in valid_ids or arm not in LAYOUT_ARMS or not SHA_RE.fullmatch(digest):
            raise InputError("候補表値")
        key = (candidate, arm)
        try:
            count = int(count_text)
        except ValueError as exc:
            raise InputError("候補表整数") from exc
        if record == "row":
            try:
                row = int(row_text)
            except ValueError as exc:
                raise InputError("候補表行番号") from exc
            if not 0 <= row <= 24 or not 0 <= count <= 80:
                raise InputError("候補表行範囲")
            rows.setdefault(key, []).append((row, count, digest))
        elif record == "summary" and row_text == "-":
            if key in summaries or count < 0 or count > 25:
                raise InputError("候補表summary重複")
            summaries[key] = (count, digest)
        else:
            raise InputError("候補表record")
    expected_keys = {(candidate, arm) for candidate in predictor.candidate_ids() for arm in LAYOUT_ARMS}
    if set(summaries) != expected_keys or not set(rows) <= expected_keys:
        raise InputError("候補または腕の欠落")
    result = {}
    for key in expected_keys:
        values = rows.get(key, [])
        if len({v[0] for v in values}) != len(values) or values != sorted(values):
            raise InputError("候補表行重複または順序")
        expected_count, expected_digest = summaries[key]
        signed = [predictor.SignedLine(*value) for value in values]
        if expected_count != len(values) or expected_digest != predictor._whole_digest(signed):
            raise InputError("候補表summary不整合")
        result[key] = tuple(values)
    return result


def _matches(lines: tuple[tuple[int, int, str], ...], candidates, arm: str) -> list[str]:
    return [candidate for candidate in predictor.candidate_ids()
            if candidates[(candidate, arm)] == lines]


def _error_class(run: dict[str, Any]) -> str:
    matches = []
    for number in range(256):
        expected = tuple((v.physical_row, v.char_count, v.sha256)
                         for v in predictor.predict_error(number))
        if expected == run["entry_lines"]:
            matches.append(number)
    if len(matches) == 1:
        return f"files_error_err_{matches[0]}"
    if run["parse_class"] is not None and not run["entry_lines"]:
        return f"files_error_parse_{run['parse_class']}"
    return "inconclusive_error"


def _gates(arms: dict[str, list[dict[str, Any]]], aux: dict[str, str], matches) -> dict[str, bool]:
    g9 = True
    for arm, runs in arms.items():
        if runs[0]["screen"] != runs[1]["screen"]:
            g9 = False
        if arm in LAYOUT_ARMS and matches[(arm, 1)] != matches[(arm, 2)]:
            g9 = False
        if arm in ERROR_ARMS and _error_class(runs[0]) != _error_class(runs[1]):
            g9 = False
    g10 = True
    for arm, runs in arms.items():
        applicable = arm != "N-wait" and not (arm == "L96" and aux["overflow"] == "page_wait")
        if applicable and any(run["screen"] != run["late_screen"] or not run["input_wait"]
                              for run in runs):
            g10 = False
    g11 = all(run["reference_unchanged"] for runs in arms.values() for run in runs)
    g12 = all(run["output_audit_clean"] for runs in arms.values() for run in runs)
    g13 = all(all(run["g13"].values()) for runs in arms.values() for run in runs)
    return {"G9": g9, "G10": g10, "G11": g11, "G12": g12, "G13": g13}


def _structure(arms: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    first = {arm: arms[arm][0]["entry_lines"] for arm in LAYOUT_ARMS}
    all_counts = [line[1] for lines in first.values() for line in lines]
    if all_counts and all(value == 80 for value in all_counts):
        return {"classification": "char_count_uninformative"}
    pattern = tuple(len(first[arm]) for arm in ("L4", "L5", "L6"))
    k = {(1, 1, 2): "K=5", (1, 2, 2): "K=4", (1, 1, 1): "K>=6"}.get(
        pattern, "rows_per_count_other")
    w1 = first["L1"][0][1] if len(first["L1"]) == 1 else None
    d4 = first["L4"][0][1] - w1 if w1 is not None and first["L4"] else None
    d5 = first["L5"][0][1] - w1 if w1 is not None and first["L5"] else None
    step4 = d4 // 3 if d4 is not None and d4 % 3 == 0 else None
    step5 = d5 // 4 if d5 is not None and d5 % 4 == 0 else None
    if step4 is not None and step4 == step5:
        width_class = "content_width" if w1 is not None and step4 == w1 + 1 else "fixed_width_cell"
    else:
        width_class = "entry_width_other"
    l11_counts = [line[1] for line in first["L11"]]
    name_width = ("width_depends_on_name_length" if len(set(l11_counts)) > 1
                  else "width_fixed_per_entry")
    return {"classification": "char_count_informative", "rows_per_count": k,
            "row_count_pattern": list(pattern), "w1": w1,
            "l4_first_minus_w1": d4, "l5_first_minus_w1": d5,
            "entry_width": width_class,
            "name_length": name_width}


def derive(arms: dict[str, list[dict[str, Any]]], aux: dict[str, str], candidates) -> dict[str, Any]:
    matches = {(arm, rep): _matches(arms[arm][rep - 1]["entry_lines"], candidates, arm)
               for arm in LAYOUT_ARMS for rep in (1, 2)}
    gates = _gates(arms, aux, matches)
    remaining = list(predictor.candidate_ids())
    first_empty_arm = None
    for arm in LAYOUT_ARMS:
        for rep in (1, 2):
            allowed = set(matches[(arm, rep)])
            remaining = [candidate for candidate in remaining if candidate in allowed]
        if not remaining and first_empty_arm is None:
            first_empty_arm = arm
    if not all(gates.values()):
        overall = "gate_failed"
    elif aux["order"] != "directory_order_skips_deleted":
        overall = "inconclusive_order"
    elif aux["empty"] != "empty_has_no_entry_rows":
        overall = "inconclusive_empty"
    elif aux["overflow"] != "scrolls_to_tail":
        overall = "inconclusive_overflow"
    elif (any(not run["extra_lines_absent"] for runs in arms.values() for run in runs)
          or any(not run["fkey_unchanged"] for runs in arms.values() for run in runs)):
        overall = "inconclusive_extra_lines"
    elif len(remaining) == 1:
        overall = remaining[0]
    elif not remaining:
        overall = "inconclusive_no_candidate"
    else:
        overall = "inconclusive_multiple_candidates"
    errors = {arm: _error_class(arms[arm][0]) for arm in ERROR_ARMS}
    return {
        "format": "m6fe-derived-v1", "overall": overall,
        "gates": gates, "candidates": remaining, "first_empty_arm": first_empty_arm,
        "aux": {**aux, "errors": errors}, "structure": _structure(arms),
        "fkey_unchanged": all(run["fkey_unchanged"] for runs in arms.values() for run in runs),
        "extra_lines_absent": all(run["extra_lines_absent"] for runs in arms.values() for run in runs),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--observations", required=True, type=Path)
    ap.add_argument("--candidates", default=HERE / "m6fe_candidates_frozen.tsv", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        arms, aux, input_digest = load_observations(args.observations)
        candidates = load_candidates(args.candidates)
        result = derive(arms, aux, candidates)
        result["input_sha256"] = input_digest
        payload = (json.dumps(result, ensure_ascii=True, sort_keys=True,
                              separators=(",", ":")) + "\n").encode("ascii")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            if args.output.exists():
                raise InputError("出力先が存在する")
            args.output.write_bytes(payload)
        return 0
    except (InputError, OSError):
        print("derive_m6fe_error=InputError", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
