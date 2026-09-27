#!/usr/bin/env python3
"""m6f-g の合成または実測行署名から凍結候補と判定名を導出する。"""
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
import predict_m6fg as predict  # noqa: E402


SHA_RE = re.compile(r"[0-9a-f]{64}")


class InputError(ValueError):
    pass


def _keys(value: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != allowed:
        raise InputError("許可列")
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
    item = _keys(value, {"line_count", "char_count", "sha256"})
    return _uint(item["line_count"], 25), _uint(item["char_count"], 2000), _sha(item["sha256"])


def _lines(value: Any) -> tuple[tuple[int, int, str], ...]:
    if not isinstance(value, list):
        raise InputError("行一覧")
    result = []
    previous = -1
    for raw in value:
        item = _keys(raw, {"physical_row", "char_count", "sha256"})
        row = _uint(item["physical_row"], 24)
        if row <= previous:
            raise InputError("行順序")
        result.append((row, _uint(item["char_count"], 80), _sha(item["sha256"])))
        previous = row
    return tuple(result)


def _run(value: Any) -> dict[str, Any]:
    item = _keys(value, {
        "screen", "late_screen", "entry_lines", "input_wait",
        "reference_unchanged", "output_audit_clean", "fkey_unchanged",
        "extra_lines_absent", "g13",
    })
    bools = ("input_wait", "reference_unchanged", "output_audit_clean",
             "fkey_unchanged", "extra_lines_absent")
    if any(not isinstance(item[key], bool) for key in bools):
        raise InputError("真偽値")
    g13 = _keys(item["g13"], {"line_sha", "char_count", "physical_row"})
    if any(not isinstance(value, bool) for value in g13.values()):
        raise InputError("G13形式")
    return {
        "screen": _summary(item["screen"]),
        "late_screen": _summary(item["late_screen"]),
        "entry_lines": _lines(item["entry_lines"]),
        **{key: item[key] for key in bools},
        "g13": dict(g13),
    }


def load_observations(path: Path) -> tuple[dict[str, list[dict[str, Any]]], str]:
    try:
        raw = path.read_bytes()
        doc = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputError("観測読取") from exc
    root = _keys(doc, {"format", "arms"})
    if root["format"] != "m6fg-observations-v1" or not isinstance(root["arms"], dict):
        raise InputError("観測形式")
    if set(root["arms"]) != set(predict.ALL_ARMS):
        raise InputError("腕一覧")
    arms = {}
    for arm in predict.ALL_ARMS:
        runs = root["arms"][arm]
        if not isinstance(runs, list) or len(runs) != 2:
            raise InputError("2走")
        arms[arm] = [_run(run) for run in runs]
    return arms, hashlib.sha256(raw).hexdigest()


def _whole(lines: tuple[tuple[int, int, str], ...]) -> str:
    digest = hashlib.sha256()
    for row, count, sha in lines:
        digest.update(f"{row}\t{count}\t{sha}\n".encode("ascii"))
    return digest.hexdigest()


def load_candidates(path: Path) -> dict[tuple[str, str], tuple[tuple[int, int, str], ...]]:
    try:
        raw_lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise InputError("候補表読取") from exc
    header = "record\tcandidate_id\tarm\tphysical_row\tchar_count\tsha256"
    if not raw_lines or raw_lines[0] != header:
        raise InputError("候補表ヘッダ")
    valid_pairs = {(candidate, arm) for arm in predict.MARK_ARMS
                   for candidate in predict.mark_candidate_ids()}
    valid_pairs |= {("size_min_digits", arm) for arm in predict.SIZE_ARMS}
    rows: dict[tuple[str, str], list[tuple[int, int, str]]] = {}
    summaries: set[tuple[str, str]] = set()
    for raw in raw_lines[1:]:
        fields = raw.split("\t")
        if len(fields) != 6:
            raise InputError("候補表列")
        record, candidate, arm, row_text, count_text, sha = fields
        key = (candidate, arm)
        if key not in valid_pairs or not SHA_RE.fullmatch(sha):
            raise InputError("候補表値")
        if record == "row":
            if key in summaries or not row_text.isdigit() or not count_text.isdigit():
                raise InputError("候補行形式")
            row, count = int(row_text), int(count_text)
            if not 0 <= row <= 24 or not 0 <= count <= 80:
                raise InputError("候補行範囲")
            rows.setdefault(key, []).append((row, count, sha))
        elif record == "summary":
            if key in summaries or row_text != "-" or not count_text.isdigit():
                raise InputError("候補summary形式")
            values = tuple(rows.get(key, []))
            if int(count_text) != len(values) or _whole(values) != sha:
                raise InputError("候補summary整合")
            if any(values[index][0] >= values[index + 1][0]
                   for index in range(len(values) - 1)):
                raise InputError("候補行順序")
            summaries.add(key)
        else:
            raise InputError("候補record")
    if summaries != valid_pairs or set(rows) - valid_pairs:
        raise InputError("候補欠落")
    return {key: tuple(rows.get(key, [])) for key in valid_pairs}


def _matches(lines, candidates, arm: str) -> list[str]:
    ids = predict.mark_candidate_ids() if arm in predict.MARK_ARMS else ("size_min_digits",)
    return [candidate for candidate in ids if candidates[(candidate, arm)] == lines]


def derive(arms: dict[str, list[dict[str, Any]]], candidates,
           manifest: dict[str, Any]) -> dict[str, Any]:
    matches = {(arm, rep): _matches(arms[arm][rep - 1]["entry_lines"], candidates, arm)
               for arm in predict.MARK_ARMS + predict.SIZE_ARMS for rep in (1, 2)}
    gates = {
        "G9": all(runs[0]["screen"] == runs[1]["screen"]
                  and runs[0]["entry_lines"] == runs[1]["entry_lines"]
                  for runs in arms.values()),
        "G10": all(run["screen"] == run["late_screen"] and run["input_wait"]
                   for runs in arms.values() for run in runs),
        "G11": all(run["reference_unchanged"] for runs in arms.values() for run in runs),
        "G12": all(run["output_audit_clean"] and run["fkey_unchanged"]
                   and run["extra_lines_absent"] for runs in arms.values() for run in runs),
        "G13": all(all(run["g13"].values()) for runs in arms.values() for run in runs),
    }
    remaining: dict[str, list[str]] = {}
    mark_results: dict[str, str] = {}
    for arm in predict.MARK_ARMS:
        values = list(predict.mark_candidate_ids())
        for rep in (1, 2):
            allowed = set(matches[(arm, rep)])
            values = [value for value in values if value in allowed]
        remaining[arm] = values
        mark_results[arm] = (values[0] if len(values) == 1 else
                             f"inconclusive_{arm}_no_candidate" if not values else
                             f"inconclusive_{arm}_multiple")

    mixed_lines = arms["G-M"][0]["entry_lines"]
    mixed_match_pairs = []
    for p_candidate in remaining["G-P"]:
        for b_candidate in remaining["G-B"]:
            expected = tuple((line.physical_row, line.char_count, line.sha256)
                             for line in predict.predict_mixed(
                                 manifest, p_candidate, b_candidate))
            if expected == mixed_lines:
                mixed_match_pairs.append([p_candidate, b_candidate])
    mixed = "mixed_row_consistent" if mixed_match_pairs else "mixed_row_inconsistent"
    size_min = all(matches[(arm, rep)] == ["size_min_digits"]
                   for arm in predict.SIZE_ARMS for rep in (1, 2))
    size = "size_min_digits" if size_min else "size_other"
    overall = "classified" if all(gates.values()) else "gate_failed"
    return {
        "format": "m6fg-derived-v1",
        "overall": overall,
        "gates": gates,
        "mark_candidates": remaining,
        "mark_judgments": mark_results,
        "mixed_match_pairs": mixed_match_pairs,
        "mixed_judgment": mixed,
        "size_judgment": size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--candidates", type=Path,
                        default=HERE / "m6fg_candidates_frozen.tsv")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        arms, input_digest = load_observations(args.observations)
        candidates = load_candidates(args.candidates)
        manifest = predict._manifest(args.manifest)
        result = derive(arms, candidates, manifest)
        result["input_sha256"] = input_digest
        payload = (json.dumps(result, ensure_ascii=True, sort_keys=True,
                              separators=(",", ":")) + "\n").encode("ascii")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            if args.output.exists():
                raise InputError("出力先")
            args.output.write_bytes(payload)
        return 0
    except (OSError, InputError, predict.PredictionError):
        print("derive_m6fg_error=InputError", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
