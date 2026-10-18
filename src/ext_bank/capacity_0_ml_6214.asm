; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6214
ml0_part_6214:
    JP fn_ok
ml0_expect:
    LD IX,CAP_ADDR_EXPECT_CHAR
; 関数途中の空隙接続。次は0x6224。
    JP ml0_part_6224
