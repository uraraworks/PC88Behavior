; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x63F0
ml3_part_63f0:
    CALL S9_BAD
    RET NZ
    CALL S9B_ADDRESS_CUR
    CALL S9_BAD
    RET NZ
    PUSH DE
; 関数途中の空隙接続。次は0x647B。
    JP ml3_part_647b
