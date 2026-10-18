; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7483
ml3_part_7483:
    CALL ml3_zero_b
    LD HL,MM_MBF_OPA
    LD B,12
; 関数途中の空隙接続。次は0x7493。
    JP ml3_part_7493
