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
; ランダムと共用のバッファ零埋め。c3-9: SQR陰性対照のためRUN_EXECの前（この位置）に置く。
rf_clear_buffer:
    CALL sq_buffer
    LD (HL),0
    LD D,H
    LD E,L
    INC DE
    LD BC,255
    LDIR
    RET
; 旧3語の本体は予約前の共通部。RUN_EXECの配置を保つ。
    DS 13
sq_open_word: DB "OPEN"
sq_close_word: DB "CLOSE"
sq_write_word: DB "WRITE"
sq_for_word: DB "FOR"
sq_as_word: DB "AS"
sq_modes: DB "INPUT",0,"OUTPUT",0,"APPEND",0
; ファイル名は式文字列。既定drive=0、明示1:/2:を外す。
; N側の入口表（0x2600、3B刻み）へ渡す。N欠落時はエラー5。
sq_filename:
    LD HL,0x2600
    JP N_COMPLEX_CALL
sq_disk_name:
    LD HL,0x2603
    JP N_COMPLEX_CALL
sq_handle_name:
    LD HL,0x2606
    JP N_COMPLEX_CALL
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
    LD HL,0x2609
    JP N_COMPLEX_CALL
SQ_OPEN:
    LD HL,0x260C
    JP N_COMPLEX_CALL
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
    LD HL,0x260F
    JP N_COMPLEX_CALL
sq_flush:
    LD HL,0x2612
    JP N_COMPLEX_CALL
sq_advance:
    LD HL,0x2615
    JP N_COMPLEX_CALL
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
    LD HL,0x2618
    JP N_COMPLEX_CALL
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
    OR A
    JR Z,sq_close_free
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
SQ_INPUT:
    LD HL,0x261B
    JP N_COMPLEX_CALL
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
