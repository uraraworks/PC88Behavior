; 代入先はすでに識別子として消費済み。ERRがあれば代入を実行しない。
    ORG 0x6110
T3_LHS_ENTRY:
    CALL T3_LOOKUP
    OR A
    RET Z
    INC HL
    INC HL
    LD A,(HL)
    CALL S9_ERROR
    LD A,1
    RET
