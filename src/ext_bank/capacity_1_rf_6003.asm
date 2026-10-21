; l4-f2: ランダム機能本体。既存の入口・断片を動かさず空隙へ配置。
    ORG 0x6003
RF1_RF_FIELD:
    CALL RF1_CALL_sq_number
    CALL RF1_CALL_sq_bad
    RET NZ
    LD HL,0
    LD (MM_RF_OFFSET),HL
RF1_rf_field_loop:
    CALL RF1_CALL_sq_comma
    CALL RF1_CALL_sq_bad
    RET NZ
    CALL RF1_CALL_PARSE_INT_ARG
    CALL RF1_CALL_sq_bad
    RET NZ
    LD A,D
    OR A
    JP NZ,RF1_rf_overflow
    PUSH DE
    LD HL,(MM_RF_OFFSET)
    ADD HL,DE
    JP RF1_rf1_field_continue
