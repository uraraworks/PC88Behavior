; 低頻度のINPUT数値変換・FOR飛越し・ファンクションキー設定。
    ORG 0x3E00
    JP slow_INPUT_NUMBER
    JP slow_RUN_SKIP_TO_MATCHING_NEXT
    JP slow_FKEY_MODE_STMT
    JP slow_FKEY_ON_STMT
slow_INPUT_NUMBER:
    LD HL,(CUR_PTR)
    PUSH HL
    LD HL,(LINE_END)
    PUSH HL
    LD HL,RUN_STR_TMP_BUF
    LD (CUR_PTR),HL
    LD A,(RUN_STR_TMP_LEN)
    LD E,A
    LD D,0
    ADD HL,DE
    LD (LINE_END),HL
    OR A
    JR NZ,_in_number
    LD HL,0
    CALL slow_cb_VAL_SET_INT
    CALL slow_cb_ASSIGN_CONVERT_CUR
    JR _in_restore
_in_number:
    CALL slow_cb_INPUT_RANGE
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_in_restore
    CALL slow_cb_PEEK_CHAR
    CP '+'
    JR Z,_in_eval
    CP '-'
    JR Z,_in_eval
    CP '&'
    JR Z,_in_eval
    CP '.'
    JR Z,_in_eval
    CP '0'
    JR C,_in_bad
    CP '9'+1
    JR NC,_in_bad
_in_eval:
    CALL slow_cb_PEEK_CHAR
    CP '+'
    CALL Z,slow_cb_ADV_PTR
    CALL slow_cb_LOGIC_OR_EXPR
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_in_restore
    CALL slow_cb_INPUT_FIX_LITERAL
    CALL slow_cb_SKIP_SPACES
    CALL slow_cb_AT_END
    JR NZ,_in_bad
    CALL slow_cb_ASSIGN_CONVERT_CUR
    JR _in_restore
_in_bad:
    LD A,13
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_FLAG),A
_in_restore:
    POP HL
    LD (LINE_END),HL
    POP HL
    LD (CUR_PTR),HL
    RET

slow_RUN_SKIP_TO_MATCHING_NEXT:
    XOR A
    LD (RUN_SCAN_DEPTH),A
_rstmn_stmt_loop:
    CALL slow_cb_SKIP_SPACES
    CALL slow_cb_AT_END
    JR Z,_rstmn_next_record
    CALL slow_cb_TRY_MATCH_FOR
    OR A
    JR Z,_rstmn_try_next_kw
    LD A,(RUN_SCAN_DEPTH)
    INC A
    LD (RUN_SCAN_DEPTH),A
    JR _rstmn_skip_rest_of_stmt
_rstmn_try_next_kw:
    CALL slow_cb_TRY_MATCH_NEXT
    OR A
    JR Z,_rstmn_skip_rest_of_stmt
    CALL slow_cb_SKIP_SPACES
    CALL slow_cb_LEX_IDENT_PEEK
    OR A
    JR Z,_rstmn_next_noname
    CALL slow_cb_LEX_IDENT_CONSUME
_rstmn_next_noname:
    LD A,(RUN_SCAN_DEPTH)
    OR A
    JR Z,_rstmn_found
    DEC A
    LD (RUN_SCAN_DEPTH),A
    JR _rstmn_after_stmt
_rstmn_skip_rest_of_stmt:
    CALL slow_cb_RUN_SKIP_REST_OF_STATEMENT
_rstmn_after_stmt:
    CALL slow_cb_AT_END
    JR Z,_rstmn_next_record
    CALL slow_cb_PEEK_CHAR
    CP ':'
    JR NZ,_rstmn_next_record
    CALL slow_cb_ADV_PTR
    JR _rstmn_stmt_loop
_rstmn_next_record:
    CALL slow_cb_RUN_ADVANCE_RECORD
    OR A
    JR Z,_rstmn_notfound
    JR _rstmn_stmt_loop
_rstmn_found:
    XOR A
    LD (ERROR_FLAG),A
    RET
_rstmn_notfound:
    LD A,26
    JP slow_cb_ERR_SET_A

slow_FKEY_MODE_STMT:
    LD A,'('
    CALL slow_cb_EXPECT_CHAR
    CALL slow_cb_PARSE_INT_ARG
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD A,D
    OR A
    JR NZ,_fkm_illegal
    LD A,E
    DEC A
    CP 10
    JR NC,_fkm_illegal
    LD (MM_FKEY_INDEX),A
    LD A,')'
    CALL slow_cb_EXPECT_CHAR
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    CALL slow_cb_SKIP_SPACES
    CALL slow_cb_TRY_MATCH_ON
    OR A
    JR NZ,_fkm_on
    CALL slow_cb_TRY_MATCH_STOP
    OR A
    JR NZ,_fkm_off
    LD HL,FKEY_OFF_WORD
    LD (RUN_KW_TEXT),HL
    LD A,3
    LD (RUN_KW_LEN),A
    CALL slow_cb_TRY_MATCH_KEYWORD_GENERIC
    OR A
    JR Z,_fk_syntax
_fkm_off:
    LD A,0
    JR _fkm_set
_fkm_on:
    LD HL,MM_FKEY_ON
    SET 3,(HL)                  ; 一度でも捕捉を有効にしたら高速連続実行を抑止
    LD A,1
_fkm_set:
    PUSH AF
    CALL slow_cb_SKIP_SPACES
    CALL slow_cb_PEEK_CHAR
    OR A
    JR Z,_fkm_end
    CP ':'
    JR NZ,_fkm_bad_end
_fkm_end:
    CALL slow_cb_FKEY_ENSURE
    LD A,(ERROR_FLAG)
    OR A
    JR NZ,_fkm_error
    CALL slow_cb_FKEY_STATE_SLOT
    POP AF
    LD B,A
    LD A,(HL)
    AND 080h                 ; RETURNまでは捕捉停止を保つ
    OR B
    LD (HL),A
    XOR A
    LD (ERROR_FLAG),A
    RET
_fkm_bad_end:
    POP AF
    JP _fk_syntax
_fkm_error:
    POP AF
    RET
_fkm_illegal:
    LD A,5
    JP slow_cb_ERR_SET_A
_fk_syntax:
    LD A,2
    JP slow_cb_ERR_SET_A
slow_FKEY_ON_STMT:
    CALL slow_cb_SKIP_SPACES
    CALL slow_cb_TRY_MATCH_GOSUB
    OR A
    JR Z,_fk_syntax
    CALL slow_cb_FKEY_ENSURE
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    XOR A
    LD (MM_FKEY_INDEX),A
    CALL slow_cb_FKEY_SLOT
    LD B,20
_fko_clear:
    LD (HL),A
    INC HL
    DJNZ _fko_clear
_fko_list:
    CALL slow_cb_SKIP_SPACES
    CALL slow_cb_PEEK_CHAR
    CP ','
    JR Z,_fko_next
    OR A
    JR Z,_fko_done
    CP ':'
    JR Z,_fko_done
    CALL slow_cb_PARSE_LINENUM_CUR
    JR C,_fk_syntax
    PUSH HL
    CALL slow_cb_RUN_FIND_LINE
    POP HL
    JR C,_fko_undefined
    PUSH HL
    CALL slow_cb_FKEY_SLOT
    POP DE
    LD (HL),E
    INC HL
    LD (HL),D
    CALL slow_cb_SKIP_SPACES
    CALL slow_cb_PEEK_CHAR
    CP ','
    JR NZ,_fko_done
_fko_next:
    CALL slow_cb_ADV_PTR
    LD A,(MM_FKEY_INDEX)
    INC A
    CP 10
    JR NC,_fk_syntax
    LD (MM_FKEY_INDEX),A
    JR _fko_list
_fko_done:
    XOR A
    LD (ERROR_FLAG),A
    RET
_fko_undefined:
    LD A,8
    JP slow_cb_ERR_SET_A

slow_cb_ADV_PTR:
    LD IX,SLOW_MAIN_ADV_PTR
    JP MM_N_PROBE
slow_cb_ASSIGN_CONVERT_CUR:
    LD IX,SLOW_MAIN_ASSIGN_CONVERT_CUR
    JP MM_N_PROBE
slow_cb_AT_END:
    LD IX,SLOW_MAIN_AT_END
    JP MM_N_PROBE
slow_cb_ERR_SET_A:
    LD IX,SLOW_MAIN_ERR_SET_A
    JP MM_N_PROBE
slow_cb_EXPECT_CHAR:
    LD IX,SLOW_MAIN_EXPECT_CHAR
    JP MM_N_PROBE
slow_cb_FKEY_ENSURE:
    LD IX,SLOW_MAIN_FKEY_ENSURE
    JP MM_N_PROBE
slow_cb_FKEY_SLOT:
    LD IX,SLOW_MAIN_FKEY_SLOT
    JP MM_N_PROBE
slow_cb_FKEY_STATE_SLOT:
    LD IX,SLOW_MAIN_FKEY_STATE_SLOT
    JP MM_N_PROBE
slow_cb_INPUT_FIX_LITERAL:
    LD IX,SLOW_MAIN_INPUT_FIX_LITERAL
    JP MM_N_PROBE
slow_cb_INPUT_RANGE:
    LD IX,SLOW_MAIN_INPUT_RANGE
    JP MM_N_PROBE
slow_cb_LEX_IDENT_CONSUME:
    LD IX,SLOW_MAIN_LEX_IDENT_CONSUME
    JP MM_N_PROBE
slow_cb_LEX_IDENT_PEEK:
    LD IX,SLOW_MAIN_LEX_IDENT_PEEK
    JP MM_N_PROBE
slow_cb_LOGIC_OR_EXPR:
    LD IX,SLOW_MAIN_LOGIC_OR_EXPR
    JP MM_N_PROBE
slow_cb_PARSE_INT_ARG:
    LD IX,SLOW_MAIN_PARSE_INT_ARG
    JP MM_N_PROBE
slow_cb_PARSE_LINENUM_CUR:
    LD IX,SLOW_MAIN_PARSE_LINENUM_CUR
    JP MM_N_PROBE
slow_cb_PEEK_CHAR:
    LD IX,SLOW_MAIN_PEEK_CHAR
    JP MM_N_PROBE
slow_cb_RUN_ADVANCE_RECORD:
    LD IX,SLOW_MAIN_RUN_ADVANCE_RECORD
    JP MM_N_PROBE
slow_cb_RUN_FIND_LINE:
    LD IX,SLOW_MAIN_RUN_FIND_LINE
    JP MM_N_PROBE
slow_cb_RUN_SKIP_REST_OF_STATEMENT:
    LD IX,SLOW_MAIN_RUN_SKIP_REST_OF_STATEMENT
    JP MM_N_PROBE
slow_cb_SKIP_SPACES:
    LD IX,SLOW_MAIN_SKIP_SPACES
    JP MM_N_PROBE
slow_cb_TRY_MATCH_FOR:
    LD IX,SLOW_MAIN_TRY_MATCH_FOR
    JP MM_N_PROBE
slow_cb_TRY_MATCH_GOSUB:
    LD IX,SLOW_MAIN_TRY_MATCH_GOSUB
    JP MM_N_PROBE
slow_cb_TRY_MATCH_KEYWORD_GENERIC:
    LD IX,SLOW_MAIN_TRY_MATCH_KEYWORD_GENERIC
    JP MM_N_PROBE
slow_cb_TRY_MATCH_NEXT:
    LD IX,SLOW_MAIN_TRY_MATCH_NEXT
    JP MM_N_PROBE
slow_cb_TRY_MATCH_ON:
    LD IX,SLOW_MAIN_TRY_MATCH_ON
    JP MM_N_PROBE
slow_cb_TRY_MATCH_STOP:
    LD IX,SLOW_MAIN_TRY_MATCH_STOP
    JP MM_N_PROBE
slow_cb_VAL_SET_INT:
    LD IX,SLOW_MAIN_VAL_SET_INT
    JP MM_N_PROBE
