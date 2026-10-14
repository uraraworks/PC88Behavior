; c1: LRT_MATCH。自作mainから移動、規則/処理は維持。
    ORG 0x780E
LRT_MATCH:
    LD A,(HL)
    OR A
    JR Z,_lm_end
    LD A,C
    OR A
    JR Z,_lm_fail
    LD A,(DE)
    CALL FOLD_UPPER
    CP (HL)
    JR NZ,_lm_fail
    INC HL
    INC DE
    DEC C
    JR LRT_MATCH
_lm_end:
    LD A,C
    OR A
    RET Z
    LD A,(DE)
    CALL LRT_NAMECH
    JR C,_lm_fail
    XOR A
    RET
_lm_fail:
    OR 1
    RET
