; docs/spec/l4-program.md 第14.17版 4.13/4.13a。測定0fc2cfc。
; 自作判断: 最大8受け皿。部分代入を保持。INPUT; / LINE INPUT; は改行抑止。
; PRINT USINGと文単位で排他的な共用域。添字の式評価と共用しない。
INPUT_VARS EQU MM_INPUT_VARS
INPUT_LINE EQU MM_INPUT_LINE
INPUT_NOCR EQU MM_INPUT_NOCR
INPUT_QUESTION EQU MM_INPUT_QUESTION
INPUT_COUNT EQU MM_INPUT_COUNT
INPUT_INDEX EQU MM_INPUT_INDEX
INPUT_MAIN_PTR EQU MM_INPUT_MAIN_PTR
INPUT_MAIN_END EQU MM_INPUT_MAIN_END
INPUT_ENTRY EQU MM_INPUT_ENTRY
    ORG 0x6AD0
in_stmt:
    XOR A
    LD (INPUT_NOCR),A
    LD (INPUT_COUNT),A
    LD A,(INPUT_LINE)
    XOR 1
    LD (INPUT_QUESTION),A
    CALL in_skip
    CALL in_peek
    CP ';'
    JR NZ,in_prompt
    CALL in_adv
    LD A,1
    LD (INPUT_NOCR),A
in_prompt:
    CALL in_skip
    CALL in_peek
    CP '"'
    JR NZ,in_targets
    CALL in_adv
in_prompt_loop:
    CALL in_end
    JP Z,in_syntax
    CALL in_peek
    CP '"'
    JR Z,in_prompt_done
    CALL in_print
    CALL in_adv
    JR in_prompt_loop
in_prompt_done:
    CALL in_adv
    CALL in_skip
    CALL in_peek
    CP ';'
    JR Z,in_prompt_sep
    CP ','
    JP NZ,in_syntax
    XOR A
    LD (INPUT_QUESTION),A
in_prompt_sep:
    CALL in_adv
in_targets:
    CALL in_skip
    CALL in_end
    JR NZ,in_target
    LD A,(INPUT_LINE)
    OR A
    JP NZ,in_syntax
    JR in_request
in_target:
    LD A,(INPUT_COUNT)
    CP 8
    JP NC,in_syntax
    XOR A
    LD (MM_RUN_ASSIGN_KIND),A
    CALL in_target_call
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
    LD A,(MM_RUN_ASSIGN_KIND)
    OR A
    JP Z,in_syntax
    PUSH HL
    CALL in_entry
    LD (INPUT_ENTRY),HL
    LD A,(MM_RUN_ASSIGN_KIND)
    LD (HL),A
    INC HL
    LD DE,MM_RUN_ASSIGN_NAME
    EX DE,HL
    LD BC,8
    LDIR
    POP HL
    EX DE,HL
    LD (HL),E
    INC HL
    LD (HL),D
    LD A,(INPUT_COUNT)
    INC A
    LD (INPUT_COUNT),A
    LD A,(INPUT_LINE)
    OR A
    JR Z,in_next_target
    LD A,(MM_RUN_ASSIGN_KIND)
    CP 3
    LD A,13
    JP NZ,in_error
    JR in_target_end
in_next_target:
    CALL in_skip
    CALL in_peek
    CP ','
    JR NZ,in_target_end
    CALL in_adv
    JR in_target
in_target_end:
    CALL in_skip
    CALL in_end
    JR Z,in_request
    CALL in_peek
    CP ':'
    JP NZ,in_syntax
in_request:
    LD HL,(MM_CUR_PTR)
    LD (INPUT_MAIN_PTR),HL
    LD HL,(MM_LINE_END)
    LD (INPUT_MAIN_END),HL
    LD A,(INPUT_QUESTION)
    OR A
    JR Z,in_request_padding
    LD A,'?'
    CALL in_print
    LD A,' '
    CALL in_print
in_request_padding:
    ; 自作判断: 先頭;は改行抑止に加えてINPUTで1桁、LINE INPUTで2桁の余白を置く。
    ; 入力前の空白未確定・完了候補ゼロという4.13/4.13aの固定点と整合。
    LD A,(INPUT_NOCR)
    OR A
    JR Z,in_read
    LD A,(INPUT_LINE)
    OR A
    JR Z,in_padding_last
    LD A,' '
    CALL in_print
in_padding_last:
    LD A,' '
    CALL in_print
in_read:
    CALL in_readline
    LD A,(INPUT_COUNT)
    OR A
    JP Z,in_missing
    LD HL,MM_INPUT_RAW
    LD (MM_CUR_PTR),HL
    LD A,(MM_RUN_INPUT_RAW_LEN)
    LD E,A
    LD D,0
    ADD HL,DE
    LD (MM_LINE_END),HL
    XOR A
    LD (INPUT_INDEX),A
in_field:
    LD A,(INPUT_INDEX)
    CALL in_entry_a
    LD A,(HL)
    LD (MM_RUN_ASSIGN_KIND),A
    INC HL
    LD DE,MM_RUN_ASSIGN_NAME
    LD BC,8
    LDIR
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD (MM_RUN_ARRAY_ASSIGN_ADDR),DE
    CALL in_token
    LD A,(MM_ERROR_FLAG)
    OR A
    JR NZ,in_retry
    LD A,(MM_RUN_ASSIGN_KIND)
    CP 3
    JR Z,in_store_value
    CALL in_number
    LD A,(MM_ERROR_FLAG)
    OR A
    JR Z,in_store_value
    LD A,(MM_ERROR_KIND)
    CP 6
    JR NZ,in_retry
    JP in_finish_error
in_store_value:
    LD HL,(MM_RUN_ARRAY_ASSIGN_ADDR)
    CALL in_store
    LD A,(MM_ERROR_FLAG)
    OR A
    JR NZ,in_finish_error
    LD A,(INPUT_INDEX)
    INC A
    LD (INPUT_INDEX),A
    LD B,A
    LD A,(INPUT_COUNT)
    CP B
    JR Z,in_last
    CALL in_peek
    CP ','
    JR NZ,in_retry
    CALL in_adv
    JR in_field
in_last:
    CALL in_end
    JR NZ,in_retry
    CALL in_restore
    LD A,(INPUT_NOCR)
    OR A
    CALL Z,in_newline
    XOR A
    LD (MM_ERROR_FLAG),A
    LD (MM_RUN_CTRL),A
    RET
in_retry:
    CALL in_restore
    CALL in_newline
    ; 表示文言は仕様で規定しない。独立に選んだ再入力案内。
    LD HL,in_redo_text
in_redo_loop:
    LD A,(HL)
    OR A
    JR Z,in_redo_done
    PUSH HL
    CALL in_print
    POP HL
    INC HL
    JR in_redo_loop
in_redo_done:
    CALL in_newline
    XOR A
    LD (MM_ERROR_FLAG),A
    JP in_request
in_redo_text: DB "?Redo from start",0
in_finish_error:
    CALL in_restore
    CALL in_newline
    RET
in_missing:
    CALL in_newline
in_syntax:
    LD A,2
in_error:
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
    RET
in_restore:
    LD HL,(INPUT_MAIN_PTR)
    LD (MM_CUR_PTR),HL
    LD HL,(INPUT_MAIN_END)
    LD (MM_LINE_END),HL
    RET
in_entry:
    LD A,(INPUT_COUNT)
in_entry_a:
    LD L,A
    LD H,0
    LD D,H
    LD E,L
    ADD HL,HL
    ADD HL,HL
    ADD HL,DE
    ADD HL,HL
    ADD HL,DE
    LD DE,INPUT_VARS
    ADD HL,DE
    RET

in_target_call:
    LD IX,IN_TARGET_ADDR
    JP B3_MAIN_CALL_ADDR
IN_TARGET_ADDR EQU 0x1787

in_token:
    LD IX,IN_TOKEN_ADDR
    JP B3_MAIN_CALL_ADDR
IN_TOKEN_ADDR EQU 0x1787

in_number:
    LD IX,IN_NUMBER_ADDR
    JP B3_MAIN_CALL_ADDR
IN_NUMBER_ADDR EQU 0x1787

in_store:
    LD IX,IN_STORE_ADDR
    JP B3_MAIN_CALL_ADDR
IN_STORE_ADDR EQU 0x1787

in_readline:
    LD IX,IN_READLINE_ADDR
    JP B3_MAIN_CALL_ADDR
IN_READLINE_ADDR EQU 0x1787

in_print:
    LD IX,IN_PRINT_ADDR
    JP B3_MAIN_CALL_ADDR
IN_PRINT_ADDR EQU 0x1787

in_newline:
    LD IX,IN_NEWLINE_ADDR
    JP B3_MAIN_CALL_ADDR
IN_NEWLINE_ADDR EQU 0x1787

in_peek:
    LD IX,IN_PEEK_ADDR
    JP B3_MAIN_CALL_ADDR
IN_PEEK_ADDR EQU 0x1787

in_adv:
    LD IX,IN_ADV_ADDR
    JP B3_MAIN_CALL_ADDR
IN_ADV_ADDR EQU 0x1787

in_skip:
    LD IX,IN_SKIP_ADDR
    JP B3_MAIN_CALL_ADDR
IN_SKIP_ADDR EQU 0x1787

in_end:
    LD IX,IN_END_ADDR
    JP B3_MAIN_CALL_ADDR
IN_END_ADDR EQU 0x1787

in_code_end:
