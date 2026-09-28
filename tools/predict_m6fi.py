#!/usr/bin/env python3
"""m6f-i 候補をメモリ内で行署名化する。本文は出力しない。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ARMS = ("I-1", "I-2", "I-3", "I-4", "E-1", "E-2")


class PredictionError(ValueError):
    pass


@dataclass(frozen=True)
class SignedLine:
    physical_row: int
    char_count: int
    sha256: str


def candidate_ids(arm: str) -> tuple[str, ...]:
    if arm == "I-1":
        return ("loads_lines",)
    if arm == "I-2":
        return ("replaces", "merges")
    if arm == "I-3":
        return ("sorted", "file_order")
    if arm == "I-4":
        return ("ok_only",)
    if arm == "E-1":
        return tuple(f"err_{n}" for n in range(256))
    if arm == "E-2":
        return tuple(f"err_{n}" for n in range(256)) + ("loads_without_error",)
    raise PredictionError("腕ID")


def _line(row: int, body: str) -> SignedLine:
    return SignedLine(row, len(body), hashlib.sha256(
        f"{row}\t{body}\n".encode("utf-8")).hexdigest())


def predict(arm: str, candidate: str) -> tuple[SignedLine, ...]:
    if candidate not in candidate_ids(arm):
        raise PredictionError("候補ID")
    if candidate == "loads_lines" or candidate == "replaces":
        bodies = ("10 PRINT 1", "20 PRINT 2")
    elif candidate == "merges":
        bodies = ("10 PRINT 9", "20 PRINT 2")
    elif candidate == "sorted":
        bodies = ("10 PRINT 1", "30 PRINT 3")
    elif candidate == "file_order":
        bodies = ("30 PRINT 3", "10 PRINT 1")
    elif candidate in ("ok_only", "loads_without_error"):
        bodies = ()
    else:
        # l4-basic.md §2: 正数と0のPRINTは先頭に空白を1つ置く。
        bodies = (" " + candidate[4:],)
    return tuple(_line(row, body) for row, body in enumerate(bodies))


def whole(lines: tuple[SignedLine, ...]) -> str:
    return hashlib.sha256("".join(
        f"{line.physical_row}\t{line.char_count}\t{line.sha256}\n"
        for line in lines).encode("ascii")).hexdigest()


def render_candidates() -> bytes:
    out = ["record\tarm\tcandidate_id\tphysical_row\tchar_count\tsha256"]
    for arm in ARMS:
        for candidate in candidate_ids(arm):
            lines = predict(arm, candidate)
            for line in lines:
                out.append(f"row\t{arm}\t{candidate}\t{line.physical_row}\t{line.char_count}\t{line.sha256}")
            out.append(f"summary\t{arm}\t{candidate}\t-\t{len(lines)}\t{whole(lines)}")
    return ("\n".join(out) + "\n").encode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    try:
        if args.output.exists():
            raise PredictionError("出力先")
        raw = render_candidates()
        args.output.write_bytes(raw)
        print("candidates_sha256=" + hashlib.sha256(raw).hexdigest())
        return 0
    except (OSError, PredictionError):
        print("predict_m6fi_error=PredictionError", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
