#!/usr/bin/env python3
"""追補2の候補画面をメモリ内で作り、行署名だけを出す。"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from predict_m6fi import SignedLine, _line, whole

HERE = Path(__file__).resolve().parent
ARMS = ("I-4'", "E-2'", "E-3", "E-3m")


class PredictionError(ValueError):
    pass


def messages(path: Path = HERE.parent / "src/l4_basic/errors.asm") -> dict[int, str]:
    source = path.read_text(encoding="utf-8")
    found = re.findall(r'^ERR_MSG_(\d+):\s*\n\s*DB "([^"\r\n]+)",0\s*$', source, re.M)
    result = {int(number): body for number, body in found}
    if len(result) != len(found) or not result:
        raise PredictionError("エラー表")
    return result


def candidate_ids(arm: str) -> tuple[str, ...]:
    if arm == "I-4'":
        return ("ok_line", "no_line")
    if arm == "E-3":
        return ("none_loaded", "upto_error", "all_numbered")
    if arm in ("E-2'", "E-3m"):
        tail = ("ok_line",) if arm == "E-3m" else ()
        return tuple(f"direct_msg_{n}" for n in sorted(messages())) + tail
    raise PredictionError("腕ID")


def predict(arm: str, candidate: str) -> tuple[SignedLine, ...]:
    if candidate not in candidate_ids(arm):
        raise PredictionError("候補ID")
    if candidate == "ok_line":
        bodies = ("Ok",)
    elif candidate in ("no_line", "none_loaded"):
        bodies = ()
    elif candidate == "upto_error":
        bodies = ("10 PRINT 1",)
    elif candidate == "all_numbered":
        bodies = ("10 PRINT 1", "30 PRINT 3")
    else:
        bodies = (messages()[int(candidate.removeprefix("direct_msg_"))],)
    return tuple(_line(row, body) for row, body in enumerate(bodies))


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
        print("predict_m6fi_add2_error=PredictionError", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
