; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7CE8
ml3_part_7ce8:
    JP Z,ml3_usr_undefined
    LD C,(HL)
    INC HL
    LD B,(HL)
    INC HL
    LD A,(HL)
    OR A
    JP Z,ml3_usr_undefined
    POP AF
    JP ml3_invoke
ml3_usr_undefined:
    POP AF
    JP S9_ILLEGAL
ml3_usr_fail:
    POP AF
; 関数途中の空隙接続。次は0x7DF2。
    JP ml3_part_7df2
