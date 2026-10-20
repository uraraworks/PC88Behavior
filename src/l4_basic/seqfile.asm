; l4-basic 第24節。ヒープ種別6: 管理42B+専用256B。
; +0..7 名前, +8 種別, +9 名前9字目, +10 drive, +11 mode,
; +12 先頭単位,+13 現単位,+14 単位内sector,+16 offset,+17 valid,
; +18 dirty,+19 column,+20 LOF(word),+22 LOC(word),+24 EOF。
SQ_INIT:
    XOR A
    LD HL,MM_SQ_HANDLES
    LD B,37
sq_init_loop:
    LD (HL),A
    INC HL
    DJNZ sq_init_loop
    RET
SQ_ERROR:
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_FLAG),A
    RET
sq_badnum:
    LD A,52
    JP SQ_ERROR
sq_opened:
    LD A,54
    JP SQ_ERROR
sq_syntax:
    LD A,2
    JP SQ_ERROR
sq_bad:
    LD A,(ERROR_FLAG)
    OR A
    RET
sq_current:
    LD IY,(MM_SQ_CURRENT)
    RET
; 任意数式を既存の整数化へ渡す。1..2以外の8bitは52。
sq_number:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '#'
    CALL Z,ADV_PTR
    CALL EXPR
    CALL sq_bad
    RET NZ
    CALL CUR_TO_INT16
    OR A
    JP Z,sq_illegal
    EX DE,HL
    LD A,H
    OR A
    JR NZ,sq_illegal
    LD A,L
    DEC A
    CP 2
    JP NC,sq_badnum
    ADD A,A
    LD E,A
    LD D,0
    LD HL,MM_SQ_HANDLES
    ADD HL,DE
    LD (MM_SQ_SLOT),HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD (MM_SQ_CURRENT),DE
    XOR A
    RET
sq_illegal:
    LD A,5
    JP SQ_ERROR
sq_select:
    CALL sq_number
    CALL sq_bad
    RET NZ
    LD HL,(MM_SQ_CURRENT)
    LD A,H
    OR L
    JP Z,sq_badnum
    JP sq_current
sq_comma:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JP NZ,sq_syntax
    JP ADV_PTR
sq_keyword:
    LD (RUN_KW_TEXT),HL
    LD (RUN_KW_LEN),A
    JP TRY_MATCH_KEYWORD_GENERIC
SQ_TRY_STMT:
    CALL SKIP_SPACES
    LD HL,sq_open_word
    LD A,4
    CALL sq_keyword
    OR A
    JR NZ,sq_do_open
    LD HL,sq_close_word
    LD A,5
    CALL sq_keyword
    OR A
    JR NZ,sq_do_close
    LD HL,sq_write_word
    LD A,5
    CALL sq_keyword
    OR A
    RET Z
    CALL SQ_WRITE
    LD A,1
    RET
sq_do_close:
    CALL SQ_CLOSE
    LD A,1
    RET
sq_do_open:
    CALL SQ_OPEN
    LD A,1
    RET
sq_open_word: DB "OPEN"
sq_close_word: DB "CLOSE"
sq_write_word: DB "WRITE"
sq_for_word: DB "FOR"
sq_as_word: DB "AS"
sq_modes: DB "INPUT",0,"OUTPUT",0,"APPEND",0
; ファイル名は式文字列。既定drive=0、明示1:/2:を外す。
sq_filename:
    CALL STRING_EXPR
    CALL sq_bad
    RET NZ
    LD HL,RUN_STR_TMP_BUF
    LD A,(RUN_STR_TMP_LEN)
    LD B,A
    XOR A
    LD (MM_SQ_DRIVE),A
    LD A,B
    CP 2
    JR C,sq_name_pad
    INC HL
    LD A,(HL)
    DEC HL
    CP ':'
    JR NZ,sq_name_pad
    LD A,(HL)
    SUB '1'
    CP 2
    JP NC,sq_syntax
    LD (MM_SQ_DRIVE),A
    INC HL
    INC HL
    DEC B
    DEC B
sq_name_pad:
    LD A,B
    OR A
    JP Z,sq_syntax
    CP 10
    JP NC,sq_syntax
    LD DE,MM_SQ_NAME
    LD C,9
sq_name_copy:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DEC C
    DJNZ sq_name_copy
    LD A,C
    OR A
    RET Z
    LD B,C
    LD A,' '
sq_name_spaces:
    LD (DE),A
    INC DE
    DJNZ sq_name_spaces
    RET
; 名前とdriveをSAVE作業へ渡し、既存の探索/通信を利用。
sq_disk_name:
    LD HL,MM_SQ_NAME
    LD DE,MM_S2_NAME
    LD BC,9
    LDIR
    LD A,(MM_SQ_DRIVE)
    LD (MM_S2_DRIVE),A
    RET
sq_handle_name:
    CALL sq_current
    PUSH IY
    POP HL
    LD DE,MM_S2_NAME
    LD BC,8
    LDIR
    LD A,(IY+9)
    LD (DE),A
    LD A,(IY+10)
    LD (MM_S2_DRIVE),A
    RET
sq_disk:
    LD (MM_SQ_OP),A
    PUSH IY
    LD A,2
    LD HL,06003h
    CALL EXT_BANK_CALL
    POP IY
    RET
sq_fat:
    CALL sq_handle_name
    LD A,6
    JP sq_disk
sq_fat_at:
    LD L,A
    LD H,0
    LD DE,MM_S2_FAT
    ADD HL,DE
    RET
; 同名ファイルの開放状態（番号が異なっても54）。
SQ_KILL:
    LD HL,(CUR_PTR)
    PUSH HL
    CALL sq_filename
    CALL sq_disk_name
    CALL SQ_KILL_CHECK
    POP HL
    LD (CUR_PTR),HL
    RET
SQ_KILL_CHECK:
    LD HL,MM_SQ_HANDLES
    LD B,2
sq_check_loop:
    PUSH BC
    PUSH HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD A,D
    OR E
    JR Z,sq_check_next
    PUSH DE
    POP IY
    LD A,(MM_S2_DRIVE)
    CP (IY+10)
    JR NZ,sq_check_next
    PUSH IY
    POP HL
    LD DE,MM_S2_NAME
    LD B,8
sq_check_name:
    LD A,(DE)
    CP (HL)
    JR NZ,sq_check_next
    INC DE
    INC HL
    DJNZ sq_check_name
    LD A,(DE)
    CP (IY+9)
    JR Z,sq_check_found
sq_check_next:
    POP HL
    INC HL
    INC HL
    POP BC
    DJNZ sq_check_loop
    RET
sq_check_found:
    POP HL
    POP BC
    JP sq_opened
SQ_OPEN:
    CALL sq_filename
    CALL sq_bad
    RET NZ
    LD HL,sq_for_word
    LD A,3
    CALL sq_keyword
    OR A
    JP Z,sq_syntax
    CALL SKIP_SPACES
    LD HL,sq_modes
    LD A,5
    CALL sq_keyword
    LD A,1
    JR NZ,sq_mode_found
    LD HL,sq_modes+6
    LD A,6
    CALL sq_keyword
    LD A,2
    JR NZ,sq_mode_found
    LD HL,sq_modes+13
    LD A,6
    CALL sq_keyword
    OR A
    JP Z,sq_syntax
    LD A,3
sq_mode_found:
    LD (MM_SQ_MODE),A
    CALL SKIP_SPACES
    LD HL,sq_as_word
    LD A,2
    CALL sq_keyword
    OR A
    JP Z,sq_syntax
    CALL sq_number
    CALL sq_bad
    RET NZ
    LD HL,(MM_SQ_CURRENT)
    LD A,H
    OR L
    JP NZ,sq_opened
    CALL sq_disk_name
    CALL SQ_KILL_CHECK
    CALL sq_bad
    RET NZ
    LD A,(MM_SQ_MODE)
    CP 1
    JR Z,sq_open_find
    LD A,7
    CALL sq_disk
    CALL sq_bad
    RET NZ
sq_open_find:
    XOR A
    CALL sq_disk
    CALL sq_bad
    RET NZ
    LD A,(MM_SQ_MODE)
    CP 2
    JR Z,sq_open_create
    LD A,(MM_S2_FOUND)
    OR A
    JR NZ,sq_open_allocate
    LD A,(MM_SQ_MODE)
    CP 3
    JR Z,sq_open_create
    LD A,53
    JP SQ_ERROR
sq_open_create:
    LD HL,(MM_HEAP_END)
    LD (HL),0x1A
    LD HL,(MM_FREE_TOP)
    LD (MM_CAPTURE_END),HL
    LD A,6
    CALL sq_disk
    LD A,4
    CALL sq_disk
    CALL sq_bad
    RET NZ
    XOR A
    CALL sq_disk
sq_open_allocate:
    LD A,6
    CALL HEAP_ALLOC_MAIN
    OR A
    JR NZ,sq_have_record
    LD A,7
    JP SQ_ERROR
sq_have_record:
    LD (MM_SQ_CURRENT),HL
    LD DE,(MM_SQ_SLOT)
    LD A,L
    LD (DE),A
    INC DE
    LD A,H
    LD (DE),A
    PUSH HL
    LD DE,9
    ADD HL,DE
    LD B,33
    XOR A
sq_record_clear:
    LD (HL),A
    INC HL
    DJNZ sq_record_clear
    POP HL
    PUSH HL
    POP IY
    LD DE,MM_SQ_NAME
    EX DE,HL
    LD BC,8
    LDIR
    LD (IY+8),6
    LD A,(MM_SQ_NAME+8)
    LD (IY+9),A
    LD A,(MM_SQ_DRIVE)
    LD (IY+10),A
    LD A,(MM_SQ_MODE)
    LD (IY+11),A
    LD A,(MM_S2_OLDUNIT)
    LD (IY+12),A
    LD (IY+13),A
    CALL sq_fat
    LD A,(IY+12)
    LD B,160
sq_count_chain:
    PUSH BC
    CALL sq_fat_at
    LD A,(HL)
    CP 160
    LD C,8
    JR C,sq_count_add
    SUB 0xC0
    LD C,A
    LD A,0xFF
sq_count_add:
    LD E,(IY+20)
    LD D,(IY+21)
    LD L,C
    LD H,0
    ADD HL,DE
    LD (IY+20),L
    LD (IY+21),H
    POP BC
    CP 160
    JR NC,sq_open_ready
    DJNZ sq_count_chain
    LD A,64
    JP SQ_ERROR
sq_open_ready:
    LD A,(IY+11)
    CP 2
    JR NZ,sq_open_append
    LD (IY+20),0
    LD (IY+21),0
    RET
sq_open_append:
    CP 3
    RET NZ
    LD A,(IY+20)
    OR (IY+21)
    RET Z
sq_append_seek:
    CALL SQ_GET
    CP 0x1A
    JR NZ,sq_append_seek
    XOR A
    LD (IY+24),A
    RET
sq_buffer:
    PUSH IY
    POP HL
    LD DE,42
    ADD HL,DE
    RET
sq_address:
    LD A,(IY+13)
    SRL A
    LD D,A
    LD A,(IY+13)
    AND 1
    ADD A,A
    ADD A,A
    ADD A,A
    ADD A,(IY+14)
    INC A
    LD E,A
    LD (MM_SQ_WORK),DE
    RET
sq_load:
    CALL sq_current
    LD A,(IY+17)
    OR A
    RET NZ
    LD A,(IY+11)
    CP 2
    JR Z,sq_zero_buffer
    LD A,(IY+20)
    OR (IY+21)
    JR Z,sq_zero_buffer
    CALL sq_handle_name
    CALL sq_address
    LD A,1
    CALL sq_disk
    CALL sq_bad
    RET NZ
    LD HL,MM_MAIN_SUB_SECTOR_BUF
    PUSH HL
    CALL sq_buffer
    EX DE,HL
    POP HL
    LD BC,256
    LDIR
    JR sq_loaded
sq_zero_buffer:
    CALL sq_buffer
    LD (HL),0
    LD D,H
    LD E,L
    INC DE
    LD BC,255
    LDIR
sq_loaded:
    LD (IY+17),1
    LD A,(IY+11)
    CP 2
    RET NZ
    INC (IY+20)
    RET NZ
    INC (IY+21)
    RET
sq_flush:
    CALL sq_current
    LD A,(IY+18)
    OR A
    RET Z
    CALL sq_handle_name
    CALL sq_address
    CALL sq_buffer
    LD (MM_SQ_WORK+2),HL
    XOR A
    LD (MM_S2_WRITE_COUNT),A
    LD A,2
    CALL sq_disk
    CALL sq_bad
    RET NZ
    LD (IY+18),0
    RET
; バッファの次のセクタへ。必要な単位は既存の割当順で探す。
sq_advance:
    CALL sq_flush
    LD (IY+17),0
    INC (IY+14)
    LD A,(IY+14)
    CP 8
    RET C
    LD (IY+14),0
    LD A,(IY+11)
    CP 1
    JR Z,sq_read_next_unit
    LD A,(MM_SQ_OUTPUT)
    PUSH AF
    OR A
    CALL NZ,sq_format_save
    CALL sq_fat
    LD A,(IY+13)
    CALL sq_fat_at
    LD A,(HL)
    CP 160
    JR C,sq_next_unit
    PUSH HL
    XOR A
    LD (MM_SQ_TOKEN),A
sq_find_free:
    LD A,8
    CALL sq_disk
    PUSH AF
    CALL sq_fat_at
    LD A,(HL)
    CP 0xFF
    JR Z,sq_free_found
    POP AF
    LD HL,MM_SQ_TOKEN
    INC (HL)
    LD A,(HL)
    CP 158
    JR C,sq_find_free
    POP HL
    LD A,68
    CALL SQ_ERROR
    JR sq_advance_restore
sq_free_found:
    LD (HL),0xC0
    POP AF
    POP HL
    LD (HL),A
    PUSH AF
    LD A,3
    CALL sq_disk
    POP AF
sq_next_unit:
    LD (IY+13),A
sq_advance_restore:
    POP AF
    OR A
    CALL NZ,sq_format_restore
    RET
sq_read_next_unit:
    ; INPUT_RAWはFATと共用なので、読取の鎖参照は受信セクタ側だけで行う。
    CALL sq_handle_name
    LD D,37
    LD E,14
    LD (MM_SQ_WORK),DE
    LD A,1
    CALL sq_disk
    JR NC,sq_read_next_ok
    LD A,64
    JP SQ_ERROR
sq_read_next_ok:
    LD A,(IY+13)
    LD L,A
    LD H,0
    LD DE,MM_MAIN_SUB_SECTOR_BUF
    ADD HL,DE
    LD A,(HL)
    CP 160
    RET NC
    LD (IY+13),A
    RET
; 式評価終了後の出力中だけ、文字列引数/連結の一時域を再利用する。
; USINGの作業と書式は、FAT更新で共用セクタを使う間だけ退避する。
sq_format_save:
    LD HL,(MM_RUN_STR_ARG1_BUF+510)
    LD (MM_SQ_WORK+10),HL
    LD HL,MM_MAIN_SUB_SECTOR_BUF
    LD DE,MM_RUN_STR_ARG1_BUF
    LD BC,512
    LDIR
    RET
sq_format_restore:
    LD HL,MM_RUN_STR_ARG1_BUF
    LD DE,MM_MAIN_SUB_SECTOR_BUF
    LD BC,512
    LDIR
    LD HL,(MM_SQ_WORK+10)
    LD (MM_RUN_STR_ARG1_BUF+510),HL
    RET
SQ_CHAR:
    PUSH AF
    LD A,(ERROR_FLAG)
    OR A
    JR Z,sq_char_ready
    POP AF
    RET
sq_char_ready:
    LD A,(MM_SQ_WRITE)
    OR A
    JR Z,sq_char_file
    POP AF
    LD HL,(MM_SQ_WORK+4)
    LD (HL),A
    INC HL
    LD (MM_SQ_WORK+4),HL
    RET
sq_char_file:
    POP AF
    PUSH BC
    PUSH DE
    PUSH HL
    PUSH IY
    PUSH AF
    CALL sq_load
    CALL sq_buffer
    LD E,(IY+16)
    LD D,0
    ADD HL,DE
    POP AF
    LD (HL),A
    LD (IY+18),1
    LD (IY+25),1
    INC (IY+19)
    LD A,(MM_SQ_OUTPUT)
    OR A
    JR Z,sq_char_no_column
    LD A,(IY+19)
    LD (VAR_COL),A
sq_char_no_column:
    INC (IY+16)
    CALL Z,sq_advance
    POP IY
    POP HL
    POP DE
    POP BC
    RET
SQ_NEWLINE:
    LD A,13
    CALL SQ_CHAR
    LD A,10
    CALL SQ_CHAR
    CALL sq_current
    LD (IY+19),0
    XOR A
    LD (VAR_COL),A
    RET
SQ_PRINT:
    CALL sq_select
    CALL sq_bad
    RET NZ
    CALL sq_comma
    CALL sq_bad
    RET NZ
    CALL sq_output_begin
    CALL PRINT_BODY
    JP sq_output_end
sq_output_begin:
    LD A,(VAR_COL)
    LD (MM_SQ_COLUMN),A
    CALL sq_current
    LD A,(IY+19)
    LD (VAR_COL),A
    LD A,1
    LD (MM_SQ_OUTPUT),A
    RET
sq_output_end:
    XOR A
    LD (MM_SQ_OUTPUT),A
    LD A,(MM_SQ_COLUMN)
    LD (VAR_COL),A
    RET
SQ_WRITE:
    CALL sq_select
    CALL sq_bad
    RET NZ
    CALL sq_comma
    CALL sq_bad
    RET NZ
    CALL sq_output_begin
sq_write_loop:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,sq_write_end
    CP ':'
    JR Z,sq_write_end
    CALL FN_IS_STRING
    OR A
    JR Z,sq_write_number
    CALL STRING_EXPR
    CALL sq_bad
    JR NZ,sq_write_done
    LD A,'"'
    CALL PRINT_CHAR
    CALL PRINT_STRING_VAL
    LD A,'"'
    CALL PRINT_CHAR
    JR sq_write_next
sq_write_number:
    CALL LOGIC_OR_EXPR
    CALL sq_bad
    JR NZ,sq_write_done
    ; PRINT_VALUEの出力を共通文字列バッファに捕捉し、外側の空白だけ除く。
    LD A,1
    LD (MM_SQ_WRITE),A
    LD HL,RUN_STR_TMP_BUF
    LD (MM_SQ_WORK+4),HL
    CALL PRINT_VALUE
    XOR A
    LD (MM_SQ_WRITE),A
    LD HL,(MM_SQ_WORK+4)
    DEC HL
    LD (HL),0
    LD HL,RUN_STR_TMP_BUF
    LD A,(HL)
    CP ' '
    JR NZ,sq_write_digits
    INC HL
sq_write_digits:
    CALL PRINT_STR
sq_write_next:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR NZ,sq_write_end
    CALL ADV_PTR
    LD A,','
    CALL PRINT_CHAR
    JR sq_write_loop
sq_write_end:
    CALL NEWLINE
sq_write_done:
    JP sq_output_end
SQ_CLOSE:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JP Z,SQ_CLOSE_ALL
    CP ':'
    JP Z,SQ_CLOSE_ALL
sq_close_list:
    CALL sq_number
    CALL sq_bad
    RET NZ
    CALL sq_close_current
    CALL sq_bad
    RET NZ
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    RET NZ
    CALL ADV_PTR
    JR sq_close_list
SQ_CLOSE_ALL:
    XOR A
    LD (ERROR_FLAG),A
    LD HL,MM_SQ_HANDLES
    LD B,2
sq_close_all_loop:
    PUSH BC
    PUSH HL
    LD (MM_SQ_SLOT),HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD (MM_SQ_CURRENT),DE
    CALL sq_close_current
    POP HL
    POP BC
    CALL sq_bad
    RET NZ
    INC HL
    INC HL
    DJNZ sq_close_all_loop
    JP sq_bad
sq_close_current:
    LD HL,(MM_SQ_CURRENT)
    LD A,H
    OR L
    RET Z
    CALL sq_current
    LD A,(IY+11)
    CP 1
    JR Z,sq_close_flush
    LD A,(IY+25)
    OR A
    JR Z,sq_close_flush
    LD A,0x1A
    CALL SQ_CHAR
sq_close_flush:
    CALL sq_flush
    CALL sq_bad
    RET NZ
    LD A,(IY+11)
    CP 1
    JR Z,sq_close_free
    CALL sq_fat
    LD A,(IY+13)
    CALL sq_fat_at
    LD A,(IY+14)
    LD B,A
    LD A,(IY+16)
    OR A
    LD A,B
    JR Z,sq_close_count
    INC A
sq_close_count:
    ADD A,0xC0
    LD (HL),A
    LD A,3
    CALL sq_disk
sq_close_free:
    LD (IY+8),0x86
    LD HL,(MM_SQ_SLOT)
    LD (HL),0
    INC HL
    LD (HL),0
    RET
; GETは1文字だけ進める。最後のCRLFの直後にはSUBを先読みしない。
SQ_GET:
    CALL sq_current
    LD A,(IY+20)
    OR (IY+21)
    JR NZ,sq_get_nonempty
    LD A,55
    CALL SQ_ERROR
    LD A,0x1A
    RET
sq_get_nonempty:
    LD A,(IY+24)
    OR A
    JR NZ,sq_get_end
    LD A,(IY+16)
    OR A
    JR NZ,sq_get_load
    LD L,(IY+22)
    LD H,(IY+23)
    LD E,(IY+20)
    LD D,(IY+21)
    OR A
    SBC HL,DE
    JR NC,sq_get_end
    INC (IY+22)
    JR NZ,sq_get_load
    INC (IY+23)
sq_get_load:
    CALL sq_load
    CALL sq_bad
    JR NZ,sq_get_end
    CALL sq_buffer
    LD E,(IY+16)
    LD D,0
    ADD HL,DE
    LD A,(HL)
    PUSH AF
    INC (IY+16)
    CALL Z,sq_advance
    POP AF
    CP 0x1A
    RET NZ
sq_get_end:
    LD (IY+24),0xFF
    LD A,0x1A
    RET
SQ_INPUT:
    LD A,(MM_INPUT_LINE)
    LD (MM_SQ_LINE),A
    CALL sq_select
    CALL sq_bad
    RET NZ
    CALL sq_comma
    CALL sq_bad
    RET NZ
sq_input_target:
    XOR A
    LD (RUN_ASSIGN_KIND),A
    LD HL,(MM_SQ_CURRENT)
    PUSH HL
    CALL INPUT_TARGET
    POP DE
    LD (MM_SQ_CURRENT),DE
    CALL sq_bad
    RET NZ
    LD A,(RUN_ASSIGN_KIND)
    OR A
    JP Z,sq_syntax
    PUSH HL
    LD A,(MM_SQ_LINE)
    OR A
    JR Z,sq_input_collect
    LD A,(RUN_ASSIGN_KIND)
    CP 3
    JR Z,sq_input_collect
    POP HL
    LD A,13
    JP SQ_ERROR
sq_input_collect:
    XOR A
    LD (MM_SQ_LEN),A
    LD (MM_SQ_QUOTE),A
sq_input_char:
    CALL SQ_GET
    LD C,A
    CALL sq_bad
    JP NZ,sq_input_abort
    LD A,C
    CP 0x1A
    JR Z,sq_input_field
    CP 13
    JR NZ,sq_input_not_cr
    CALL SQ_GET             ; 規定のCRLFのLFを除く
    JR sq_input_field
sq_input_not_cr:
    CP 10
    JR Z,sq_input_field
    LD A,(MM_SQ_LINE)
    OR A
    JR NZ,sq_input_put
    LD A,C
    CP '"'
    JR NZ,sq_input_separator
    LD A,(MM_SQ_QUOTE)
    XOR 1
    LD (MM_SQ_QUOTE),A
sq_input_separator:
    LD A,(MM_SQ_QUOTE)
    OR A
    JR NZ,sq_input_put
    LD A,C
    CP ','
    JR Z,sq_input_field
sq_input_put:
    LD A,(MM_SQ_LEN)
    CP 255
    JR Z,sq_input_char
    LD E,A
    LD D,0
    LD HL,MM_INPUT_RAW
    ADD HL,DE
    LD (HL),C
    INC A
    LD (MM_SQ_LEN),A
    JR sq_input_char
sq_input_field:
    LD HL,(CUR_PTR)
    PUSH HL
    LD HL,(LINE_END)
    PUSH HL
    LD A,(MM_SQ_LINE)
    LD (MM_INPUT_LINE),A
    LD HL,MM_INPUT_RAW
    LD (CUR_PTR),HL
    LD A,(MM_SQ_LEN)
    LD E,A
    LD D,0
    ADD HL,DE
    LD (LINE_END),HL
    CALL INPUT_TOKEN
    POP HL
    LD (LINE_END),HL
    POP HL
    LD (CUR_PTR),HL
    CALL sq_bad
    JR NZ,sq_input_abort
    LD A,(RUN_ASSIGN_KIND)
    CP 3
    JR Z,sq_input_store
    CALL INPUT_NUMBER
    CALL sq_bad
    JR Z,sq_input_store
    LD A,(ERROR_KIND)
    CP 13
    JR NZ,sq_input_abort
    XOR A
    LD (ERROR_FLAG),A
    LD HL,0                 ; 非数値からの数値入力は自作判断で0
    CALL VAL_SET_INT
    CALL ASSIGN_CONVERT_CUR
sq_input_store:
    POP HL
    CALL INPUT_STORE
    CALL sq_bad
    RET NZ
    LD A,(MM_SQ_LINE)
    OR A
    RET NZ
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    RET NZ
    CALL ADV_PTR
    JP sq_input_target
sq_input_abort:
    POP HL
    RET
; 古い未実装語の予約処理より前で、括弧つきの呼出しだけを拾う。
SQ_TRY_FUNC:
    LD HL,(CUR_PTR)
    PUSH HL
    LD HL,sq_eof_word
    LD A,3
    CALL sq_keyword
    OR A
    LD A,0
    JR NZ,sq_func_found
    LD HL,sq_loc_word
    LD A,3
    CALL sq_keyword
    OR A
    LD A,1
    JR NZ,sq_func_found
    LD HL,sq_lof_word
    LD A,3
    CALL sq_keyword
    OR A
    LD A,2
    JR NZ,sq_func_found
sq_func_none:
    POP HL
    LD (CUR_PTR),HL
    XOR A
    RET
sq_func_found:
    PUSH AF
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP '('
    JR Z,sq_func_paren
    POP AF
    JR sq_func_none
sq_func_paren:
    CALL ADV_PTR
    POP AF
    CALL sq_func_value
    POP BC
    LD A,1
    RET
sq_eof_word: DB "EOF"
sq_loc_word: DB "LOC"
sq_lof_word: DB "LOF"
SQ_EOF:
    XOR A
    JR sq_func_value
SQ_LOC:
    LD A,1
    JR sq_func_value
SQ_LOF:
    LD A,2
sq_func_value:
    PUSH AF
    LD HL,(MM_SQ_CURRENT)
    PUSH HL
    CALL sq_number
    CALL sq_bad
    JR NZ,sq_func_bad
    LD HL,(MM_SQ_CURRENT)
    LD A,H
    OR L
    JR NZ,sq_func_open
    LD A,60                 ; 第14.8節の未開放番号1での観測を維持
    CALL SQ_ERROR
    JR sq_func_bad
sq_func_open:
    CALL sq_current
    LD A,')'
    CALL EXPECT_CHAR
    CALL sq_bad
    JR NZ,sq_func_bad
    POP DE
    POP AF
    OR A
    JR Z,sq_func_eof
    DEC A
    JR Z,sq_func_loc
    LD L,(IY+20)
    LD H,(IY+21)
    JR sq_func_set
sq_func_loc:
    LD L,(IY+22)
    LD H,(IY+23)
    JR sq_func_set
sq_func_eof:
    LD L,(IY+24)
    LD H,L
sq_func_set:
    LD (MM_SQ_CURRENT),DE
    JP VAL_SET_INT
sq_func_bad:
    POP DE
    POP AF
    LD (MM_SQ_CURRENT),DE
    RET
