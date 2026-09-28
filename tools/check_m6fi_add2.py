#!/usr/bin/env python3
"""追補2の媒体・打鍵・予測器と新規凍結表を起動前に照合する。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import derive_m6fi_add2 as derive
import predict_m6fi_add2 as predict

HERE = Path(__file__).resolve().parent


def verify(manifest: Path, candidates: Path, frozen: Path, predictor: Path,
           scenario_only: bool = False) -> None:
    rows = [line.split("\t") for line in frozen.read_text(encoding="ascii").splitlines()]
    values = dict(rows)
    if (len(rows) != 3 or any(len(row) != 2 for row in rows) or len(values) != 3 or
            set(values) != {"manifest_sha256", "candidates_sha256", "predictor_sha256"}):
        raise ValueError("凍結表")
    checks = (("manifest_sha256", manifest),) if scenario_only else (
        ("manifest_sha256", manifest), ("candidates_sha256", candidates),
        ("predictor_sha256", predictor))
    for key, path in checks:
        if hashlib.sha256(path.read_bytes()).hexdigest() != values[key]:
            raise ValueError("凍結SHA")
    if not scenario_only and candidates.read_bytes() != predict.render_candidates():
        raise ValueError("候補再生成")
    doc = json.loads(manifest.read_bytes())
    if doc.get("format") != "m6fi-add2-scenario-v1":
        raise ValueError("manifest")
    names = [entry["name"] for entry in doc["entries"]]
    if names != ["qia", "qib", "qid", "qie"]:
        raise ValueError("名前")
    arms = doc["arms"]
    if [arm["id"] for arm in arms] != list(predict.ARMS):
        raise ValueError("腕")
    target = {"I-4'": names[0], "E-2'": names[2], "E-3": names[3], "E-3m": names[3]}
    for arm in arms:
        if (re.findall(r'\bload "2:([^"\n]+)"', arm["command"]) != [target[arm["id"]]] or
                arm["runs"] != 2 or arm["drive2"] != "ascii" or arm["final_frame"] != 8000 or
                arm["list_frame"] != (4000 if arm["id"] == "E-3" else None)):
            raise ValueError("打鍵・計画")
    if not scenario_only and len(derive.load_candidates(candidates)) != sum(
            len(predict.candidate_ids(a)) for a in predict.ARMS):
        raise ValueError("候補数")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--candidates", type=Path, default=HERE / "m6fi_add2_candidates_frozen.tsv")
    ap.add_argument("--frozen", type=Path, default=HERE / "m6fi_add2_frozen.tsv")
    ap.add_argument("--predictor", type=Path, default=HERE / "predict_m6fi_add2.py")
    ap.add_argument("--scenario-only", action="store_true")
    args = ap.parse_args()
    try:
        verify(args.manifest, args.candidates, args.frozen, args.predictor, args.scenario_only)
        print("m6fi_add2_gate=ok")
        return 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, derive.InputError):
        print("m6fi_add2_gate=ng", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
