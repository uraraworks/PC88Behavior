; c1: MID_COMPUTE。自作mainから移動、規則/処理は維持。
    ORG 0x73EE
MID_COMPUTE:
    LD (RUN_TMP16),DE
    LD A,(RUN_ARG1)
    OR A
    JR NZ,_mc_start_nz
    LD A,1
_mc_start_nz:
    LD B,A
    LD A,(RUN_STR_ARG1_LEN)
    LD C,A
    LD A,B
    CP C
    JR Z,_mc_have_start
    JR C,_mc_have_start
    XOR A
    LD (RUN_STR_TMP_LEN),A
    XOR A
    LD (ERROR_FLAG),A
    RET
_mc_have_start:
    LD A,C
    SUB B
    INC A
    LD D,A
    LD A,(RUN_TMP16)
    LD E,A
    LD A,D
    CP E
    JR C,_mc_use_avail
    LD A,E
    JR _mc_have_copylen
_mc_use_avail:
    LD A,D
_mc_have_copylen:
    LD (RUN_STR_TMP_LEN),A
    OR A
    JR NZ,_mc_copy
    XOR A
    LD (ERROR_FLAG),A
    RET
_mc_copy:
    LD C,A
    LD HL,RUN_STR_ARG1_BUF
    LD D,0
    LD A,B
    DEC A
    LD E,A
    ADD HL,DE
    LD DE,RUN_STR_TMP_BUF
    LD B,C
    CALL CAP_STR_COPY_BN
    XOR A
    LD (ERROR_FLAG),A
    RET
