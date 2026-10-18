; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6F03
ml3_part_6f03:
    LD A,2
    CALL S9_ERROR
    JP ml3_call_fail
ml3_call_valid:
    POP DE
    POP HL
; 関数途中の空隙接続。次は0x6F13。
    JP ml3_part_6f13
