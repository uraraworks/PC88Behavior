; c1: STR_APPEND_UDECの同bank末尾。
    ORG 0x70C6
_sau_show:
    LD A,1
    LD (PUD_STARTED),A
    LD A,(PUD_DIGIT)
    ADD A,'0'
    CALL STR_APPEND_CHAR
_sau_advance:
    LD DE,2
    ADD IX,DE
    DJNZ _sau_again
    RET
_sau_again:
    JP _sau_place_loop
