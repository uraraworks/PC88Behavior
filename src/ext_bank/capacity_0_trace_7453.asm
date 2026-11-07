; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x7453
trace_peek:
    LD IX,CAP_ADDR_PEEK_CHAR
    CALL CAP_ADDR_MAIN_CALL
    JP trace_check
