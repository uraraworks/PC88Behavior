; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x72F4
ml3_part_72f4:
    CALL ml3_zero_b
    LD HL,MM_RHS_DATA
    LD B,8
; 関数途中の空隙接続。次は0x7483。
    JP ml3_part_7483
