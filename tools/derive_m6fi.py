#!/usr/bin/env python3
"""m6f-i の2走の行署名を凍結候補へ照合し、関門と判定を導く。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import predict_m6fi as predict

SHA = re.compile(r"[0-9a-f]{64}\Z")


class InputError(ValueError):
    pass


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise InputError("許可列")
    return value


def _summary(value):
    v = _keys(value, ("line_count", "char_count", "sha256"))
    if (type(v["line_count"]) is not int or not 0 <= v["line_count"] <= 25
            or type(v["char_count"]) is not int or not 0 <= v["char_count"] <= 2000
            or not isinstance(v["sha256"], str) or not SHA.fullmatch(v["sha256"])):
        raise InputError("全体署名")
    return (v["line_count"], v["char_count"], v["sha256"])


def _lines(value):
    if not isinstance(value, list):
        raise InputError("行一覧")
    out = []
    for item in value:
        v = _keys(item, ("physical_row", "char_count", "sha256"))
        row, count, digest = v["physical_row"], v["char_count"], v["sha256"]
        if (type(row) is not int or not 0 <= row <= 24 or
                type(count) is not int or not 0 <= count <= 80 or
                not isinstance(digest, str) or not SHA.fullmatch(digest) or
                (out and row <= out[-1][0])):
            raise InputError("行署名")
        out.append((row, count, digest))
    return tuple(out)


def load_observations(path: Path):
    raw = path.read_bytes()
    doc = _keys(json.loads(raw), ("format", "arms"))
    if doc["format"] != "m6fi-observations-v1" or set(doc["arms"]) != set(predict.ARMS):
        raise InputError("観測形式")
    arms = {}
    for arm in predict.ARMS:
        runs = doc["arms"][arm]
        if not isinstance(runs, list) or len(runs) != 2:
            raise InputError("2走")
        converted = []
        for run in runs:
            v = _keys(run, ("screen", "late_screen", "load_screen", "load_late_screen",
                            "entry_lines", "input_wait", "load_input_wait",
                            "reference_unchanged", "output_audit_clean", "fkey_unchanged",
                            "extra_lines_absent", "g13"))
            for key in ("input_wait", "load_input_wait", "reference_unchanged",
                        "output_audit_clean", "fkey_unchanged", "extra_lines_absent"):
                if type(v[key]) is not bool:
                    raise InputError("真偽")
            g13 = _keys(v["g13"], ("line_sha", "char_count", "physical_row"))
            if any(type(value) is not bool for value in g13.values()):
                raise InputError("G13")
            converted.append({"screen": _summary(v["screen"]),
                "late_screen": _summary(v["late_screen"]),
                "load_screen": None if v["load_screen"] is None else _summary(v["load_screen"]),
                "load_late_screen": None if v["load_late_screen"] is None else _summary(v["load_late_screen"]),
                "entry_lines": _lines(v["entry_lines"]), "g13": g13,
                **{key: v[key] for key in ("input_wait", "load_input_wait",
                    "reference_unchanged", "output_audit_clean", "fkey_unchanged",
                    "extra_lines_absent")}})
        arms[arm] = converted
    return arms, hashlib.sha256(raw).hexdigest()


def load_candidates(path: Path):
    rows = path.read_text(encoding="ascii").splitlines()
    if not rows or rows[0] != "record\tarm\tcandidate_id\tphysical_row\tchar_count\tsha256":
        raise InputError("候補ヘッダ")
    valid = {(arm, candidate) for arm in predict.ARMS
             for candidate in predict.candidate_ids(arm)}
    values = {key: [] for key in valid}
    summaries = set()
    for raw in rows[1:]:
        fields = raw.split("\t")
        if len(fields) != 6:
            raise InputError("候補列")
        kind, arm, candidate, row, count, digest = fields
        key = (arm, candidate)
        if key not in valid or not SHA.fullmatch(digest):
            raise InputError("候補値")
        if kind == "row":
            if key in summaries or not row.isdecimal() or not count.isdecimal():
                raise InputError("候補行")
            triple = (int(row), int(count), digest)
            if not 0 <= triple[0] <= 24 or not 0 <= triple[1] <= 80 or (
                    values[key] and triple[0] <= values[key][-1][0]):
                raise InputError("候補範囲")
            values[key].append(triple)
        elif kind == "summary":
            if (key in summaries or row != "-" or count != str(len(values[key]))
                    or digest != predict.whole(tuple(predict.SignedLine(*v)
                                                  for v in values[key]))):
                raise InputError("候補summary")
            summaries.add(key)
        else:
            raise InputError("候補record")
    if summaries != valid:
        raise InputError("候補欠落")
    return {key: tuple(value) for key, value in values.items()}


def derive(arms, candidates):
    gates = {
        "G9": all(runs[0]["screen"] == runs[1]["screen"] and
                  runs[0]["entry_lines"] == runs[1]["entry_lines"] for runs in arms.values()),
        "G10": all(run["screen"] == run["late_screen"] and run["input_wait"] and
                   (arm not in predict.ARMS[:3] or (run["load_screen"] is not None and
                    run["load_screen"] == run["load_late_screen"] and run["load_input_wait"]))
                   for arm, runs in arms.items() for run in runs),
        "G11": all(run["reference_unchanged"] for runs in arms.values() for run in runs),
        "G12": all(run["output_audit_clean"] and run["fkey_unchanged"] and
                   run["extra_lines_absent"] for runs in arms.values() for run in runs),
        "G13": all(all(run["g13"].values()) for runs in arms.values() for run in runs),
    }
    matches = {}
    judgments = {}
    for arm in predict.ARMS:
        remaining = [candidate for candidate in predict.candidate_ids(arm)
                     if all(run["entry_lines"] == candidates[(arm, candidate)]
                            for run in arms[arm])]
        matches[arm] = remaining
        judgments[arm] = (remaining[0] if len(remaining) == 1 else
                          f"inconclusive_{arm}" if len(remaining) > 1 else
                          "not_trapped" if arm.startswith("E-") else "other")
    return {"format": "m6fi-derived-v1", "overall": "classified" if all(gates.values()) else "gate_failed",
            "gates": gates, "matches": matches, "judgments": judgments}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--observations", required=True, type=Path)
    ap.add_argument("--candidates", type=Path,
                    default=Path(__file__).with_name("m6fi_candidates_frozen.tsv"))
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        arms, digest = load_observations(args.observations)
        doc = derive(arms, load_candidates(args.candidates))
        doc["input_sha256"] = digest
        raw = (json.dumps(doc, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
        if args.output is None:
            sys.stdout.buffer.write(raw)
        elif not args.output.exists():
            args.output.write_bytes(raw)
        else:
            raise InputError("出力先")
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, InputError):
        print("derive_m6fi_error=InputError", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
