; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7453
ml3_part_7453:
    JP NZ,ml3_usr_fail
    CALL S9_CLOSE
    CALL S9_BAD
; 関数途中の空隙接続。次は0x7463。
    JP ml3_part_7463
