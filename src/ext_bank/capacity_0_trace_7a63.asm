; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x7A63
trace_line_start:
    LD IX,CAP_ADDR_PRINT_CHAR
    CALL CAP_ADDR_MAIN_CALL
    LD HL,(MM_RUN_CUR_LINENO)
    JP trace_line_num
