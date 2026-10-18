; §4.24。CALL/USR/DEF USR/VARPTR専用。配置予算内の断片。
    ORG 0x7463
ml3_part_7463:
    JP NZ,ml3_usr_fail
    POP AF
    POP DE
    PUSH AF
    LD C,0
; 関数途中の空隙接続。次は0x7473。
    JP ml3_part_7473
