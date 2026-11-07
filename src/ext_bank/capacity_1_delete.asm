; l4-program.md 9.1: 指定行の存在と文末を検証してから削除する。
    ORG 0x6998
delete_stmt:
    LD HL,CAP_DELETE_TEXT
    LD (MM_RUN_KW_TEXT),HL
    LD A,6
    LD (MM_RUN_KW_LEN),A
    LD IX,CAP_TRACE_MATCH
    CALL CAP_ADDR_MAIN_CALL
    OR A
    RET Z
    CALL delete_peek
    CP '-'
    JR Z,delete_from_start
    CALL delete_parse
    JR C,delete_illegal
    LD (MM_RUN_ARG1),HL
    CALL delete_peek
    CP '-'
    JR Z,delete_range
    LD HL,(MM_RUN_ARG1)
    JR delete_endpoint
delete_from_start:
    LD HL,MM_PROGRAM_AREA
    LD (MM_RUN_ARG1),HL
delete_range:
    LD IX,CAP_ADDR_ADV_PTR
    CALL CAP_ADDR_MAIN_CALL
    CALL delete_parse
    JR C,delete_illegal
delete_endpoint:
    LD DE,(MM_RUN_ARG1)
    OR A
    SBC HL,DE
    JR C,delete_illegal
    ADD HL,DE
    LD (MM_RUN_TMP16),HL
    CALL delete_peek
    OR A
    JR Z,delete_loop
    CP ':'
    JR NZ,delete_syntax
delete_loop:
    LD HL,(MM_RUN_ARG1)
    LD DE,(MM_RUN_TMP16)
    OR A
    SBC HL,DE
    PUSH AF
    ADD HL,DE
    PUSH HL
    INC HL
    INC HL
    LD C,(HL)
    LD B,0
    INC BC
    INC BC
    INC BC
    LD H,D
    LD L,E
    OR A
    SBC HL,BC
    LD (MM_RUN_TMP16),HL
    POP HL
    LD IX,CAP_DELETE_REMOVE
    CALL CAP_ADDR_MAIN_CALL
    POP AF
    JR NZ,delete_loop
    LD A,2
    LD (MM_RUN_CTRL),A
    LD A,1
    RET
delete_syntax:
    LD A,2
    JR delete_error
delete_illegal:
    LD A,5
delete_error:
    LD IX,CAP_TRACE_ERROR
    CALL CAP_ADDR_MAIN_CALL
    LD A,1
    RET
delete_peek:
    LD IX,CAP_ADDR_SKIP_SPACES
    CALL CAP_ADDR_MAIN_CALL
    LD IX,CAP_ADDR_PEEK_CHAR
    JP CAP_ADDR_MAIN_CALL
