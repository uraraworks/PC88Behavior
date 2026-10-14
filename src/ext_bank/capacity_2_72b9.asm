; c1: STR_APPEND_CHAR。自作mainから移動、規則/処理は維持。
    ORG 0x72B9
STR_APPEND_CHAR:
    PUSH BC
    LD B,A
    LD A,(RUN_STR_TMP_LEN)
    CP 255
    JR NC,_sac_full
    PUSH HL
    PUSH DE
    LD HL,RUN_STR_TMP_BUF
    LD E,A
    LD D,0
    ADD HL,DE
    LD (HL),B
    POP DE
    POP HL
    LD A,(RUN_STR_TMP_LEN)
    INC A
    LD (RUN_STR_TMP_LEN),A
_sac_full:
    POP BC
    RET
