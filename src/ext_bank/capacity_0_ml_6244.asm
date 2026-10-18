; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6244
ml0_part_6244:
    JP FN_MAIN_CALL_ADDR
ml0_copy:
    LD IX,CAP_ADDR_STR_COPY_BN
; 関数途中の空隙接続。次は0x6B25。
    JP ml0_part_6b25
