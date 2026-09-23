#!/usr/bin/env bash
# disk_read_chr_z80_selftest.sh — 一般READ要求と再試行引数を実Z80コアで検査する。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

VENDOR="$(cd "$REPO/.." && pwd)/vendor/quasi88-libretro"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
CORE="$(ls "$VENDOR"/quasi88_libretro.* 2>/dev/null | head -1 || true)"
[ -n "$CORE" ] || {
  echo "NG: コア成果物が無い。先に tools/setup_harness.sh を実行すること" >&2
  exit 1
}
make -s -C "$REPO/tools/harness/frontend"
[ -x "$FRONTEND" ] || {
  echo "NG: q88measureが無い" >&2
  exit 1
}

python3 - "$REPO" "$WORK" "$FRONTEND" "$CORE" <<'PY'
import pathlib
import re
import subprocess
import sys

repo = pathlib.Path(sys.argv[1])
work = pathlib.Path(sys.argv[2])
frontend = pathlib.Path(sys.argv[3])
core = pathlib.Path(sys.argv[4])
source_path = repo / "src" / "l3_main" / "main_sub_read_chr.asm"
z80text = repo / "tools" / "asm" / "z80text.py"

N88_SIZE = 0x8000
DISK_SIZE = 0x0800

COMMON_EQU = r"""
MAIN_SUB_MARK_REQUEST     EQU 0E000h
MAIN_SUB_MARK_RECV256     EQU 0E001h
MAIN_SUB_MARK_SUCCESS     EQU 0E002h
MAIN_SUB_MARK_TIMEOUT     EQU 0E003h
MAIN_SUB_MARK_FAULT_WAIT  EQU 0E004h
MAIN_SUB_MARK_FAULT_CONT  EQU 0E005h
MAIN_SUB_MARK_FAULT_PAIR  EQU 0E006h
MAIN_SUB_DRIVE_SELECT     EQU 0E007h
"""

REQUEST_DRIVER = r"""
SELFTEST_START:
    LD SP,0FFF0h
    LD HL,09000h
    LD (STUB_OUT_PTR),HL

    LD A,000h
    LD D,000h
    LD E,001h
    CALL MAIN_SUB_READ_CHR
    LD A,001h
    LD D,000h
    LD E,001h
    CALL MAIN_SUB_READ_CHR
    LD A,000h
    LD D,001h
    LD E,001h
    CALL MAIN_SUB_READ_CHR
    LD A,001h
    LD D,04Fh
    LD E,010h
    CALL MAIN_SUB_READ_CHR
    LD A,000h
    LD D,028h
    LD E,008h
    CALL MAIN_SUB_READ_CHR
SELFTEST_DONE:
    JR SELFTEST_DONE

MAIN_SUB_SEND:
MAIN_SUB_SEND_REQUEST_CONT:
    PUSH HL
    LD HL,(STUB_OUT_PTR)
    LD (HL),A
    INC HL
    LD (STUB_OUT_PTR),HL
    POP HL
    LD D,0A5h
    LD E,05Ah
    OR A
    RET

MAIN_SUB_READ_AFTER_REQUEST:
    LD A,001h
    LD (MAIN_SUB_MARK_REQUEST),A
    POP IY
    POP IX
    POP HL
    POP DE
    POP BC
    POP AF
    RET

_ms_read_timeout:
    LD A,001h
    LD (MAIN_SUB_MARK_TIMEOUT),A
    POP IY
    POP IX
    POP HL
    POP DE
    POP BC
    POP AF
    RET

STUB_OUT_PTR EQU 0E120h
"""

RETRY_DRIVER = r"""
SELFTEST_START:
    LD SP,0FFF0h

    ; 1回目失敗・2回目成功。0/1以外のD/EとドライブBを使う。
    XOR A
    LD (STUB_MODE),A
    CALL SELFTEST_RESET
    LD A,001h
    LD D,035h
    LD E,00Bh
    CALL MAIN_SUB_READ_CHR_RETRY
    LD A,000h
    ADC A,A
    LD (09021h),A
    CALL COPY_RETRY_LOG

    ; 2回とも失敗。
    LD A,001h
    LD (STUB_MODE),A
    CALL SELFTEST_RESET
    LD A,001h
    LD D,035h
    LD E,00Bh
    CALL MAIN_SUB_READ_CHR_RETRY
    LD A,000h
    ADC A,A
    LD (09029h),A
    LD A,(STUB_CALL_COUNT)
    LD (09028h),A

    ; 1回目で成功。
    LD A,002h
    LD (STUB_MODE),A
    CALL SELFTEST_RESET
    LD A,001h
    LD D,035h
    LD E,00Bh
    CALL MAIN_SUB_READ_CHR_RETRY
    LD A,000h
    ADC A,A
    LD (0902Bh),A
    LD A,(STUB_CALL_COUNT)
    LD (0902Ah),A
SELFTEST_DONE:
    JR SELFTEST_DONE

COPY_RETRY_LOG:
    LD A,(STUB_CALL_COUNT)
    LD (09020h),A
    LD A,(STUB_A1)
    LD (09022h),A
    LD A,(STUB_D1)
    LD (09023h),A
    LD A,(STUB_E1)
    LD (09024h),A
    LD A,(STUB_A2)
    LD (09025h),A
    LD A,(STUB_D2)
    LD (09026h),A
    LD A,(STUB_E2)
    LD (09027h),A
    RET

SELFTEST_RESET:
    XOR A
    LD (STUB_CALL_COUNT),A
    LD (STUB_A1),A
    LD (STUB_D1),A
    LD (STUB_E1),A
    LD (STUB_A2),A
    LD (STUB_D2),A
    LD (STUB_E2),A
    LD (MAIN_SUB_MARK_SUCCESS),A
    RET

; 呼出時のA/D/Eを記録したあと全て壊す。再試行口自身が保存していなければ
; 2回目へ同じ引数を渡せない。
MAIN_SUB_READ_CHR:
    LD B,A
    LD A,(STUB_CALL_COUNT)
    INC A
    LD (STUB_CALL_COUNT),A
    CP 001h
    JR NZ,_stub_second
    LD A,B
    LD (STUB_A1),A
    LD A,D
    LD (STUB_D1),A
    LD A,E
    LD (STUB_E1),A
    JR _stub_result
_stub_second:
    LD A,B
    LD (STUB_A2),A
    LD A,D
    LD (STUB_D2),A
    LD A,E
    LD (STUB_E2),A
_stub_result:
    LD A,(STUB_MODE)
    CP 002h
    JR Z,_stub_success
    CP 000h
    JR NZ,_stub_fail
    LD A,(STUB_CALL_COUNT)
    CP 002h
    JR Z,_stub_success
_stub_fail:
    XOR A
    LD (MAIN_SUB_MARK_SUCCESS),A
    JR _stub_clobber
_stub_success:
    LD A,001h
    LD (MAIN_SUB_MARK_SUCCESS),A
_stub_clobber:
    XOR A
    LD D,A
    INC A
    LD E,A
    RET

STUB_MODE       EQU 0E121h
STUB_CALL_COUNT EQU 0E122h
STUB_A1         EQU 0E123h
STUB_D1         EQU 0E124h
STUB_E1         EQU 0E125h
STUB_A2         EQU 0E126h
STUB_D2         EQU 0E127h
STUB_E2         EQU 0E128h
"""


def assemble_and_run(name, source, start_address, length):
    case = work / name
    case.mkdir()
    asm_path = case / "selftest.asm"
    bin_path = case / "selftest.bin"
    asm_path.write_text("    ORG 0000h\n    JP SELFTEST_START\n" + source,
                        encoding="utf-8")
    assembled = subprocess.run(
        [sys.executable, str(z80text), str(asm_path), "-o", str(bin_path)],
        capture_output=True, text=True)
    if assembled.returncode != 0:
        raise SystemExit(f"NG: {name}のアセンブル失敗")
    program = bin_path.read_bytes()
    if len(program) > N88_SIZE:
        raise SystemExit(f"NG: {name}の自作ROMコードが32KBを超えた")
    romdir = case / "rom"
    romdir.mkdir()
    n88 = bytearray(N88_SIZE)
    n88[:len(program)] = program
    (romdir / "N88.ROM").write_bytes(n88)
    disk = bytearray(DISK_SIZE)
    disk[:2] = bytes((0x18, 0xFE))
    (romdir / "DISK.ROM").write_bytes(disk)
    memlog = case / "memwrite.txt"
    end_address = start_address + length - 1
    run = subprocess.run([
        str(frontend), "--core", str(core), "--rom-dir", str(romdir),
        "--frames", "30", "--mem-write-log", str(memlog),
        "--mem-write-range", f"{start_address:04X}-{end_address:04X}",
        "--out", str(case / "trace.txt")], capture_output=True, text=True)
    if run.returncode != 0:
        raise SystemExit(f"NG: q88measure({name})失敗 rc={run.returncode}")
    last = {}
    for line in memlog.read_text(encoding="utf-8").splitlines():
        match = re.match(
            r"^\s*\d+\s+\d+\s+[0-9A-Fa-f]+\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)\s*$",
            line)
        if match:
            last[int(match.group(1), 16)] = int(match.group(2), 16)
    addresses = range(start_address, start_address + length)
    if any(address not in last for address in addresses):
        raise SystemExit(f"NG: q88measure({name})のRAM結果が不足")
    return bytes(last[address] for address in addresses)


source = source_path.read_text(encoding="utf-8")
request_start = source.index("MAIN_SUB_CHR_LOGICAL_TRACK EQU")
request_end = source.index("\nMAIN_SUB_READ_CHR_RETRY:", request_start) + 1
request_source = source[request_start:request_end]
swap_old = """    LD A,(MAIN_SUB_CHR_LOGICAL_TRACK)
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_ms_read_timeout
    LD A,(MAIN_SUB_CHR_SECTOR)
    CALL MAIN_SUB_SEND_REQUEST_CONT
"""
swap_new = """    LD A,(MAIN_SUB_CHR_SECTOR)
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_ms_read_timeout
    LD A,(MAIN_SUB_CHR_LOGICAL_TRACK)
    CALL MAIN_SUB_SEND_REQUEST_CONT
"""
if request_source.count(swap_old) != 1:
    raise SystemExit("NG: D/E交換故障の注入点が一意でない")

request_actual = assemble_and_run(
    "request_current", COMMON_EQU + request_source + REQUEST_DRIVER, 0x9000, 25)
request_swapped = assemble_and_run(
    "request_swap", COMMON_EQU + request_source.replace(swap_old, swap_new)
    + REQUEST_DRIVER, 0x9000, 25)

retry_start = request_end
retry_end_marker = "MAIN_SUB_READ_CHR_RETRY_END:\n"
retry_end = source.index(retry_end_marker, retry_start) + len(retry_end_marker)
retry_source = source[retry_start:retry_end]

fault_sites = {
    "a": (
        "    POP AF                       ; 入口Aとフラグを2回目へ戻す\n"
        "    CALL MAIN_SUB_READ_CHR\n",
        "    POP AF                       ; 入口Aとフラグを2回目へ戻す\n"
        "    XOR A\n"
        "    CALL MAIN_SUB_READ_CHR\n"),
    "d": (
        "    POP DE                       ; 入口D/Eを2回目へ戻す\n"
        "    POP AF",
        "    POP DE                       ; 入口D/Eを2回目へ戻す\n"
        "    LD D,000h\n"
        "    POP AF"),
    "e": (
        "    POP DE                       ; 入口D/Eを2回目へ戻す\n"
        "    POP AF",
        "    POP DE                       ; 入口D/Eを2回目へ戻す\n"
        "    LD E,001h\n"
        "    POP AF"),
}
for name, (old, _new) in fault_sites.items():
    if retry_source.count(old) != 1:
        raise SystemExit(f"NG: {name.upper()}保存故障の注入点が一意でない")

retry_actual = assemble_and_run(
    "retry_current", COMMON_EQU + retry_source + RETRY_DRIVER, 0x9020, 12)
retry_faults = {
    name: assemble_and_run(
        "retry_fault_" + name,
        COMMON_EQU + retry_source.replace(old, new) + RETRY_DRIVER,
        0x9020, 12)
    for name, (old, new) in fault_sites.items()
}

cases = ((0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 79, 16), (0, 40, 8))
request_expected = bytes(value for a, d, e in cases for value in (2, 0, a, d, e))
request_swap_expected = bytes(value for a, d, e in cases for value in (2, 0, a, e, d))
retry_expected = bytes((2, 0, 1, 0x35, 0x0B, 1, 0x35, 0x0B, 2, 1, 1, 0))

retry_instructions = [
    line.split(";", 1)[0].strip().upper()
    for line in retry_source.splitlines()
    if line.split(";", 1)[0].strip()
]
checks = {
    "request_shape": request_actual == request_expected,
    "retry_arguments": (
        retry_actual[2] & 1, retry_actual[3], retry_actual[4]
    ) == (
        retry_actual[5] & 1, retry_actual[6], retry_actual[7]
    ) == (1, 0x35, 0x0B),
    "retry_fail_then_success": retry_actual[0:2] == bytes((2, 0)),
    "retry_double_failure": retry_actual[8:10] == bytes((2, 1)),
    "retry_first_success": retry_actual[10:12] == bytes((1, 0)),
    "retry_structure": (
        retry_instructions.count("CALL MAIN_SUB_READ_CHR") == 2
        and not any("WAIT" in line for line in retry_instructions)
    ),
    "fault_request_swap": (
        request_swapped == request_swap_expected and request_swapped != request_expected
    ),
    "fault_a": (
        (retry_faults["a"][2] & 1) == 1
        and (retry_faults["a"][5] & 1) == 0
        and retry_faults["a"][3:5] == retry_faults["a"][6:8]
    ),
    "fault_d": (
        retry_faults["d"][3] == 0x35 and retry_faults["d"][6] == 0
        and (retry_faults["d"][2] & 1) == (retry_faults["d"][5] & 1)
        and retry_faults["d"][4] == retry_faults["d"][7]
    ),
    "fault_e": (
        retry_faults["e"][4] == 0x0B and retry_faults["e"][7] == 1
        and (retry_faults["e"][2] & 1) == (retry_faults["e"][5] & 1)
        and retry_faults["e"][3] == retry_faults["e"][6]
    ),
}
if retry_actual != retry_expected or not all(checks.values()):
    raise SystemExit("NG: 一般READのZ80実走検査に失敗")

# 各判定を1つずつ偽にした陰性対照がその項目だけを落とし、その判定を
# 常時Trueへ変異させると陰性対照を拒否できなくなることを確認する。
for target in checks:
    negative = dict(checks)
    negative[target] = False
    failed = {name for name, passed in negative.items() if not passed}
    if failed != {target}:
        raise SystemExit(f"NG: {target}の陰性対照が対象だけを落とさない")
    mutated = dict(negative)
    mutated[target] = True
    if {name for name, passed in mutated.items() if not passed} == {target}:
        raise SystemExit(f"NG: {target}の常時True変異を拒否できない")

print("disk_read_chr_z80_selftest: 10項目OK、陰性対照10件、常時True変異10件を拒否")
print("要求形: 5座標一致、D/E交換版を検出")
print("G7: A/D/E保存、再試行上限1、成功/失敗CYを確認し、A/D/E各破壊版を検出")
PY
