; l4-program.md 10.1: RENUM の引数と変更前の範囲検査。
; ONWHILE_WORK は文境界でのみ使う一時領域で、編集終了後に破棄する。
    ORG 0x3000
    JP renum_entry
    JP renum_resume
renum_parse:
    LD HL,10
    LD (MM_RENUM_NEW),HL
    LD (MM_RENUM_STEP),HL
    LD HL,0
    LD (MM_RENUM_OLD),HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR Z,renum_old_comma
    OR A
    JR Z,renum_validate
    CP ':'
    JR Z,renum_validate
    CALL PARSE_LINENUM_CUR
    JP C,renum_syntax
    LD (MM_RENUM_NEW),HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR NZ,renum_end
renum_old_comma:
    CALL ADV_PTR
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR Z,renum_step_comma
    OR A
    JR Z,renum_validate
    CP ':'
    JR Z,renum_validate
    CALL PARSE_LINENUM_CUR
    JP C,renum_syntax
    LD (MM_RENUM_OLD),HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR NZ,renum_end
renum_step_comma:
    CALL ADV_PTR
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,renum_validate
    CP ':'
    JR Z,renum_validate
    CALL PARSE_LINENUM_CUR
    JP C,renum_syntax
    LD A,H
    OR L
    JP Z,renum_illegal
    LD (MM_RENUM_STEP),HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
renum_end:
    OR A
    JR Z,renum_validate
    CP ':'
    JR NZ,renum_syntax
renum_validate:
    LD HL,(MM_RENUM_NEW)
    LD (MM_RENUM_NEXT),HL
    LD HL,MM_PROGRAM_AREA
    LD (MM_RENUM_PTR),HL
    XOR A
    LD (MM_RENUM_SCAN_PREV),A
renum_check_record:
    LD HL,(MM_RENUM_PTR)
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD A,D
    AND E
    INC A
    JR Z,renum_checked
    EX DE,HL
    LD DE,(MM_RENUM_OLD)
    OR A
    SBC HL,DE
    JR C,renum_check_unchanged
    LD A,(MM_RENUM_SCAN_PREV)
    OR A
    JR Z,renum_check_number
    LD HL,(MM_RENUM_MAP_LINE)
    LD DE,(MM_RENUM_NEW)
    OR A
    SBC HL,DE
    JP NC,renum_illegal
    XOR A
    LD (MM_RENUM_SCAN_PREV),A
renum_check_number:
    LD HL,(MM_RENUM_NEXT)
    LD DE,65530
    OR A
    SBC HL,DE
    JR NC,renum_illegal
    ADD HL,DE
    LD DE,(MM_RENUM_STEP)
    ADD HL,DE
    JR NC,renum_check_save
    LD HL,0
    DEC HL
renum_check_save:
    LD (MM_RENUM_NEXT),HL
    JR renum_check_advance
renum_check_unchanged:
    LD HL,(MM_RENUM_PTR)
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
    LD (MM_RENUM_MAP_LINE),HL
    LD A,1
    LD (MM_RENUM_SCAN_PREV),A
renum_check_advance:
    LD HL,(MM_RENUM_PTR)
    INC HL
    INC HL
    LD E,(HL)
    LD D,0
    INC HL
    ADD HL,DE
    LD (MM_RENUM_PTR),HL
    JR renum_check_record
renum_checked:
    XOR A
    LD (MM_ERROR_FLAG),A
    RET
renum_syntax:
    LD A,2
    JP ERR_SET_A
renum_illegal:
    LD A,5
    JP ERR_SET_A

; 存在する旧行番号を新番号へ写す。本文変更中も旧行番号のヘッダを
; 保持し、全参照を書き終えた後でヘッダを更新する（10.1節）。
; HL=旧番号、戻りHL=新番号、CF=1なら未定義。
renum_lookup:
    LD (MM_RENUM_TARGET),HL
    LD HL,(MM_RENUM_NEW)
    LD (MM_RENUM_MAP_NEXT),HL
    LD HL,MM_PROGRAM_AREA
    LD (MM_RENUM_MAP_PTR),HL
renum_map_loop:
    LD HL,(MM_RENUM_MAP_PTR)
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD A,D
    AND E
    INC A
    JR Z,renum_map_missing
    EX DE,HL
    LD (MM_RENUM_MAP_LINE),HL
    LD DE,(MM_RENUM_OLD)
    OR A
    SBC HL,DE
    JR C,renum_map_before
    LD HL,(MM_RENUM_MAP_NEXT)
    JR renum_map_compare
renum_map_before:
    LD HL,(MM_RENUM_MAP_LINE)
renum_map_compare:
    LD (MM_RENUM_RESULT),HL
    LD HL,(MM_RENUM_MAP_LINE)
    LD DE,(MM_RENUM_TARGET)
    OR A
    SBC HL,DE
    JR Z,renum_map_found
    JR NC,renum_map_missing
    LD HL,(MM_RENUM_MAP_LINE)
    LD DE,(MM_RENUM_OLD)
    OR A
    SBC HL,DE
    JR C,renum_map_advance
    LD HL,(MM_RENUM_MAP_NEXT)
    LD DE,(MM_RENUM_STEP)
    ADD HL,DE
    LD (MM_RENUM_MAP_NEXT),HL
renum_map_advance:
    LD HL,(MM_RENUM_MAP_PTR)
    INC HL
    INC HL
    LD E,(HL)
    LD D,0
    INC HL
    ADD HL,DE
    LD (MM_RENUM_MAP_PTR),HL
    JR renum_map_loop
renum_map_found:
    LD HL,(MM_RENUM_RESULT)
    OR A
    RET
renum_map_missing:
    SCF
    RET

; HLの行番号を十進ASCIIへ変換する。書換え前の数字は上書きしない。
; 返り値はMM_RUN_STR_TMP_BUFとMM_RENUM_NEW_LEN（1〜5）。
renum_format:
    LD (MM_RENUM_TARGET),HL
    XOR A
    LD (MM_RENUM_NEW_LEN),A
    LD IX,renum_places
    LD B,5
renum_format_place:
    LD L,(IX+0)
    LD H,(IX+1)
    LD (MM_RENUM_MAP_LINE),HL
    XOR A
    LD (MM_RENUM_DIGIT),A
renum_format_subtract:
    LD HL,(MM_RENUM_TARGET)
    LD DE,(MM_RENUM_MAP_LINE)
    OR A
    SBC HL,DE
    JR C,renum_format_output
    LD (MM_RENUM_TARGET),HL
    LD A,(MM_RENUM_DIGIT)
    INC A
    LD (MM_RENUM_DIGIT),A
    JR renum_format_subtract
renum_format_output:
    LD A,(MM_RENUM_NEW_LEN)
    OR A
    JR NZ,renum_format_append
    LD A,(MM_RENUM_DIGIT)
    OR A
    JR NZ,renum_format_append
    LD A,B
    CP 1
    JR NZ,renum_format_advance
renum_format_append:
    LD A,(MM_RENUM_NEW_LEN)
    LD E,A
    LD D,0
    LD HL,MM_RUN_STR_TMP_BUF
    ADD HL,DE
    LD A,(MM_RENUM_DIGIT)
    ADD A,'0'
    LD (HL),A
    LD A,(MM_RENUM_NEW_LEN)
    INC A
    LD (MM_RENUM_NEW_LEN),A
renum_format_advance:
    INC IX
    INC IX
    DJNZ renum_format_place
    RET
renum_places:
    DW 10000,1000,100,10,1

; l4-program.md 10.1: 引用符・REM・DATAを避け、行番号参照を列挙する。
; HL=行レコード。見つかるたびREF_START/ENDとTARGETを返し、次回は続きから。
renum_scan_begin:
    INC HL
    INC HL
    LD E,(HL)
    LD D,0
    INC HL
    LD (MM_CUR_PTR),HL
    ADD HL,DE
    LD (MM_LINE_END),HL
    XOR A
    LD (MM_RENUM_SCAN_PREV),A
    LD (MM_RENUM_SCAN_LIST),A
    LD (MM_RENUM_ERROR_CONTEXT),A
    RET
renum_scan_next:
    LD A,(MM_RENUM_SCAN_LIST)
    OR A
    JP Z,renum_scan_loop
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JP Z,renum_scan_comma
    XOR A
    LD (MM_RENUM_SCAN_LIST),A
    JP renum_scan_loop
renum_scan_comma:
    CALL ADV_PTR
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JP Z,renum_scan_comma
    JP renum_scan_number
renum_scan_loop:
    CALL PEEK_CHAR
    OR A
    JP Z,renum_scan_done
    CP 39
    JP Z,renum_scan_done
    CP '"'
    JP Z,renum_scan_quote
    LD A,(MM_RENUM_SCAN_PREV)
    CP 'A'
    JP C,renum_scan_try_word
    CP 'Z'+1
    JP C,renum_scan_one
    CP 'a'
    JP C,renum_scan_try_word
    CP 'z'+1
    JP C,renum_scan_one
renum_scan_try_word:
    CALL renum_word_find
    OR A
    JP Z,renum_scan_one
    LD (MM_CUR_PTR),HL
    CP 3
    JP Z,renum_scan_done
    CP 4
    JP Z,renum_scan_data
    CP 5
    JP Z,renum_scan_go
    CP 6
    JP Z,renum_scan_loop
    CP 7
    JP Z,renum_scan_on
    CP 8
    JP Z,renum_scan_error_word
    CP 2
    JP NZ,renum_scan_single
    LD A,1
    LD (MM_RENUM_SCAN_LIST),A
renum_scan_single:
    CALL SKIP_SPACES
    JP renum_scan_number
renum_scan_on:
    LD A,1
    LD (MM_RENUM_ERROR_CONTEXT),A
    JP renum_scan_loop
renum_scan_error_word:
    LD A,(MM_RENUM_ERROR_CONTEXT)
    CP 1
    LD A,0
    JR NZ,renum_scan_error_store
    LD A,2
renum_scan_error_store:
    LD (MM_RENUM_ERROR_CONTEXT),A
    JP renum_scan_loop
renum_scan_go:
    CALL SKIP_SPACES
    LD IX,renum_go_words
    CALL renum_word_match
    OR A
    JP Z,renum_scan_loop
    LD (MM_CUR_PTR),HL
    LD A,1
    LD (MM_RENUM_SCAN_LIST),A
    CALL SKIP_SPACES
renum_scan_number:
    CALL PEEK_CHAR
    CP ','
    JP NZ,renum_scan_digit
    LD A,(MM_RENUM_SCAN_LIST)
    OR A
    JP NZ,renum_scan_comma
    JP renum_scan_not_number
renum_scan_digit:
    CP '0'
    JP C,renum_scan_not_number
    CP '9'+1
    JP NC,renum_scan_not_number
    LD HL,(MM_CUR_PTR)
    LD (MM_RENUM_REF_START),HL
    CALL PARSE_LINENUM_CUR
    JP C,renum_scan_not_number
    LD A,(MM_RENUM_ERROR_CONTEXT)
    CP 2
    JR NZ,renum_scan_target
    LD A,H
    OR L
    JR NZ,renum_scan_target
    ; ON ERROR GOTO 0 は捕捉解除であり行参照ではない。
    XOR A
    LD (MM_RENUM_ERROR_CONTEXT),A
    LD (MM_RENUM_SCAN_LIST),A
    LD (MM_RENUM_SCAN_PREV),A
    JP renum_scan_loop
renum_scan_target:
    XOR A
    LD (MM_RENUM_ERROR_CONTEXT),A
    LD (MM_RENUM_TARGET),HL
    LD HL,(MM_CUR_PTR)
    LD (MM_RENUM_REF_END),HL
    XOR A
    LD (MM_RENUM_SCAN_PREV),A
    OR A
    RET
renum_scan_not_number:
    XOR A
    LD (MM_RENUM_ERROR_CONTEXT),A
    LD (MM_RENUM_SCAN_LIST),A
    LD (MM_RENUM_SCAN_PREV),A
    JP renum_scan_loop
renum_scan_quote:
    CALL ADV_PTR
renum_scan_quote_loop:
    CALL PEEK_CHAR
    OR A
    JP Z,renum_scan_done
    CP '"'
    CALL ADV_PTR
    JP NZ,renum_scan_quote_loop
    XOR A
    LD (MM_RENUM_SCAN_PREV),A
    JP renum_scan_loop
renum_scan_data:
    CALL PEEK_CHAR
    OR A
    JP Z,renum_scan_done
    CP ':'
    JP Z,renum_scan_one
    CP '"'
    JP NZ,renum_scan_data_one
    CALL ADV_PTR
renum_scan_data_quote:
    CALL PEEK_CHAR
    OR A
    JP Z,renum_scan_done
    CP '"'
    CALL ADV_PTR
    JP NZ,renum_scan_data_quote
    JP renum_scan_data
renum_scan_data_one:
    CALL ADV_PTR
    JP renum_scan_data
renum_scan_one:
    CALL PEEK_CHAR
    PUSH AF
    CP ' '
    JR Z,renum_scan_keep_context
    XOR A
    LD (MM_RENUM_ERROR_CONTEXT),A
renum_scan_keep_context:
    POP AF
    CP '0'
    JR C,renum_scan_store_prev
    CP '9'+1
    JR NC,renum_scan_store_prev
    ; 識別子内の数字を越えて語尾を命令語と誤認しない。
    LD A,(MM_RENUM_SCAN_PREV)
    AND 0DFh
    CP 'A'
    JR C,renum_scan_digit_prev
    CP 'Z'+1
    JR C,renum_scan_advance
renum_scan_digit_prev:
    CALL PEEK_CHAR
renum_scan_store_prev:
    LD (MM_RENUM_SCAN_PREV),A
renum_scan_advance:
    CALL ADV_PTR
    JP renum_scan_loop
renum_scan_done:
    SCF
    RET

; IX は長さ・種類・最大7文字の固定長テーブル。HLは一致直後。
renum_word_find:
    LD IX,renum_words
renum_word_match:
    LD A,(IX+0)
    OR A
    RET Z
    PUSH IX
    LD B,A
    INC IX
    INC IX
    LD HL,(MM_CUR_PTR)
renum_word_char:
    PUSH HL
    LD DE,(MM_LINE_END)
    OR A
    SBC HL,DE
    POP HL
    JP NC,renum_word_no
    LD A,(HL)
    AND 0DFh
    CP (IX+0)
    JP NZ,renum_word_no
    INC HL
    INC IX
    DJNZ renum_word_char
    PUSH HL
    LD DE,(MM_LINE_END)
    OR A
    SBC HL,DE
    POP HL
    JP Z,renum_word_yes
    LD A,(HL)
    AND 0DFh
    CP 'A'
    JP C,renum_word_yes
    CP 'Z'+1
    JP C,renum_word_no
renum_word_yes:
    POP IX
    LD A,(IX+1)
    OR A
    RET
renum_word_no:
    POP IX
    LD DE,9
    ADD IX,DE
    JP renum_word_match
renum_words:
    DB 4,2,"GOTO",0,0,0
    DB 5,2,"GOSUB",0,0
    DB 4,1,"THEN",0,0,0
    DB 4,1,"ELSE",0,0,0
    DB 7,1,"RESTORE"
    DB 6,1,"RESUME",0
    DB 3,1,"RUN",0,0,0,0
    DB 3,3,"REM",0,0,0,0
    DB 4,4,"DATA",0,0,0
    DB 2,5,"GO",0,0,0,0,0
    DB 2,6,"IF",0,0,0,0,0
    DB 2,7,"ON",0,0,0,0,0
    DB 5,8,"ERROR",0,0
    DB 0
renum_go_words:
    DB 2,2,"TO",0,0,0,0,0
    DB 3,2,"SUB",0,0,0,0
    DB 0

; 参照の数字をMM_RUN_STR_TMP_BUFの十進文字列へ置換する。
; 前後のレコードと番兵を重なりに応じて移し、行長と走査終端を更新する。
renum_replace_reference:
    LD HL,(MM_RENUM_REF_END)
    LD DE,(MM_RENUM_REF_START)
    OR A
    SBC HL,DE
    LD A,L
    LD B,A
    LD A,(MM_RENUM_NEW_LEN)
    SUB B
    LD (MM_RENUM_DELTA),A
    JP Z,renum_replace_copy
    JP M,renum_replace_shrink
    ; 行長の8bit表現と可変領域の境界を先に検査する。
    LD B,A
    LD HL,(MM_RENUM_PTR)
    INC HL
    INC HL
    LD A,(HL)
    ADD A,B
    JP C,renum_replace_memory
    LD A,B
    LD E,A
    LD D,0
    PUSH DE
    CALL PROGRAM_FIND_END
    INC HL
    INC HL
    POP DE
    PUSH HL
    ADD HL,DE
    LD DE,(MM_RUN_FOR_STACK)
    OR A
    SBC HL,DE
    POP HL
    JR C,renum_replace_room
    JR NZ,renum_replace_memory
renum_replace_room:
    DEC HL                         ; 元の番兵末尾
    LD (MM_RENUM_COPY_END),HL
    LD A,(MM_RENUM_DELTA)
    LD E,A
    LD D,0
    ADD HL,DE
    EX DE,HL                      ; DE=移動先末尾
    LD HL,(MM_RENUM_COPY_END)
    PUSH HL
    LD BC,(MM_RENUM_REF_END)
    OR A
    SBC HL,BC
    LD B,H
    LD C,L
    INC BC
    POP HL
    LDDR
    JR renum_replace_adjust
renum_replace_shrink:
    CALL PROGRAM_FIND_END
    INC HL
    INC HL
    LD DE,(MM_RENUM_REF_END)
    OR A
    SBC HL,DE
    LD B,H
    LD C,L
    LD HL,(MM_RENUM_REF_START)
    LD A,(MM_RENUM_NEW_LEN)
    LD E,A
    LD D,0
    ADD HL,DE
    EX DE,HL                      ; DE=移動先
    LD HL,(MM_RENUM_REF_END)
    LDIR
renum_replace_adjust:
    LD HL,(MM_RENUM_PTR)
    INC HL
    INC HL
    LD A,(MM_RENUM_DELTA)
    ADD A,(HL)
    LD (HL),A
    LD HL,(MM_LINE_END)
    LD A,(MM_RENUM_DELTA)
    LD E,A
    LD D,0
    BIT 7,E
    JR Z,renum_replace_positive
    DEC D
renum_replace_positive:
    ADD HL,DE
    LD (MM_LINE_END),HL
renum_replace_copy:
    LD HL,MM_RUN_STR_TMP_BUF
    LD DE,(MM_RENUM_REF_START)
    LD A,(MM_RENUM_NEW_LEN)
    LD C,A
    LD B,0
    LDIR
    EX DE,HL
    LD (MM_CUR_PTR),HL
    XOR A
    RET
renum_replace_memory:
    LD A,7
    CALL ERR_SET_A
    SCF
    RET

; 表示が必要な未定義参照では A=2 で中断する。呼出側が警告を出し、
; 次の入口から走査を再開する。旧ヘッダは参照を全て処理するまで保持する。
renum_entry:
    CALL renum_parse
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
    LD HL,MM_PROGRAM_AREA
    LD (MM_RENUM_PTR),HL
renum_record:
    LD HL,(MM_RENUM_PTR)
    LD A,(HL)
    INC HL
    AND (HL)
    INC A
    JR Z,renum_headers
    LD HL,(MM_RENUM_PTR)
    CALL renum_scan_begin
renum_resume:
    CALL renum_scan_next
    JR C,renum_next_record
    LD HL,(MM_RENUM_TARGET)
    CALL renum_lookup
    JR C,renum_missing_return
    CALL renum_format
    CALL renum_replace_reference
    LD A,(MM_ERROR_FLAG)
    OR A
    RET NZ
    JR renum_resume
renum_missing_return:
    LD A,2
    RET
renum_next_record:
    LD HL,(MM_LINE_END)
    LD (MM_RENUM_PTR),HL
    JR renum_record
renum_headers:
    LD HL,(MM_RENUM_NEW)
    LD (MM_RENUM_NEXT),HL
    LD HL,MM_PROGRAM_AREA
    LD (MM_RENUM_PTR),HL
renum_header_loop:
    LD HL,(MM_RENUM_PTR)
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD A,D
    AND E
    INC A
    JR Z,renum_complete
    EX DE,HL
    LD DE,(MM_RENUM_OLD)
    OR A
    SBC HL,DE
    JR C,renum_header_advance
    LD HL,(MM_RENUM_PTR)
    LD DE,(MM_RENUM_NEXT)
    LD (HL),E
    INC HL
    LD (HL),D
    EX DE,HL
    LD DE,(MM_RENUM_STEP)
    ADD HL,DE
    LD (MM_RENUM_NEXT),HL
renum_header_advance:
    LD HL,(MM_RENUM_PTR)
    INC HL
    INC HL
    LD E,(HL)
    LD D,0
    INC HL
    ADD HL,DE
    LD (MM_RENUM_PTR),HL
    JR renum_header_loop
renum_complete:
    LD A,2
    LD (MM_RUN_CTRL),A
    XOR A
    LD (MM_ERROR_FLAG),A
    RET
