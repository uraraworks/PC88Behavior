; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6F13
ml3_part_6f13:
    POP BC
    JP ml3_call_user
ml3_call_fail:
    POP HL
    POP HL
    POP HL
    RET
; 関数途中の空隙接続。次は0x7403。
    JP ml3_part_7403
