; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7413
ml3_part_7413:
    LD A,'('
    CALL S9_EXPECT
    CALL S9_BAD
; 関数途中の空隙接続。次は0x7423。
    JP ml3_part_7423
