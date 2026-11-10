; l4-program.md 第13節。画面と行整形はmain側の既存処理を使う。
    ORG 0x7700
edit_stmt:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,edit_missing
    CP ':'
    JR Z,edit_missing
    CP '.'
    JR NZ,edit_number
    CALL ADV_PTR
    LD HL,(MM_PROG_CUR_LINENO)
    JR edit_find
edit_number:
    CALL PARSE_LINENUM_CUR
    JR C,edit_illegal
    LD DE,65530
    OR A
    SBC HL,DE
    JR NC,edit_illegal
    ADD HL,DE
edit_find:
    PUSH HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,edit_end_valid
    CP ':'
    JR Z,edit_end_valid
    POP HL
    LD A,2
    JP ERR_SET_A
edit_end_valid:
    POP HL
    LD (MM_PROG_CUR_LINENO),HL
    CALL RUN_FIND_LINE
    JR C,edit_missing
    LD (MM_RUN_ARG1),HL
    CALL edit_cb_CLS_SCREEN
    CALL edit_cb_NEWLINE
    LD HL,(MM_RUN_ARG1)
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    LD A,(HL)
    INC HL
    PUSH HL
    PUSH AF
    EX DE,HL
    CALL edit_cb_PRINT_UDEC
    LD A,' '
    CALL edit_cb_PRINT_CHAR
    POP AF
    POP HL
    CALL edit_cb_LIST_RENDER_TEXT
    XOR A
    LD (MM_VAR_COL),A
    CALL edit_cb_SET_CURSOR
    LD A,3
    LD (MM_RUN_CTRL),A
    RET
edit_missing:
    CALL edit_cb_CLS_SCREEN
    LD A,8
    JP ERR_SET_A
edit_illegal:
    LD A,5
    JP ERR_SET_A
edit_cb_CLS_SCREEN:
    LD IX,EDIT_MAIN_CLS_SCREEN
    JP MM_N_PROBE
edit_cb_NEWLINE:
    LD IX,EDIT_MAIN_NEWLINE
    JP MM_N_PROBE
edit_cb_PRINT_UDEC:
    LD IX,EDIT_MAIN_PRINT_UDEC
    JP MM_N_PROBE
edit_cb_PRINT_CHAR:
    LD IX,EDIT_MAIN_PRINT_CHAR
    JP MM_N_PROBE
edit_cb_LIST_RENDER_TEXT:
    LD IX,EDIT_MAIN_LIST_RENDER_TEXT
    JP MM_N_PROBE
edit_cb_SET_CURSOR:
    LD IX,EDIT_MAIN_SET_CURSOR
    JP MM_N_PROBE
