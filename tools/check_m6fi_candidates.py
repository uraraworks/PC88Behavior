#!/usr/bin/env python3
"""m6f-i のmanifest・全候補署名・予測器を凍結表へ照合する。"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import derive_m6fi as derive
import predict_m6fi as predict

HERE = Path(__file__).resolve().parent


def verify(manifest: Path, candidates: Path, frozen: Path, predictor: Path) -> None:
    rows = [line.split("\t") for line in frozen.read_text(encoding="ascii").splitlines()]
    values = dict(rows)
    if any(len(row) != 2 for row in rows) or len(rows) != 3 or set(values) != {
            "manifest_sha256", "candidates_sha256", "predictor_sha256"}:
        raise ValueError("凍結表")
    for key, path in (("manifest_sha256", manifest), ("candidates_sha256", candidates),
                      ("predictor_sha256", predictor)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != values[key]:
            raise ValueError("凍結SHA")
    if candidates.read_bytes() != predict.render_candidates():
        raise ValueError("候補再生成")
    doc = __import__("json").loads(manifest.read_bytes())
    if (doc.get("format") != "m6fi-scenario-v1" or
            [arm.get("id") for arm in doc["arms"]] != list(predict.ARMS)):
        raise ValueError("manifest")
    expected = sum(len(predict.candidate_ids(arm)) for arm in predict.ARMS)
    if len(derive.load_candidates(candidates)) != expected:
        raise ValueError("候補数")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--candidates", type=Path, default=HERE / "m6fi_candidates_frozen.tsv")
    ap.add_argument("--frozen", type=Path, default=HERE / "m6fi_frozen.tsv")
    ap.add_argument("--predictor", type=Path, default=HERE / "predict_m6fi.py")
    args = ap.parse_args()
    try:
        verify(args.manifest, args.candidates, args.frozen, args.predictor)
        print("m6fi_candidates_gate=ok")
        return 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, derive.InputError):
        print("m6fi_candidates_gate=ng", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
