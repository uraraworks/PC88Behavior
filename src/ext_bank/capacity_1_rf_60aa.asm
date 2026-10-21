; l4-f2: ランダム機能本体。既存の入口・断片を動かさず空隙へ配置。
    ORG 0x60AA
RF1_rf1_field_continue:
    LD DE,256
    OR A
    SBC HL,DE
    JP Z,RF1_rf_field_fits
    JP C,RF1_rf_field_fits
    POP DE
    JP RF1_rf_overflow
RF1_rf_field_fits:
    LD HL,CAP_ADDR_RF_AS_WORD
    LD A,2
    CALL RF1_CALL_sq_keyword
    OR A
    JP Z,RF1_rf_field_syntax
    CALL SKIP_SPACES
    CALL RF1_CALL_LEX_IDENT_CONSUME
    CP 3
    JP NZ,RF1_rf_field_syntax
    POP BC
    LD HL,(MM_SQ_CURRENT)
    LD A,H
    OR L
    JP Z,RF1_rf_field_next
    PUSH BC
    XOR A
    LD (MM_RUN_STR_TMP_LEN),A
    CALL RF1_CALL_VAR_WRITE_STRING
    POP BC
    CALL RF1_CALL_sq_bad
    RET NZ
    LD DE,9
    ADD HL,DE
    LD (HL),3
    INC HL
    LD (HL),C
    INC HL
    PUSH HL
    CALL RF1_CALL_sq_current
    CALL RF1_CALL_sq_buffer
    LD DE,(MM_RF_OFFSET)
    ADD HL,DE
    EX DE,HL
    POP HL
    LD (HL),E
    INC HL
    LD (HL),D
    JP RF1_rf_field_next
RF1_rf_field_syntax:
    POP DE
    JP RF1_CALL_sq_syntax
RF1_rf_overflow:
    LD A,50
    JP RF1_CALL_SQ_ERROR
