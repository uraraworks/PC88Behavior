#!/usr/bin/env python3
"""q88measure のテキスト画面を、本文を表示せず署名・比較する。

比較対象は ``--out`` の「測定終了時のテキスト画面」節が出力した行番号と
行本文そのもの。行本文の strip、大小文字変換、空白圧縮は行わない。
ハッシュ入力は各行を ``行番号<TAB>本文<LF>`` とした UTF-8 バイト列である。

終了コードは一致0、不一致1、入力・期待値不備2。標準出力にはハッシュ、
行数、文字数と位置・分類だけを出し、画面本文は出さない。
"""
from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


SCREEN_HEADER = "[測定終了時のテキスト画面]"
ROW_RE = re.compile(r"^\s*(\d+)\| ?(.*)$")


class ScreenError(ValueError):
    """画面節または期待値が不正。"""


@dataclass(frozen=True)
class Signature:
    line_count: int
    char_count: int
    sha256: str


def read_screen(path: Path) -> list[tuple[int, str]]:
    """画面節を読み、物理行番号と未正規化の本文を返す。"""
    text = path.read_text(encoding="utf-8", errors="strict")
    lines = text.splitlines()
    try:
        start = lines.index(SCREEN_HEADER) + 1
    except ValueError as exc:
        raise ScreenError("画面節の見出しが無い") from exc

    rows: list[tuple[int, str]] = []
    for line in lines[start:]:
        if not line.strip():
            break
        match = ROW_RE.match(line)
        if not match:
            raise ScreenError("画面節に行形式でない行がある")
        row = int(match.group(1))
        if not 0 <= row < 25:
            raise ScreenError("画面の物理行番号が範囲外")
        if rows and row <= rows[-1][0]:
            raise ScreenError("画面の物理行番号が昇順でない、または重複している")
        rows.append((row, match.group(2)))
    return rows


def signature(rows: list[tuple[int, str]]) -> Signature:
    canonical = "".join(f"{row}\t{body}\n" for row, body in rows).encode("utf-8")
    return Signature(
        line_count=len(rows),
        char_count=sum(len(body) for _, body in rows),
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


def read_expected(path: Path, scenario: str) -> Signature:
    found: Signature | None = None
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 4:
            raise ScreenError(f"期待値TSVの{line_no}行目が4列でない")
        name, line_count, char_count, sha256 = fields
        if name != scenario:
            continue
        if found is not None:
            raise ScreenError("同じシナリオの期待値が複数ある")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ScreenError("期待SHA-256の形式が不正")
        try:
            found = Signature(int(line_count), int(char_count), sha256)
        except ValueError as exc:
            raise ScreenError("期待行数または文字数が整数でない") from exc
    if found is None:
        raise ScreenError("指定シナリオの期待値が無い")
    return found


def print_signature(prefix: str, value: Signature) -> None:
    print(f"{prefix}line_count={value.line_count}")
    print(f"{prefix}char_count={value.char_count}")
    print(f"{prefix}sha256={value.sha256}")


def compare_rows(
    reference: list[tuple[int, str]], target: list[tuple[int, str]]
) -> bool:
    """本文を出さず、差の位置と分類を出す。"""
    ref_by_row = dict(reference)
    target_by_row = dict(target)
    ref_only = sorted(ref_by_row.keys() - target_by_row.keys())
    target_only = sorted(target_by_row.keys() - ref_by_row.keys())
    content_rows: list[int] = []
    changed_chars = 0
    first_row: int | None = None
    first_column: int | None = None

    for row in sorted(ref_by_row.keys() & target_by_row.keys()):
        ref_body = ref_by_row[row]
        target_body = target_by_row[row]
        if ref_body == target_body:
            continue
        content_rows.append(row)
        limit = max(len(ref_body), len(target_body))
        differing = [
            column
            for column in range(limit)
            if (ref_body[column] if column < len(ref_body) else None)
            != (target_body[column] if column < len(target_body) else None)
        ]
        changed_chars += len(differing)
        if first_row is None:
            first_row = row
            first_column = differing[0]

    if not ref_only and not target_only and not content_rows:
        print("screen_compare=match")
        return True

    print("screen_compare=mismatch")
    print(f"reference_only_line_count={len(ref_only)}")
    print(f"target_only_line_count={len(target_only)}")
    print(f"content_mismatch_line_count={len(content_rows)}")
    print(f"content_mismatch_char_count={changed_chars}")
    if ref_only:
        print(f"first_reference_only_row={ref_only[0]}")
    if target_only:
        print(f"first_target_only_row={target_only[0]}")
    if first_row is not None:
        print(f"first_content_mismatch_row={first_row}")
        print(f"first_content_mismatch_column={first_column}")
        ref_len = len(ref_by_row[first_row])
        target_len = len(target_by_row[first_row])
        kind = "same_length_replacement" if ref_len == target_len else "length_difference"
        print(f"first_content_mismatch_kind={kind}")
        print(f"first_reference_line_chars={ref_len}")
        print(f"first_target_line_chars={target_len}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--compare-report", type=Path)
    group.add_argument("--expected", type=Path)
    parser.add_argument("--scenario")
    args = parser.parse_args()

    if bool(args.expected) != bool(args.scenario):
        parser.error("--expected と --scenario は同時に指定する")

    try:
        rows = read_screen(args.report)
        actual = signature(rows)
        if args.compare_report:
            target_rows = read_screen(args.compare_report)
            target = signature(target_rows)
            print_signature("reference_", actual)
            print_signature("target_", target)
            return 0 if compare_rows(rows, target_rows) else 1
        print_signature("", actual)
        if args.expected:
            expected = read_expected(args.expected, args.scenario)
            if actual == expected:
                print("screen_expectation=match")
                return 0
            print("screen_expectation=mismatch")
            print(f"expected_line_count={expected.line_count}")
            print(f"expected_char_count={expected.char_count}")
            print(f"expected_sha256={expected.sha256}")
            return 1
        return 0
    except (OSError, UnicodeError, ScreenError) as exc:
        print(f"screen_error={type(exc).__name__}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
