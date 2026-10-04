#!/usr/bin/env python3
"""RAM正典・ソースの整合検査。公式ROM・private/は使用しない。"""
import argparse
from collections import Counter
from itertools import combinations
from pathlib import Path
import re
import shutil
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools/asm"))
import memmap
import z80text

# 番地ではない値のみ。ファイル・命令全体・個数を固定し、新規の直書きは許さない。
ALLOW = {
    ("l3_main/main_sub_read.asm", "MAIN_SUB_TIMEOUT_LIMIT EQU 0FFFFh"): "待機回数65535",
    ("l3_main/vsync_regcheck.asm", "LD IY,0x99AA"): "レジスタ保持試験のデータ",
    ("l4_basic/interp.asm", "LD HL,0FFFFh"): "真値-1",
    ("l4_basic/run.asm", "LD HL,0FFFFh"): "真値-1",
    ("l4_basic/run.asm", "LD HL,0C752h"): "乱数の初期値（下位ワード）",
    ("l4_basic/run.asm", "LD HL,0804Fh"): "乱数の初期値（上位ワード）",
}
HEX = re.compile(r"\b0x[0-9a-f]+\b|\$[0-9a-f]+\b|\b[0-9][0-9a-f]*h\b", re.I)
SYMBOL = re.compile(r"\bMM_\w+\b")


def check_sources(src):
    errors, seen = [], Counter()
    symbols = set(memmap.addresses()) | {"MM_" + r.name + "_SIZE" for r in memmap.REGIONS}
    for path in sorted(src.rglob("*.asm")):
        rel = path.relative_to(src).as_posix()
        for no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = z80text.strip_comment(raw)
            # 文字列内の数字はオペランドではない。
            code = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'', "", code)
            for name in SYMBOL.findall(code):
                if name not in symbols:
                    errors.append(f"{rel}:{no}: 正典にない名前 {name}")
            equ = re.match(r"\s*(\w+)\s+EQU\s+(MM_\w+)\s*$", code, re.I)
            if equ:
                expected = memmap.ALIASES.get(equ[1], "MM_" + equ[1])
                if equ[2] != expected:
                    errors.append(f"{rel}:{no}: 正典と異なるEQU {equ[1]} -> {equ[2]}")
            literals = []
            for token in HEX.findall(code):
                value = int(token[2:], 16) if token.lower().startswith("0x") else int(
                    token[1:] if token.startswith("$") else token[:-1], 16)
                if 0x8000 <= value <= 0xFFFF:
                    literals.append(token)
            if not literals:
                continue
            key = (rel, " ".join(code.split()))
            if key in ALLOW:
                seen[key] += 1
            else:
                errors.append(f"{rel}:{no}: RAM番地の直書き {', '.join(literals)}")
    for key in ALLOW:
        if seen[key] != 1:
            errors.append(f"許可例外の個数が不一致: {key}: {seen[key]}")
    return errors


def check_map(regions=memmap.REGIONS):
    errors = []
    by_name = {r.name: r for r in regions}
    if len(by_name) != len(regions):
        errors.append("構造名が重複")
    for r in regions:
        if not (0x8000 <= r.base < r.base + r.size <= 0x10000):
            errors.append(f"範囲が不正: {r.name}")
        if not r.retention or not r.use or r.profile not in {
                "normal", "ext-test", "vsync-test", "measure"}:
            errors.append(f"注記が不正: {r.name}")
    actual = set()
    for a, b in combinations(regions, 2):
        if max(a.base, b.base) < min(a.base + a.size, b.base + b.size):
            pair = frozenset((a.name, b.name))
            actual.add(pair)
            if not memmap.OVERLAPS.get(pair):
                errors.append(f"未宣言の重なり: {a.name}/{b.name}")
    if actual != set(memmap.OVERLAPS):
        errors.append("重なり宣言に過不足がある")
    for name, (region, offset) in memmap.FIELDS.items():
        # スタック上端・捕捉終端は非包含端点。
        size = by_name[region].size
        if not (0 <= offset < size or
                (name in {"MM_STACK_TOP", "MM_CAPTURE_END"} and offset == size)):
            errors.append(f"構造外の名前: {name}")
    # EQU生成とPython側の番地を別の式評価器で突き合わせる。
    for line in memmap.asm_prelude().splitlines()[1:]:
        name, _, expression = line.split()
        if name in memmap.FIELDS and z80text.eval_expr(
                z80text.parse_expr(expression), {}, 0) != memmap.addresses()[name]:
            errors.append(f"生成EQUの不一致: {name}")
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=REPO / "src")
    args = ap.parse_args()
    errors = check_sources(args.src) + check_map()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    # 陰性対照は同じ検査関数に一時コピーを渡す。本体を変更しない。
    with tempfile.TemporaryDirectory(prefix="pc88-memmap-") as tmp:
        src = Path(tmp) / "src"
        for original in args.src.rglob("*.asm"):
            copy = src / original.relative_to(args.src)
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, copy)
        path = src / "l4_basic/program.asm"
        with path.open("a", encoding="utf-8") as out:
            out.write("\n    LD HL,0E883h ; 陰性対照\n")
        negative = check_sources(src)
        if len(negative) != 1 or "RAM番地の直書き" not in negative[0]:
            print("陰性対照: 直書きを検出できない", file=sys.stderr)
            return 1
    from dataclasses import replace
    moved = tuple(replace(r, base=next(region.base for region in memmap.REGIONS
                                     if region.name == "SINGLE"))
                  if r.name == "RND" else r for r in memmap.REGIONS)
    if not any("未宣言の重なり" in error for error in check_map(moved)):
        print("陰性対照: 重なりを検出できない", file=sys.stderr)
        return 1
    print("memmap_selftest: OK（直書き・EQU別名・範囲・生成EQU・陰性対照2種）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
