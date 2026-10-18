; docs/spec/l4-basic.md 14.8。機能未測定の受理値は自作の空文字/0。
; 名前は完全一致。接頭辞の分割は未測定なので既存の識別子を保つ。
    ORG 0x789D
T3_RHS_ENTRY:
    CALL S9_IDENT_PEEK
    OR A
    RET Z
    CALL T3_LOOKUP
    OR A
    RET Z
    PUSH HL
    LD HL,(CUR_PTR)
    LD A,(MM_IDENT_LEN)
    LD E,A
    LD D,0
    ADD HL,DE
    LD (CUR_PTR),HL
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    POP HL
    CP '('
    JP Z,t3_rhs_call
    LD A,(HL)
    CP 253                      ; DATE$/TIME$の引数なし
    JP Z,t3_empty
    JP t3_rhs_error
t3_rhs_call:
    JP ml3_rhs_dispatch
    DB 0,0,0
t3_rhs_args:
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP ')'
    JP Z,t3_call_empty
    CALL S9_NUM_ARG
    CALL S9_BAD
    JP NZ,t3_arg_error
    POP AF
    CP 254                      ; INPのみ実際に読む
    JP Z,t3_inp
    OR A
    JP NZ,t3_rhs_error
    LD A,(MM_IDENT_BUF+7)
    CP '$'
    JP Z,t3_empty
    LD HL,0
    CALL S9_SET_INT
    JP t3_handled
    ORG 0x7CB7
t3_call_empty:
    POP AF
    LD A,2
    JP t3_rhs_error
t3_arg_error:
    POP AF
    JP t3_handled
t3_inp:
    CALL S9B_ADDRESS_CUR
    CALL S9_BAD
    JP NZ,t3_handled
    LD C,E
    LD B,0
    IN A,(C)
    LD L,A
    LD H,0
    CALL S9_SET_INT
    JP t3_handled
t3_empty:
    XOR A
    LD (MM_RUN_STR_TMP_LEN),A
    CALL S9_OK
    JP t3_handled
t3_rhs_error:
    CALL S9_ERROR
t3_handled:
    LD A,1
    RET
T3_RESERVED_END:
