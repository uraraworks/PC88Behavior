; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6273
ml0_part_6273:
    JP fn_ok
ml0_def_type:
    CALL fn_type
ml0_def_fail:
    POP DE
    RET
; 関数途中の空隙接続。次は0x6AEE。
    JP ml0_part_6aee
