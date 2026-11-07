; l4-program.md 9.2: TRON/TROFF と行番号表示。
    ORG 0x77C3
trace_check:
    OR A
    JP Z,trace_valid
    CP ':'
    JP NZ,trace_error
    JP trace_valid
