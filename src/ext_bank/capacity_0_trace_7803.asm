; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x7803
trace_line:
    LD A,(MM_TRACE_ENABLED)
    OR A
    RET Z
    LD A,'['
    JP trace_line_start
