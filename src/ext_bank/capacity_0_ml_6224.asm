; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6224
ml0_part_6224:
    JP FN_MAIN_CALL_ADDR
ml0_address:
    LD IX,CAP_ADDR_ML_ADDRESS
; 関数途中の空隙接続。次は0x6234。
    JP ml0_part_6234
