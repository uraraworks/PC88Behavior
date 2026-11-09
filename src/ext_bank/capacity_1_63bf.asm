; l4-program.md 10.1: 警告文字列の各文字を主ROMの出力へ渡す。
    ORG 0x63BF
renum_print_text:
    LD A,(HL)
    INC HL
    OR A
    RET Z
    PUSH HL
    LD IX,RN_CHAR_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    POP HL
    JR renum_print_text
rn_undefined: DB "Undefined line ",0
RN_CHAR_ADDR EQU 0x1787
