; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x77D3
trace_valid:
    POP BC
    LD A,B
    LD (MM_TRACE_ENABLED),A
    LD A,1
    RET
