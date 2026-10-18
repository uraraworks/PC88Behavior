; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6B53
ml0_part_6b53:
    JP FN_MAIN_CALL_ADDR

ml0_varptr_bad:
    POP HL
    JP fn_syntax
