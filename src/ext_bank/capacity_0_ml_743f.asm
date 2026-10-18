; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x743F
ml0_part_743f:
    CALL fn_peek
    CP ')'
    JP Z,ml0_varptr_valid
    CP '('
    JP NZ,ml0_varptr_bad
ml0_varptr_valid:
    POP HL
; 関数途中の空隙接続。次は0x77A9。
    JP ml0_part_77a9
