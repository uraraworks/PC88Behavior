; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x77E3
trace_error:
    POP BC
    LD A,2
    LD IX,CAP_TRACE_ERROR
    CALL CAP_ADDR_MAIN_CALL
    LD A,1
    RET
