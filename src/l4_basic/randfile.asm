; l4-basic第25節から独立実装。番号・枠・媒体処理はseqfileと共有。
; FIELD / LSET・RSET / MK*$本体はcapacity断片へ配置する。
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

; 既存の文/代入として受理できなかった場合だけ追加語を照合する。
; 通常の文の表・照合経路には入れない。候補は先頭文字で除外する。
RF_TRY_ASSIGN:
    ; IFのTHEN/ELSE内でも、今消費した識別子の先頭へ戻す。
    ; 代入判定で読み飛ばした空白を戻し、実際の識別子長を引く。
    LD HL,(CUR_PTR)
rf_stmt_rewind:
    DEC HL
    LD A,(HL)
    CP ' '
    JR Z,rf_stmt_rewind
    INC HL
    LD A,(MM_IDENT_LEN)
    LD E,A
    LD D,0
    OR A
    SBC HL,DE
    LD (CUR_PTR),HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CALL FOLD_UPPER
    LD E,A
    LD HL,rf_stmt_table
rf_stmt_loop:
    LD A,(HL)
    OR A
    RET Z
    LD B,A
    INC HL
    LD A,(HL)
    CP E
    JR NZ,rf_stmt_skip
    PUSH HL
    PUSH BC
    PUSH DE
    LD A,B
    CALL sq_keyword
    POP DE
    POP BC
    POP HL
    OR A
    JR NZ,rf_stmt_found
rf_stmt_skip:
    PUSH DE
    LD E,B
    LD D,0
    ADD HL,DE
    POP DE
    INC HL
    INC HL
    JR rf_stmt_loop
rf_stmt_found:
    LD E,B
    LD D,0
    ADD HL,DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    ; RUN_MATCH_STMT_KEYWORDの返り先を外し、文の実行元へ直接戻す。
    ; この入口はRUN_EXEC_ONE_STMTから呼ぶ照合の失敗先だけに接続する。
    POP BC
    EX DE,HL
    JP (HL)
rf_stmt_table:
    DB 5,"FIELD"
    DW RF_FIELD
    DB 4,"LSET"
    DW RF_LSET
    DB 4,"RSET"
    DW RF_RSET
    DB 0

; 既存予約語表で一致したRF関数だけがここへ来る。CUR_PTRは'('。
RF_FUNC:
    BIT 4,A
    JR NZ,rf_func_convert
    AND 15
    CALL rf_make
    LD A,1
    RET
rf_func_convert:
    AND 15
    CALL rf_convert
    LD A,1
    RET
rf_end:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    RET Z
    CP ':'
    RET Z
    JP sq_syntax
RF_OPEN_READY:
    LD A,(MM_RF_NEW)
    OR A
    RET Z
    LD (IY+20),0
    LD (IY+21),0
    CALL sq_fat
    LD A,(IY+12)
    CALL sq_fat_at
    LD (HL),0xC0
    LD A,3
    JP sq_disk
; 未開放番号では構文だけ受理して変数を変更しない（25.9自作判断）。
RF_FIELD:
    PUSH AF
    LD A,1
    LD IX,0x6003
    JP CAPACITY_BANK_CALL
RF_LSET:
    XOR A
    JR rf_set
RF_RSET:
    LD A,1
rf_set:
    PUSH AF
    LD A,3
    LD IX,0x602A
    JP CAPACITY_BANK_CALL
rf_transfer:
    LD (MM_RF_PUT),A
    CALL sq_number
    CALL sq_bad
    RET NZ
    LD A,D                    ; sq_numberはDE=枠を返す
    OR E
    JR NZ,rf_opened
    LD A,60                   ; 未開放の番号（14.8節・25.1節の連鎖誤り）
    JP SQ_ERROR
rf_opened:
    PUSH DE
    POP IY
    LD L,(IY+22)
    LD H,(IY+23)
    INC HL
    LD (MM_RF_TARGET),HL
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    CP ','
    JR NZ,rf_record_ready
    CALL ADV_PTR
    CALL PARSE_INT_ARG
    CALL sq_bad
    RET NZ
    BIT 7,D
    JP NZ,sq_illegal
    LD (MM_RF_TARGET),DE
rf_record_ready:
    CALL rf_end
    CALL sq_bad
    RET NZ
    LD HL,(MM_RF_TARGET)
    LD A,H
    OR L
    JR Z,rf_record_zero
    LD A,(MM_RF_PUT)
    OR A
    JR NZ,rf_record_seek
    EX DE,HL
    LD L,(IY+20)
    LD H,(IY+21)
    OR A
    SBC HL,DE                 ; LOF-番号
    JR NC,rf_record_seek
rf_past_end:
    LD A,55
    JP SQ_ERROR
rf_record_zero:
    LD A,(MM_RF_PUT)
    OR A
    JR Z,rf_past_end
    LD A,68
    JP SQ_ERROR
rf_record_seek:
    CALL sq_current
    LD A,(IY+12)
    LD (IY+13),A
    LD (IY+14),0
    LD HL,(MM_RF_TARGET)
    DEC HL
    LD (MM_RF_INDEX),HL
rf_seek_loop:
    LD HL,(MM_RF_INDEX)
    LD A,H
    OR L
    JR Z,rf_record_io
    DEC HL
    LD (MM_RF_INDEX),HL
    CALL sq_advance
    CALL sq_bad
    RET NZ
    JR rf_seek_loop
rf_record_io:
    CALL sq_handle_name
    LD A,(MM_RF_PUT)
    OR A
    JR NZ,rf_record_write
    CALL sq_address
    LD A,1
    CALL sq_disk
    CALL sq_bad
    RET NZ
    CALL sq_buffer
    EX DE,HL
    LD HL,MM_MAIN_SUB_SECTOR_BUF
    LD BC,256
    LDIR
    JR rf_record_done
rf_record_write:
    LD A,7
    CALL sq_disk
    CALL sq_bad
    RET NZ
    LD (IY+18),1
    CALL sq_flush
    CALL sq_bad
    RET NZ
    LD DE,(MM_RF_TARGET)
    LD L,(IY+20)
    LD H,(IY+21)
    OR A
    SBC HL,DE                 ; LOF-番号
    JR NC,rf_record_done
    LD (IY+20),E
    LD (IY+21),D
    CALL sq_fat
    LD A,(IY+13)
    CALL sq_fat_at
    LD A,(IY+14)
    ADD A,0xC1
    LD (HL),A
    LD A,3
    CALL sq_disk
    CALL sq_bad
    RET NZ
rf_record_done:
    LD HL,(MM_RF_TARGET)
    LD (IY+22),L
    LD (IY+23),H
    RET
; MBF変換は既存経路を共有。長いCV入力は先頭規定長を採る自作判断。
rf_make:
    PUSH AF
    LD A,3
    LD IX,0x609E
    JP CAPACITY_BANK_CALL
rf_make_bad:
    POP AF
    RET
rf_convert:
    PUSH AF
    LD A,'('
    CALL EXPECT_CHAR
    CALL sq_bad
    JR NZ,rf_make_bad
    CALL STRING_EXPR
    CALL sq_bad
    JR NZ,rf_make_bad
    LD A,')'
    CALL EXPECT_CHAR
    CALL sq_bad
    JR NZ,rf_make_bad
    POP BC                    ; B=規定長
    LD A,(RUN_STR_TMP_LEN)
    CP B
    JP C,sq_illegal
    LD A,B
    CP 2
    LD HL,(RUN_STR_TMP_BUF)
    JP Z,VAL_SET_INT
    LD C,A
    LD B,0
    LD HL,RUN_STR_TMP_BUF
    LD DE,CUR_DATA
    LDIR                      ; Aは保たれる
    LD C,A
    LD B,A
    DEC DE
    LD A,(DE)
    OR A
    JR NZ,rf_convert_nz
    ; 指数0は数値0。仮数の印を捨てて全バイト0に正規化する。
rf_convert_zero:
    LD (DE),A
    DEC DE
    DJNZ rf_convert_zero
rf_convert_nz:
    LD A,C
    CP 4
    LD A,1
    JR Z,rf_convert_type
    INC A
rf_convert_type:
    LD (CUR_TYPE),A
    RET
RF_END:

; 図形GET/PUTの既存の'('不一致からだけ呼ぶ。
RF_TRY_TRANSFER:
    CP '#'
    JR Z,rf_transfer_file
    CP '0'
    JP C,sq_syntax
    CP '9'+1
    JP NC,sq_syntax
rf_transfer_file:
    LD A,(RUN_STMT_KIND)
    SUB 51
    JP rf_transfer
