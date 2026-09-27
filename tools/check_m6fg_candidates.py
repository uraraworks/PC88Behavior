#!/usr/bin/env python3
"""m6f-g の manifest・候補表・予測器ソースを凍結SHAと照合する。"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import derive_m6fg as derive  # noqa: E402
import predict_m6fg as predict  # noqa: E402


class GateError(ValueError):
    pass


def frozen_values(path: Path) -> dict[str, str]:
    try:
        rows = [line.split("\t") for line in path.read_text(encoding="ascii").splitlines()]
    except (OSError, UnicodeError) as exc:
        raise GateError("凍結表読取") from exc
    if any(len(row) != 2 for row in rows):
        raise GateError("凍結表形式")
    values = dict(rows)
    if len(values) != len(rows) or set(values) != {
            "manifest_sha256", "candidates_sha256", "predictor_sha256"}:
        raise GateError("凍結表キー")
    return values


def verify(manifest_path: Path, candidates_path: Path,
           frozen_path: Path, predictor_path: Path) -> None:
    values = frozen_values(frozen_path)
    manifest_raw = manifest_path.read_bytes()
    candidates_raw = candidates_path.read_bytes()
    predictor_raw = predictor_path.read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != values["manifest_sha256"]:
        raise GateError("manifest SHA")
    if hashlib.sha256(candidates_raw).hexdigest() != values["candidates_sha256"]:
        raise GateError("候補表 SHA")
    if hashlib.sha256(predictor_raw).hexdigest() != values["predictor_sha256"]:
        raise GateError("予測器 SHA")
    manifest = predict._manifest(manifest_path)
    if candidates_raw != predict.render_candidates(manifest):
        raise GateError("候補表再生成")
    parsed = derive.load_candidates(candidates_path)
    expected = len(predict.mark_candidate_ids()) * 2 + 2
    if len(parsed) != expected:
        raise GateError("候補組数")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--candidates", type=Path,
                        default=HERE / "m6fg_candidates_frozen.tsv")
    parser.add_argument("--frozen", type=Path, default=HERE / "m6fg_frozen.tsv")
    parser.add_argument("--predictor", type=Path, default=HERE / "predict_m6fg.py")
    args = parser.parse_args()
    try:
        verify(args.manifest, args.candidates, args.frozen, args.predictor)
        print("m6fg_candidates_gate=ok")
        return 0
    except (OSError, GateError, derive.InputError, predict.PredictionError):
        print("m6fg_candidates_gate=ng", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
