; l4-program.md 10.1: RENUM入口と未定義参照の警告。処理本体はN側。
    ORG 0x6996
renum_try_bank:
    LD HL,(MM_LINE_END)
    LD DE,(MM_CUR_PTR)
    OR A
    SBC HL,DE
    LD A,L
    CP 5
    JR NC,rn_room
rn_nomatch:
    XOR A
    RET
rn_room:
    LD HL,(MM_CUR_PTR)
    LD DE,rn_word
    LD B,5
rn_match:
    LD A,(HL)
    AND 0DFh
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,rn_nomatch
    INC HL
    INC DE
    DJNZ rn_match
    PUSH HL
    LD DE,(MM_LINE_END)
    OR A
    SBC HL,DE
    POP HL
    JR Z,rn_matched
    LD A,(HL)
    AND 0DFh
    CP 'A'
    JR C,rn_matched
    CP 'Z'+1
    JR C,rn_nomatch
rn_matched:
    LD (MM_CUR_PTR),HL
    LD A,(MM_N_ROM_PRESENT)
    OR A
    JR NZ,rn_detected
    LD IX,RN_DETECT_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    LD A,(MM_N_ROM_PRESENT)
rn_detected:
    CP 1
    JR Z,rn_present
    LD A,5
    LD IX,RN_ERROR_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    LD A,1
    RET
rn_present:
    LD HL,0x3000
rn_invoke:
    CALL MM_N_ROM_CALL
    CP 2
    JR Z,rn_warning
    LD A,(MM_ERROR_FLAG)
    OR A
    JR NZ,rn_handled
    LD IX,RN_RESET_ADDR
    CALL BANK1_MAIN_CALL_ADDR
rn_handled:
    LD A,1
    RET
rn_warning:
    LD HL,rn_undefined
    CALL renum_print_text
    LD HL,(MM_RENUM_TARGET)
    LD IX,RN_UDEC_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    LD HL,rn_in
    CALL renum_print_text
    LD HL,(MM_RENUM_PTR)
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
    LD IX,RN_UDEC_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    LD IX,RN_NEWLINE_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    LD HL,0x3003
    JR rn_invoke
RN_DETECT_ADDR EQU 0x1787
RN_ERROR_ADDR EQU 0x1787
RN_RESET_ADDR EQU 0x1787
RN_UDEC_ADDR EQU 0x1787
RN_NEWLINE_ADDR EQU 0x1787
