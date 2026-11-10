; l4-program.md 11.1: MERGE。媒体読取はLOADの状態機械を使用する。
; N表示中はRAM中継でmainを呼び、拡張バンクを直接呼ばない。
    ORG 0x3600
    JP mc_merge
    JP mc_common
    JP mc_chain
    JP mc_save_entry
    JP motor_stmt
mc_merge:
    CALL sq_filename
    CALL ncb_sq_bad
    RET NZ
    CALL ncb_rf_end
    CALL ncb_sq_bad
    RET NZ
    LD HL,MM_SQ_NAME
    LD DE,MM_LOAD_NAME
    LD BC,9
    LDIR
    LD A,(MM_SQ_DRIVE)
    LD (MM_LOAD_DRIVE),A
    XOR A
    LD (MM_BINARY_MODE),A
    LD (MM_LOAD_ALLOW_OWN),A
    LD (MM_LOAD_PHASE),A
    LD (MM_LOAD_READ_OK),A
    LD (MM_SQ_WORK+39),A       ; 先に全行を検証し、成功後に取り込む。
mc_merge_next:
    CALL mc_load_step
    CP 1
    JR Z,mc_merge_read
    CP 2
    JR Z,mc_merge_found         ; 種別確認後も既存プログラムを残す。
    CP 3
    JR Z,mc_merge_line
    CP 4
    JR Z,mc_merge_missing
    CP 5
    JR Z,mc_merge_type
    CP 6
    JR Z,mc_merge_io
    LD A,(MM_SQ_WORK+39)
    OR A
    JR NZ,mc_merge_done
    INC A
    LD (MM_SQ_WORK+39),A
    XOR A
    LD (MM_LOAD_PHASE),A
    LD (MM_LOAD_READ_OK),A
    JR mc_merge_next
mc_merge_done:
    JP mc_load_finish
mc_merge_read:
    CALL mc_load_read
    JR mc_merge_next
mc_merge_found:
    ; l4-program.md 11.1: 空のASCIIファイルでもLOADと同じ状態を消す。
    LD A,(MM_SQ_WORK+39)
    OR A
    JR Z,mc_merge_next
    CALL mc_cb_RUN_CLEAR_STATE
    CALL ncb_sq_bad
    RET NZ
    JR mc_merge_next
mc_merge_line:
    LD A,(MM_SQ_WORK+39)
    OR A
    JR NZ,mc_merge_store_line
    LD A,(MM_LOAD_LINE_LEN)
    LD (MM_VAR_LINELEN),A
    OR A
    JR Z,mc_merge_invalid
    LD A,(MM_LINE_BUF)
    CP '0'
    JR C,mc_merge_invalid
    CP '9'+1
    JR NC,mc_merge_invalid
    CALL mc_cb_PARSE_LINENUM
    JR C,mc_merge_invalid
    LD A,(MM_LOAD_LINE_LEN)
    CP B
    JR Z,mc_merge_invalid
    XOR A
    LD (MM_LOAD_LINE_LEN),A
    JR mc_merge_next
mc_merge_store_line:
    CALL mc_load_line
    CALL ncb_sq_bad
    RET NZ
    JR mc_merge_next
mc_merge_invalid:
    LD A,59
    JP ncb_SQ_ERROR
mc_merge_missing:
    LD A,53
    JP ncb_SQ_ERROR
mc_merge_type:
    LD A,59
    JP ncb_SQ_ERROR
mc_merge_io:
    LD A,64
    JP ncb_SQ_ERROR

; COMMON名表はヒープ種別7の独立枠。各要素は名前8Bと配列印1B。
; l4-program.md 11.3: 指定だけを記録し、変数自体は作らない。
mc_common:
    CALL ncb_SKIP_SPACES
    CALL mc_cb_LEX_IDENT_CONSUME
    OR A
    JP Z,ncb_sq_syntax
    LD HL,MM_IDENT_BUF
    LD DE,MM_SQ_WORK+20
    LD BC,8
    LDIR
    XOR A
    LD (MM_SQ_WORK+28),A
    CALL ncb_SKIP_SPACES
    CALL ncb_PEEK_CHAR
    CP '('
    JR NZ,mc_common_name
    CALL ncb_ADV_PTR
    CALL ncb_SKIP_SPACES
    CALL ncb_PEEK_CHAR
    CP ')'
    JP NZ,ncb_sq_syntax
    CALL ncb_ADV_PTR
    LD A,1
    LD (MM_SQ_WORK+28),A
mc_common_name:
    LD HL,mc_common_key
    LD DE,MM_IDENT_BUF
    LD BC,8
    LDIR
mc_common_find_table:
    LD A,7
    CALL mc_cb_HEAP_FIND_MAIN
    OR A
    JR Z,mc_common_new_table
    ; 反復実行されたCOMMONは同じ名前を重複登録しない。
    PUSH HL
    CALL mc_common_table_has
    POP HL
    OR A
    JR NZ,mc_common_after_store
    PUSH HL
    LD DE,9
    ADD HL,DE
    LD A,(HL)
    POP HL
    CP 32
    JR C,mc_common_have
    LD HL,MM_IDENT_BUF+7
    INC (HL)
    JR NZ,mc_common_find_table
    JR mc_common_full
mc_common_new_table:
    LD A,7
    CALL mc_cb_HEAP_ALLOC_MAIN
    OR A
    JR Z,mc_common_full
    PUSH HL
    LD DE,MM_IDENT_BUF
    LD B,8
mc_common_copykey:
    LD A,(DE)
    LD (HL),A
    INC DE
    INC HL
    DJNZ mc_common_copykey
    LD (HL),7
    INC HL
    LD (HL),0
    POP HL
mc_common_have:
    PUSH HL
    LD DE,9
    ADD HL,DE
    LD A,(HL)
    INC (HL)
    LD L,A
    LD H,0
    LD D,H
    LD E,L
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    ADD HL,DE
    LD DE,10
    ADD HL,DE
    POP DE
    ADD HL,DE
    EX DE,HL
    LD HL,MM_SQ_WORK+20
    LD BC,9
    LDIR
mc_common_after_store:
    CALL ncb_SKIP_SPACES
    CALL ncb_PEEK_CHAR
    CP ','
    RET NZ
    CALL ncb_ADV_PTR
    JP mc_common
mc_common_full:
    LD A,7
    JP ncb_SQ_ERROR
mc_common_key:
    DB "COMMON##"
; HL=表先頭。名前と配列印が一致するとA=1。
mc_common_table_has:
    LD DE,9
    ADD HL,DE
    LD C,(HL)
    INC HL
mc_common_has_next:
    LD A,C
    OR A
    RET Z
    PUSH HL
    PUSH BC
    LD DE,MM_SQ_WORK+20
    LD B,9
mc_common_has_compare:
    LD A,(DE)
    CP (HL)
    JR NZ,mc_common_has_different
    INC DE
    INC HL
    DJNZ mc_common_has_compare
    POP BC
    POP HL
    LD A,1
    RET
mc_common_has_different:
    POP BC
    POP HL
    LD DE,9
    ADD HL,DE
    DEC C
    JR mc_common_has_next

; l4-program.md 11.2: CHAIN前に変数領域を退避し、読み込み後に戻す。
; SQ_WORKの後半は媒体処理と重ならない文実行中の退避域。
MC_FLAGS EQU MM_SQ_WORK+20
MC_LINE EQU MM_SQ_WORK+21
MC_FOR EQU MM_SQ_WORK+23
MC_BACK EQU MM_SQ_WORK+25
MC_LEN EQU MM_SQ_WORK+27
MC_FREE EQU MM_SQ_WORK+29
MC_REC EQU MM_SQ_WORK+31
MC_TABLE EQU MM_SQ_WORK+33
MC_NEXT EQU MM_SQ_WORK+35
MC_DELETE EQU MM_SQ_WORK+37

mc_chain:
    CALL ncb_SKIP_SPACES
    LD HL,MC_MAIN_mc_merge_word
    LD A,5
    CALL ncb_sq_keyword
    OR A
    LD A,0
    JR Z,mc_chain_filename
    INC A
mc_chain_filename:
    PUSH AF
    CALL sq_filename
    CALL ncb_sq_bad
    POP BC
    RET NZ
    LD A,B
    LD (MC_FLAGS),A
    LD HL,0
    LD (MC_LINE),HL
    CALL ncb_SKIP_SPACES
    CALL ncb_PEEK_CHAR
    CP ','
    JR NZ,mc_chain_end
    CALL ncb_ADV_PTR
    CALL ncb_SKIP_SPACES
    CALL ncb_PEEK_CHAR
    CP '0'
    JR C,mc_chain_option
    CP '9'+1
    JR NC,mc_chain_option
    CALL mc_cb_PARSE_LINENUM_CUR
    JP C,ncb_sq_syntax
    LD (MC_LINE),HL
    LD A,(MC_FLAGS)
    OR 4
    LD (MC_FLAGS),A
    CALL ncb_SKIP_SPACES
    CALL ncb_PEEK_CHAR
    CP ','
    JR NZ,mc_chain_end
    CALL ncb_ADV_PTR
mc_chain_option:
    CALL ncb_SKIP_SPACES
    LD HL,MC_MAIN_mc_all_word
    LD A,3
    CALL ncb_sq_keyword
    OR A
    JR Z,mc_chain_delete_option
    LD A,(MC_FLAGS)
    OR 2
    LD (MC_FLAGS),A
    CALL ncb_SKIP_SPACES
    CALL ncb_PEEK_CHAR
    CP ','
    JR NZ,mc_chain_end
    CALL ncb_ADV_PTR
    CALL ncb_SKIP_SPACES
mc_chain_delete_option:
    LD HL,MC_MAIN_mc_delete_word
    LD A,6
    CALL ncb_sq_keyword
    OR A
    JP Z,ncb_sq_syntax
    LD A,(MC_FLAGS)
    BIT 0,A
    JP Z,ncb_sq_syntax
    OR 8
    LD (MC_FLAGS),A
    LD HL,(MM_CUR_PTR)
    LD (MC_DELETE),HL
    JR mc_chain_prepare
mc_chain_end:
    CALL ncb_rf_end
    CALL ncb_sq_bad
    RET NZ
mc_chain_prepare:
    LD HL,MM_SQ_NAME
    LD DE,MM_LOAD_NAME
    LD BC,9
    LDIR
    LD A,(MM_SQ_DRIVE)
    LD (MM_LOAD_DRIVE),A
    XOR A
    LD (MM_BINARY_MODE),A
    LD (MM_LOAD_PHASE),A
    LD (MM_LOAD_READ_OK),A
    INC A
    LD (MM_LOAD_ALLOW_OWN),A
mc_chain_next:
    CALL mc_load_step
    CP 1
    JR Z,mc_chain_read
    CP 2
    JR Z,mc_chain_found
    CP 3
    JR Z,mc_chain_line
    CP 4
    JP Z,mc_merge_missing
    CP 5
    JP Z,mc_merge_type
    CP 6
    JR Z,mc_chain_io
    CALL mc_chain_restore
    JP mc_chain_start
mc_chain_read:
    CALL mc_load_read
    JR mc_chain_next
mc_chain_io:
    LD A,(MC_FLAGS)
    BIT 4,A
    JR Z,mc_chain_io_error
    CALL mc_chain_restore
mc_chain_io_error:
    JP mc_merge_io
mc_chain_found:
    LD A,(MC_FLAGS)
    BIT 3,A
    JR Z,mc_chain_no_delete
    LD HL,(MC_DELETE)
    LD (MM_CUR_PTR),HL
    CALL delete_stmt
    CALL ncb_sq_bad
    RET NZ
mc_chain_no_delete:
    CALL mc_chain_snapshot
    CALL ncb_sq_bad
    RET NZ
    LD A,(MC_FLAGS)
    OR 16
    LD (MC_FLAGS),A
    LD A,(MC_FLAGS)
    BIT 0,A
    JR Z,mc_chain_clear
    CALL mc_cb_RUN_CLEAR_STATE
    JR mc_chain_clear_checked
mc_chain_clear:
    CALL mc_cb_PROGRAM_CLEAR
mc_chain_clear_checked:
    CALL ncb_sq_bad
    JR Z,mc_chain_next
    CALL mc_chain_restore
    RET
mc_chain_line:
    CALL mc_load_line
    CALL ncb_sq_bad
    JR Z,mc_chain_next
    CALL mc_chain_restore
    RET

; 本文の拡張から退避領域を守り、空きが足りない場合は誤り7。
mc_chain_snapshot:
    LD HL,(MM_RUN_FOR_STACK)
    LD (MC_FOR),HL
    LD HL,(MM_FREE_TOP)
    LD (MC_FREE),HL
    LD HL,(MM_HEAP_END)
    LD DE,(MM_HEAP_START)
    OR A
    SBC HL,DE
    LD (MC_LEN),HL
    LD DE,12
    ADD HL,DE
    EX DE,HL
    LD HL,(MC_FREE)
    OR A
    SBC HL,DE
    JR C,mc_chain_memory
    LD (MC_BACK),HL
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    JR C,mc_chain_memory
    LD HL,(MC_BACK)
    LD (MM_RUN_FOR_STACK),HL
    EX DE,HL
    LD HL,MM_STRING_FLAGS
    LD BC,12
    LDIR
    LD HL,(MC_LEN)
    LD B,H
    LD C,L
    LD A,B
    OR C
    RET Z
    LD HL,(MM_HEAP_START)
    LDIR
    RET
mc_chain_memory:
    LD A,7
    JP ncb_SQ_ERROR

mc_chain_restore:
    LD HL,(MC_FOR)
    LD (MM_RUN_FOR_STACK),HL
    LD HL,(MC_FREE)
    LD (MM_FREE_TOP),HL
    LD HL,(MC_BACK)
    LD DE,MM_STRING_FLAGS
    LD BC,12
    LDIR
    LD DE,(MM_HEAP_START)
    LD BC,(MC_LEN)
    LD A,B
    OR C
    JR Z,mc_restore_end
    LDIR
mc_restore_end:
    LD (MM_HEAP_END),DE
    ; COMMON表を探す。非COMMONの単純変数・配列は空き枠にする。
    LD HL,0
    LD (MC_TABLE),HL
    LD HL,(MM_HEAP_START)
mc_find_table:
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    ADD HL,DE
    JR Z,mc_filter_start
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    POP HL
    CP 7
    JR NZ,mc_find_next
    LD (MC_TABLE),HL
    JR mc_filter_start
mc_find_next:
    CALL mc_record_size
    ADD HL,DE
    JR mc_find_table
mc_filter_start:
    LD HL,(MM_HEAP_START)
mc_filter_loop:
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    ADD HL,DE
    RET Z
    LD (MC_REC),HL
    CALL mc_record_size
    ADD HL,DE
    LD (MC_NEXT),HL
    LD HL,(MC_REC)
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    BIT 7,A
    JR NZ,mc_filter_next
    CP 7
    JR Z,mc_filter_next
    CP 3
    JR NC,mc_filter_drop
    LD A,(MC_FLAGS)
    BIT 1,A
    JR NZ,mc_filter_next
    CALL mc_is_common
    OR A
    JR NZ,mc_filter_next
mc_filter_drop:
    CALL mc_release_record
    LD HL,(MC_REC)
    LD DE,8
    ADD HL,DE
    SET 7,(HL)
mc_filter_next:
    LD HL,(MC_NEXT)
    JR mc_filter_loop

; 破棄する長文字列・文字列配列のページも解放する。
mc_release_record:
    LD HL,(MC_REC)
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    CP 1
    JR Z,mc_release_scalar
    CP 2
    RET NZ
    LD DE,5
    ADD HL,DE                ; 次元数
    LD A,(HL)
    INC HL
    LD B,A
    LD A,(HL)                ; 要素幅3の配列は文字列
    CP 3
    RET NZ
    INC HL
    LD A,B
    ADD A,A
    LD E,A
    LD D,0
    ADD HL,DE
mc_release_array_loop:
    LD DE,(MC_NEXT)
    OR A
    SBC HL,DE
    ADD HL,DE
    RET Z
    LD A,(HL)
    OR A
    JR Z,mc_release_array_next
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    PUSH HL
    CALL mc_cb_ARRAY_PAGE_FREE
    POP HL
    INC HL
    JR mc_release_array_loop
mc_release_array_next:
    INC HL
    INC HL
    INC HL
    JR mc_release_array_loop
mc_release_scalar:
    INC HL
    LD A,(HL)
    CP 2
    RET NZ
    INC HL
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    JP mc_cb_ARRAY_PAGE_FREE

; HL=枠先頭、DE=枠の物理長。
mc_record_size:
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    AND 07Fh
    CP 1
    LD DE,42
    JR Z,mc_size_done
    CP 2
    LD DE,298
    JR NZ,mc_size_done
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
mc_size_done:
    POP HL
    RET
mc_is_common:
    LD HL,(MM_HEAP_START)
mc_common_find_next_table:
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    ADD HL,DE
    JR NZ,mc_common_check_table
    XOR A
    RET
mc_common_check_table:
    LD (MC_TABLE),HL
    PUSH HL
    LD DE,8
    ADD HL,DE
    LD A,(HL)
    POP HL
    CP 7
    JR Z,mc_common_scan_table
mc_common_skip_table:
    CALL mc_record_size
    ADD HL,DE
    JR mc_common_find_next_table
mc_common_scan_table:
    LD DE,9
    ADD HL,DE
    LD C,(HL)
    INC HL
mc_common_scan:
    LD A,C
    OR A
    JR NZ,mc_common_check_entry
    LD HL,(MC_TABLE)
    JR mc_common_skip_table
mc_common_check_entry:
    PUSH HL
    PUSH BC
    LD DE,(MC_REC)
    LD B,8
mc_common_compare:
    LD A,(DE)
    CP (HL)
    JR NZ,mc_common_different
    INC HL
    INC DE
    DJNZ mc_common_compare
    LD A,(DE)
    DEC A
    CP (HL)
    JR Z,mc_common_match
mc_common_different:
    POP BC
    POP HL
    LD DE,9
    ADD HL,DE
    DEC C
    JR mc_common_scan
mc_common_match:
    POP BC
    POP HL
    LD A,1
    RET
mc_load_step:
    LD A,1
    LD HL,06400h
    JP mc_cb_EXT_BANK_CALL
mc_cb_LEX_IDENT_CONSUME:
    LD IX,MC_MAIN_LEX_IDENT_CONSUME
    JP MM_N_PROBE
mc_cb_HEAP_FIND_MAIN:
    LD IX,MC_MAIN_HEAP_FIND_MAIN
    JP MM_N_PROBE
mc_cb_HEAP_ALLOC_MAIN:
    LD IX,MC_MAIN_HEAP_ALLOC_MAIN
    JP MM_N_PROBE
mc_cb_PARSE_LINENUM_CUR:
    LD IX,MC_MAIN_PARSE_LINENUM_CUR
    JP MM_N_PROBE
mc_cb_PROGRAM_CLEAR:
    LD IX,MC_MAIN_PROGRAM_CLEAR
    JP MM_N_PROBE
mc_cb_ARRAY_PAGE_FREE:
    LD IX,MC_MAIN_ARRAY_PAGE_FREE
    JP MM_N_PROBE
mc_cb_RUN_CLEAR_STATE:
    LD IX,MC_MAIN_RUN_CLEAR_STATE
    JP MM_N_PROBE

; RUN中は既存の実行器へ分岐位置を返す。直接モードならここから実行する。
mc_chain_start:
    LD A,(MM_SQ_WORK+20)
    BIT 2,A
    JR Z,mc_start_first
    LD HL,(MM_SQ_WORK+21)
    CALL mc_cb_RUN_FIND_LINE
    JR C,mc_start_missing
    JR mc_start_found
mc_start_first:
    LD HL,MM_PROGRAM_AREA
    LD A,(HL)
    INC HL
    AND (HL)
    DEC HL
    INC A
    JR NZ,mc_start_found
    LD A,2
    LD (MM_RUN_CTRL),A
    LD HL,(MM_LINE_END)
    LD (MM_CUR_PTR),HL
    RET
mc_start_found:
    PUSH HL
    LD HL,(MM_RUN_CUR_RECORD)
    LD DE,MC_MAIN_DIRECT_RECORD
    OR A
    SBC HL,DE
    POP HL
    PUSH AF
    CALL mc_cb_RUN_ENTER_RECORD
    LD A,1
    LD (MM_RUN_CTRL),A
    POP AF
    RET NZ
    CALL mc_cb_RUN_EXEC
    LD HL,(MM_LINE_END)
    LD (MM_CUR_PTR),HL
    RET
mc_start_missing:
    LD A,8
    JP ncb_SQ_ERROR

mc_load_read:
    LD A,(MM_LOAD_DRIVE)
    LD HL,MM_LOAD_READ_TRACK
    LD D,(HL)
    INC HL
    LD E,(HL)
    CALL mc_cb_MAIN_SUB_READ_CHR_RETRY
    LD A,0
    JR C,mc_read_done
    INC A
mc_read_done:
    LD (MM_LOAD_READ_OK),A
    RET
mc_load_line:
    LD A,(MM_LOAD_LINE_LEN)
    LD (MM_VAR_LINELEN),A
    OR A
    JR Z,mc_bad_line
    LD A,(MM_LINE_BUF)
    CP '0'
    JR C,mc_bad_line
    CP '9'+1
    JR NC,mc_bad_line
    CALL mc_cb_PARSE_LINENUM
    JR C,mc_bad_line
    CALL mc_cb_PROGRAM_STORE_LINE
    XOR A
    LD (MM_LOAD_LINE_LEN),A
    RET
mc_bad_line:
    LD A,57
    JP ncb_SQ_ERROR
mc_load_finish:
    LD HL,(MM_LINE_END)
    LD (MM_CUR_PTR),HL
    LD A,2
    LD (MM_RUN_CTRL),A
    RET


mc_cb_MAIN_SUB_READ_CHR_RETRY:
    LD IX,MC_MAIN_MAIN_SUB_READ_CHR_RETRY
    JP MM_N_PROBE
mc_cb_PARSE_LINENUM:
    LD IX,MC_MAIN_PARSE_LINENUM
    JP MM_N_PROBE
mc_cb_PROGRAM_STORE_LINE:
    LD IX,MC_MAIN_PROGRAM_STORE_LINE
    JP MM_N_PROBE
mc_cb_RUN_FIND_LINE:
    LD IX,MC_MAIN_RUN_FIND_LINE
    JP MM_N_PROBE
mc_cb_RUN_ENTER_RECORD:
    LD IX,MC_MAIN_RUN_ENTER_RECORD
    JP MM_N_PROBE
mc_cb_RUN_EXEC:
    LD IX,MC_MAIN_RUN_EXEC
    JP MM_N_PROBE

mc_save_entry:
    ; l4-program.md 11.1–11.2: 自作保存形式はASCII行と異なる種別で記録。
    ; 名前だけのSAVEは既存のASCII書出し経路へ一時的な ,A を渡す。
    XOR A
    LD (MM_SAVE_PROGRAM_FORMAT),A
    LD HL,(CUR_PTR)
    PUSH HL
    CALL ncb_SKIP_SPACES
    CALL ncb_PEEK_CHAR
    CP '"'
    JR NZ,_save_normal
    CALL ncb_ADV_PTR
_save_find_quote:
    CALL mc_cb_AT_END
    JR Z,_save_normal
    CALL ncb_PEEK_CHAR
    CP '"'
    JR Z,_save_quote_end
    CALL ncb_ADV_PTR
    JR _save_find_quote
_save_quote_end:
    CALL ncb_ADV_PTR
    CALL ncb_SKIP_SPACES
    CALL ncb_PEEK_CHAR
    OR A
    JR Z,_save_default
    CP ':'
    JR NZ,_save_normal
_save_default:
    LD DE,(CUR_PTR)
    POP HL
    PUSH DE
    LD BC,(LINE_END)
    PUSH BC
    PUSH HL
    EX DE,HL
    OR A
    SBC HL,DE
    LD B,H
    LD C,L
    POP HL
    LD DE,MM_RUN_STR_ARG1_BUF
    LDIR
    LD A,','
    LD (DE),A
    INC DE
    LD A,'A'
    LD (DE),A
    INC DE
    EX DE,HL
    LD (LINE_END),HL
    LD HL,MM_RUN_STR_ARG1_BUF
    LD (CUR_PTR),HL
    LD A,0x80                ; l3-disk-format.md 1.3: プログラム種別。
    LD (MM_SAVE_PROGRAM_FORMAT),A
    LD A,2
    LD HL,06080h
    CALL mc_cb_EXT_BANK_CALL
    POP HL
    LD (LINE_END),HL
    POP HL
    LD (CUR_PTR),HL
    RET
_save_normal:
    POP HL
    LD (CUR_PTR),HL
    LD A,2
    LD HL,06080h
    JP mc_cb_EXT_BANK_CALL


mc_cb_EXT_BANK_CALL:
    LD IX,MC_MAIN_EXT_BANK_CALL
    JP MM_N_PROBE
mc_cb_AT_END:
    LD IX,MC_MAIN_AT_END
    JP MM_N_PROBE

; l4-program.md 第12節: MOTORは30hの写しのbit3だけを変更する。
motor_stmt:
    CALL ncb_SKIP_SPACES
    CALL ncb_PEEK_CHAR
    OR A
    JR Z,motor_on
    CP ':'
    JR Z,motor_on
    CALL mc_cb_FN_IS_STRING
    OR A
    JR NZ,motor_type
    CALL mc_cb_EXPR
    CALL ncb_sq_bad
    RET NZ
    ; 第12節: 小数も式そのものが0かどうかで判定する。
    CALL mc_cb_VAL_IS_NEGATIVE
    OR A
    JP NZ,ncb_sq_illegal
    XOR A
    LD (MM_RHS_TYPE),A
    LD HL,255
    LD (MM_RHS_DATA),HL
    CALL mc_cb_VAL_COMPARE_CUR_RHS
    CP 1
    JP Z,ncb_sq_illegal
    CALL mc_cb_VAL_CUR_IS_ZERO
    OR A
    JR Z,motor_on
    LD A,(MM_SCR_P30)
    AND 0F7h
    JR motor_write
motor_on:
    LD A,(MM_SCR_P30)
    OR 8
motor_write:
    LD (MM_SCR_P30),A
    OUT (0x30),A
    RET
motor_type:
    LD A,13
    JP ncb_SQ_ERROR


mc_cb_FN_IS_STRING:
    LD IX,MC_MAIN_FN_IS_STRING
    JP MM_N_PROBE
mc_cb_EXPR:
    LD IX,MC_MAIN_EXPR
    JP MM_N_PROBE
mc_cb_VAL_IS_NEGATIVE:
    LD IX,MC_MAIN_VAL_IS_NEGATIVE
    JP MM_N_PROBE
mc_cb_VAL_COMPARE_CUR_RHS:
    LD IX,MC_MAIN_VAL_COMPARE_CUR_RHS
    JP MM_N_PROBE
mc_cb_VAL_CUR_IS_ZERO:
    LD IX,MC_MAIN_VAL_CUR_IS_ZERO
    JP MM_N_PROBE
