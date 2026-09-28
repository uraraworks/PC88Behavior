#!/usr/bin/env python3
"""公式ROMによる J-1 読戻しの LIST/FILES を行署名だけで検査する。"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import compare_screen_signatures as css


def signed(row: int, content: str) -> tuple[int, int, str]:
    return row, len(content), hashlib.sha256(f"{row}\t{content}\n".encode("utf-8")).hexdigest()


def rows(path: Path, snapshot: str) -> tuple[tuple[int, int, str], ...]:
    screen = css.read_report(path, snapshot)
    present = [(row, line.char_count, line.sha256)
               for row, line in sorted(screen.lines.items()) if row != 19]
    return tuple(present[:-1])  # 最後は入力待ち行。


def main() -> int:
    try:
        path = Path(sys.argv[1])
        list_expected = (signed(0, "10 PRINT 1"),)
        padded = "qsb".ljust(9)
        files_expected = (signed(0, padded[:6] + " " + padded[6:] + " 1"),)
        checks = (("LIST", "list", "list_late", list_expected),
                  ("FILES", "files", "files_late", files_expected))
        status = 0
        for label, first, late, expected in checks:
            good = rows(path, first) == rows(path, late) == expected
            print(f"{label}\t{'OK' if good else 'NG'}")
            status |= not good
        return status
    except (OSError, ValueError, IndexError, css.SignatureInputError):
        print("読戻し\tNG")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
