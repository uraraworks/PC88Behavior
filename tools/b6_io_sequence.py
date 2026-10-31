#!/usr/bin/env python3
"""B6 の入出力列を値と PC を除いて要約・比較する。位置は 0 始まり。"""
import argparse
from collections import Counter
import re
import sys

N = r"[0-9]+"
KEY = r"(?:IN|OUT) [0-9A-F]{4} (?:lo|hi)"
PORT = re.compile(rf"port ({KEY}) ({N})")
SUMMARY = [re.compile(p) for p in (
    r"# 識別子: G1", r"# 走: [A-Za-z0-9][A-Za-z0-9_-]*",
    r"# 開始: (?:boot-sector|first-hi)", rf"(?:events|dropped|runs): {N}",
    rf"port {KEY} {N}")]
COMPARE = [re.compile(p) for p in (
    r"result: (?:same|self-ends-first|official-ends-first|diverged)",
    rf"position: {N}",
    rf"context (?:official|self) (?:-[1-8]|\+?[0-8]) {KEY} {N}")]
ROW = re.compile(r"\s*\d+\s+\d+\s+main\s+(IN|OUT)\s+([0-9A-Fa-f]{4})\s+\S+\s+([0-9A-Fa-f]{4})\s*")
END = re.compile(r"\s*#\s*取りこぼし:\s*(\d+)件\s*/\s*総イベント数:\s*(\d+)件\s*")


def checked(lines, patterns):
    bad = sum(not any(p.fullmatch(line) for p in patterns) for line in lines)
    if bad:
        print(bad, file=sys.stderr)
        return False
    return True


def parse_log(lines):
    active = False
    found = False
    ended = False
    rows = []
    totals = None
    for line in lines:
        line = line.rstrip("\r\n")
        if line.strip() == "# main":
            if found:
                raise ValueError
            active = found = True
            continue
        if active and line.strip() == "# sub":
            ended = True
            break
        if not active:
            continue
        m = END.fullmatch(line)
        if m:
            if totals is not None:
                raise ValueError
            totals = tuple(map(int, m.groups()))
        elif not line.strip() or line.lstrip().startswith("#"):
            continue
        else:
            m = ROW.fullmatch(line)
            if not m:
                raise ValueError
            direction, port, pc = m.groups()
            rows.append((direction, port.upper(), int(pc, 16)))
    if not found or not ended or totals is None:
        raise ValueError
    start = next((i for i, row in enumerate(rows) if 0xC000 <= row[2] <= 0xC0FF), None)
    mode = "boot-sector"
    if start is None:
        start = next((i for i, row in enumerate(rows) if row[2] >= 0x8000), None)
        mode = "first-hi"
    if start is None:
        raise ValueError
    runs = []
    for direction, port, pc in rows[start:]:
        key = (direction, port, "hi" if pc >= 0x8000 else "lo")
        if runs and runs[-1][0] == key:
            runs[-1] = (key, runs[-1][1] + 1)
        else:
            runs.append((key, 1))
    return mode, totals, runs


def seq_lines(runs):
    return [f"port {' '.join(key)} {count}" for key, count in runs]


def summary(mode, totals, runs, name):
    dropped, events = totals
    counts = Counter()
    for key, count in runs:
        counts[key] += count
    return (["# 識別子: G1", f"# 走: {name}", f"# 開始: {mode}",
             f"events: {events}", f"dropped: {dropped}", f"runs: {len(runs)}"]
            + seq_lines(sorted(counts.items())))


def read_sequence(lines):
    result = []
    for line in lines:
        m = PORT.fullmatch(line.rstrip("\r\n"))
        if not m or int(m.group(2)) < 1:
            raise ValueError
        result.append((tuple(m.group(1).split()), int(m.group(2))))
    return result


def compare(a, b):
    k = 0
    while k < min(len(a), len(b)) and a[k][0] == b[k][0]:
        k += 1
    if k == len(a) == len(b):
        result = "same"
    elif k == len(b):
        result = "self-ends-first"
    elif k == len(a):
        result = "official-ends-first"
    else:
        result = "diverged"
    out = [f"result: {result}", f"position: {k}"]
    for name, runs in (("official", a), ("self", b)):
        for i in range(max(0, k - 8), min(len(runs), k + 9)):
            key, count = runs[i]
            out.append(f"context {name} {i-k:+d} {' '.join(key)} {count}")
    return out


def write(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def selftest():
    raw = ["# main", "0 0 main IN 0010 A5 C123", "1 0 main IN 0020 A5 C001",
           "2 0 main IN 0020 A5 C002", "3 0 main OUT 0030 -- 1234",
           "# 取りこぼし: 2件 / 総イベント数: 4件", "# sub"]
    mode, totals, runs = parse_log(raw)
    assert mode == "boot-sector" and totals == (2, 4) and [x[1] for x in runs] == [2, 1]
    mode2, _, _ = parse_log([s.replace("C001", "9001").replace("C002", "9002") for s in raw])
    assert mode2 == "first-hi"
    lines = summary(mode, totals, runs, "self-1") + seq_lines(runs) + compare(runs, runs)
    assert all("A5" not in s and "C001" not in s and "C002" not in s for s in lines)
    assert checked(summary(mode, totals, runs, "self-1"), SUMMARY)
    assert checked(seq_lines(runs), [PORT])
    assert read_sequence(seq_lines(runs)) == runs
    assert [compare(a, b)[0] for a, b in ((runs, runs), (runs, runs[:1]), (runs[:1], runs), (runs, runs[::-1]))] == [
        "result: same", "result: self-ends-first", "result: official-ends-first", "result: diverged"]
    long = [(("IN", f"{i:04X}", "hi"), 1) for i in range(20)]
    out = compare(long, long[:10] + [(("OUT", "0000", "hi"), 1)])
    assert "context official -8 IN 0002 hi 1" in out and "context official +8 IN 0012 hi 1" in out
    assert len([s for s in out if s.startswith("context official")]) == 17
    assert checked(out, COMPARE)
    import contextlib
    import io
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        assert not checked([seq_lines(runs)[0] + " A5"], [PORT])
    assert err.getvalue() == "1\n"
    print("OK: B6 自己検査")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="command")
    s = sub.add_parser("summarize")
    s.add_argument("input")
    s.add_argument("--name", required=True)
    s.add_argument("--id", required=True, choices=["G1"])
    s.add_argument("--out", required=True)
    s.add_argument("--seq-out", required=True)
    c = sub.add_parser("compare")
    c.add_argument("official")
    c.add_argument("self_sequence")
    c.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.selftest and args.command is None:
        selftest()
        return 0
    if args.command == "summarize":
        with open(args.input, encoding="utf-8", errors="replace") as f:
            mode, totals, runs = parse_log(f)
        a, b = summary(mode, totals, runs, args.name), seq_lines(runs)
        valid_summary = checked(a, SUMMARY)
        valid_sequence = checked(b, [PORT])
        if not valid_summary or not valid_sequence:
            return 1
        write(args.out, a)
        write(args.seq_out, b)
    elif args.command == "compare":
        with open(args.official, encoding="utf-8", errors="replace") as f:
            a = read_sequence(f)
        with open(args.self_sequence, encoding="utf-8", errors="replace") as f:
            b = read_sequence(f)
        out = compare(a, b)
        if not checked(out, COMPARE):
            return 1
        write(args.out, out)
    else:
        parser.print_usage(sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, UnicodeError):
        print("入力または出力を処理できません", file=sys.stderr)
        sys.exit(1)
