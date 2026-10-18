; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6406
ml3_part_6406:
    JP Z,ml3_varptr
    PUSH AF
    CALL B3_ADV_PTR
; 関数途中の空隙接続。次は0x6D25。
    JP ml3_part_6d25
