; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6B25
ml0_part_6b25:
    JP FN_MAIN_CALL_ADDR

ml0_def_fwd:
    LD IX,CAP_ADDR_ML_DEF
; 関数途中の空隙接続。次は0x6B53。
    JP ml0_part_6b53
