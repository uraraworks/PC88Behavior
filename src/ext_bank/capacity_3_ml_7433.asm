; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7433
ml3_part_7433:
    CALL S9B_EXPR
    LD A,(MM_CUR_TYPE)
    JP ml3_usr_close
; 関数途中の空隙接続。次は0x7443。
    JP ml3_part_7443
