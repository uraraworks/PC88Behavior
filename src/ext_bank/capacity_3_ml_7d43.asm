; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7D43
ml3_part_7d43:
    LD A,L
    CP E
    RET Z
ml3_zero_store:
    LD (HL),0
    INC HL
    JP ml3_zero_range
; 関数途中の空隙接続。次は0x7D53。
    JP ml3_part_7d53
