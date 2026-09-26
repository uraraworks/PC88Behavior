#!/usr/bin/env python3
"""m6f-e 関門G4: manifest・54候補表・凍結SHAを相互照合する。"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import derive_m6fe  # noqa: E402
import predict_m6fe  # noqa: E402


class GateError(ValueError):
    pass


def _frozen(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise GateError("凍結表読取") from exc
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 2 or fields[0] in out:
            raise GateError("凍結表形式")
        out[fields[0]] = fields[1]
    if set(out) != {"manifest_sha256", "candidates_sha256"}:
        raise GateError("凍結表キー")
    return out


def verify(manifest_path: Path, candidates_path: Path, frozen_path: Path) -> None:
    values = _frozen(frozen_path)
    manifest_raw = manifest_path.read_bytes()
    candidates_raw = candidates_path.read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != values["manifest_sha256"]:
        raise GateError("manifest SHA")
    if hashlib.sha256(candidates_raw).hexdigest() != values["candidates_sha256"]:
        raise GateError("候補表 SHA")
    manifest = predict_m6fe._manifest(manifest_path)
    expected = predict_m6fe.render_candidates(manifest, predict_m6fe.LAYOUT_ARMS)
    if candidates_raw != expected:
        raise GateError("候補表再生成")
    # 欠落・重複・summary不整合は共通の厳格parserでも独立に検査する。
    parsed = derive_m6fe.load_candidates(candidates_path)
    if len(parsed) != 54 * len(predict_m6fe.LAYOUT_ARMS):
        raise GateError("候補組数")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--candidates", type=Path, default=HERE / "m6fe_candidates_frozen.tsv")
    ap.add_argument("--frozen", type=Path, default=HERE / "m6fe_frozen.tsv")
    args = ap.parse_args()
    try:
        verify(args.manifest, args.candidates, args.frozen)
        print("m6fe_candidates_gate=ok")
        return 0
    except (GateError, derive_m6fe.InputError, predict_m6fe.PredictionError, OSError):
        print("m6fe_candidates_gate=ng", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
