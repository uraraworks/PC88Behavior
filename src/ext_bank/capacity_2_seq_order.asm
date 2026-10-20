; 既存のSAVE割当順を参照するだけの入口。
    ORG 0x6640
sq_border:
    LD A,(MM_SQ_TOKEN)
    LD E,A
    LD D,0
    LD HL,s2_order
    ADD HL,DE
    LD A,(HL)
    RET
