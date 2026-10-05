; docs/spec/l4-program.md 第4.18節だけから独立実装。
; 本体はバンク1。mainの呼び先はEXT_BANK_MAIN_CALLで窓を復元して呼ぶ。
; 未測定・自作判断: WHILEはFOR共用19B枠。先頭の変数ポインタ0が識別印。
; +2/+4/+6=WEND直後のrecord/ptr/end、+12/+14/+16=WHILE文頭の位置。
; NEXT/WENDは目的の枠より内側を取り除く。GOSUBは既存の下向き7B枠。
; 未測定・自作判断: 整数化の境界は既存CINTと共有。ON割り込み系は未対応。
; 捕捉ERR 2のEND後の直接入力とLISTは既存処理を維持する。
; 深さは共用域の容量まで。編集/NEW/CLEAR/RUNは既存RUN_FOR_SP初期化を共有。
    ORG 0x7310
    JP ow_on
    ORG 0x7320
    JP ow_while
    ORG 0x7330
    JP ow_wend
    ORG 0x7340
    JP ow_find_for
    ORG 0x7350
    LD HL,(MM_RUN_FOR_FRAME_PTR)
    LD DE,12
    ADD HL,DE
    JP ow_restore_position

ow_on:
    CALL ow_skip
    CALL ow_error_word
    OR A
    JR Z,ow_on_expression
    ; ON ERROR GOTOの既存の捕捉/解除をそのまま維持する。
    CALL ow_skip
    CALL ow_goto_word
    OR A
    JP Z,ow_syntax
    CALL ow_skip
    CALL ow_linenum
    JP C,ow_syntax
    LD (MM_RUN_ERROR_HANDLER_LINE),HL
    JP ow_ok
ow_on_expression:
    CALL ow_expr
    CALL ow_bad
    RET NZ
    CALL ow_int
    OR A
    JP Z,ow_overflow
    LD A,D
    OR A
    JP NZ,ow_illegal
    LD A,E
    LD (MM_OW_ON_SELECT),A
    CALL ow_skip
    CALL ow_goto_word
    OR A
    JR NZ,ow_on_goto
    CALL ow_gosub_word
    OR A
    JP Z,ow_syntax
    LD A,1
    JR ow_on_mode
ow_on_goto:
    XOR A
ow_on_mode:
    LD (MM_OW_ON_GOSUB),A
    XOR A
    LD (MM_OW_ON_CHOSEN),A
ow_on_list:
    ; 未測定・自作判断: 未選択も数字としての構文だけは検査する。
    ; 存在検査は選択された行だけ。リスト長の独自上限は設けない。
    CALL ow_skip
    CALL ow_linenum
    JP C,ow_syntax
    LD A,(MM_OW_ON_SELECT)
    OR A
    JR Z,ow_on_next
    DEC A
    LD (MM_OW_ON_SELECT),A
    JR NZ,ow_on_next
    LD (MM_OW_ON_TARGET),HL
    LD A,1
    LD (MM_OW_ON_CHOSEN),A
ow_on_next:
    CALL ow_skip
    CALL ow_peek
    CP ','
    JR NZ,ow_on_list_end
    CALL ow_adv
    JR ow_on_list
ow_on_list_end:
    CP ':'
    JR Z,ow_on_dispatch
    OR A                       ; PEEK_CHARは行末で0
    JP NZ,ow_syntax
ow_on_dispatch:
    LD A,(MM_OW_ON_CHOSEN)
    OR A
    JP Z,ow_ok
    LD HL,(MM_OW_ON_TARGET)
    CALL ow_find_line
    JP C,ow_undefined
    PUSH HL
    LD A,(MM_OW_ON_GOSUB)
    OR A
    JR Z,ow_on_enter
    ; リスト全部を消費済み。RETURNはON文末のコロン/行末へ戻る。
    CALL ow_gosub_push
    CALL ow_bad
    JR Z,ow_on_enter
    POP HL
    RET
ow_on_enter:
    POP HL
    CALL ow_enter
    JP ow_jump

ow_while:
    LD HL,(MM_RUN_CUR_RECORD)
    LD (MM_OW_BEGIN_REC),HL
    LD HL,(MM_CUR_PTR)
    LD DE,5
    OR A
    SBC HL,DE
    LD (MM_OW_BEGIN_PTR),HL
    LD HL,(MM_LINE_END)
    LD (MM_OW_BEGIN_END),HL
    CALL ow_seek_wend            ; 必ず条件評価より先。実行位置は触らない。
    CALL ow_bad
    RET NZ
    CALL ow_remove_same
    CALL ow_expr
    CALL ow_bad
    RET NZ
    CALL ow_skip
    CALL ow_peek
    CP ':'
    JR Z,ow_while_test
    OR A
    JP NZ,ow_syntax
ow_while_test:
    CALL ow_nonzero
    OR A
    JR NZ,ow_while_push
    LD HL,MM_OW_END_REC
    CALL ow_restore_position
    JP ow_ok                   ; WEND直後の区切りを通常処理へ返す。
ow_while_push:
    CALL ow_for_room
    JP C,ow_memory
    PUSH HL
    XOR A
    LD (HL),A
    INC HL
    LD (HL),A
    INC HL
    EX DE,HL
    LD HL,MM_OW_END_REC
    LD BC,6
    LDIR
    POP HL
    LD DE,12
    ADD HL,DE
    EX DE,HL
    LD HL,MM_OW_BEGIN_REC
    LD BC,6
    LDIR
    LD HL,(MM_RUN_FOR_SP)
    INC HL
    LD (MM_RUN_FOR_SP),HL
    JP ow_ok

ow_wend:
    ; 未測定・自作判断: 対応WENDが一致する枠を探し、その内側も破棄。
    LD HL,(MM_RUN_FOR_SP)
    LD (MM_OW_INDEX),HL
ow_wend_loop:
    CALL ow_prev_slot
    JP Z,ow_without_while
    CALL ow_is_while
    JR NZ,ow_wend_loop
    INC HL
    INC HL
    LD DE,(MM_RUN_CUR_RECORD)
    CALL ow_pointer_equal
    JR NZ,ow_wend_loop
    LD DE,(MM_CUR_PTR)
    CALL ow_pointer_equal
    JR NZ,ow_wend_loop
    LD DE,6                     ; +6から+12へ
    ADD HL,DE
    CALL ow_restore_position
    LD HL,(MM_OW_INDEX)
    LD (MM_RUN_FOR_SP),HL        ; 条件へ戻る前に自分の状態も取り除く。
    JP ow_jump

ow_remove_same:
    LD HL,(MM_RUN_FOR_SP)
    LD (MM_OW_INDEX),HL
ow_remove_loop:
    CALL ow_prev_slot
    RET Z
    CALL ow_is_while
    JR NZ,ow_remove_loop
    LD DE,12
    ADD HL,DE
    LD DE,(MM_OW_BEGIN_REC)
    CALL ow_pointer_equal
    JR NZ,ow_remove_loop
    LD DE,(MM_OW_BEGIN_PTR)
    CALL ow_pointer_equal
    JR NZ,ow_remove_loop
    LD HL,(MM_OW_INDEX)
    LD (MM_RUN_FOR_SP),HL
    RET

; NEXTの探索。MODE=1はIDENT_BUFと同名、0は最上位のFOR。
; WHILE識別印を変数ポインタとして参照しない。
ow_find_for:
    LD HL,(MM_RUN_FOR_SP)
    LD (MM_OW_INDEX),HL
ow_find_for_loop:
    CALL ow_prev_slot
    RET Z
    CALL ow_is_while
    JR Z,ow_find_for_loop
    LD A,(MM_OW_FIND_MODE)
    OR A
    JR Z,ow_find_for_found
    PUSH HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
    LD DE,MM_IDENT_BUF
    LD B,8
ow_find_for_name:
    LD A,(DE)
    CP (HL)
    JR NZ,ow_find_for_mismatch
    INC DE
    INC HL
    DJNZ ow_find_for_name
    POP HL
ow_find_for_found:
    LD HL,(MM_OW_INDEX)
    INC HL
    LD (MM_RUN_FOR_SP),HL
    LD A,1
    RET
ow_find_for_mismatch:
    POP HL
    JR ow_find_for_loop

ow_prev_slot:
    LD HL,(MM_OW_INDEX)
    LD A,H
    OR L
    RET Z
    DEC HL
    LD (MM_OW_INDEX),HL
    CALL ow_for_slot
    LD A,1
    OR A
    RET
ow_is_while:
    LD A,(HL)
    INC HL
    OR (HL)
    DEC HL
    RET
ow_pointer_equal:             ; HLから2BをDEと比較しHLは2B進む
    LD A,(HL)
    INC HL
    CP E
    LD A,(HL)
    INC HL
    RET NZ
    CP D
    RET
ow_restore_position:          ; HLはrecord/ptr/endの6B組
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    LD (MM_RUN_CUR_RECORD),DE
    LD A,(DE)
    LD (MM_RUN_CUR_LINENO),A
    INC DE
    LD A,(DE)
    LD (MM_RUN_CUR_LINENO+1),A
    LD E,(HL)
    INC HL
    LD D,(HL)
    INC HL
    LD (MM_CUR_PTR),DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD (MM_LINE_END),DE
    RET

; 入れ子の対応探索。REM/'は行末、DATAは引用符を守って次のコロンまで。
; 未測定・自作判断: 'とDATAも除外。直接WHILEは現在の入力行だけを探索。
ow_seek_wend:
    LD HL,(MM_RUN_CUR_RECORD)
    LD (MM_OW_SCAN_REC),HL
    LD HL,1
    LD (MM_OW_NEST),HL
    LD HL,(MM_CUR_PTR)
    LD DE,(MM_LINE_END)
ow_scan:
    CALL ow_more
    JP NC,ow_scan_line
    LD A,(HL)
    CP '"'
    JR Z,ow_scan_string
    CP 027h
    JP Z,ow_scan_line
    CALL ow_ident
    JR NC,ow_scan_char
    LD IX,ow_rem_word
    LD B,3
    CALL ow_word
    JP Z,ow_scan_line
    LD IX,ow_data_word
    LD B,4
    CALL ow_word
    JR Z,ow_scan_data
    LD IX,ow_while_word
    LD B,5
    CALL ow_word
    JR Z,ow_scan_nested
    LD IX,ow_wend_word
    LD B,4
    CALL ow_word
    JR Z,ow_scan_wend
ow_scan_ident:
    INC HL
    CALL ow_more
    JP NC,ow_scan_line
    LD A,(HL)
    CALL ow_ident
    JR C,ow_scan_ident
    JP ow_scan
ow_scan_nested:
    PUSH HL
    LD HL,(MM_OW_NEST)
    INC HL
    LD (MM_OW_NEST),HL
    POP HL
    JP ow_scan
ow_scan_wend:
    PUSH HL
    LD HL,(MM_OW_NEST)
    DEC HL
    LD (MM_OW_NEST),HL
    LD A,H
    OR L
    POP HL
    JP NZ,ow_scan
    LD (MM_OW_END_PTR),HL
    LD (MM_OW_END_END),DE
    LD HL,(MM_OW_SCAN_REC)
    LD (MM_OW_END_REC),HL
    XOR A
    LD (MM_ERROR_FLAG),A
    RET
ow_scan_char:
    INC HL
    JP ow_scan
ow_scan_string:
    CALL ow_quote
    JP ow_scan
ow_scan_data:
    CALL ow_more
    JP NC,ow_scan_line
    LD A,(HL)
    CP ':'
    JR Z,ow_scan_char
    CP '"'
    JR NZ,ow_scan_data_char
    CALL ow_quote
    JR ow_scan_data
ow_scan_data_char:
    INC HL
    JR ow_scan_data
ow_scan_line:
    LD HL,(MM_OW_SCAN_REC)
    LD A,(HL)
    INC HL
    OR (HL)
    JP Z,ow_without_wend        ; 直接モードの仮レコードは行番号0
    INC HL
    LD C,(HL)
    LD B,0
    INC HL
    ADD HL,BC
    LD A,(HL)
    INC HL
    AND (HL)
    INC A
    JP Z,ow_without_wend        ; 行番号FFFFは番兵
    DEC HL
    LD (MM_OW_SCAN_REC),HL
    INC HL
    INC HL
    LD C,(HL)
    LD B,0
    INC HL
    PUSH HL
    ADD HL,BC
    EX DE,HL
    POP HL
    JP ow_scan

ow_more:                       ; HL<DEならCF=1
    PUSH HL
    OR A
    SBC HL,DE
    POP HL
    RET
ow_quote:
    INC HL
ow_quote_loop:
    CALL ow_more
    RET NC
    LD A,(HL)
    INC HL
    CP '"'
    JR NZ,ow_quote_loop
    RET
ow_ident:
    CP '_'
    JR Z,ow_ident_yes
    CP '$'
    JR Z,ow_ident_yes
    CP '%'
    JR Z,ow_ident_yes
    CP '#'
    JR Z,ow_ident_yes
    CP '!'
    JR Z,ow_ident_yes
    CP '0'
    JR C,ow_ident_no
    CP '9'+1
    JR C,ow_ident_yes
    OR 20h
    CP 'a'
    JR C,ow_ident_no
    CP 'z'+1
    JR C,ow_ident_yes
ow_ident_no:
    OR A
    RET
ow_ident_yes:
    SCF
    RET
ow_word:                       ; 探索専用、大小を区別しない語境界照合
    PUSH HL                    ; 不一致は位置不変、一致は語末HL/Z
ow_word_loop:
    CALL ow_more
    JR NC,ow_word_no
    LD A,(HL)
    OR 20h
    CP (IX+0)
    JR NZ,ow_word_no
    INC IX
    INC HL
    DJNZ ow_word_loop
    CALL ow_more
    JR NC,ow_word_yes
    LD A,(HL)
    CALL ow_ident
    JR C,ow_word_no
ow_word_yes:
    POP BC
    XOR A
    RET
ow_word_no:
    POP HL
    LD A,1
    OR A
    RET
ow_while_word: DB "while"
ow_wend_word: DB "wend"
ow_rem_word: DB "rem"
ow_data_word: DB "data"

ow_ok:
    XOR A
    LD (MM_ERROR_FLAG),A
    LD (MM_RUN_CTRL),A
    RET
ow_jump:
    CALL ow_ok
    LD A,1
    LD (MM_RUN_CTRL),A
    RET
ow_syntax:
    LD A,2
    JR ow_error
ow_illegal:
    LD A,5
    JR ow_error
ow_overflow:
    LD A,6
    JR ow_error
ow_memory:
    LD A,7
    JR ow_error
ow_undefined:
    LD A,8
    JR ow_error
ow_without_wend:
    LD A,29
    JR ow_error
ow_without_while:
    LD A,30
ow_error:
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
    RET
ow_bad:
    LD A,(MM_ERROR_FLAG)
    OR A
    RET

ow_skip:
    LD IX,OW_SKIP_ADDR
    JP OW_MAIN_CALL_ADDR
OW_SKIP_ADDR EQU 0x1787

ow_peek:
    LD IX,OW_PEEK_ADDR
    JP OW_MAIN_CALL_ADDR
OW_PEEK_ADDR EQU 0x1787

ow_adv:
    LD IX,OW_ADV_ADDR
    JP OW_MAIN_CALL_ADDR
OW_ADV_ADDR EQU 0x1787

ow_expr:
    LD IX,OW_EXPR_ADDR
    JP OW_MAIN_CALL_ADDR
OW_EXPR_ADDR EQU 0x1787

ow_int:
    LD IX,OW_INT_ADDR
    JP OW_MAIN_CALL_ADDR
OW_INT_ADDR EQU 0x1787

ow_nonzero:
    LD IX,OW_NONZERO_ADDR
    JP OW_MAIN_CALL_ADDR
OW_NONZERO_ADDR EQU 0x1787

ow_error_word:
    LD IX,OW_ERROR_WORD_ADDR
    JP OW_MAIN_CALL_ADDR
OW_ERROR_WORD_ADDR EQU 0x1787

ow_goto_word:
    LD IX,OW_GOTO_WORD_ADDR
    JP OW_MAIN_CALL_ADDR
OW_GOTO_WORD_ADDR EQU 0x1787

ow_gosub_word:
    LD IX,OW_GOSUB_WORD_ADDR
    JP OW_MAIN_CALL_ADDR
OW_GOSUB_WORD_ADDR EQU 0x1787

ow_linenum:
    LD IX,OW_LINENUM_ADDR
    JP OW_MAIN_CALL_ADDR
OW_LINENUM_ADDR EQU 0x1787

ow_find_line:
    LD IX,OW_FIND_LINE_ADDR
    JP OW_MAIN_CALL_ADDR
OW_FIND_LINE_ADDR EQU 0x1787

ow_enter:
    LD IX,OW_ENTER_ADDR
    JP OW_MAIN_CALL_ADDR
OW_ENTER_ADDR EQU 0x1787

ow_gosub_push:
    LD IX,OW_GOSUB_PUSH_ADDR
    JP OW_MAIN_CALL_ADDR
OW_GOSUB_PUSH_ADDR EQU 0x1787

ow_for_slot:
    LD IX,OW_FOR_SLOT_ADDR
    JP OW_MAIN_CALL_ADDR
OW_FOR_SLOT_ADDR EQU 0x1787

ow_for_room:
    LD IX,OW_FOR_ROOM_ADDR
    JP OW_MAIN_CALL_ADDR
OW_FOR_ROOM_ADDR EQU 0x1787
OW_MAIN_CALL_ADDR EQU 0x1787
OW_CODE_END:
