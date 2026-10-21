; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6107
ml3_part_6107:

ml3_rhs_dispatch:
    INC HL
    LD A,(HL)
    CP 251
; 関数途中の空隙接続。次は0x6406。
    ; 通常の番号はCP 251後の符号が正。条件JPは常に10ステート。
    ; RFの0x82..0x98だけを空き2Bの枝から共通常駐部へ渡す。
    JP P,ml3_part_6406
    JR rf_func_bridge
