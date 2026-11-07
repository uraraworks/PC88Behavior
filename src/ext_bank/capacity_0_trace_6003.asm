; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x6003
trace_stmt:
    LD HL,CAP_TRACE_TRON_TEXT
    LD A,4
    CALL trace_match
    OR A
    JP trace_cond
