#!/usr/bin/env python3
"""FILES 適合試験の期待値TSVを検査し、署名reportを腕単位で比較する。"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare_screen_signatures as css  # noqa: E402
from extract_files_conform_expected import (  # noqa: E402
    ADD2_ARMS, ADD3_ARMS, BASE_ARMS, EXPECTATIONS, SHA256_RE,
)

ALL_ARMS = BASE_ARMS + ADD2_ARMS + ADD3_ARMS
EXPECTATION_RE = re.compile(r"(?:media|drive|drive_expr|error|wait_then):[A-Za-z0-9]+\Z")


class CheckError(ValueError):
    pass


def load_expected(path: pathlib.Path) -> dict[str, tuple[tuple[int, int, str], ...]]:
    try:
        raw = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError):
        raise CheckError("expected_read") from None
    if raw[:2] != [
        "# files-conform-expected-v1",
        "# kind\\tarm\\texpectation\\tphysical_row\\tchar_count\\tsha256",
    ]:
        raise CheckError("expected_header")
    result: dict[str, list[tuple[int, int, str]]] = {}
    declared_count: dict[str, int] = {}
    current = None
    for line in raw[2:]:
        fields = line.split("\t")
        if len(fields) != 6:
            raise CheckError("expected_columns")
        kind, arm, expectation, row_text, count_text, digest = fields
        if kind == "arm":
            if arm not in ALL_ARMS or arm in result or expectation != EXPECTATIONS[arm]:
                raise CheckError("expected_arm")
            if not EXPECTATION_RE.fullmatch(expectation) or row_text != "-" or digest != "-":
                raise CheckError("expected_arm_fields")
            try:
                count = int(count_text)
            except ValueError:
                raise CheckError("expected_arm_count") from None
            if count < 0 or count > 19:
                raise CheckError("expected_arm_count")
            result[arm] = []
            declared_count[arm] = count
            current = arm
        elif kind == "row":
            if arm != current or expectation != "-":
                raise CheckError("expected_row_arm")
            try:
                row, count = int(row_text), int(count_text)
            except ValueError:
                raise CheckError("expected_row_number") from None
            if (row < 0 or row > 18 or count < 0 or count > 80
                    or SHA256_RE.fullmatch(digest) is None
                    or any(item[0] == row for item in result[arm])):
                raise CheckError("expected_row_value")
            result[arm].append((row, count, digest))
        else:
            raise CheckError("expected_kind")
    if tuple(result) != ALL_ARMS:
        raise CheckError("expected_arm_order")
    for arm, rows in result.items():
        if len(rows) != declared_count[arm] or rows != sorted(rows):
            raise CheckError("expected_row_count")
    return {arm: tuple(rows) for arm, rows in result.items()}


def entry_lines(signature: css.ScreenSignature) -> tuple[tuple[int, int, str], ...]:
    rows = [(row, item.char_count, item.sha256)
            for row, item in sorted(signature.lines.items()) if row != 19]
    if not rows:
        return ()
    prompt_row = rows[-1][0]
    return tuple(item for item in rows if item[0] != prompt_row)


def mismatch(expected: tuple[tuple[int, int, str], ...],
             actuals: tuple[tuple[tuple[int, int, str], ...], ...]) -> tuple[int, int | None]:
    expected_by_row = {item[0]: item[1:] for item in expected}
    actual_maps = [{item[0]: item[1:] for item in actual} for actual in actuals]
    rows = sorted(set(expected_by_row).union(*(set(value) for value in actual_maps)))
    bad = [row for row in rows
           if any(value.get(row) != expected_by_row.get(row) for value in actual_maps)]
    return len(bad), bad[0] if bad else None


def compare(path: pathlib.Path, expected_path: pathlib.Path, arm: str) -> int:
    expected = load_expected(expected_path)
    if arm not in expected:
        raise CheckError("unknown_arm")
    try:
        final = entry_lines(css.read_report(path, "final"))
        late = entry_lines(css.read_report(path, "late"))
    except Exception:
        raise CheckError("report_read") from None
    count, first = mismatch(expected[arm], (final, late))
    if count == 0:
        print("OK\t0\t-")
        return 0
    print(f"NG\t{count}\t{first}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("expected", type=pathlib.Path)
    comp = sub.add_parser("compare")
    comp.add_argument("--expected", required=True, type=pathlib.Path)
    comp.add_argument("--arm", required=True)
    comp.add_argument("--report", required=True, type=pathlib.Path)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            load_expected(args.expected)
            print("OK files_conform_expected valid")
            return 0
        return compare(args.report, args.expected, args.arm)
    except CheckError as exc:
        print(f"NG {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
