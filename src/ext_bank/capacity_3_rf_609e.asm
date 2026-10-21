; l4-f2: ランダム機能本体。既存の入口・断片を動かさず空隙へ配置。
    ORG 0x609E
RF3_rf_make:
    PUSH AF
    LD A,'('
    CALL EXPECT_CHAR
    CALL S9_BAD
    JP NZ,RF3_rf_make_bad
    CALL RF3_CALL_LOGIC_OR_EXPR
    CALL S9_BAD
    JP NZ,RF3_rf_make_bad
    LD A,')'
    CALL EXPECT_CHAR
    CALL S9_BAD
    JP NZ,RF3_rf_make_bad
    POP AF
    PUSH AF
    CP 2
    JP NZ,RF3_rf_make_float
    CALL RF3_CALL_CUR_TO_INT16
    OR A
    JP Z,RF3_rf_make_overflow
    LD (MM_RUN_STR_TMP_BUF),DE
    POP AF
    LD (MM_RUN_STR_TMP_LEN),A
    RET
RF3_rf_make_float:
    CP 4
    JP NZ,RF3_rf_make_double
    CALL RF3_CALL_VAL_LOAD_CUR_TO_OPA
    LD HL,MM_MBF_OPA
    LD BC,4
    JP RF3_rf_make_copy
RF3_rf_make_double:
    CALL RF3_CALL_VAL_LOAD_CUR_TO_OPA_D
    LD HL,MM_MBF_DOUBLE_RAM_BASE
    LD BC,8
    JP RF3_rf_make_copy
