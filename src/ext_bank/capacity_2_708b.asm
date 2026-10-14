; c1: INPUT_STORE。自作mainから移動、規則/処理は維持。
    ORG 0x708B
INPUT_STORE:
    LD A,H
    OR L
    JR Z,_in_plain
    LD (RUN_ARRAY_ASSIGN_ADDR),HL
    LD A,(RUN_ASSIGN_KIND)
    CP 3
    JP Z,ARRAY_STRING_STORE
    CP 1
    CALL Z,ARRAY_SINGLE
    LD A,(CUR_TYPE)
    LD C,2
    OR A
    JR Z,_in_array
    LD C,4
    CP 1
    JR Z,_in_array
    LD C,8
_in_array:
    LD B,0
    LD HL,CUR_DATA
    LD DE,(RUN_ARRAY_ASSIGN_ADDR)
    LDIR
    RET
_in_plain:
    LD A,(RUN_ASSIGN_KIND)
    CP 3
    JP Z,ASSIGN_STRING_FROM_TMP
    JP ASSIGN_NUMERIC_FROM_CUR
