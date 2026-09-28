#!/usr/bin/env python3
"""m6f-i の観測から行署名だけを2走一致で固定する。"""
import argparse
import json
import pathlib
import re
import sys

GROUPS = (("m6fi-observations-v1", ("I-1", "I-2", "I-3", "E-1")),
          ("m6fi-add2-observations-v1", ("I-4'", "E-2'", "E-3", "E-3m")))
HEX = re.compile(r"[0-9a-f]{64}\Z")


def extract(path, fmt, arms):
    root = json.loads(path.read_text(encoding="ascii"))
    if root.get("format") != fmt or not set(arms).issubset(root.get("arms", {})):
        raise ValueError("形式または腕")
    result = {}
    for arm in arms:
        runs = root["arms"][arm]
        if len(runs) != 2:
            raise ValueError("走数")
        values = []
        for run in runs:
            rows = run["entry_lines"]
            parsed = []
            for item in rows:
                if set(item) != {"physical_row", "char_count", "sha256"}:
                    raise ValueError("行欄")
                row, count, digest = item["physical_row"], item["char_count"], item["sha256"]
                if (type(row) is not int or not 0 <= row <= 18 or
                    type(count) is not int or not 0 <= count <= 80 or
                    not isinstance(digest, str) or not HEX.fullmatch(digest)):
                    raise ValueError("行値")
                parsed.append((row, count, digest))
            if parsed != sorted(set(parsed)):
                raise ValueError("行順")
            load = run["load_screen"]
            if load is not None:
                if (set(load) != {"line_count", "char_count", "sha256"} or
                    type(load["line_count"]) is not int or
                    type(load["char_count"]) is not int or
                    not isinstance(load["sha256"], str) or not HEX.fullmatch(load["sha256"])):
                    raise ValueError("途中署名")
                load = (load["line_count"], load["char_count"], load["sha256"])
            values.append((tuple(parsed), load))
        if values[0] != values[1]:
            raise ValueError("2走不一致")
        result[arm] = values[0]
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("base", type=pathlib.Path)
    p.add_argument("add2", type=pathlib.Path)
    p.add_argument("output", type=pathlib.Path)
    a = p.parse_args()
    try:
        if a.output.exists():
            raise ValueError("出力先が存在")
        values = {}
        for path, (fmt, arms) in zip((a.base, a.add2), GROUPS):
            values.update(extract(path, fmt, arms))
        lines = ["# load-conform-expected-v1", "# kind\tarm\tphysical_row\tchar_count\tsha256"]
        for _, arms in GROUPS:
            for arm in arms:
                rows, load = values[arm]
                lines.append(f"arm\t{arm}\t-\t{len(rows)}\t-")
                lines.extend(f"row\t{arm}\t{r}\t{n}\t{h}" for r, n, h in rows)
                if load is not None:
                    lines.append(f"load\t{arm}\t{load[0]}\t{load[1]}\t{load[2]}")
        a.output.write_text("\n".join(lines) + "\n", encoding="ascii")
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"NG {type(exc).__name__}", file=sys.stderr)
        return 1
    print("OK 2走一致の署名を固定")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
