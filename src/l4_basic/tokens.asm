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
    db 33, "IF...THEN...ELSE/IF...GOTO...ELSE", 0xD1
    db 22, "PRINTUSING/LPRINTUSING", 0xFF, 0x90
    db 20, "FOR...TO...STEP-NEXT", 0xC8
    db 20, "ON...GOSUB/ON...GOTO", 0xFD
    db 18, "DEFINT/SNG/DBL/STR", 0xB7
    db 17, "KEY(N)ON/OFF/STOP", 0xDC
    db 16, "TIME$ON/OFF/STOP", 0xFF, 0xB1
    db 15, "HELPON/OFF/STOP", 0xCF
    db 15, "STOPON/OFF/STOP", 0xFF, 0xA9
    db 14, "COMON/OFF/STOP", 0xAC
    db 14, "MK1$/MKS$/MKD$", 0xF5
    db 13, "LINEINPUTWAIT", 0xE8
    db 12, "CMDPCMRECORD", 0x9C
    db 12, "CMDVOICECOPY", 0xA5
    db 12, "FILES/LFILES", 0xC6
    db 12, "GOSUB-RETURN", 0xCD
    db 12, "ONTIME$GOSUB", 0xFF, 0x84
    db 12, "PRINT/LPRINT", 0xFF, 0x8F
    db 11, "CMDVOICELFO", 0xA6
    db 11, "CMDVOICEREG", 0xA7
    db 11, "CVI/CVS/CVD", 0xB3
    db 11, "ONERRORGOTO", 0xFF, 0x80
    db 11, "ONHELPGOSUB", 0xFF, 0x81
    db 11, "ONSTOPGOSUB", 0xFF, 0x83
    db 11, "PRINT#USING", 0xFF, 0x8E
    db 11, "WIDTHLPRINT", 0xFF, 0xBA
    db 10, "CMDPCMLOAD", 0x9A
    db 10, "CMDPCMPLAY", 0x9B
    db 10, "CMDPCMSAVE", 0x9D
    db 10, "CMDPCMSTOP", 0x9E
    db 10, "LINEINPUT#", 0xE7
    db 10, "ONCOMGOSUB", 0xFE
    db 10, "ONKEYGOSUB", 0xFF, 0x82
    db 10, "OPTIONBASE", 0xFF, 0x86
    db 10, "TRON/TROFF", 0xFF, 0xB2
    db 10, "WHILE-WEND", 0xFF, 0xB8
    db 9, "CMDRHYTHM", 0xA0
    db 9, "CMDUNLINK", 0xA3
    db 9, "GOTO/GOTO", 0xCE
    db 9, "INPUTWAIT", 0xD7
    db 9, "LINEINPUT", 0xE6
    db 9, "LIST/LUST", 0xE9
    db 9, "LSET/RSET", 0xF1
    db 9, "RANDOMIZE", 0xFF, 0x94
    db 8, "(1)PAINT", 0x80
    db 8, "(1)POINT", 0x81
    db 8, "(2)PAINT", 0x82
    db 8, "(2)POINT", 0x83
    db 8, "CMDSOUND", 0xA1
    db 8, "CMDSTOPM", 0xA2
    db 8, "CMDVOICE", 0xA4
    db 7, "CMDOUTM", 0x97
    db 7, "CMDPLAY", 0x9F
    db 7, "CONSOLE", 0xAD
    db 7, "ERL/ERR", 0xC2
    db 7, "KEYLIST", 0xDD
    db 7, "RESTORE", 0xFF, 0x98
    db 7, "STRING$", 0xFF, 0xAB
    db 6, "AKCNV$", 0x85
    db 6, "CIRCLE", 0x92
    db 6, "CMDBGM", 0x96
    db 6, "CMDPAL", 0x98
    db 6, "CMDPCM", 0x99
    db 6, "COLOR=", 0xA9
    db 6, "COLOR@", 0xAA
    db 6, "COMMON", 0xAB
    db 6, "CSRLIN", 0xB2
    db 6, "DEFUSR", 0xB8
    db 6, "DELETE", 0xB9
    db 6, "INKEY$", 0xD2
    db 6, "INPUT#", 0xD5
    db 6, "INPUT$", 0xD6
    db 6, "KACNV$", 0xDA
    db 6, "KPLOAD", 0xE0
    db 6, "LOCATE", 0xED
    db 6, "NEWCMD", 0xFA
    db 6, "PRESET", 0xFF, 0x8C
    db 6, "PRINT#", 0xFF, 0x8D
    db 6, "RESUME", 0xFF, 0x99
    db 6, "RIGHT$", 0xFF, 0x9A
    db 6, "SCREEN", 0xFF, 0x9F
    db 6, "SEARCH", 0xFF, 0xA0
    db 6, "SPACE$", 0xFF, 0xA4
    db 6, "STATUS", 0xFF, 0xA7
    db 6, "VARPTR", 0xFF, 0xB5
    db 6, "WINDOW", 0xFF, 0xBB
    db 6, "WRITE#", 0xFF, 0xBD
    db 5, "ATTR$", 0x88
    db 5, "BLOAD", 0x8B
    db 5, "BSAVE", 0x8C
    db 5, "CHAIN", 0x8F
    db 5, "CLEAR", 0x93
    db 5, "CLOSE", 0x94
    db 5, "COLOR", 0xA8
    db 5, "DATE$", 0xB5
    db 5, "DEFFN", 0xB6
    db 5, "DSKI$", 0xBC
    db 5, "DSKO$", 0xBD
    db 5, "ERASE", 0xC1
    db 5, "ERROR", 0xC3
    db 5, "FIELD", 0xC5
    db 5, "INPUT", 0xD4
    db 5, "INSTR", 0xD8
    db 5, "LEFT$", 0xE2
    db 5, "LOAD?", 0xEB
    db 5, "MERGE", 0xF3
    db 5, "MOTOR", 0xF7
    db 5, "NEWON", 0xFB
    db 5, "POINT", 0xFF, 0x89
    db 5, "RENUM", 0xFF, 0x97
    db 5, "TIME$", 0xFF, 0xB0
    db 5, "WIDTH", 0xFF, 0xB9
    db 5, "WRITE", 0xFF, 0xBC
    db 4, "AUTO", 0x89
    db 4, "BEEP", 0x8A
    db 4, "CALL", 0x8D
    db 4, "CDBL", 0x8E
    db 4, "CHR$", 0x90
    db 4, "CINT", 0x91
    db 4, "CONT", 0xAE
    db 4, "COPY", 0xAF
    db 4, "CSNG", 0xB1
    db 4, "DATA", 0xB4
    db 4, "DSKF", 0xBB
    db 4, "EDIT", 0xBE
    db 4, "FPOS", 0xC9
    db 4, "GET@", 0xCC
    db 4, "HEX$", 0xD0
    db 4, "KILL", 0xDE
    db 4, "KLEN", 0xDF
    db 4, "KPOS", 0xE1
    db 4, "LINE", 0xE5
    db 4, "LOAD", 0xEA
    db 4, "LPOS", 0xF0
    db 4, "MID$", 0xF4
    db 4, "NAME", 0xF8
    db 4, "OCT$", 0xFC
    db 4, "OPEN", 0xFF, 0x85
    db 4, "PEEK", 0xFF, 0x88
    db 4, "POKE", 0xFF, 0x8A
    db 4, "PSET", 0xFF, 0x91
    db 4, "PUT@", 0xFF, 0x93
    db 4, "READ", 0xFF, 0x95
    db 4, "ROLL", 0xFF, 0x9C
    db 4, "SAVE", 0xFF, 0x9E
    db 4, "STOP", 0xFF, 0xA8
    db 4, "STR$", 0xFF, 0xAA
    db 4, "SWAP", 0xFF, 0xAC
    db 4, "TERM", 0xFF, 0xAF
    db 4, "VIEW", 0xFF, 0xB6
    db 4, "WAIT", 0xFF, 0xB7
    db 3, "ABS", 0x84
    db 3, "ASC", 0x86
    db 3, "ATN", 0x87
    db 3, "CLS", 0x95
    db 3, "COS", 0xB0
    db 3, "DIM", 0xBA
    db 3, "END", 0xBF
    db 3, "EOF", 0xC0
    db 3, "EXP", 0xC4
    db 3, "FIX", 0xC7
    db 3, "FRE", 0xCA
    db 3, "GET", 0xCB
    db 3, "INP", 0xD3
    db 3, "INT", 0xD9
    db 3, "KEY", 0xDB
    db 3, "LEN", 0xE3
    db 3, "LET", 0xE4
    db 3, "LOC", 0xEC
    db 3, "LOF", 0xEE
    db 3, "LOG", 0xEF
    db 3, "MAP", 0xF2
    db 3, "MON", 0xF6
    db 3, "NEW", 0xF9
    db 3, "OUT", 0xFF, 0x87
    db 3, "POS", 0xFF, 0x8B
    db 3, "PUT", 0xFF, 0x92
    db 3, "REM", 0xFF, 0x96
    db 3, "RND", 0xFF, 0x9B
    db 3, "RUN", 0xFF, 0x9D
    db 3, "SET", 0xFF, 0xA1
    db 3, "SGN", 0xFF, 0xA2
    db 3, "SIN", 0xFF, 0xA3
    db 3, "SPC", 0xFF, 0xA5
    db 3, "SQR", 0xFF, 0xA6
    db 3, "TAB", 0xFF, 0xAD
    db 3, "TAN", 0xFF, 0xAE
    db 3, "USR", 0xFF, 0xB3
    db 3, "VAL", 0xFF, 0xB4
    db 0        ; 番兵（語長0＝表の終端）
