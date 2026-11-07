; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x7A57
trace_line_end:
    LD A,']'
    LD IX,CAP_ADDR_PRINT_CHAR
    JP CAP_ADDR_MAIN_CALL
