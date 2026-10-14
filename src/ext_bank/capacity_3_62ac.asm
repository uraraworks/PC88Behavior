; c1: DATA_PARSE_RAW_TOKEN。自作mainから移動、規則/処理は維持。
    ORG 0x62AC
DATA_PARSE_RAW_TOKEN:
    XOR A
    LD (RUN_STR_TMP_LEN),A
_dprt_loop:
    CALL AT_END
    JR Z,_dprt_done
    CALL PEEK_CHAR
    CP ','
    JR Z,_dprt_done
    CP ':'
    JR Z,_dprt_done
    LD B,A
    LD A,(RUN_STR_TMP_LEN)
    CP 255
    JR NC,_dprt_skip
    LD HL,RUN_STR_TMP_BUF
    LD D,0
    LD E,A
    ADD HL,DE
    LD (HL),B
    LD A,(RUN_STR_TMP_LEN)
    INC A
    LD (RUN_STR_TMP_LEN),A
_dprt_skip:
    CALL ADV_PTR
    JR _dprt_loop
_dprt_done:
    XOR A
    LD (ERROR_FLAG),A
    RET
