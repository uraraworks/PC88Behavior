; l4-basic第25節から独立実装。番号・枠・媒体処理はseqfileと共有。
; FIELD / LSET・RSET / MK*$本体はcapacity断片へ配置する。
SQ_TRY_STMT:
    CALL SKIP_SPACES
    ; 通常文では追加語の照合を避け、FORやキー入力の周期を保つ。
    CALL PEEK_CHAR
    AND 0DFh
    CP 'M'
    JR Z,sq_try_m
    CP 'C'
    JR Z,sq_try_c
    JR sq_try_open_real
sq_try_m:
    LD HL,sq_motor_word
    LD A,5
    CALL sq_keyword
    OR A
    JR Z,sq_try_merge_real
    LD HL,0x360C
    CALL N_COMPLEX_CALL
    LD A,1
    RET
sq_try_c:
    LD HL,mc_common_word
    LD A,6
    CALL sq_keyword
    OR A
    JR Z,sq_try_merge
    LD HL,0x3603
    CALL N_COMPLEX_CALL
    LD A,1
    RET
sq_try_merge:
    LD HL,mc_chain_word
    LD A,5
    CALL sq_keyword
    OR A
    JR Z,sq_try_open_real
    LD HL,0x3606
    CALL N_COMPLEX_CALL
    LD A,1
    RET
sq_try_merge_real:
    LD HL,mc_merge_word
    LD A,5
    CALL sq_keyword
    OR A
    JR Z,sq_try_open_real
    LD HL,0x3600
    CALL N_COMPLEX_CALL
    LD A,1
    RET
sq_try_open_real:
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
sq_motor_word: DB "MOTOR"
mc_merge_word: DB "MERGE"
mc_common_word: DB "COMMON"
mc_chain_word: DB "CHAIN"
mc_all_word: DB "ALL"
mc_delete_word: DB "DELETE"

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
; GET/PUTのファイル処理はN側の入口表へ渡す。
rf_transfer:
    LD HL,0x261E
    JP N_COMPLEX_CALL
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

; l4-program.md 第12節。値の検査後に30h bit3だけを変更する。
; OUT文の30h・31hの写しを実際の出力と同時に更新する。
RECORD_OUT:
    LD A,C
    CP 0x30
    LD A,E
    JR NZ,record_out_31
    LD (MM_SCR_P30),A
    JR record_out_write
record_out_31:
    LD A,C
    CP 0x31
    LD A,E
    JR NZ,record_out_write
    LD (MM_SCR_P31),A
record_out_write:
    OUT (C),A
    RET

; 種別0x80を含む非ASCII形式は本文を読まず誤り59にする。
mc_load_program_type:
    LD A,5
    RET

mc_save_program_type:
    LD A,(MM_BINARY_MODE)
    OR A
    RET NZ
    LD A,(MM_SAVE_PROGRAM_FORMAT)
    RET
