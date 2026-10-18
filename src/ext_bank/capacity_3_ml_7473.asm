; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7473
ml3_part_7473:
    CALL ml3_table
    OR A
; 関数途中の空隙接続。次は0x7CE8。
    JP ml3_part_7ce8
