; c1: DATA_ENTER_RECORD。自作mainから移動、規則/処理は維持。
    ORG 0x6CAE
DATA_ENTER_RECORD:
    LD (RUN_DATA_REC),HL
    INC HL
    INC HL
    LD A,(HL)
    LD C,A
    LD B,0
    INC HL
    LD (CUR_PTR),HL
    ADD HL,BC
    LD (LINE_END),HL
    RET

DATA_ADVANCE_RECORD:
    LD HL,(RUN_DATA_REC)
    LD DE,2
    ADD HL,DE
    LD A,(HL)
    LD C,A
    LD B,0
    INC BC
    INC BC
    INC BC
    LD HL,(RUN_DATA_REC)
    ADD HL,BC
    LD A,(HL)
    LD B,A
    PUSH HL
    INC HL
    LD A,(HL)
    POP HL
    CP 0FFh
    JR NZ,_dar_have
    LD A,B
    CP 0FFh
    JR NZ,_dar_have
    XOR A
    RET
_dar_have:
    CALL DATA_ENTER_RECORD
    LD A,1
    RET
