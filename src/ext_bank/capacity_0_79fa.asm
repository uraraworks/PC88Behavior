; c1: INPUT_FIX_LITERAL。自作mainから移動、規則/処理は維持。
    ORG 0x79FA
INPUT_FIX_LITERAL:
    LD A,(CUR_TYPE)
    OR A
    RET NZ
    LD A,(CUR_DATA)
    OR A
    RET NZ
    LD A,(CUR_DATA+1)
    CP 0x80
    RET NZ
    LD HL,RUN_STR_TMP_BUF
    LD A,(RUN_STR_TMP_LEN)
    LD B,A
    LD A,(HL)
    CP '+'
    JR NZ,_ifl_digits
    INC HL
    DEC B
    RET Z
_ifl_digits:
    LD A,(HL)
    CP '0'
    RET C
    CP '9'+1
    RET NC
    INC HL
    DJNZ _ifl_digits
    CALL VAL_LOAD_CUR_TO_OPA
    CALL MBF_NEG
    JP VAL_SET_SINGLE_FROM_RES
