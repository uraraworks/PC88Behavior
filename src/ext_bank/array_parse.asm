; 配列引数解析。bank1の旧DIM本体の領域を再利用。
    ORG 0x7758
; 名前と評価済み添字はCPUスタックへ退避し、入れ子の配列式と独立させる。
; 自作判断: 通常入力行に収まる32次元まで。未測定の長い次元はERR 9。
ar_parse:
    LD HL,MM_IDENT_BUF
    LD B,4
ar_p_name:
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    PUSH DE
    DJNZ ar_p_name
    LD B,0
    CALL ar_adv
ar_p_loop:
    PUSH BC
    CALL ar_expr
    POP BC
    LD A,(MM_ERROR_FLAG)
    OR A
    JR NZ,ar_p_fail
    PUSH BC
    CALL ar_int
    POP BC
    JR C,ar_p_overflow
    BIT 7,D
    JR NZ,ar_p_negative
    PUSH DE
    INC B
    PUSH BC
    CALL ar_skip
    CALL ar_peek
    POP BC
    CP ','
    JR NZ,ar_p_close
    LD A,B
    CP 32
    JR NC,ar_p_range
    PUSH BC
    CALL ar_adv
    POP BC
    JR ar_p_loop
ar_p_close:
    CP ')'
    JR NZ,ar_p_syntax
    PUSH BC
    CALL ar_adv
    POP BC
    LD A,B
    LD (MM_AR_NDIM),A
    LD L,B
    LD H,0
    ADD HL,HL
    LD DE,MM_AR_ARGS
    ADD HL,DE
ar_p_pop:
    POP DE
    DEC HL
    LD (HL),D
    DEC HL
    LD (HL),E
    DJNZ ar_p_pop
    JR ar_p_restore
ar_p_syntax:
    LD A,2
    JR ar_p_error
ar_p_range:
    LD A,9
    JR ar_p_error
ar_p_overflow:
    LD A,6
    JR ar_p_error
ar_p_negative:
    LD A,5
ar_p_error:
    PUSH BC
    CALL ar_error
    POP BC
ar_p_fail:
    LD A,B
    OR A
    JR Z,ar_p_restore
ar_p_discard:
    POP DE
    DJNZ ar_p_discard
ar_p_restore:
    LD HL,MM_IDENT_BUF+7
    LD B,4
ar_p_restore_loop:
    POP DE
    LD (HL),D
    DEC HL
    LD (HL),E
    DEC HL
    DJNZ ar_p_restore_loop
    LD A,(MM_ERROR_FLAG)
    OR A
    RET


AP_SKIP_ADDR EQU 0x1787
ar_skip:
    LD IX,AP_SKIP_ADDR
    JP BANK1_MAIN_CALL_ADDR

AP_PEEK_ADDR EQU 0x1787
ar_peek:
    LD IX,AP_PEEK_ADDR
    JP BANK1_MAIN_CALL_ADDR

AP_ADV_ADDR EQU 0x1787
ar_adv:
    LD IX,AP_ADV_ADDR
    JP BANK1_MAIN_CALL_ADDR

AP_EXPR_ADDR EQU 0x1787
ar_expr:
    LD IX,AP_EXPR_ADDR
    JP BANK1_MAIN_CALL_ADDR

AP_INT_ADDR EQU 0x1787
ar_int:
    LD IX,AP_INT_ADDR
    JP BANK1_MAIN_CALL_ADDR

ar_error:
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
    RET
