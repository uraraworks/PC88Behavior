; FILES構文入口。処理本体は拡張バンク1。
FILES_STMT:
    LD A,1
    LD HL,06600h
    JP EXT_BANK_CALL
