#!/usr/bin/env python3
"""行別画面署名を比較し、本文なしの固定フィールドだけを返す。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,63}")
SHA_RE = re.compile(r"[0-9a-f]{64}")


class SignatureInputError(ValueError):
    """署名reportの形式が不正。入力値は例外文へ含めない。"""


@dataclass(frozen=True)
class LineSignature:
    char_count: int
    sha256: str


@dataclass(frozen=True)
class ScreenSignature:
    lines: dict[int, LineSignature]
    line_count: int
    char_count: int
    sha256: str


def _uint(value: str, *, maximum: int | None = None) -> int:
    if not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise SignatureInputError("整数形式")
    result = int(value)
    if maximum is not None and result > maximum:
        raise SignatureInputError("整数範囲")
    return result


def read_report(path: Path, snapshot_id: str) -> ScreenSignature:
    if not ID_RE.fullmatch(snapshot_id):
        raise SignatureInputError("snapshot_id形式")
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError) as exc:
        raise SignatureInputError("読取失敗") from exc
    found: ScreenSignature | None = None
    seen_ids: set[str] = set()
    index = 0
    while index < len(raw_lines):
        fields = raw_lines[index].split("\t")
        if len(fields) != 2 or fields[0] != "snapshot_id" or not ID_RE.fullmatch(fields[1]):
            raise SignatureInputError("snapshot_id行")
        record_id = fields[1]
        if record_id in seen_ids:
            raise SignatureInputError("snapshot_id重複")
        seen_ids.add(record_id)
        index += 1
        if index >= len(raw_lines) or raw_lines[index] != "physical_row\tchar_count\tsha256":
            raise SignatureInputError("列許可リスト")
        index += 1
        lines: dict[int, LineSignature] = {}
        previous_row = -1
        while index < len(raw_lines) and not raw_lines[index].startswith("line_count\t"):
            fields = raw_lines[index].split("\t")
            if len(fields) != 3 or not SHA_RE.fullmatch(fields[2]):
                raise SignatureInputError("行署名形式")
            row = _uint(fields[0], maximum=24)
            chars = _uint(fields[1], maximum=80)
            if row <= previous_row:
                raise SignatureInputError("行順序")
            lines[row] = LineSignature(chars, fields[2])
            previous_row = row
            index += 1
        if index + 2 >= len(raw_lines):
            raise SignatureInputError("summary欠落")
        count_fields = raw_lines[index].split("\t")
        chars_fields = raw_lines[index + 1].split("\t")
        sha_fields = raw_lines[index + 2].split("\t")
        if (len(count_fields) != 2 or count_fields[0] != "line_count"
                or len(chars_fields) != 2 or chars_fields[0] != "char_count"
                or len(sha_fields) != 2 or sha_fields[0] != "sha256"
                or not SHA_RE.fullmatch(sha_fields[1])):
            raise SignatureInputError("summary形式")
        line_count = _uint(count_fields[1], maximum=25)
        char_count = _uint(chars_fields[1], maximum=2000)
        if line_count != len(lines) or char_count != sum(v.char_count for v in lines.values()):
            raise SignatureInputError("summary整合性")
        value = ScreenSignature(lines, line_count, char_count, sha_fields[1])
        if record_id == snapshot_id:
            found = value
        index += 3
    if found is None:
        raise SignatureInputError("snapshot欠落")
    return found


def compare(actual: ScreenSignature, expected: ScreenSignature) -> dict[str, object]:
    rows = sorted(actual.lines.keys() | expected.lines.keys())
    mismatches = [row for row in rows if actual.lines.get(row) != expected.lines.get(row)]
    common = actual.lines.keys() & expected.lines.keys()
    char_count_difference = (
        actual.char_count != expected.char_count
        or any(actual.lines[row].char_count != expected.lines[row].char_count for row in common)
    )
    matches = (
        not mismatches
        and actual.line_count == expected.line_count
        and actual.char_count == expected.char_count
        and actual.sha256 == expected.sha256
    )
    return {
        "match": matches,
        "mismatch_line_count": len(mismatches),
        "first_mismatch_physical_row": mismatches[0] if mismatches else None,
        "char_count_difference": char_count_difference,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual", required=True, type=Path)
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--snapshot-id", required=True)
    args = parser.parse_args()
    try:
        result = compare(
            read_report(args.actual, args.snapshot_id),
            read_report(args.expected, args.snapshot_id),
        )
    except SignatureInputError:
        print("screen_signature_error=SignatureInputError", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return 0 if result["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
