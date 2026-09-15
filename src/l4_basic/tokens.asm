; L4_BASIC トークン表 — src/l4_basic/make_token_table.py が生成
; 手で編集しない（再実行で再生成する）。
; 入力: src/l4_basic/keywords.tsv（189語）。番号の規則は
; docs/notes/l4-token-design.md「追記（2026-09-15、番号の振り方）」。
;
; 引き方の並び順: 語の長さの降順（最長一致）。同じ長さは
; 大文字ASCII辞書順（昇順）で安定させてある。短い語が長い語の
; 先頭に一致する組（例: ON と ONERRORGOTO 系）があるため、
; 字句解析はこの並び順のまま先頭から順に試すこと。
;
; 各エントリ: db 語長, 語（ASCII文字列。$ @ 等の記号を含む）,
;            db トークン（1バイトまたは 0xFF+2バイト目の2バイト）
; 表の終端は 語長0 の番兵行。

L4_TOKEN_TABLE:
    db 9, "RANDOMIZE", 0xFF, 0x8B
    db 7, "CONSOLE", 0x9F
    db 7, "RESTORE", 0xFF, 0x90
    db 7, "STRING$", 0xFF, 0xA6
    db 6, "AKCNV$", 0x89
    db 6, "CIRCLE", 0x97
    db 6, "COMMON", 0x9E
    db 6, "CSRLIN", 0xA4
    db 6, "DEFDBL", 0xAB
    db 6, "DEFINT", 0xAC
    db 6, "DEFSNG", 0xAD
    db 6, "DEFSTR", 0xAE
    db 6, "DELETE", 0xAF
    db 6, "INKEY$", 0xCE
    db 6, "IRESET", 0xD3
    db 6, "KACNV$", 0xD5
    db 6, "KPLOAD", 0xDA
    db 6, "LFILES", 0xDF
    db 6, "LOCATE", 0xE5
    db 6, "LPRINT", 0xE9
    db 6, "OPTION", 0xFC
    db 6, "PRESET", 0xFF, 0x87
    db 6, "RESUME", 0xFF, 0x91
    db 6, "RETURN", 0xFF, 0x92
    db 6, "RIGHT$", 0xFF, 0x93
    db 6, "SCREEN", 0xFF, 0x99
    db 6, "SEARCH", 0xFF, 0x9A
    db 6, "SPACE$", 0xFF, 0x9E
    db 6, "STATUS", 0xFF, 0xA2
    db 6, "VARPTR", 0xFF, 0xB3
    db 6, "WINDOW", 0xFF, 0xBA
    db 5, "ATTR$", 0x8D
    db 5, "BLOAD", 0x90
    db 5, "BSAVE", 0x91
    db 5, "CHAIN", 0x94
    db 5, "CLEAR", 0x98
    db 5, "CLOSE", 0x99
    db 5, "COLOR", 0x9C
    db 5, "DATE$", 0xA9
    db 5, "DSKI$", 0xB2
    db 5, "DSKO$", 0xB3
    db 5, "ERASE", 0xB9
    db 5, "ERROR", 0xBC
    db 5, "FIELD", 0xBE
    db 5, "FILES", 0xBF
    db 5, "GO TO", 0xC6
    db 5, "GOSUB", 0xC7
    db 5, "INPUT", 0xD0
    db 5, "INSTR", 0xD1
    db 5, "KANJI", 0xD6
    db 5, "LEFT$", 0xDC
    db 5, "LLIST", 0xE2
    db 5, "MERGE", 0xEC
    db 5, "MOTOR", 0xF3
    db 5, "PAINT", 0xFF, 0x80
    db 5, "POINT", 0xFF, 0x83
    db 5, "PRINT", 0xFF, 0x88
    db 5, "RBYTE", 0xFF, 0x8C
    db 5, "RENUM", 0xFF, 0x8F
    db 5, "TIME$", 0xFF, 0xAC
    db 5, "TROFF", 0xFF, 0xAE
    db 5, "USING", 0xFF, 0xB0
    db 5, "WBYTE", 0xFF, 0xB6
    db 5, "WHILE", 0xFF, 0xB8
    db 5, "WIDTH", 0xFF, 0xB9
    db 5, "WRITE", 0xFF, 0xBB
    db 4, "AUTO", 0x8E
    db 4, "BEEP", 0x8F
    db 4, "CALL", 0x92
    db 4, "CDBL", 0x93
    db 4, "CHR$", 0x95
    db 4, "CINT", 0x96
    db 4, "CONT", 0xA0
    db 4, "COPY", 0xA1
    db 4, "CSNG", 0xA3
    db 4, "DATA", 0xA8
    db 4, "DSKF", 0xB1
    db 4, "EDIT", 0xB4
    db 4, "ELSE", 0xB5
    db 4, "FPOS", 0xC3
    db 4, "GOTO", 0xC8
    db 4, "HELP", 0xC9
    db 4, "HEX$", 0xCA
    db 4, "IEEE", 0xCB
    db 4, "ISET", 0xD4
    db 4, "KILL", 0xD8
    db 4, "KLEN", 0xD9
    db 4, "KPOS", 0xDB
    db 4, "LINE", 0xE0
    db 4, "LIST", 0xE1
    db 4, "LOAD", 0xE3
    db 4, "LPOS", 0xE8
    db 4, "LSET", 0xEA
    db 4, "MID$", 0xED
    db 4, "MKD$", 0xEE
    db 4, "MKI$", 0xEF
    db 4, "MKS$", 0xF0
    db 4, "NAME", 0xF4
    db 4, "NEXT", 0xF6
    db 4, "OCT$", 0xF8
    db 4, "OPEN", 0xFB
    db 4, "PEEK", 0xFF, 0x81
    db 4, "POKE", 0xFF, 0x84
    db 4, "POLL", 0xFF, 0x85
    db 4, "PSET", 0xFF, 0x89
    db 4, "READ", 0xFF, 0x8D
    db 4, "ROLL", 0xFF, 0x95
    db 4, "RSET", 0xFF, 0x96
    db 4, "SAVE", 0xFF, 0x98
    db 4, "SPC(", 0xFF, 0x9F
    db 4, "STEP", 0xFF, 0xA3
    db 4, "STOP", 0xFF, 0xA4
    db 4, "STR$", 0xFF, 0xA5
    db 4, "SWAP", 0xFF, 0xA7
    db 4, "TAB(", 0xFF, 0xA8
    db 4, "TERM", 0xFF, 0xAA
    db 4, "THEN", 0xFF, 0xAB
    db 4, "TRON", 0xFF, 0xAF
    db 4, "VIEW", 0xFF, 0xB4
    db 4, "WAIT", 0xFF, 0xB5
    db 4, "WEND", 0xFF, 0xB7
    db 3, "ABS", 0x88
    db 3, "AND", 0x8A
    db 3, "ASC", 0x8B
    db 3, "ATN", 0x8C
    db 3, "CLS", 0x9A
    db 3, "CMD", 0x9B
    db 3, "COM", 0x9D
    db 3, "COS", 0xA2
    db 3, "CVD", 0xA5
    db 3, "CVI", 0xA6
    db 3, "CVS", 0xA7
    db 3, "DEF", 0xAA
    db 3, "DIM", 0xB0
    db 3, "END", 0xB6
    db 3, "EOF", 0xB7
    db 3, "EQV", 0xB8
    db 3, "ERL", 0xBA
    db 3, "ERR", 0xBB
    db 3, "EXP", 0xBD
    db 3, "FIX", 0xC0
    db 3, "FOR", 0xC2
    db 3, "FRE", 0xC4
    db 3, "GET", 0xC5
    db 3, "IMP", 0xCD
    db 3, "INP", 0xCF
    db 3, "INT", 0xD2
    db 3, "KEY", 0xD7
    db 3, "LEN", 0xDD
    db 3, "LET", 0xDE
    db 3, "LOC", 0xE4
    db 3, "LOF", 0xE6
    db 3, "LOG", 0xE7
    db 3, "MAP", 0xEB
    db 3, "MOD", 0xF1
    db 3, "MON", 0xF2
    db 3, "NEW", 0xF5
    db 3, "NOT", 0xF7
    db 3, "OFF", 0xF9
    db 3, "OUT", 0xFE
    db 3, "PEN", 0xFF, 0x82
    db 3, "POS", 0xFF, 0x86
    db 3, "PUT", 0xFF, 0x8A
    db 3, "REM", 0xFF, 0x8E
    db 3, "RND", 0xFF, 0x94
    db 3, "RUN", 0xFF, 0x97
    db 3, "SET", 0xFF, 0x9B
    db 3, "SGN", 0xFF, 0x9C
    db 3, "SIN", 0xFF, 0x9D
    db 3, "SQR", 0xFF, 0xA0
    db 3, "SRQ", 0xFF, 0xA1
    db 3, "TAN", 0xFF, 0xA9
    db 3, "USR", 0xFF, 0xB1
    db 3, "VAL", 0xFF, 0xB2
    db 3, "XOR", 0xFF, 0xBC
    db 2, "FN", 0xC1
    db 2, "IF", 0xCC
    db 2, "ON", 0xFA
    db 2, "OR", 0xFD
    db 2, "TO", 0xFF, 0xAD
    db 1, "'", 0x80
    db 1, "*", 0x81
    db 1, "+", 0x82
    db 1, "-", 0x83
    db 1, "/", 0x84
    db 1, "<", 0x85
    db 1, "=", 0x86
    db 1, ">", 0x87
    db 1, "^", 0xFF, 0xBD
    db 1, "¥", 0xFF, 0xBE
    db 0        ; 番兵（語長0＝表の終端）
