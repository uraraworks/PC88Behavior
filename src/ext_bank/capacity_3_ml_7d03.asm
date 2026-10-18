; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7D03
ml3_part_7d03:
    CALL ml3_zero_b
    LD A,(MM_VAL_SP)
    LD E,A
    LD D,0
    LD H,D
; 関数途中の空隙接続。次は0x7D13。
    JP ml3_part_7d13
