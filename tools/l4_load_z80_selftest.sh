#!/usr/bin/env bash
# LOADの行切出し・鎖・ERR57を実Z80で検査する。画面は作らない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
source "$REPO/tools/lib_l3_measure.sh"
CORE="$(find_l3_core)"
[ -n "$CORE" ] || { printf 'NG コアなし\n' >&2; exit 1; }
ensure_l3_frontend || exit 1
WORK="$(mktemp -d "${TMPDIR:-/tmp}/load-z80.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

make_rom() {
  local out="$1" fault="$2"
  mkdir "$out"
  python3 - "$REPO" "$out" "$fault" <<'PY'
import pathlib,sys
repo,out,fault=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2]),sys.argv[3]
sys.path.insert(0,str(repo/'tools'/'asm'))
sys.path.insert(0, str(repo / "src"))
import memmap
import z80text
bank=(repo/'src/ext_bank/bank1.asm').read_text(encoding='utf-8')
# この検査の小型ROMでは、mainの試験関数を窓外に直接置く。
# 実ビルドでの汎用中継経路はconform_load.shが検査する。
for name in ('PARSE_LINENUM','PROGRAM_STORE_LINE','SELECT_ERROR_MSG',
             'PRINT_STR','NEWLINE'):
    old=f'_b1_call_{name.lower()}:\n    LD IX,BANK1_{name}_ADDR\n    JP BANK1_MAIN_CALL_ADDR'
    new=f'_b1_call_{name.lower()}:\n    JP {name}'
    assert bank.count(old)==1
    bank=bank.replace(old,new)
head,line_part=bank.split('_load_line:\n',1)
assert line_part.count('    JP _load_dispatch\n')==1
bank=head+'_load_line:\n'+line_part.replace('    JP _load_dispatch\n',
                                      '    JP _test_load_dispatch\n',1)
if fault=='eof':
    old="    CP 01Ah\n    JP Z,_lb_done"
    assert bank.count(old)==1
    bank=bank.replace(old,"    CP 01Bh\n    JP Z,_lb_done")
gap=(repo/'src/l4_basic/load_gap.asm').read_text(encoding='utf-8')
harness=r'''
    ORG 0
    JP TEST_START
    ORG 0100h
ERROR_FLAG EQU 0E880h
ERROR_KIND EQU 0E8A0h
RUN_CTRL EQU 0D005h
VAR_LINELEN EQU 0E82Ah
LINE_BUF EQU 0E82Bh
TEST_START:
    LD SP,0F000h
    XOR A
    LD (0E300h),A
    LD (0E301h),A
    LD (0E302h),A
    LD (ERROR_FLAG),A
    LD (LOAD_LINE_LEN),A
    LD (LOAD_SKIP_LF),A
    LD (0E105h),A
    LD A,6
    LD (0E105h),A
    LD A,0C1h
    LD (0E106h),A
    LD A,160
    LD (LOAD_CHAIN_GUARD),A
    LD A,5
    LD (LOAD_UNIT),A
    LD A,7
    LD (LOAD_UNIT_SECTOR),A
    LD A,3
    LD (LOAD_PHASE),A
    CALL 06400h
    CP 1
    JP NZ,FAIL_1
    LD A,(LOAD_READ_TRACK)
    CP 2
    JP NZ,FAIL_1
    LD A,(LOAD_READ_SECTOR)
    CP 16
    JP NZ,FAIL_1
    LD A,1
    LD (LOAD_READ_OK),A
    ; 第1単位の最終セクタの末尾でCR。LFは次の単位の先頭。
    LD HL,0DF00h
    LD (HL),0FFh
    LD DE,0DF01h
    LD BC,255
    LDIR
    LD HL,0DFFBh
    LD (HL),'1'
    INC HL
    LD (HL),'0'
    INC HL
    LD (HL),' '
    INC HL
    LD (HL),'A'
    INC HL
    LD (HL),0Dh
    LD A,251
    LD (LOAD_BYTE_OFFSET),A
    CALL 06400h
    CP 3
    JP NZ,FAIL_2
    CALL _load_line
    LD A,(0E302h)
    CP 1
    JP NZ,FAIL_8
    LD A,(LOAD_PHASE)
    CP 3
    JP NZ,FAIL_9
    CALL 06400h
    CP 1
    JP NZ,FAIL_3
    LD A,(LOAD_UNIT)
    CP 6
    JP NZ,FAIL_3
    LD A,(LOAD_READ_TRACK)
    CP 3
    JP NZ,FAIL_3
    LD A,(LOAD_READ_SECTOR)
    CP 1
    JP NZ,FAIL_3
    ; LFを飛ばし、2行目のCR LF、続く0x1Aで終了。
    LD HL,0DF00h
    LD (HL),0Ah
    INC HL
    LD (HL),'2'
    INC HL
    LD (HL),'0'
    INC HL
    LD (HL),' '
    INC HL
    LD (HL),'B'
    INC HL
    LD (HL),0Dh
    INC HL
    LD (HL),0Ah
    INC HL
    LD (HL),01Ah
    CALL 06400h
    CP 3
    JP NZ,FAIL_4
    CALL _load_line
    LD A,(0E302h)
    CP 2
    JP NZ,FAIL_4
    CALL 06400h
    OR A
    JP NZ,FAIL_5
    ; 行番号のない行でERR57。先に登録した2行は残る。
    XOR A
    LD (LOAD_BYTE_OFFSET),A
    LD (LOAD_LINE_LEN),A
    LD (LOAD_SKIP_LF),A
    LD A,4
    LD (LOAD_PHASE),A
    LD HL,0DF00h
    LD (HL),'A'
    INC HL
    LD (HL),'B'
    INC HL
    LD (HL),'C'
    INC HL
    LD (HL),0Dh
    CALL 06400h
    CP 3
    JP NZ,FAIL_6
    CALL _load_line
    LD A,(ERROR_KIND)
    CP 57
    JP NZ,FAIL_6
    LD A,(0E302h)
    CP 2
    JP NZ,FAIL_6
    LD A,1
    LD (0E300h),A
HALT_OK:
    JR HALT_OK

PARSE_LINENUM:
    LD A,(LOAD_LINE_BUF)
    CP '0'
    JR C,PARSE_FAIL
    CP '9'+1
    JR NC,PARSE_FAIL
    LD HL,10
    LD B,2
    OR A
    RET
PARSE_FAIL:
    SCF
    RET
PROGRAM_STORE_LINE:
    LD A,(0E302h)
    OR A
    JR Z,STORE_FIRST
    CP 1
    JP NZ,FAIL_7
    LD A,(LOAD_LINE_BUF)
    CP '2'
    JP NZ,FAIL_7
    LD A,(LOAD_LINE_BUF+3)
    CP 'B'
    JP NZ,FAIL_7
    JR STORE_COUNT
STORE_FIRST:
    LD A,(LOAD_LINE_BUF)
    CP '1'
    JP NZ,FAIL_7
    LD A,(LOAD_LINE_BUF+3)
    CP 'A'
    JP NZ,FAIL_7
STORE_COUNT:
    LD A,(LOAD_LINE_LEN)
    CP 4
    JP NZ,FAIL_7
    LD A,(0E302h)
    INC A
    LD (0E302h),A
    RET
SELECT_ERROR_MSG:
    LD HL,0
    RET
PRINT_STR:
    RET
NEWLINE:
    RET
_test_load_dispatch:
    RET
FAIL_1:
    LD A,1
    JR FAIL
FAIL_2:
    LD A,2
    JR FAIL
FAIL_3:
    LD A,3
    JR FAIL
FAIL_4:
    LD A,4
    JR FAIL
FAIL_5:
    LD A,5
    JR FAIL
FAIL_6:
    LD A,6
    JR FAIL
FAIL_7:
    LD A,7
    JR FAIL
FAIL_8:
    LD A,8
    JR FAIL
FAIL_9:
    LD A,9
FAIL:
    LD (0E301h),A
HALT_FAIL:
    JR HALT_FAIL
'''
src=harness+'\n'+gap+'\n'+bank
asm_path=out/'test.asm';asm_path.write_text(memmap.asm_prelude() + src,encoding='utf-8')
code=z80text.Assembler().assemble(asm_path)
if len(code)>0x8000: raise SystemExit('ROM容量')
rom=bytearray(0x8000);rom[:len(code)]=code
(out/'N88.ROM').write_bytes(rom)
disk=bytearray(0x800);disk[:2]=bytes((0x18,0xFE))
(out/'DISK.ROM').write_bytes(disk)
PY
}

last_values() {
  python3 - "$1" <<'PY'
import re,sys
values={}
for line in open(sys.argv[1],encoding='utf-8',errors='replace'):
    m=re.match(r'\s*\d+\s+\d+\s+[0-9A-Fa-f]{4}\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})',line)
    if m: values[m.group(1).upper()]=m.group(2).upper()
print(values.get('E300','00'),values.get('E301','00'),values.get('E302','00'))
PY
}
run_one() {
  local kind="$1" out="$WORK/$1" log="$WORK/$1.memlog"
  make_rom "$out" "$kind" || return 2
  "$FRONTEND" --core "$CORE" --rom-dir "$out" --frames 30 \
    --mem-write-log "$log" --mem-write-range E300-E302 \
    >"$WORK/$1.stdout" 2>"$WORK/$1.stderr" || return 2
  last_values "$log"
}
read -r pass fail count <<<"$(run_one normal)"
[ "$pass" = 01 ] && [ "$fail" = 00 ] && [ "$count" = 02 ] || {
  printf 'NG Z80正常系 %s/%s/%s\n' "$pass" "$fail" "$count" >&2; exit 1;
}
read -r pass fail count <<<"$(run_one eof)"
[ "$pass" != 01 ] && [ "$fail" != 00 ] || { printf 'NG EOF陰性対照\n' >&2; exit 1; }
printf 'OK Z80: CR LF・0x1A・複数セクタ/単位・ERR57、EOF陰性対照\n'
