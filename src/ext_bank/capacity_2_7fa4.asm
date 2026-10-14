; c1: STR_APPEND_UDEC。自作mainから移動、規則/処理は維持。
    ORG 0x7FA4
STR_APPEND_UDEC:
    LD (PUD_VALUE),HL
    XOR A
    LD (PUD_STARTED),A
    LD IX,CAP_PUD_PLACES
    LD B,5
_sau_place_loop:
    LD L,(IX+0)
    LD H,(IX+1)
    LD (PUD_PLACE),HL
    XOR A
    LD (PUD_DIGIT),A
_sau_sub_loop:
    LD HL,(PUD_VALUE)
    LD DE,(PUD_PLACE)
    OR A
    SBC HL,DE
    JR C,_sau_sub_done
    LD (PUD_VALUE),HL
    LD A,(PUD_DIGIT)
    INC A
    LD (PUD_DIGIT),A
    JP _sau_sub_loop
_sau_sub_done:
    LD A,B
    CP 1
    JR NZ,_sau_not_last
    LD A,(PUD_DIGIT)
    ADD A,'0'
    CALL STR_APPEND_CHAR
    JP _sau_advance
_sau_not_last:
    LD A,(PUD_DIGIT)
    OR A
    JP NZ,_sau_show
    LD A,(PUD_STARTED)
    OR A
    JP Z,_sau_advance
    JP _sau_show
