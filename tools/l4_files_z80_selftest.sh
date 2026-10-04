#!/usr/bin/env bash
# FILESのバンク1本体を実Z80で検査する。公式ROM・公式媒体は使わない。
# 1単位、10単位、異なる終端値、16桁セルの各欄、種別の印(0xA0=ピリオド・
# 0x01=アスタリスク、docs/spec/l4-basic.md第3.12版11.1節規則3)、
# 大きさ3桁(100・158単位)を照合し、mem-write-logへは合否2バイトだけを
# 書く。CP 160を壊す陰性対照、および印の判定を壊す陰性対照も必須。
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
source "$REPO/tools/lib_l3_measure.sh"
CORE="$(find_l3_core)"
[ -n "$CORE" ] || { echo "NG: q88measure用コアが無い" >&2; exit 1; }
ensure_l3_frontend || exit 1

WORK="$(mktemp -d "${TMPDIR:-/tmp}/l4-files-z80.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

make_rom() {
  local out="$1" fault="$2"
  mkdir -p "$out"
  python3 - "$REPO" "$out" "$fault" <<'PY'
import pathlib, sys
repo = pathlib.Path(sys.argv[1])
out = pathlib.Path(sys.argv[2])
fault = sys.argv[3]
sys.path.insert(0, str(repo / "tools" / "asm"))
sys.path.insert(0, str(repo / "src"))
import memmap
import z80text

bank = (repo / "src" / "ext_bank" / "bank1.asm").read_text(encoding="utf-8")
if fault == "chain_fault":
    old = "    CP 160\n    JP C,_fb_chain_loop"
    new = "    CP 194\n    JP C,_fb_chain_loop"
    if bank.count(old) != 1:
        raise SystemExit("陰性対照の置換点が一意でない")
    bank = bank.replace(old, new)
elif fault == "mark_fault":
    # 0xA0(SAVE ,P)の判定を壊し、印がピリオドにならないようにする。
    old = "    CP 0A0h\n    JP Z,_fb_mark_period"
    new = "    CP 0A1h\n    JP Z,_fb_mark_period"
    if bank.count(old) != 1:
        raise SystemExit("陰性対照の置換点が一意でない")
    bank = bank.replace(old, new)

harness = r'''
    ORG 0
    JP TEST_START
    ORG 0100h
TEST_START:
    LD SP,MM_STACK_TOP
    XOR A
    LD (0E300h),A
    LD (0E301h),A
    ; FATを0xFF、試験エントリを空白で初期化する。
    LD HL,MM_FILES_FAT_BUF
    LD (HL),0FFh
    LD DE,MM_FILES_FAT_BUF+1
    LD BC,255
    LDIR
    LD HL,MM_MAIN_SUB_SECTOR_BUF
    LD B,16
    LD A,' '
T_CLEAR_ENTRY:
    LD (HL),A
    INC HL
    DJNZ T_CLEAR_ENTRY
    ; 名前6/拡張子3/種別/先頭単位はすべて合成値。
    LD HL,MM_MAIN_SUB_SECTOR_BUF
    LD (HL),'A'
    INC HL
    LD (HL),'B'
    INC HL
    LD (HL),'C'
    INC HL
    LD (HL),'D'
    INC HL
    LD (HL),'E'
    INC HL
    LD (HL),'F'
    INC HL
    LD (HL),'X'
    INC HL
    LD (HL),'Y'
    INC HL
    LD (HL),'Z'
    LD A,080h
    LD (MM_MAIN_SUB_SECTOR_BUF+9),A

    ; 1単位、終端0xC1。
    LD A,0C1h
    LD (MM_FILES_FAT_BUF+5),A
    LD A,5
    LD (MM_MAIN_SUB_SECTOR_BUF+10),A
    CALL T_RESET_SCAN
    CALL 06110h
    CP 2
    JP NZ,T_FAIL1
    LD A,(MM_FILES_SIZE_VALUE)
    CP 1
    JP NZ,T_FAIL1
    ; セルは欄ごとに検査し、画面本文として外へ出さない。
    LD A,(MM_FILES_CELL_BUF)
    CP 'A'
    JP NZ,T_FAIL2
    LD A,(MM_FILES_CELL_BUF+5)
    CP 'F'
    JP NZ,T_FAIL2
    LD A,(MM_FILES_CELL_BUF+6)
    CP '.'
    JP NZ,T_FAIL2
    LD A,(MM_FILES_CELL_BUF+7)
    CP 'X'
    JP NZ,T_FAIL2
    LD A,(MM_FILES_CELL_BUF+9)
    CP 'Z'
    JP NZ,T_FAIL2
    LD A,(MM_FILES_CELL_BUF+10)
    CP ' '
    JP NZ,T_FAIL2
    LD A,(MM_FILES_CELL_BUF+11)
    CP '1'
    JP NZ,T_FAIL2
    LD A,(MM_FILES_CELL_BUF+12)
    CP ' '
    JP NZ,T_FAIL2
    LD A,(MM_FILES_CELL_BUF+15)
    CP ' '
    JP NZ,T_FAIL2

    ; 10単位: 20→...→29、最後は0xC1。
    LD HL,MM_FILES_FAT_BUF+20
    LD A,21
    LD B,9
T_CHAIN10:
    LD (HL),A
    INC HL
    INC A
    DJNZ T_CHAIN10
    LD (HL),0C1h
    LD A,20
    LD (MM_MAIN_SUB_SECTOR_BUF+10),A
    CALL T_RESET_SCAN
    CALL 06110h
    CP 2
    JP NZ,T_FAIL3
    LD A,(MM_FILES_SIZE_VALUE)
    CP 10
    JP NZ,T_FAIL3
    LD A,(MM_FILES_CELL_BUF+11)
    CP '1'
    JP NZ,T_FAIL3
    LD A,(MM_FILES_CELL_BUF+12)
    CP '0'
    JP NZ,T_FAIL3
    LD A,(MM_FILES_CELL_BUF+13)
    CP ' '
    JP NZ,T_FAIL3

    ; 終端の使用セクタ数は単位数へ足さない。0xC8でも1単位。
    LD A,0C8h
    LD (MM_FILES_FAT_BUF+40),A
    LD A,40
    LD (MM_MAIN_SUB_SECTOR_BUF+10),A
    CALL T_RESET_SCAN
    CALL 06110h
    CP 2
    JP NZ,T_FAIL4
    LD A,(MM_FILES_SIZE_VALUE)
    CP 1
    JP NZ,T_FAIL4

    ; 0xA0(SAVE ,P)はピリオド。第11.1節規則3(m6f-g)。
    LD A,0A0h
    LD (MM_MAIN_SUB_SECTOR_BUF+9),A
    LD A,0C1h
    LD (MM_FILES_FAT_BUF+5),A
    LD A,5
    LD (MM_MAIN_SUB_SECTOR_BUF+10),A
    CALL T_RESET_SCAN
    CALL 06110h
    CP 2
    JP NZ,T_FAIL5
    LD A,(MM_FILES_CELL_BUF+6)
    CP '.'
    JP NZ,T_FAIL5

    ; 0x01(BSAVE)はアスタリスク。
    LD A,001h
    LD (MM_MAIN_SUB_SECTOR_BUF+9),A
    CALL T_RESET_SCAN
    CALL 06110h
    CP 2
    JP NZ,T_FAIL6
    LD A,(MM_FILES_CELL_BUF+6)
    CP '*'
    JP NZ,T_FAIL6

    ; 0x80に戻し、大きさ100単位→'100'（3桁、m6f-g）。
    LD A,080h
    LD (MM_MAIN_SUB_SECTOR_BUF+9),A
    CALL BUILD_CHAIN_100
    XOR A
    LD (MM_MAIN_SUB_SECTOR_BUF+10),A
    CALL T_RESET_SCAN
    CALL 06110h
    CP 2
    JP NZ,T_FAIL7
    LD A,(MM_FILES_SIZE_VALUE)
    CP 100
    JP NZ,T_FAIL7
    LD A,(MM_FILES_CELL_BUF+11)
    CP '1'
    JP NZ,T_FAIL7
    LD A,(MM_FILES_CELL_BUF+12)
    CP '0'
    JP NZ,T_FAIL7
    LD A,(MM_FILES_CELL_BUF+13)
    CP '0'
    JP NZ,T_FAIL7

    ; 大きさ158単位→'158'（割り当て可能単位の最大、m6f-g）。
    CALL BUILD_CHAIN_158
    CALL T_RESET_SCAN
    CALL 06110h
    CP 2
    JP NZ,T_FAIL8
    LD A,(MM_FILES_SIZE_VALUE)
    CP 158
    JP NZ,T_FAIL8
    LD A,(MM_FILES_CELL_BUF+11)
    CP '1'
    JP NZ,T_FAIL8
    LD A,(MM_FILES_CELL_BUF+12)
    CP '5'
    JP NZ,T_FAIL8
    LD A,(MM_FILES_CELL_BUF+13)
    CP '8'
    JP NZ,T_FAIL8

    LD A,1
    LD (0E300h),A
T_HALT:
    JR T_HALT

; unit 0開始、FAT[0..N-2]=1..N-1、FAT[N-1]=終端0xC1で長さNの鎖を作る。
BUILD_CHAIN_100:
    LD HL,MM_FILES_FAT_BUF
    LD B,99
    LD A,1
BC100_LOOP:
    LD (HL),A
    INC HL
    INC A
    DJNZ BC100_LOOP
    LD (HL),0C1h
    RET

BUILD_CHAIN_158:
    LD HL,MM_FILES_FAT_BUF
    LD B,157
    LD A,1
BC158_LOOP:
    LD (HL),A
    INC HL
    INC A
    DJNZ BC158_LOOP
    LD (HL),0C1h
    RET

T_RESET_SCAN:
    LD A,2
    LD (MM_FILES_PHASE),A
    LD A,1
    LD (MM_FILES_READ_OK),A
    XOR A
    LD (MM_FILES_ENTRY_INDEX),A
    LD (MM_FILES_ENTRY_COUNT),A
    RET

T_FAIL1:
    LD A,1
    JP T_FAIL
T_FAIL2:
    LD A,2
    JP T_FAIL
T_FAIL3:
    LD A,3
    JP T_FAIL
T_FAIL4:
    LD A,4
    JP T_FAIL
T_FAIL5:
    LD A,5
    JP T_FAIL
T_FAIL6:
    LD A,6
    JP T_FAIL
T_FAIL7:
    LD A,7
    JP T_FAIL
T_FAIL8:
    LD A,8
T_FAIL:
    LD (0E301h),A
T_FAIL_HALT:
    JR T_FAIL_HALT
'''
src = harness + "\n" + bank
tmp = out / "files_test.asm"
tmp.write_text(memmap.asm_prelude() + src, encoding="utf-8")
asm = z80text.Assembler()
code = asm.assemble(tmp)
if len(code) > 0x8000:
    raise SystemExit("試験ROMが32KBを超えた")
rom = bytearray(0x8000)
rom[:len(code)] = code
(out / "N88.ROM").write_bytes(rom)
disk = bytearray(0x800)
disk[:2] = bytes((0x18, 0xFE))
(out / "DISK.ROM").write_bytes(disk)
PY
}

last_values() {
  python3 - "$1" <<'PY'
import re, sys
last = {}
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    m = re.match(r"\s*\d+\s+\d+\s+[0-9A-Fa-f]{4}\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})", line)
    if m:
        last[m.group(1).upper()] = m.group(2).upper()
print(last.get("E300", "00"), last.get("E301", "00"))
PY
}

run_one() {
  local kind="$1" out="$WORK/$1" log="$WORK/$1.memlog"
  make_rom "$out" "$kind" || return 2
  "$FRONTEND" --core "$CORE" --rom-dir "$out" --frames 30 \
    --mem-write-log "$log" --mem-write-range E300-E301 \
    >"$WORK/$1.stdout" 2>"$WORK/$1.stderr" || return 2
  last_values "$log"
}

read -r normal_pass normal_fail <<<"$(run_one normal)" || exit 1
if [ "$normal_pass" != "01" ] || [ "$normal_fail" != "00" ]; then
  echo "NG: 正常系が不合格(pass=$normal_pass fail=$normal_fail)" >&2
  exit 1
fi
echo "OK: 実Z80で1単位・10単位・終端・16桁セル・印(0xA0/0x01)・3桁の大きさ(100/158)を確認"

read -r fault_pass fault_fail <<<"$(run_one chain_fault)" || exit 1
if [ "$fault_pass" = "01" ] || [ "$fault_fail" = "00" ]; then
  echo "NG: 陰性対照(CP 160破壊)を検出できない" >&2
  exit 1
fi
echo "OK: 陰性対照(CP 160破壊)は不合格"

read -r mark_fault_pass mark_fault_fail <<<"$(run_one mark_fault)" || exit 1
if [ "$mark_fault_pass" = "01" ] || [ "$mark_fault_fail" = "00" ]; then
  echo "NG: 陰性対照(0xA0印判定破壊)を検出できない" >&2
  exit 1
fi
echo "OK: 陰性対照(0xA0印判定破壊)は不合格"
echo "l4_files_z80_selftest: OK"
