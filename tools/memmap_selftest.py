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
import subprocess

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
    ("ext_bank/bank0.asm", "LD H,0xFF"): "LOGの負指数を16bitへ符号拡張",
}
HEX = re.compile(r"\b0x[0-9a-f]+\b|\$[0-9a-f]+\b|\b[0-9][0-9a-f]*h\b", re.I)
SYMBOL = re.compile(r"\bMM_\w+\b")

# 段Bで許可した仮置き領域は段D/Eで全廃。保存位置も固定域へ移設済み。
OLD_DYNAMIC = {"STRING_PAGES", "CAPTURE", "PROGRAM", "VARTAB", "ARRAY",
               "FOR_STACK", "GOSUB_STACK"}


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
                elif (0x80 <= value <= 0xFF and
                      re.match(r"\s*LD\s+[HD]\s*,", code, re.I)):
                    # INKEY旧キューのLD H,0E9hのような分割番地も禁止する。
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
                "normal", "ext-test", "vsync-test", "measure", "inkey-test"}:
            errors.append(f"注記が不正: {r.name}")
        if r.name in OLD_DYNAMIC:
            errors.append(f"動的構造の仮置きが残留: {r.name}")
        if r.name == "CPU_STACK":
            if not (0xE600 <= r.base and r.base + r.size == 0xF3C8):
                errors.append("CPUスタックがE600–F3C7外、または上端がF3C8でない")
            if r.size < 384:
                errors.append("CPUスタックの残りが384B未満")
        elif r.name == "TEXT":
            if (r.base, r.size) != (0xF3C8, 3000):
                errors.append("テキストVRAMの配置が変更された")
        elif not ((0xE600 <= r.base and r.base + r.size <= 0xF3C8) or
                  (0xFF80 <= r.base and r.base + r.size <= 0x10000)):
            errors.append(f"固定域が指定範囲外（利用者領域への残留を禁止）: {r.name}")
    # TEXT自身はハードウェアの予約領域。固定/動的/試験/スタックの全域を禁止する。
    for r in regions:
        if r.name != "TEXT" and max(r.base, 0xF3C8) < min(r.base + r.size, 0xFF80):
            errors.append(f"25行テキストVRAMへ領域が侵入: {r.name}")
    stack = by_name["CPU_STACK"]
    # 宣言したサイズだけでなく、固定域の上端から実際に残る連続長も検査する。
    fixed_end = max(r.base + r.size for r in regions
                    if r.name not in {"CPU_STACK", "TEXT"}
                    and r.base < 0xF3C8)
    if 0xF3C8 - max(fixed_end, stack.base) < 384:
        errors.append("固定域からCPUスタック上端までの残りが384B未満")
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
        # スタック上端だけは非包含端点。捕捉上端は実行時ポインタ。
        size = by_name[region].size
        if not (0 <= offset < size or
                (name in {"MM_STACK_TOP"} and offset == size)):
            errors.append(f"構造外の名前: {name}")
    # EQU生成とPython側の番地を別の式評価器で突き合わせる。
    for line in memmap.asm_prelude().splitlines()[1:]:
        name, _, expression = line.split()
        if name in memmap.FIELDS and z80text.eval_expr(
                z80text.parse_expr(expression), {}, 0) != memmap.addresses()[name]:
            errors.append(f"生成EQUの不一致: {name}")
    return errors


def check_value_stack():
    """本体の32回成功・33回目拒否・破損SP拒否・復元を実Z80で確かめる。"""
    source = (REPO / "src/l4_basic/interp.asm").read_text()
    routines = source[source.index("VAL_STACK_ADDR:\n"):
                      source.index("; VAL_LOAD_CUR_TO_OPA —")]
    core = next((REPO.parent / "vendor/quasi88-libretro").glob("quasi88_libretro.*"))
    harness = """
    ORG 0
    DI
    LD SP,MM_STACK_TOP
    XOR A
    LD (MM_VAL_SP),A
    LD (MM_ERROR_FLAG),A
    LD HL,MM_CUR_TYPE
    LD B,9
fill:
    LD (HL),0x5A
    INC HL
    DJNZ fill
    LD A,0xA5
    LD (MM_LIT_BUF),A
    LD B,32
push_loop:
    CALL VAL_PUSH
    JP C,fail
    DJNZ push_loop
    CALL VAL_PUSH
    JP NC,fail
    LD A,(MM_VAL_SP)
    CP 32
    JP NZ,fail
    LD A,(MM_ERROR_FLAG)
    CP 1
    JP NZ,fail
    LD A,(MM_ERROR_KIND)
    CP 7
    JP NZ,fail
    LD A,(MM_LIT_BUF)
    CP 0xA5
    JP NZ,fail
    LD HL,MM_INTERP_EXT_RAM_BASE
    LD BC,MM_VALUE_STACK_SIZE
verify:
    LD A,(HL)
    CP 0x5A
    JP NZ,fail
    INC HL
    DEC BC
    LD A,B
    OR C
    JR NZ,verify
    LD A,255
    LD (MM_VAL_SP),A
    CALL VAL_PUSH
    JP NC,fail
    LD A,(MM_VAL_SP)
    CP 255
    JP NZ,fail
    LD A,32
    LD (MM_VAL_SP),A
    LD B,32
pop_loop:
    CALL VAL_POP
    DJNZ pop_loop
    LD A,(MM_VAL_SP)
    OR A
    JP NZ,fail
    CALL VAL_MOVE_CUR_TO_RHS
    LD HL,MM_RHS_TYPE
    LD B,9
rhs_loop:
    LD A,(HL)
    CP 0x5A
    JP NZ,fail
    INC HL
    DJNZ rhs_loop
    LD A,1
    JR done
fail:
    XOR A
done:
    LD (MM_TEXT_BASE),A
stop:
    JR stop
VAL_SP EQU MM_VAL_SP
VAL_STACK EQU MM_INTERP_EXT_RAM_BASE
VAL_STACK_DEPTH EQU MM_VALUE_STACK_SIZE/9
CUR_TYPE EQU MM_CUR_TYPE
CUR_DATA EQU MM_CUR_DATA
RHS_TYPE EQU MM_RHS_TYPE
ERROR_FLAG EQU MM_ERROR_FLAG
ERROR_KIND EQU MM_ERROR_KIND
"""
    with tempfile.TemporaryDirectory(prefix="pc88-valstack-") as temp:
        root = Path(temp)
        for fault in (False, True):
            code = routines.replace("    CP VAL_STACK_DEPTH\n    JR NC,_vpush_oom\n", "") if fault else routines
            asm = root / "probe.asm"
            asm.write_text(memmap.asm_prelude() + harness + code)
            rom = z80text.Assembler().assemble(asm)
            (root / "N88.ROM").write_bytes(rom + bytes(0x8000 - len(rom)))
            (root / "DISK.ROM").write_bytes(bytes((0x18, 0xFE)) + bytes(0x7FE))
            log = root / "memlog.txt"
            addr = memmap.addresses()["MM_TEXT_BASE"]
            subprocess.run([str(REPO / "tools/harness/frontend/q88measure"),
                            "--core", str(core), "--rom-dir", str(root), "--frames", "8",
                            "--mem-write-log", str(log), "--mem-write-range", f"{addr:04X}-{addr:04X}"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL)
            rows = [line.split() for line in log.read_text().splitlines()]
            values = [row[-1] for row in rows if len(row) == 5 and row[-2] == f"{addr:04X}"]
            if values != ["00" if fault else "01"]:
                raise AssertionError(f"VAL_STACKの{'陰性対照' if fault else '正常系'}が不一致: {values}")


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
        with path.open("w", encoding="utf-8") as out:
            out.write("    LD H,0E9h ; 分割番地の陰性対照\n")
        negative = check_sources(src)
        if len(negative) != 1 or "RAM番地の直書き" not in negative[0]:
            print("陰性対照: 分割番地を検出できない", file=sys.stderr)
            return 1
    from dataclasses import replace
    moved = tuple(replace(r, base=next(region.base for region in memmap.REGIONS
                                     if region.name == "SINGLE"))
                  if r.name == "RND" else r for r in memmap.REGIONS)
    if not any("未宣言の重なり" in error for error in check_map(moved)):
        print("陰性対照: 重なりを検出できない", file=sys.stderr)
        return 1
    moved = tuple(replace(r, base=0xC000) if r.name == "SINGLE" else r
                  for r in memmap.REGIONS)
    if not any("固定域が指定範囲外" in error for error in check_map(moved)):
        print("陰性対照: 利用者領域の固定域を検出できない", file=sys.stderr)
        return 1
    moved = tuple(replace(r, base=0xFD28) if r.name == "RND" else r
                  for r in memmap.REGIONS)
    if not any("25行テキストVRAMへ領域が侵入" in error for error in check_map(moved)):
        print("陰性対照: VRAMへの侵入を検出できない", file=sys.stderr)
        return 1
    moved = tuple(replace(r, base=0xF3C8-383, size=383) if r.name == "CPU_STACK" else r
                  for r in memmap.REGIONS)
    if not any("CPUスタックの残りが384B未満" in error for error in check_map(moved)):
        print("陰性対照: 383Bのスタックを検出できない", file=sys.stderr)
        return 1
    moved = tuple(replace(r, base=0xF3C8-383) if r.name == "RND" else r
                  for r in memmap.REGIONS)
    if not any("固定域からCPUスタック上端までの残りが384B未満" in error for error in check_map(moved)):
        print("陰性対照: 固定域がスタックの残りを減らす配置を検出できない", file=sys.stderr)
        return 1
    for name in sorted(OLD_DYNAMIC):
        restored = memmap.REGIONS + (memmap.Region(name, 0xC400, 16, '保持', '旧仮置き陰性対照'),)
        if not any("動的構造の仮置きが残留" in e for e in check_map(restored)):
            raise AssertionError(f"仮置き再導入を検出できない: {name}")
    assert memmap.CONSTANTS["MM_USER_START"] == 0x8400
    assert memmap.CONSTANTS["MM_USER_LIMIT_DEFAULT"] == 0xE5FF
    assert set(memmap.DYNAMIC_STRUCTURES) == {"PROGRAM", "HEAP", "STRING_PAGES", "FOR_STACK", "GOSUB_STACK", "CAPTURE"}
    check_value_stack()
    print("memmap_selftest: OK（段D/E仮置き全廃・利用者領域に固定域なし・25行VRAM禁止・スタック400B/最低384B・分割番地・EQU・重なり・陰性対照7種＋旧仮置き7構造）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
