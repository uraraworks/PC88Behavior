; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7D23
ml3_part_7d23:
    LD DE,MM_INTERP_EXT_RAM_BASE+MM_VALUE_STACK_SIZE
    CALL ml3_zero_range
    RET
ml3_zero_b:
    XOR A
    LD (HL),A
    INC HL
; 関数途中の空隙接続。次は0x7D33。
    JP ml3_part_7d33
