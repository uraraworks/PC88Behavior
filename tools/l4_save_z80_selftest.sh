#!/usr/bin/env bash
# SAVE ,A の媒体管理を実Z80で検査する。公式媒体は使わない。
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND="$REPO/tools/harness/frontend/q88measure"
source "$REPO/tools/lib_l3_measure.sh"
CORE="$(find_l3_core)"
[ -n "$CORE" ] || { echo 'NG: コアなし' >&2; exit 1; }
ensure_l3_frontend
WORK="$(mktemp -d "${TMPDIR:-/tmp}/l4-save-z80.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

make_rom() {
  local out="$1" fault="$2"
  mkdir "$out"
  python3 - "$REPO" "$out" "$fault" <<'PY'
from pathlib import Path
import sys
repo,out,fault=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
sys.path.insert(0,str(repo/'tools'/'asm'))
import z80text
bank=(repo/'src/ext_bank/bank2.asm').read_text(encoding='utf-8')
for name in ('read','write','list'):
    prefix='    LD A,(S2_DRIVE)\n' if name=='read' else ''
    old=('s2_write:\n    JP s2_write_stream' if name=='write' else
         f's2_{name}:\n{prefix}    LD IX,BANK2_{ {"read":"READ_CHR","capture_begin":"CAPTURE_BEGIN","capture_end":"CAPTURE_END","list":"LIST_RENDER"}[name]}_ADDR\n    JP BANK2_MAIN_CALL_ADDR')
    new=f's2_{name}:\n    JP T_{name.upper()}'
    if bank.count(old)!=1: raise SystemExit(f'置換点不一致: {name}')
    bank=bank.replace(old,new)
import re
for name, following in (('capture_begin','capture_end'),('capture_end','list')):
    pattern=f's2_{name}:\\n.*?(?=s2_{following}:)'
    bank,count=re.subn(pattern,f's2_{name}:\\n    JP T_{name.upper()}\\n',bank,flags=re.S)
    if count!=1: raise SystemExit(f'置換点不一致: {name}')
if fault=='order':
    old='    DB 72,73,68,69'
    if bank.count(old)!=1: raise SystemExit('割当順の故障点が一意でない')
    bank=bank.replace(old,'    DB 73,72,68,69',1)
harness=r'''
    ORG 0
    JP T_START
    ORG 0100h
T_MODE EQU 0E300h
T_WRITES EQU 0E301h
T_BODIES EQU 0E302h
T_FAILCODE EQU 0E303h
T_PASS EQU 0E304h
T_START:
    LD SP,0F000h
    XOR A
    LD (T_PASS),A
    LD (T_FAILCODE),A
    LD HL,S2_NAME
    LD B,9
    LD A,' '
T_NAME_PAD:
    LD (HL),A
    INC HL
    DJNZ T_NAME_PAD
    LD A,'Q'
    LD (S2_NAME),A
    XOR A
    LD (S2_DRIVE),A
    ; 10セクタで72→73、8セクタ境界をまたぐ。
    LD (T_MODE),A
    CALL T_RESET
    CALL s2_parse_done
    LD A,(S2_ERROR_FLAG)
    OR A
    JP NZ,T_FAIL1
    LD A,(T_BODIES)
    CP 10
    JP NZ,T_FAIL2
    LD A,(T_WRITES)
    CP 14
    JP NZ,T_FAIL3
    ; 同名上書きで旧単位10をRAMのFATから解放。
    LD A,1
    LD (T_MODE),A
    CALL T_RESET
    CALL s2_parse_done
    LD A,(S2_ERROR_FLAG)
    OR A
    JP NZ,T_FAIL4
    LD A,(T_BODIES)
    CP 1
    JP NZ,T_FAIL5
    ; 保護媒体はERR61、媒体への書込み0。
    LD A,2
    LD (T_MODE),A
    CALL T_RESET
    CALL s2_parse_done
    LD A,(S2_ERROR_KIND)
    CP 61
    JP NZ,T_FAIL6
    LD A,(T_WRITES)
    OR A
    JP NZ,T_FAIL6
    ; 空き不足はERR68、媒体への書込み0。
    LD A,3
    LD (T_MODE),A
    CALL T_RESET
    CALL s2_parse_done
    LD A,(S2_ERROR_KIND)
    CP 68
    JP NZ,T_FAIL7
    LD A,(T_WRITES)
    OR A
    JP NZ,T_FAIL7
    LD A,1
    LD (T_PASS),A
T_HALT:
    JR T_HALT
T_RESET:
    XOR A
    LD (T_WRITES),A
    LD (T_BODIES),A
    LD (S2_ERROR_FLAG),A
    RET
T_READ:
    PUSH DE
    LD HL,S2_BUF
    LD (HL),0FFh
    LD DE,S2_BUF+1
    LD BC,255
    LDIR
    POP DE
    LD A,E
    CP 13
    JR NZ,T_READ_FAT
    XOR A
    LD (S2_BUF),A
    LD A,(T_MODE)
    CP 2
    JR NZ,T_READ_DONE
    LD A,010h
    LD (S2_BUF),A
    JR T_READ_DONE
T_READ_FAT:
    CP 14
    JR C,T_READ_DIR
    CP 17
    JR NC,T_READ_DONE
    LD A,0A0h
    LD (S2_BUF+74),A
    LD (S2_BUF+75),A
    LD A,(T_MODE)
    CP 3
    JR NZ,T_READ_OLD
    LD HL,S2_BUF
    LD B,160
    LD A,0C1h
T_FILL_FULL:
    LD (HL),A
    INC HL
    DJNZ T_FILL_FULL
    JR T_READ_TAIL
T_READ_OLD:
    CP 1
    JR NZ,T_READ_TAIL
    LD A,0C1h
    LD (S2_BUF+10),A
T_READ_TAIL:
    LD HL,S2_BUF+160
    LD B,96
    LD A,E
    ADD A,04Ch
T_FILL_TAIL:
    LD (HL),A
    INC HL
    DJNZ T_FILL_TAIL
    JR T_READ_DONE
T_READ_DIR:
    CP 1
    JR NZ,T_READ_DONE
    LD A,(T_MODE)
    CP 1
    JR NZ,T_READ_DONE
    LD HL,S2_NAME
    LD DE,S2_BUF
    LD BC,9
    LDIR
    XOR A
    LD (S2_BUF+9),A
    LD A,10
    LD (S2_BUF+10),A
T_READ_DONE:
    OR A
    RET
T_CAPTURE_BEGIN:
    XOR A
    LD (S2_CAPTURE_OVER),A
    RET
T_LIST:
    LD A,(T_MODE)
    OR A
    JR NZ,T_LIST_SHORT
    LD HL,2305
    LD (S2_CAPTURE_LEN),HL
    JR T_LIST_FILL
T_LIST_SHORT:
    LD HL,1
    LD (S2_CAPTURE_LEN),HL
T_LIST_FILL:
    LD HL,09000h
    LD (HL),'A'
    LD DE,09001h
    LD BC,2304
    LDIR
    LD A,01Ah
    LD (09900h),A
    RET
T_CAPTURE_END:
    RET
T_WRITE:
    PUSH AF
    LD A,(T_WRITES)
    INC A
    LD (T_WRITES),A
    POP AF
    LD A,E
    CP 14
    JR C,T_WRITE_BODY_OR_DIR
    CP 17
    JR NC,T_WRITE_BAD
    LD A,(S2_BUF+160)
    LD B,A
    LD A,E
    ADD A,04Ch
    CP B
    JR NZ,T_WRITE_BAD
    LD A,(S2_BUF+72)
    LD B,A
    LD A,(T_MODE)
    OR A
    JR NZ,T_WRITE_OVER_FAT
    LD A,B
    CP 73
    JR NZ,T_WRITE_BAD
    LD A,(S2_BUF+73)
    CP 0C2h
    JR NZ,T_WRITE_BAD
    JR T_WRITE_OK
T_WRITE_OVER_FAT:
    LD A,B
    CP 0C1h
    JR NZ,T_WRITE_BAD
    LD A,(S2_BUF+10)
    CP 0FFh
    JR NZ,T_WRITE_BAD
    JR T_WRITE_OK
T_WRITE_BODY_OR_DIR:
    LD A,D
    CP 37
    JR NZ,T_WRITE_BODY
    LD A,E
    CP 1
    JR NZ,T_WRITE_BAD
    LD A,(S2_BUF)
    CP 'Q'
    JR NZ,T_WRITE_BAD
    LD A,(S2_BUF+9)
    OR A
    JR NZ,T_WRITE_BAD
    LD A,(S2_BUF+10)
    CP 72
    JR NZ,T_WRITE_BAD
    JR T_WRITE_OK
T_WRITE_BODY:
    LD A,D
    CP 36
    JR NZ,T_WRITE_BAD
    LD A,(T_BODIES)
    INC A
    LD (T_BODIES),A
    CP E
    JR NZ,T_WRITE_BAD
    LD B,A
    LD A,(HL)
    LD C,A
    LD A,B
    CP 10
    LD A,C
    JR NZ,T_BODY_EXPECT_A
    CP 01Ah
    JR NZ,T_WRITE_BAD
    JR T_BODY_PTR
T_BODY_EXPECT_A:
    CP 'A'
    JR NZ,T_WRITE_BAD
T_BODY_PTR:
    LD A,H
    SUB 090h
    INC A
    CP B
    JR NZ,T_WRITE_BAD
T_WRITE_OK:
    OR A
    RET
T_WRITE_BAD:
    LD A,8
    LD (T_FAILCODE),A
    SCF
    RET
T_FAIL1:
    LD A,(T_FAILCODE)
    OR A
    JP NZ,T_FAIL_HALT
    LD A,1
    JP T_FAIL
T_FAIL2: LD A,2
    JP T_FAIL
T_FAIL3: LD A,3
    JP T_FAIL
T_FAIL4: LD A,4
    JP T_FAIL
T_FAIL5: LD A,5
    JP T_FAIL
T_FAIL6: LD A,6
    JP T_FAIL
T_FAIL7: LD A,7
T_FAIL:
    LD (T_FAILCODE),A
T_FAIL_HALT:
    JR T_FAIL_HALT
'''
# 偽のsub ROMを使い、BANK2本体をN88 ROMの0x6000へ直接配置する。
program=(repo/'src/l4_basic/program.asm').read_text(encoding='utf-8')
direct=program[program.index('_bhl_direct:\n'):].split('\n; ---------------------------------------------------------------------',1)[0]
if fault=='prompt':
    direct=direct.replace('    XOR A\n    LD (SAVE_DONE_FLAG),A', '    LD A,1')
harness=harness.replace('    LD A,1\n    LD (T_PASS),A', '    CALL _bhl_direct\n    OR A\n    JP NZ,T_FAIL7\n    LD A,1\n    LD (T_PASS),A')
source=harness+'\nSAVE_DONE_FLAG EQU 0E24Bh\nBASIC_RUN_DIRECT:\n    LD A,1\n    LD (SAVE_DONE_FLAG),A\n    RET\n'+direct+'\n'+bank
p=out/'save_test.asm'; p.write_text(source,encoding='utf-8')
a=z80text.Assembler(); code=a.assemble(p)
if len(code)>0x8000: raise SystemExit('試験ROM超過')
rom=bytearray(0x8000); rom[:len(code)]=code
(out/'N88.ROM').write_bytes(rom)
disk=bytearray(0x800); disk[:2]=bytes((0x18,0xFE))
(out/'DISK.ROM').write_bytes(disk)
PY
}

last_values() {
  python3 - "$1" <<'PY'
import re,sys
last={}
for line in open(sys.argv[1],encoding='utf-8',errors='replace'):
    m=re.match(r'\s*\d+\s+\d+\s+[0-9A-Fa-f]{4}\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2})',line)
    if m: last[m.group(1).upper()]=m.group(2).upper()
print(last.get('E304','00'),last.get('E303','00'),last.get('E301','00'),last.get('E302','00'))
PY
}
run_one() {
  local kind="$1" out="$WORK/$1" log="$WORK/$1.memlog"
  make_rom "$out" "$kind"
  "$FRONTEND" --core "$CORE" --rom-dir "$out" --frames 30 \
    --mem-write-log "$log" --mem-write-range E300-E304 \
    >"$WORK/$1.stdout" 2>"$WORK/$1.stderr"
  last_values "$log"
}
read -r pass fail writes bodies <<<"$(run_one normal)"
[ "$pass" = 01 ] && [ "$fail" = 00 ] || { echo "NG: 正例($pass/$fail/$writes/$bodies)" >&2; exit 1; }
read -r pass fail writes bodies <<<"$(run_one order)"
[ "$pass" != 01 ] && [ "$fail" != 00 ] || { echo 'NG: 割当順の陰性対照' >&2; exit 1; }
read -r pass fail writes bodies <<<"$(run_one prompt)"
[ "$pass" != 01 ] && [ "$fail" != 00 ] || { echo 'NG: Ok抑止の陰性対照' >&2; exit 1; }
# LISTそのもののCR LF・0x1Aは公式なしのJ-1/J-2本体照合で確認する。
bash "$REPO/tools/conform_save.sh" >"$WORK/conform.out"
[ "$(grep -c $'\tOK$' "$WORK/conform.out")" = 6 ] || { echo 'NG: SAVE適合' >&2; exit 1; }
echo 'l4_save_z80_selftest: OK（10セクタ・2単位・旧鎖解放・FAT末尾保持・ERR61/68・陰性対照）'
