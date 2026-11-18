; INPUT/LINE INPUT の入力待ち。画面編集と生入力バッファを同期する。
; 画面側はKEY_READが更新し、ここでは通知された操作をバッファへ適用する。
    ORG 0x7000
n_input_readline:
    XOR A
    LD (MM_RUN_INPUT_RAW_LEN),A
    LD (MM_INPUT_ENTRY),A       ; バッファ内のカーソル位置
ni_loop:
    CALL ni_cb_CURSOR_INPUT
    CALL ni_cb_KEY_READ
    OR A
    JR Z,ni_loop
    CP 2
    RET Z
    CP 3
    JR Z,ni_tab
    CP 4
    JR Z,ni_delete
    CP 5
    JR Z,ni_word
    LD A,E
    PUSH AF
    CALL ni_store
    JR C,ni_noecho
    POP AF
    CALL ni_cb_PRINT_CHAR
    JR ni_loop
ni_noecho:
    POP AF
    JR ni_loop
ni_tab:
    LD B,E
ni_tab_loop:
    PUSH BC
    LD A,020h
    CALL ni_store
    POP BC
    DJNZ ni_tab_loop
    JR ni_loop
ni_word:
    LD A,(MM_INPUT_ENTRY)
    SUB E
    JR NC,ni_word_set
    XOR A
ni_word_set:
    LD (MM_INPUT_ENTRY),A
    JR ni_loop
ni_delete:
    LD A,(MM_INPUT_ENTRY)
    OR A
    JR Z,ni_loop
    DEC A
    LD (MM_INPUT_ENTRY),A
    LD E,A
    LD A,(MM_RUN_INPUT_RAW_LEN)
    CP E
    JR C,ni_loop
    JR Z,ni_loop
    DEC A
    LD (MM_RUN_INPUT_RAW_LEN),A
    SUB E
    LD C,A
    LD B,0
    LD D,0
    LD HL,MM_INPUT_RAW
    ADD HL,DE
    PUSH HL
    INC HL
    POP DE
    LD A,B
    OR C
    JR Z,ni_loop
    LDIR
    JR ni_loop
ni_store:
    PUSH AF
    LD A,(MM_INPUT_ENTRY)
    CP 254
    JR NC,ni_store_full
    LD E,A
    LD D,0
    LD HL,MM_INPUT_RAW
    ADD HL,DE
    POP AF
    LD (HL),A
    LD A,E
    INC A
    LD (MM_INPUT_ENTRY),A
    LD E,A
    LD A,(MM_RUN_INPUT_RAW_LEN)
    CP E
    JR NC,ni_store_ok
    LD A,E
    LD (MM_RUN_INPUT_RAW_LEN),A
ni_store_ok:
    OR A
    RET
ni_store_full:
    POP AF
    SCF
    RET
ni_cb_CURSOR_INPUT:
    LD IX,NI_MAIN_CURSOR_INPUT
    JP MM_N_PROBE
ni_cb_KEY_READ:
    LD IX,NI_MAIN_KEY_READ
    JP MM_N_PROBE
ni_cb_PRINT_CHAR:
    LD IX,NI_MAIN_PRINT_CHAR
    JP MM_N_PROBE
