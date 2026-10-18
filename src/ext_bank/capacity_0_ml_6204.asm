; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6204
ml0_part_6204:
    CALL ml0_copy
    POP DE
    POP HL
    LD (HL),E
    INC HL
    LD (HL),D
    POP HL
; 関数途中の空隙接続。次は0x6214。
    JP ml0_part_6214
