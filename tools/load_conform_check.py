#!/usr/bin/env python3
"""LOAD の固定署名と q88measure 署名reportを比較する。"""
import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import compare_screen_signatures as css
from extract_load_conform_expected import GROUPS

ARMS = tuple(arm for _, group in GROUPS for arm in group)
HEX = re.compile(r"[0-9a-f]{64}\Z")


def expected(path):
    lines = path.read_text(encoding="ascii").splitlines()
    if lines[:2] != ["# load-conform-expected-v1", "# kind\tarm\tphysical_row\tchar_count\tsha256"]:
        raise ValueError("見出し")
    data = {}
    active = None
    for line in lines[2:]:
        f = line.split("\t")
        if len(f) != 5:
            raise ValueError("列")
        kind, arm, row, count, digest = f
        if kind == "arm":
            if arm not in ARMS or arm in data or row != "-" or digest != "-":
                raise ValueError("腕")
            data[arm] = [int(count), [], None]
            active = arm
        elif kind in ("row", "load"):
            if arm != active or not HEX.fullmatch(digest):
                raise ValueError("署名")
            value = (int(row), int(count), digest)
            if kind == "row":
                if not 0 <= value[0] <= 18 or not 0 <= value[1] <= 80 or data[arm][2] is not None:
                    raise ValueError("行")
                data[arm][1].append(value)
            else:
                if data[arm][2] is not None or arm not in ("I-1", "I-2", "I-3", "E-3"):
                    raise ValueError("途中")
                data[arm][2] = value
        else:
            raise ValueError("種別")
    if tuple(data) != ARMS:
        raise ValueError("順序")
    for arm, (n, rows, load) in data.items():
        if n != len(rows) or rows != sorted(rows) or len({r[0] for r in rows}) != n:
            raise ValueError("行数")
        if (load is None) != (arm not in ("I-1", "I-2", "I-3", "E-3")):
            raise ValueError("途中有無")
    return data


def entries(sig):
    rows = [(r, x.char_count, x.sha256) for r, x in sorted(sig.lines.items()) if r != 19]
    return rows[:-1]


def summary(sig):
    return (sig.line_count, sig.char_count, sig.sha256)


def compare(data, arm, report):
    wanted, load_wanted = data[arm][1:]
    actuals = [entries(css.read_report(report, name)) for name in ("final", "late")]
    by_row = {r: (n, h) for r, n, h in wanted}
    rows = sorted(set(by_row).union(*({r for r, _, _ in actual} for actual in actuals)))
    bad = [r for r in rows if any({x: (n, h) for x, n, h in actual}.get(r) != by_row.get(r)
                                  for actual in actuals)]
    if load_wanted is not None:
        # 観測側の全画面署名には公式ROMのファンクションキー行が含まれる。
        # 自作ROMはその行を出さないため全画面ハッシュは比較不能。両時点の
        # 安定性と、仕様12.1節の2行（LOAD後のOkと通常の入力待ち）を検査する。
        first = css.read_report(report, "load")
        second = css.read_report(report, "load_late")
        first_rows = [v for r, v in sorted(first.lines.items()) if r != 19]
        if (summary(first) != summary(second) or len(first_rows) != 2 or
                first_rows[-1].char_count != 2):
            bad.append(25)
    if bad:
        print(f"NG\t{len(set(bad))}\t{min(bad)}")
        return 1
    print("OK\t0\t-")
    return 0


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="mode", required=True)
    v = sub.add_parser("validate"); v.add_argument("expected", type=pathlib.Path)
    c = sub.add_parser("compare"); c.add_argument("--expected", required=True, type=pathlib.Path)
    c.add_argument("--arm", required=True); c.add_argument("--report", required=True, type=pathlib.Path)
    a = p.parse_args()
    try:
        data = expected(a.expected)
        if a.mode == "validate":
            print("OK LOAD期待値形式")
            return 0
        if a.arm not in data:
            raise ValueError("未知の腕")
        return compare(data, a.arm, a.report)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, IndexError):
        print("NG 署名形式", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
