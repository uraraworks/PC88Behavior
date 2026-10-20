; LOAD構文入口。処理本体は拡張バンク1。
LOAD_STMT:
    CALL SQ_CLOSE_ALL
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,1
    LD HL,06800h
    JP EXT_BANK_CALL
