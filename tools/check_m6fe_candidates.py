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


def _frozen(path: Path, addendum3: bool = False) -> dict[str, str]:
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
    expected = ({"manifest_sha256", "print_candidates_sha256", "candidates_sha256"}
                if addendum3 else {"manifest_sha256", "candidates_sha256"})
    if set(out) != expected:
        raise GateError("凍結表キー")
    return out


def verify(manifest_path: Path, candidates_path: Path, frozen_path: Path,
           addendum2: bool = False, addendum3: bool = False,
           print_candidates_path: Path | None = None) -> None:
    values = _frozen(frozen_path, addendum3)
    manifest_raw = manifest_path.read_bytes()
    candidates_raw = candidates_path.read_bytes()
    if hashlib.sha256(manifest_raw).hexdigest() != values["manifest_sha256"]:
        raise GateError("manifest SHA")
    if hashlib.sha256(candidates_raw).hexdigest() != values["candidates_sha256"]:
        raise GateError("候補表 SHA")
    manifest = predict_m6fe._manifest(manifest_path, addendum2, addendum3)
    expected = (predict_m6fe.render_add3_candidates(manifest) if addendum3 else
                predict_m6fe.render_add2_candidates(manifest) if addendum2 else
                predict_m6fe.render_candidates(manifest, predict_m6fe.LAYOUT_ARMS))
    if candidates_raw != expected:
        raise GateError("候補表再生成")
    # 欠落・重複・summary不整合は共通の厳格parserでも独立に検査する。
    parsed = (derive_m6fe.load_add3_candidates(candidates_path) if addendum3 else
              derive_m6fe.load_add2_candidates(candidates_path) if addendum2 else
              derive_m6fe.load_candidates(candidates_path))
    expected_count = ((162 * len(predict_m6fe.ADD3_FILES_ARMS)) if addendum3 else
                      (162 * len(predict_m6fe.ADD2_ARMS)) if addendum2 else
                      (54 * len(predict_m6fe.LAYOUT_ARMS)))
    if len(parsed) != expected_count:
        raise GateError("候補組数")
    if addendum3:
        if print_candidates_path is None:
            raise GateError("PRINT予測表なし")
        print_raw = print_candidates_path.read_bytes()
        if hashlib.sha256(print_raw).hexdigest() != values["print_candidates_sha256"]:
            raise GateError("PRINT予測表 SHA")
        if print_raw != predict_m6fe.render_add3_print_candidates():
            raise GateError("PRINT予測表再生成")
        if len(derive_m6fe.load_add3_print_candidates(print_candidates_path)) != 6:
            raise GateError("PRINT予測組数")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--candidates", type=Path)
    ap.add_argument("--frozen", type=Path)
    ap.add_argument("--addendum2", action="store_true")
    ap.add_argument("--addendum3", action="store_true")
    ap.add_argument("--print-candidates", type=Path)
    args = ap.parse_args()
    try:
        if args.addendum2 and args.addendum3:
            raise GateError("追補モード重複")
        candidates = args.candidates or HERE / (
            "m6fe_add3_candidates_frozen.tsv" if args.addendum3 else
            "m6fe_add2_candidates_frozen.tsv" if args.addendum2 else "m6fe_candidates_frozen.tsv")
        frozen = args.frozen or HERE / (
            "m6fe_add3_frozen.tsv" if args.addendum3 else
            "m6fe_add2_frozen.tsv" if args.addendum2 else "m6fe_frozen.tsv")
        print_candidates = args.print_candidates or (HERE / "m6fe_add3_print_frozen.tsv")
        verify(args.manifest, candidates, frozen, args.addendum2, args.addendum3,
               print_candidates if args.addendum3 else None)
        print("m6fe_candidates_gate=ok")
        return 0
    except (GateError, derive_m6fe.InputError, predict_m6fe.PredictionError, OSError):
        print("m6fe_candidates_gate=ng", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
