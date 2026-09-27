#!/usr/bin/env python3
"""m6f-g の観測JSONから FILES 適合試験用の行署名(G-P/G-B/G-M/G-Z1/G-Z2)を
既存の tools/files_conform_expected.tsv へ追記する。

既存の行(m6f-e由来の24腕)は一切書き換えない。抽出方式は
extract_files_conform_expected.py の load_one() をそのまま使う。
"""

from __future__ import annotations

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import extract_files_conform_expected as extract  # noqa: E402

HEADER = (
    "# files-conform-expected-v1",
    "# kind\\tarm\\texpectation\\tphysical_row\\tchar_count\\tsha256",
)


class AppendError(ValueError):
    pass


def fail(reason: str) -> None:
    raise AppendError(reason)


def append(observations: pathlib.Path, tsv: pathlib.Path) -> None:
    if not tsv.is_file():
        fail("tsv_missing")
    try:
        existing = tsv.read_text(encoding="ascii")
    except (OSError, UnicodeError):
        fail("tsv_read")
    lines = existing.splitlines()
    if tuple(lines[:2]) != HEADER:
        fail("tsv_header")
    if not existing.endswith("\n"):
        fail("tsv_no_trailing_newline")
    for arm in extract.G_ARMS:
        if any(line.startswith(f"arm\t{arm}\t") for line in lines):
            fail("tsv_already_has_g_arms")
    try:
        values = extract.load_g(observations)
    except extract.ExtractError as exc:
        fail(f"observations_{exc}")
        return
    extract.validate_g_relations(values)
    block_lines: list[str] = []
    for arm in extract.G_ARMS:
        block_lines.extend(extract.render_arm_block(arm, values[arm]))
    block = "\n".join(block_lines) + "\n"
    tsv.write_text(existing + block, encoding="ascii", newline="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations", type=pathlib.Path,
                         help="m6fg-observations-v1 形式のJSON(2走分、5腕)")
    parser.add_argument("tsv", type=pathlib.Path,
                         help="追記先のtools/files_conform_expected.tsv")
    args = parser.parse_args()
    try:
        append(args.observations, args.tsv)
    except AppendError as exc:
        print(f"NG {exc}", file=sys.stderr)
        return 1
    print("OK m6fg rows appended")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
