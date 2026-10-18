; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x77A9
ml0_part_77a9:
    LD (MM_CUR_PTR),HL
    CALL ML0_LVALUE_ENTRY
    CALL fn_bad
    RET NZ
ml0_varptr_close:
    PUSH HL
    LD A,')'
    CALL ml0_expect
    POP HL
    CALL fn_bad
; 関数途中の空隙接続。次は0x7A2C。
    JP ml0_part_7a2c
