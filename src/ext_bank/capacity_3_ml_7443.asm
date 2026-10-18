; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7443
ml3_part_7443:
ml3_usr_string:
    CALL S9_STRING_EXPR
    LD A,3
ml3_usr_close:
    PUSH AF
    CALL S9_BAD
; 関数途中の空隙接続。次は0x7453。
    JP ml3_part_7453
