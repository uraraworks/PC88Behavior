; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7493
ml3_part_7493:
    CALL ml3_zero_b
    LD HL,MM_MBF_DOUBLE_RAM_BASE
    LD B,24
; 関数途中の空隙接続。次は0x7D03。
    JP ml3_part_7d03
