; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7423
ml3_part_7423:
    JP NZ,ml3_usr_pop
    CALL S9_IS_STRING
    OR A
    JP NZ,ml3_usr_string
; 関数途中の空隙接続。次は0x7433。
    JP ml3_part_7433
