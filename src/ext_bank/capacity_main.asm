
; c1: SAVE捕捉もmainの窓を復元してからbank1へ入る。
LIST_RENDER_ALL:
    PUSH AF
    LD A,1
    LD IX,0x7FB9
    JP CAPACITY_BANK_CALL

TRACE_TRON_TEXT: DB "TRON"
TRACE_TROFF_TEXT: DB "TROFF"
DELETE_TEXT: DB "DELETE"
DELETE_PARSE_FIND:
    CALL SKIP_SPACES
    CALL PARSE_LINENUM_CUR
    RET C
    JP RUN_FIND_LINE

; 初めてDELETEを使うときに中継を配置し、ROMの有無を記憶する。
N_ROM_CALL EQU MM_N_ROM_CALL
N_DELETE_STMT:
    LD HL,DELETE_TEXT
    LD (MM_RUN_KW_TEXT),HL
    LD A,6
    LD (MM_RUN_KW_LEN),A
    CALL TRY_MATCH_KEYWORD_GENERIC
    OR A
    RET Z
    LD HL,0x7600
    JR n_common_call

AUTO_STRIP_MARK:
    LD A,(MM_AUTO_ACTIVE)
    AND 6
    CP 6
    RET NZ
    LD HL,LINE_BUF
    LD A,(VAR_LINELEN)
    LD B,A
    OR A
    RET Z
_auto_strip:
    LD A,(HL)
    CP '*'
    JR Z,_auto_strip_found
    CP '0'
    RET C
    CP '9'+1
    RET NC
    INC HL
    DJNZ _auto_strip
    RET
_auto_strip_found:
    LD (HL),' '
    RET

; l4-program.md 10.2: AUTO の引数解析はN側で実行する。
AUTO_TEXT: DB "AUTO"
N_AUTO_STMT:
    LD HL,AUTO_TEXT
    LD (MM_RUN_KW_TEXT),HL
    LD A,4
    LD (MM_RUN_KW_LEN),A
    CALL TRY_MATCH_KEYWORD_GENERIC
    OR A
    RET Z
    LD HL,0x2000
n_common_call:
    PUSH HL
    LD A,(MM_N_ROM_PRESENT)
    OR A
    CALL Z,N_DETECT
    LD A,(MM_N_ROM_PRESENT)
    POP HL
    CP 1
    JR Z,n_common_present
    LD A,5
    CALL ERR_SET_A
    LD A,1
    RET
n_common_present:
    CALL N_ROM_CALL
    LD A,1
    OR A
    RET

FKEY_WORD EQU IK_NAME+2
FKEY_OFF_WORD EQU TRACE_TROFF_TEXT+2
FKEY_ENSURE:
    LD HL,(MM_FKEY_PTR)
    LD A,H
    OR L
    RET NZ
    LD HL,0700Bh
    LD A,3
    JP EXT_BANK_CALL

INCLUDE "../l4_basic/inkey_main.asm"
