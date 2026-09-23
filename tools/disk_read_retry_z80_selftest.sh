#!/usr/bin/env bash
# disk_read_retry_z80_selftest.sh — READ再試行を実際のZ80コアで検査する。
#
# src/l3_main/disk_read_retry.asm を、呼出時のAをRAMへ記録する
# MAIN_SUB_READ_KNOWNスタブと一緒に自作ROMへ組み込み、q88measureの
# --mem-write-logで呼出回数・2回分のA・戻りCYを回収する。
# 公式ROM・私物は使わず、画面本文やデータポート値列も出力しない。
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
retry_path = repo / "src" / "l3_main" / "disk_read_retry.asm"
z80text = repo / "tools" / "asm" / "z80text.py"

OUT_BASE = 0x9000
OUT_LEN = 16
N88_SIZE = 0x8000
DISK_SIZE = 0x0800

# 修正前実装はドライブBの2回目がA=0となり、このq88measure実走検査で落ちる。
OLD_ROUTINE = """MAIN_SUB_READ_KNOWN_RETRY:
    CALL MAIN_SUB_READ_KNOWN
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A
    RET NZ
    CALL MAIN_SUB_READ_KNOWN
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A
    RET NZ
    SCF
    RET
MAIN_SUB_READ_KNOWN_RETRY_END:
"""

DRIVER = r"""
SELFTEST_START:
    LD SP,0FFF0h

    ; mode 0: 1回目失敗、2回目成功。ドライブA。
    XOR A
    LD (STUB_MODE),A
    CALL SELFTEST_RESET
    XOR A
    CALL MAIN_SUB_READ_KNOWN_RETRY
    LD A,000h
    ADC A,A
    LD (09003h),A
    LD A,(STUB_CALL_COUNT)
    LD (09000h),A
    LD A,(STUB_A1)
    LD (09001h),A
    LD A,(STUB_A2)
    LD (09002h),A

    ; mode 0: 1回目失敗、2回目成功。ドライブB（今回の回帰検査）。
    XOR A
    LD (STUB_MODE),A
    CALL SELFTEST_RESET
    LD A,001h
    CALL MAIN_SUB_READ_KNOWN_RETRY
    LD A,000h
    ADC A,A
    LD (09007h),A
    LD A,(STUB_CALL_COUNT)
    LD (09004h),A
    LD A,(STUB_A1)
    LD (09005h),A
    LD A,(STUB_A2)
    LD (09006h),A

    ; mode 1: 2回とも失敗。CY=1で戻ること。
    LD A,001h
    LD (STUB_MODE),A
    CALL SELFTEST_RESET
    LD A,001h
    CALL MAIN_SUB_READ_KNOWN_RETRY
    LD A,000h
    ADC A,A
    LD (0900Bh),A
    LD A,(STUB_CALL_COUNT)
    LD (09008h),A
    LD A,(STUB_A1)
    LD (09009h),A
    LD A,(STUB_A2)
    LD (0900Ah),A

    ; mode 2: 1回目で成功。再試行せずCY=0で戻ること。
    LD A,002h
    LD (STUB_MODE),A
    CALL SELFTEST_RESET
    LD A,001h
    CALL MAIN_SUB_READ_KNOWN_RETRY
    LD A,000h
    ADC A,A
    LD (0900Fh),A
    LD A,(STUB_CALL_COUNT)
    LD (0900Ch),A
    LD A,(STUB_A1)
    LD (0900Dh),A
    LD A,(STUB_A2)
    LD (0900Eh),A

SELFTEST_DONE:
    JR SELFTEST_DONE

SELFTEST_RESET:
    XOR A
    LD (STUB_CALL_COUNT),A
    LD (STUB_A1),A
    LD (STUB_A2),A
    LD (MAIN_SUB_MARK_SUCCESS),A
    RET

; mode 0: 初回失敗・2回目成功、mode 1: 常に失敗、mode 2: 常に成功。
; 実物と同じくAF/BCを保存し、入口Aを呼出順にRAMへ記録する。
MAIN_SUB_READ_KNOWN:
    PUSH AF
    PUSH BC
    LD B,A
    LD A,(STUB_CALL_COUNT)
    INC A
    LD (STUB_CALL_COUNT),A
    CP 001h
    JR NZ,_stub_log_second
    LD A,B
    LD (STUB_A1),A
    JR _stub_choose_result
_stub_log_second:
    LD A,B
    LD (STUB_A2),A
_stub_choose_result:
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
    JR _stub_return
_stub_success:
    LD A,001h
    LD (MAIN_SUB_MARK_SUCCESS),A
_stub_return:
    POP BC
    POP AF
    RET

STUB_MODE       EQU 0E100h
STUB_CALL_COUNT EQU 0E101h
STUB_A1         EQU 0E102h
STUB_A2         EQU 0E103h
"""


def make_source(retry_source: str) -> str:
    return f"""    ORG 0000h
    JP SELFTEST_START
MAIN_SUB_MARK_SUCCESS EQU 0E002h
MAIN_SUB_BOOT_DONE    EQU 0E008h

{retry_source}
{DRIVER}
"""


def assemble_and_run(name: str, retry_source: str) -> bytes:
    case = work / name
    case.mkdir()
    asm_path = case / "selftest.asm"
    bin_path = case / "selftest.bin"
    asm_path.write_text(make_source(retry_source), encoding="utf-8")
    assembled = subprocess.run(
        [sys.executable, str(z80text), str(asm_path), "-o", str(bin_path)],
        capture_output=True, text=True)
    if assembled.returncode != 0:
        raise SystemExit(
            f"NG: {name}のアセンブル失敗\n{assembled.stdout}\n{assembled.stderr}")
    program = bin_path.read_bytes()
    if len(program) > N88_SIZE:
        raise SystemExit(f"NG: {name}の自作ROMコードが32KBを超えた")

    romdir = case / "rom"
    romdir.mkdir()
    n88 = bytearray(N88_SIZE)
    n88[:len(program)] = program
    (romdir / "N88.ROM").write_bytes(n88)
    disk = bytearray(DISK_SIZE)
    disk[:2] = bytes((0x18, 0xFE))  # JR $
    (romdir / "DISK.ROM").write_bytes(disk)

    memlog = case / "memwrite.txt"
    run = subprocess.run([
        str(frontend), "--core", str(core), "--rom-dir", str(romdir),
        "--frames", "30", "--mem-write-log", str(memlog),
        "--mem-write-range", "9000-900F", "--out", str(case / "trace.txt")],
        capture_output=True, text=True)
    if run.returncode != 0:
        raise SystemExit(f"NG: q88measure({name})失敗 rc={run.returncode}\n{run.stderr}")

    last = {}
    for line in memlog.read_text(encoding="utf-8").splitlines():
        match = re.match(
            r"^\s*\d+\s+\d+\s+[0-9A-Fa-f]+\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)\s*$",
            line)
        if match:
            last[int(match.group(1), 16)] = int(match.group(2), 16)
    missing = [address for address in range(OUT_BASE, OUT_BASE + OUT_LEN)
               if address not in last]
    if missing:
        raise SystemExit(
            "NG: q88measure(%s)のRAM結果が不足: %s" %
            (name, ",".join(f"{address:04X}" for address in missing)))
    return bytes(last[address] for address in range(OUT_BASE, OUT_BASE + OUT_LEN))


source = retry_path.read_text(encoding="utf-8")
start = source.index("MAIN_SUB_READ_KNOWN_RETRY:\n")
end_marker = "MAIN_SUB_READ_KNOWN_RETRY_END:\n"
end = source.index(end_marker, start) + len(end_marker)

actual = assemble_and_run("current", source)
expected = bytes((
    2, 0, 0, 0,  # drive A, fail -> success
    2, 1, 1, 0,  # drive B, fail -> success
    2, 1, 1, 1,  # drive B, fail -> fail
    1, 1, 0, 0,  # drive B, first success
))
if actual != expected:
    raise SystemExit(
        "NG: 現行実装のZ80実走結果が不一致 "
        f"actual={actual.hex()} expected={expected.hex()}")

faulty_source = source[:start] + OLD_ROUTINE + source[end:]
faulty = assemble_and_run("old_fault", faulty_source)
if faulty[4] != 2 or (faulty[5] & 1) != 1 or (faulty[6] & 1) != 0:
    raise SystemExit(
        "NG: 修正前実装の陰性対照がドライブB引継ぎ欠陥を再現しない "
        f"count={faulty[4]} A1={faulty[5]:02X} A2={faulty[6]:02X}")
if faulty == expected:
    raise SystemExit("NG: 修正前実装を挿入しても挙動検査が落ちない")

print("Z80実走OK: A/Bとも入力維持、再試行上限1、成功CY=0、2回失敗CY=1")
print("陰性対照OK: 修正前実装はドライブBの2回目がA=0となり不一致")
PY

echo "disk_read_retry_z80_selftest: OK"
