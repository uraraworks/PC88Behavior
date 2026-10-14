; c1: STR_FROM_CUR。自作mainから移動、規則/処理は維持。
    ORG 0x6F71
STR_FROM_CUR:
    XOR A
    LD (RUN_STR_TMP_LEN),A
    LD A,(CUR_TYPE)
    CP 2
    JR NZ,_sfc_check_int
    CALL VAL_LOAD_CUR_TO_OPA_D
    CALL MBF_DTOS
    CALL VAL_SET_SINGLE_FROM_RES
_sfc_check_int:
    LD A,(CUR_TYPE)
    OR A
    JR NZ,_sfc_single
    LD HL,(CUR_DATA)
    BIT 7,H
    JR Z,_sfc_int_pos
    XOR A
    SUB L
    LD L,A
    LD A,0
    SBC A,H
    LD H,A
    LD A,'-'
    CALL STR_APPEND_CHAR
    JR _sfc_int_digits
_sfc_int_pos:
    LD A,' '
    CALL STR_APPEND_CHAR
_sfc_int_digits:
    JP STR_APPEND_UDEC
_sfc_single:
    CALL VAL_LOAD_CUR_TO_OPA
    CALL MBF_FOUT
    LD A,(UA_EXP)
    OR A
    JR Z,_sfc_s_zero_sign
    LD A,(FOUT_SIGN)
    OR A
    JR NZ,_sfc_s_neg
_sfc_s_zero_sign:
    LD A,' '
    CALL STR_APPEND_CHAR
    JR _sfc_s_digits
_sfc_s_neg:
    LD A,'-'
    CALL STR_APPEND_CHAR
_sfc_s_digits:
    LD A,(FOUT_LEN)
    LD B,A
    LD C,0
_sfc_s_loop:
    LD A,B
    OR A
    RET Z
    PUSH BC
    LD HL,FOUT_BUF
    LD D,0
    LD E,C
    ADD HL,DE
    LD A,(HL)
    CALL STR_APPEND_CHAR
    POP BC
    INC C
    DEC B
    JR _sfc_s_loop
