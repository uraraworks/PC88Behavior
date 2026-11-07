; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x6B63
trace_set:
    PUSH BC
    LD IX,CAP_ADDR_SKIP_SPACES
    CALL CAP_ADDR_MAIN_CALL
    JP trace_peek
