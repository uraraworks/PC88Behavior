; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x601C
trace_cond:
    JP Z,trace_try_off
    LD B,1
    JP trace_set
trace_try_off:
    LD HL,CAP_TRACE_TROFF_TEXT
    LD A,5
    CALL trace_match
    OR A
    JP trace_off_done
