; 第14.17版 4.13/4.13a。INPUTの引用内コンマと空白、LINE INPUTの行全体。
; 自作判断: LINE INPUTの末尾空白は命令側で除く。不整合引用は再入力。
it_token:
    XOR A
    LD (MM_RUN_STR_TMP_LEN),A
    LD (MM_ERROR_FLAG),A
    LD HL,(MM_CUR_PTR)
    LD DE,(MM_LINE_END)
    LD A,(MM_INPUT_LINE)
    OR A
    JR NZ,it_line
it_spaces:
    CALL it_end
    JR Z,it_done
    LD A,(HL)
    CP ' '
    JR NZ,it_start
    INC HL
    JR it_spaces
it_start:
    CP '"'
    JR NZ,it_bare
    INC HL
it_quote:
    CALL it_end
    JR Z,it_bad
    LD A,(HL)
    INC HL
    CP '"'
    JR Z,it_quote_end
    CALL it_put
    JR it_quote
it_quote_end:
    CALL it_end
    JR Z,it_done
    LD A,(HL)
    CP ','
    JR Z,it_done
    CP ' '
    JR NZ,it_bad
    INC HL
    JR it_quote_end
it_bare:
    CALL it_end
    JR Z,it_trim
    LD A,(HL)
    CP ','
    JR Z,it_trim
    INC HL
    CALL it_put
    JR it_bare
it_line:
    CALL it_end
    JR Z,it_trim
    LD A,(HL)
    INC HL
    CALL it_put
    JR it_line
it_trim:
    PUSH HL
    LD A,(MM_RUN_STR_TMP_LEN)
    LD C,A
    LD B,0
    LD HL,MM_RUN_STR_TMP_BUF
    ADD HL,BC
it_trim_loop:
    LD A,C
    OR A
    JR Z,it_trim_end
    DEC HL
    LD A,(HL)
    CP ' '
    JR NZ,it_trim_end
    DEC C
    JR it_trim_loop
it_trim_end:
    LD A,C
    LD (MM_RUN_STR_TMP_LEN),A
    POP HL
it_done:
    LD (MM_CUR_PTR),HL
    RET
it_bad:
    LD A,1
    LD (MM_ERROR_FLAG),A
    JR it_done
it_end:
    LD A,H
    CP D
    RET NZ
    LD A,L
    CP E
    RET
it_put:
    PUSH HL
    PUSH DE
    PUSH AF
    LD A,(MM_RUN_STR_TMP_LEN)
    LD E,A
    LD D,0
    LD HL,MM_RUN_STR_TMP_BUF
    ADD HL,DE
    INC A
    LD (MM_RUN_STR_TMP_LEN),A
    POP AF
    LD (HL),A
    POP DE
    POP HL
    RET
it_code_end:

