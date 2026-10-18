; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7EBF
ml3_part_7ebf:
    JP B3_MAIN_CALL_ADDR
ml3_call_user:
    LD IX,CAP_ADDR_ML_CALL_USER
    JP B3_MAIN_CALL_ADDR
ml3_invoke:
    LD IX,CAP_ADDR_ML_INVOKE
    JP B3_MAIN_CALL_ADDR

ml3_varptr:
    CALL B3_ADV_PTR
    LD IX,CAP_ADDR_ML_VARPTR
    CALL B3_MAIN_CALL_ADDR
    JP t3_handled
; 関数途中の空隙接続。次は0x6107。
    JP ml3_part_6107
