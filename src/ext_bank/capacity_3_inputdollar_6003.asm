; l4-basic.md 26: INPUT$(n)の引数をCINTと同じ規則で整数化する。
    ORG 0x6003
input_dollar:
    CALL S9_BYTE_ARG
    CALL S9_BAD
    RET NZ
    LD A,E
    OR A
    JP Z,S9_ILLEGAL
    PUSH DE
    CALL S9_CLOSE
    POP DE
    CALL S9_BAD
    RET NZ
    LD A,E
    LD (MM_RUN_ARG1),A
    XOR A
    LD (S9_TMP_LEN),A
    JP input_dollar_wait
