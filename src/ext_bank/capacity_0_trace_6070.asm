; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x6070
trace_off_done:
    RET Z
    LD B,0
    JP trace_set
trace_line_num:
    LD IX,CAP_ADDR_PRINT_UDEC
    CALL CAP_ADDR_MAIN_CALL
    JP trace_line_end
