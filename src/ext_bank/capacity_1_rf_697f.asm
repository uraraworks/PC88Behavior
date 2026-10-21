; l4-f2: ランダム機能本体。既存の入口・断片を動かさず空隙へ配置。
    ORG 0x697F
RF1_rf_field_next:
    LD HL,(MM_RF_OFFSET)
    LD B,0
    ADD HL,BC
    LD (MM_RF_OFFSET),HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JP Z,RF1_rf_field_loop
    JP RF1_CALL_rf_end
