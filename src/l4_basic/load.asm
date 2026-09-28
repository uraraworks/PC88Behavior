; LOAD構文入口。処理本体は拡張バンク1。
LOAD_STMT:
    LD A,1
    LD HL,06800h
    JP EXT_BANK_CALL
