; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x77F3
trace_match:
    LD (MM_RUN_KW_TEXT),HL
    LD (MM_RUN_KW_LEN),A
    LD IX,CAP_TRACE_MATCH
    JP CAP_ADDR_MAIN_CALL
