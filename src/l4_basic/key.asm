; docs/spec/l4-program.md 5.7（第14.19版、測定082347d）だけを根拠に実装。
; 未確定部分: 11文字まで保存、RUN/NEW/CLEARで既定へ戻す、押下展開なし。
; ON/OFFは独立状態だけ保持し、文字行とCONSOLEの窓を変えない。
    ORG 0x7A00
    JP ky_stmt
ky_stmt:
    CALL B3_SKIP_SPACES
    LD HL,ky_on
    CALL ky_match
    OR A
    JP NZ,ky_enable
    LD HL,ky_off
    CALL ky_match
    OR A
    JP NZ,ky_disable
    LD HL,ky_list
    CALL ky_match
    OR A
    JP NZ,ky_listing
    CALL ky_missing
    RET NZ
    CALL S9_IS_STRING
    OR A
    JP NZ,S9_TYPE
    CALL S9_PARSE_INT
    CALL S9_BAD
    RET NZ
    LD A,D
    OR A
    JP NZ,S9_ILLEGAL
    LD A,E
    DEC A
    CP 10
    JP NC,S9_ILLEGAL
    LD (MM_FKEY_INDEX),A
    CALL S9_COMMA
    CALL S9_BAD
    RET NZ
    CALL ky_missing
    RET NZ
    CALL S9_IS_STRING
    OR A
    JP Z,S9_TYPE
    CALL S9_STRING_EXPR
    CALL S9_BAD
    RET NZ
    CALL ky_end
    JP NZ,ky_syntax
    CALL ky_storage
    CALL S9_BAD
    RET NZ
    LD A,(MM_FKEY_INDEX)
    LD HL,(MM_FKEY_PTR)
    OR A
    JR Z,ky_store
    LD B,A
    LD DE,12
ky_find:
    ADD HL,DE
    DJNZ ky_find
ky_store:
    LD A,(S9_TMP_LEN)
    CP 12
    JR C,ky_store_len
    LD A,11
ky_store_len:
    LD (HL),A
    INC HL
    OR A
    JR Z,ky_redraw
    LD C,A
    LD B,0
    EX DE,HL
    LD HL,S9_TMP
    LDIR
    JR ky_redraw
ky_storage:
    LD HL,(MM_FKEY_PTR)
    LD A,H
    OR L
    RET NZ
    LD A,5
    LD IX,KY_ALLOC_ADDR
    CALL B3_MAIN_CALL_ADDR
    OR A
    JR NZ,ky_storage_new
    LD A,7
    JP S9_ERROR
ky_storage_new:
    LD B,8
    XOR A
ky_storage_name:
    LD (HL),A
    INC HL
    DJNZ ky_storage_name
    LD (HL),5
    INC HL
    LD (MM_FKEY_PTR),HL
    LD HL,062A8h
    LD A,1
    LD IX,KY_BANKCALL_ADDR
    JP B3_MAIN_CALL_ADDR
KY_ALLOC_ADDR EQU 0x1787
ky_redraw:
    LD HL,062A4h
    LD A,1
    LD IX,KY_BANKCALL_ADDR
    CALL B3_MAIN_CALL_ADDR
    JP S9_OK
ky_enable:
    LD A,1
    LD (MM_FKEY_ON),A
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP '1'                     ; 観測済みON 1だけを追加受理
    JR NZ,ky_on_end
    CALL B3_ADV_PTR
ky_on_end:
    CALL ky_end
    JP NZ,ky_syntax
    JP S9_OK
ky_disable:
    XOR A
    LD (MM_FKEY_ON),A
    CALL ky_end
    JP NZ,ky_syntax
    JP S9_OK
ky_missing:
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    OR A
    JR Z,ky_no_operand
    CP ':'
    JR Z,ky_no_operand
    XOR A
    RET
ky_no_operand:
    LD A,22
    CALL S9_ERROR
    LD A,1
    OR A
    RET
ky_end:
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    OR A
    RET Z
    CP ':'
    RET
ky_syntax:
    LD A,2
    JP S9_ERROR
ky_match:
    LD B,(HL)
    INC HL
    LD DE,(MM_CUR_PTR)
    PUSH HL
    LD HL,(MM_LINE_END)
    OR A
    SBC HL,DE
    LD A,H
    OR A
    JR NZ,ky_match_room
    LD A,L
    CP B
    JR C,ky_match_short
ky_match_room:
    POP HL
ky_match_loop:
    LD A,(DE)
    CALL ky_upper
    CP (HL)
    JR NZ,ky_match_fail
    INC HL
    INC DE
    DJNZ ky_match_loop
    LD HL,(MM_LINE_END)
    OR A
    SBC HL,DE
    JR Z,ky_match_yes
    LD A,(DE)
    CALL ky_upper
    CP 'A'
    JR C,ky_match_yes
    CP 'Z'+1
    JR C,ky_match_fail
ky_match_yes:
    LD H,D
    LD L,E
    LD (MM_CUR_PTR),HL
    LD A,1
    RET
ky_match_short:
    POP HL
ky_match_fail:
    XOR A
    RET
ky_upper:
    CP 'a'
    RET C
    CP 'z'+1
    RET NC
    SUB 32
    RET
KY_BANKCALL_ADDR EQU 0x1787
ky_on: DB 2,"ON"
ky_off: DB 3,"OFF"
ky_list: DB 4,"LIST"
; 独自一覧: 空行のあと5組。接頭部の非空白数5/4/6/5/5と自作既定値で45セル。
ky_listing:
    CALL ky_end
    JP NZ,ky_syntax
    LD HL,062ACh
    LD A,1
    LD IX,KY_BANKCALL_ADDR
    CALL B3_MAIN_CALL_ADDR
    CALL in_newline
    LD HL,ky_prefix
    LD DE,S9_ARG
    LD B,5
ky_list_slot:
    LD A,(HL)
    INC HL
    OR A
    JR Z,ky_list_value
    PUSH HL
    PUSH DE
    PUSH BC
    CALL in_print
    POP BC
    POP DE
    POP HL
    JR ky_list_slot
ky_list_value:
    PUSH HL
    PUSH BC
    PUSH DE
    LD A,(DE)
    LD B,A
    INC DE
    OR A
    JR Z,ky_list_newline
ky_list_char:
    LD A,(DE)
    INC DE
    PUSH DE
    PUSH BC
    CALL in_print
    POP BC
    POP DE
    DJNZ ky_list_char
ky_list_newline:
    CALL in_newline
    POP HL
    LD DE,12
    ADD HL,DE
    EX DE,HL
    POP BC
    POP HL
    DJNZ ky_list_slot
    JP S9_OK
ky_prefix: DB "K001:",0,"K02:",0,"KEY03:",0,"K004:",0,"K005:",0
KY_STMT_END:
