; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x6254
ml0_part_6254:
    JP NZ,ml0_def_fail
    PUSH DE
    POP BC
    POP DE
    PUSH BC
    LD C,1
    CALL ml0_table
    POP DE
    OR A
    JP Z,fn_memory
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD (HL),1
; 関数途中の空隙接続。次は0x6273。
    JP ml0_part_6273
