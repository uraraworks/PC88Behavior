; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6107
ml3_part_6107:

ml3_rhs_dispatch:
    INC HL
    LD A,(HL)
    CP 251
; 関数途中の空隙接続。次は0x6406。
    JP ml3_part_6406
