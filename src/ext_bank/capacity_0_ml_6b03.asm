; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6B03
ml0_part_6b03:
    CALL fn_adv
    CALL fn_expr
    CALL fn_bad
    RET NZ
; 関数途中の空隙接続。次は0x6B33。
    JP ml0_part_6b33
