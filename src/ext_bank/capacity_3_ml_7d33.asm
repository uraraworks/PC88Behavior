; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7D33
ml3_part_7d33:
    DEC B
    JP NZ,ml3_zero_b
    RET
ml3_zero_range:
    LD A,H
    CP D
    JP NZ,ml3_zero_store
; 関数途中の空隙接続。次は0x7D43。
    JP ml3_part_7d43
