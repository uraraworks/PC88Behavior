; l4-f2: ランダム機能本体。既存の入口・断片を動かさず空隙へ配置。
    ORG 0x602A
RF3_rf_set:
    PUSH AF
    CALL SKIP_SPACES
    CALL LEX_IDENT_CONSUME
    CP 3
    JR NZ,RF3_rf_set_syntax
    CALL RF3_CALL_VAR_GET_OR_CREATE
    OR A
    JR Z,RF3_rf_set_memory
    PUSH HL
    LD A,'='
    CALL EXPECT_CHAR
    CALL S9_BAD
    JR NZ,RF3_rf_set_bad
    CALL STRING_EXPR
    CALL S9_BAD
    JR NZ,RF3_rf_set_bad
    POP HL
    POP AF
    PUSH AF
    LD DE,9
    ADD HL,DE
    LD A,(HL)
    INC HL
    LD C,(HL)
    INC HL
    CP 2
    JR C,RF3_rf_set_address
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
RF3_rf_set_address:
    POP AF
    LD D,A
    LD A,(MM_RUN_STR_TMP_LEN)
    CP C
    JR C,RF3_rf_set_short
    LD A,C
RF3_rf_set_short:
    LD E,A                    ; E=コピー長、C=元の長さ
    LD A,C
    SUB E
    LD B,A                    ; B=空白数
    LD A,D
    OR A
    JR Z,RF3_rf_set_left
    CALL RF3_rf_spaces
    LD B,E
    LD DE,MM_RUN_STR_TMP_BUF
    EX DE,HL
    JP RF3_CALL_STR_COPY_BN
RF3_rf_set_left:
    PUSH BC
    LD B,E
    LD DE,MM_RUN_STR_TMP_BUF
    EX DE,HL
    CALL RF3_CALL_STR_COPY_BN
    EX DE,HL
    POP BC
RF3_rf_spaces:
    LD A,B
    OR A
    RET Z
RF3_rf_spaces_loop:
    LD (HL),' '
    INC HL
    DJNZ RF3_rf_spaces_loop
    RET
RF3_rf_set_bad:
    POP HL
    POP AF
    RET
RF3_rf_set_syntax:
    POP AF
    JP RF3_CALL_sq_syntax
RF3_rf_set_memory:
    POP AF
    LD A,7
    JP S9_ERROR
