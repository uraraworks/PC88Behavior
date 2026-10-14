; docs/spec/l4-basic.md 14.8 の誤り番号だけから作った表。
; 7文字の名前、明示$、引数なし/呼出し/左辺の番号。
; 全用法0の4語は既存変数/配列経路へ残す。
    ORG 0x6D30
T3_LOOKUP:
    LD IX,t3_words
t3_lookup_next:
    LD A,(IX+0)
    OR A
    RET Z
    PUSH IX
    POP HL
    LD DE,MM_IDENT_BUF
    LD B,7
t3_lookup_cmp:
    LD A,(DE)
    CP (HL)
    JR NZ,t3_lookup_skip
    INC HL
    INC DE
    DJNZ t3_lookup_cmp
    LD A,(MM_IDENT_SFX)
    CP 3
    LD A,0
    JR NZ,t3_lookup_suffix
    LD A,'$'
t3_lookup_suffix:
    CP (HL)
    JR NZ,t3_lookup_skip
    LD A,(MM_IDENT_SFX)
    OR A
    JR Z,t3_lookup_found
    CP 3
    JR NZ,t3_lookup_skip
t3_lookup_found:
    INC HL
    LD A,1
    RET
t3_lookup_skip:
    LD DE,11
    ADD IX,DE
    JR t3_lookup_next
t3_words:
    DB "ATTR",0,0,0,'$',2,2,2
    DB "DSKI",0,0,0,'$',2,2,2
    DB "MAP",0,0,0,0,0,2,2,2
    DB "SEARCH",0,0,2,2,2
    DB "VARPTR",0,0,2,2,2
    DB "CVD",0,0,0,0,0,2,13,2
    DB "CVI",0,0,0,0,0,2,13,2
    DB "CVS",0,0,0,0,0,2,13,2
    DB "DATE",0,0,0,'$',253,2,2
    DB "TIME",0,0,0,'$',253,2,2
    DB "DSKF",0,0,0,0,33,33,2
    DB "EOF",0,0,0,0,0,2,60,2
    DB "LOC",0,0,0,0,0,2,60,2
    DB "LOF",0,0,0,0,0,2,60,2
    DB "FPOS",0,0,0,0,2,56,2
    DB "INP",0,0,0,0,0,2,254,2
    DB "LPOS",0,0,0,0,2,0,2
    DB "MKD",0,0,0,0,'$',2,0,2
    DB "MKI",0,0,0,0,'$',2,0,2
    DB "MKS",0,0,0,0,'$',2,0,2
    DB "PEN",0,0,0,0,0,2,0,2
    DB "STATUS",0,0,33,33,33
    DB "USR",0,0,0,0,0,2,5,2
    DB 0
T3_WORDS_END:
