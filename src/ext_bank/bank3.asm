; READ/RESTORE/CONTのバンク3本体。mainの共有処理は汎用中継で呼ぶ。
    ORG 0x6000
EXT_BANK3_TEST_ENTRY:
    LD A,0xB3
    RET

IDENT_BUF EQU MM_IDENT_BUF
RUN_ASSIGN_NAME EQU MM_RUN_ASSIGN_NAME
RUN_DATA_STATE EQU MM_RUN_DATA_STATE
RUN_DATA_REC EQU MM_RUN_DATA_REC
RUN_CONT_REC EQU MM_RUN_CONT_REC
RUN_CONT_PTR EQU MM_RUN_CONT_PTR
RUN_CONT_END EQU MM_RUN_CONT_END
RUN_CUR_RECORD EQU MM_RUN_CUR_RECORD
RUN_CTRL EQU MM_RUN_CTRL
ERROR_FLAG EQU MM_ERROR_FLAG
ERROR_KIND EQU MM_ERROR_KIND
LINE_END EQU MM_LINE_END
CUR_PTR EQU MM_CUR_PTR

    ORG 0x6100
; READ_STMT — 第6.1節。カンマ区切りで複数変数へ同時READできる
;   (%・#の丸めは適用せずそのまま代入する、仕様書に無い判断)。
READ_STMT:
_read_one:
    CALL B3_SKIP_SPACES
    CALL B3_LEX_IDENT_CONSUME
    OR A
    JR Z,_read_syntax
    CP 3
    JR Z,_read_string_target
    LD HL,IDENT_BUF
    LD DE,RUN_ASSIGN_NAME
    LD BC,8
    LDIR
    XOR A
    CALL B3_DATA_READ_ONE
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,RUN_ASSIGN_NAME
    LD DE,IDENT_BUF
    LD BC,8
    LDIR
    CALL B3_VAR_WRITE_NUMERIC
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    JR _read_next
_read_string_target:
    LD HL,IDENT_BUF
    LD DE,RUN_ASSIGN_NAME
    LD BC,8
    LDIR
    LD A,1
    CALL B3_DATA_READ_ONE
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
    LD HL,RUN_ASSIGN_NAME
    LD DE,IDENT_BUF
    LD BC,8
    LDIR
    CALL B3_VAR_WRITE_STRING
    LD A,(ERROR_FLAG)
    OR A
    RET NZ
_read_next:
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP ','
    JR NZ,_read_done
    CALL B3_ADV_PTR
    JR _read_one
_read_done:
    XOR A
    LD (ERROR_FLAG),A
    RET
_read_syntax:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET


    ORG 0x6180
S9D_GOSUB_PUSH:
    LD HL,(MM_RUN_GOSUB_SP)
    INC HL
    LD (MM_STACK_INDEX),HL
    CALL S9D_GOSUB_SLOT
    PUSH HL
    LD HL,(MM_RUN_FOR_SP)
    LD (MM_STACK_INDEX),HL
    CALL S9D_FOR_SLOT
    EX DE,HL
    POP HL
    PUSH HL
    OR A
    SBC HL,DE
    POP HL
    JR C,_rgp_oom
    LD DE,(MM_RUN_CUR_RECORD)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD DE,(MM_CUR_PTR)
    LD (HL),E
    INC HL
    LD (HL),D
    INC HL
    LD DE,(MM_LINE_END)
    LD (HL),E
    INC HL
    LD (HL),D
    LD HL,(MM_RUN_GOSUB_SP)
    INC HL
    LD (MM_RUN_GOSUB_SP),HL
    XOR A
    LD (ERROR_FLAG),A
    RET
_rgp_oom:
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    RET


    ORG 0x6200
; RESTORE_STMT — 第6.2節。行番号指定(第8節28)は本段階では対応せず、
;   引数があれば構文の誤り扱い(仕様書に無い判断、安全側に倒す)。
RESTORE_STMT:
    CALL B3_SKIP_SPACES
    CALL B3_AT_END
    JR Z,_restore_ok
    CALL B3_PEEK_CHAR
    CP ':'
    JR Z,_restore_ok
    LD A,1
    LD (ERROR_FLAG),A
    LD A,2
    LD (ERROR_KIND),A
    RET
_restore_ok:
    XOR A
    LD (RUN_DATA_STATE),A
    LD HL,0
    LD (RUN_DATA_REC),HL
    XOR A
    LD (ERROR_FLAG),A
    RET


    ORG 0x6230
; ページはスタック域の直下から下向き。256B境界への丸めはしない。
B3_PAGE_ALLOC:
    LD DE,(MM_STACK_BOTTOM)
    DEC D
    LD HL,MM_STRING_FLAGS
    LD C,1
    LD B,MM_STRING_PAGE_COUNT
b3_page_loop:
    LD A,(HL)
    AND C
    JR Z,b3_page_candidate
b3_page_next:
    DEC D
    RLC C
    JR NC,b3_page_same_byte
    INC HL
b3_page_same_byte:
    DJNZ b3_page_loop
b3_page_full:
    XOR A
    RET
b3_page_candidate:
    PUSH HL
    LD HL,(MM_HEAP_END)
    OR A
    SBC HL,DE
    POP HL
    JR Z,b3_page_room
    JR NC,b3_page_full
b3_page_room:
    LD A,(HL)
    OR C
    LD (HL),A
    PUSH HL
    LD HL,(MM_FREE_TOP)
    OR A
    SBC HL,DE
    POP HL
    JR C,b3_page_alloc_done
    LD (MM_FREE_TOP),DE
b3_page_alloc_done:
    LD A,1
    RET
; DE=解放するページ。ページは動かさず、最下端だけ再走査する。
B3_PAGE_FREE:
    LD HL,(MM_STACK_BOTTOM)
    OR A
    SBC HL,DE
    LD A,H
    DEC A
    LD HL,MM_STRING_FLAGS
b3_page_free_byte:
    CP 8
    JR C,b3_page_free_mask
    SUB 8
    INC HL
    JR b3_page_free_byte
b3_page_free_mask:
    LD C,1
    OR A
    JR Z,b3_page_free_apply
    LD B,A
b3_page_free_rotate:
    RLC C
    DJNZ b3_page_free_rotate
b3_page_free_apply:
    LD A,C
    CPL
    AND (HL)
    LD (HL),A
    LD DE,(MM_STACK_BOTTOM)
    LD (MM_FREE_TOP),DE
    LD HL,MM_STRING_FLAGS
    LD C,1
    LD B,MM_STRING_PAGE_COUNT
b3_page_lowest:
    DEC D
    LD A,(HL)
    AND C
    JR Z,b3_page_lowest_next
    LD (MM_FREE_TOP),DE
b3_page_lowest_next:
    RLC C
    JR NC,b3_page_lowest_same
    INC HL
b3_page_lowest_same:
    DJNZ b3_page_lowest
    RET

    ORG 0x6300
; =======================================================================
; CONT(第4.11節) — 直接モードのコマンド(interp.asm DIRECT_LINEから
;   STMT_KIND=4で呼ばれる、RUNと同じ位置づけ)。STOP_STMTが保存した
;   RUN_CONT_*から再開し、RUN_EXECの通常の継続処理(_run_after_stmt、
;   ERROR_FLAG=0・RUN_CTRL=0で開始)へそのまま合流する。
; =======================================================================
CONT_STMT:
    LD HL,(RUN_CONT_REC)
    LD A,H
    OR L
    JR NZ,_cont_have
    LD A,1
    LD (ERROR_FLAG),A
    LD A,17
    LD (ERROR_KIND),A
    XOR A
    RET
_cont_have:
    LD (RUN_CUR_RECORD),HL
    LD HL,(RUN_CONT_PTR)
    LD (CUR_PTR),HL
    LD HL,(RUN_CONT_END)
    LD (LINE_END),HL
    LD HL,0
    LD (RUN_CONT_REC),HL
    XOR A
    LD (RUN_CTRL),A
    LD (ERROR_FLAG),A
    LD A,1
    RET

B3_MAIN_CALL_ADDR EQU 0x1787
B3_SKIP_SPACES_ADDR EQU 0x1787
B3_LEX_IDENT_CONSUME_ADDR EQU 0x1787
B3_DATA_READ_ONE_ADDR EQU 0x1787
B3_VAR_WRITE_NUMERIC_ADDR EQU 0x1787
B3_VAR_WRITE_STRING_ADDR EQU 0x1787
B3_PEEK_CHAR_ADDR EQU 0x1787
B3_ADV_PTR_ADDR EQU 0x1787
B3_AT_END_ADDR EQU 0x1787
B3_SKIP_SPACES:
    LD IX,B3_SKIP_SPACES_ADDR
    JP B3_MAIN_CALL_ADDR
B3_LEX_IDENT_CONSUME:
    LD IX,B3_LEX_IDENT_CONSUME_ADDR
    JP B3_MAIN_CALL_ADDR
B3_DATA_READ_ONE:
    LD IX,B3_DATA_READ_ONE_ADDR
    JP B3_MAIN_CALL_ADDR
B3_VAR_WRITE_NUMERIC:
    LD IX,B3_VAR_WRITE_NUMERIC_ADDR
    JP B3_MAIN_CALL_ADDR
B3_VAR_WRITE_STRING:
    LD IX,B3_VAR_WRITE_STRING_ADDR
    JP B3_MAIN_CALL_ADDR
B3_PEEK_CHAR:
    LD IX,B3_PEEK_CHAR_ADDR
    JP B3_MAIN_CALL_ADDR
B3_ADV_PTR:
    LD IX,B3_ADV_PTR_ADDR
    JP B3_MAIN_CALL_ADDR
B3_AT_END:
    LD IX,B3_AT_END_ADDR
    JP B3_MAIN_CALL_ADDR

; FREは数値/文字列の引数を評価し、同じ自作空きバイト数を返す。
S9D_FRE:
    CALL S9_IS_STRING
    OR A
    JR Z,s9d_fre_numeric
    CALL S9_STRING_EXPR
    JR s9d_fre_close
s9d_fre_numeric:
    CALL S9B_EXPR
s9d_fre_close:
    CALL S9_BAD
    RET NZ
    CALL S9_CLOSE
    CALL S9_BAD
    RET NZ
    LD HL,(MM_FREE_TOP)
    LD DE,(MM_HEAP_END)
    OR A
    SBC HL,DE
    JP S9_SET_INT

; 初期化後に位置を再計算。CPUスタック/固定域には触れない。
S9D_LAYOUT:
    LD HL,(MM_USER_LIMIT)
    INC HL
    LD (MM_RUN_GOSUB_STACK),HL
    LD DE,(MM_STACK_SIZE)
    OR A
    SBC HL,DE
    LD (MM_STACK_BOTTOM),HL
    LD (MM_FREE_TOP),HL
    LD DE,MM_STACK_RESERVED
    ADD HL,DE
    LD (MM_RUN_FOR_STACK),HL
    RET

S9D_FOR_SLOT:
    LD HL,(MM_STACK_INDEX)
    LD D,H
    LD E,L
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    PUSH HL
    ADD HL,HL
    POP DE
    ADD HL,DE
    LD DE,(MM_RUN_FOR_STACK)
    ADD HL,DE
    RET


S9D_GOSUB_SLOT:
    LD HL,(MM_STACK_INDEX)
    LD D,H
    LD E,L
    ADD HL,HL
    ADD HL,HL
    ADD HL,HL
    OR A
    SBC HL,DE
    EX DE,HL
    LD HL,(MM_RUN_GOSUB_STACK)
    OR A
    SBC HL,DE
    RET


; DE=FOR深さ。HL=次のフレーム、CF=1は共用域不足。
S9D_FOR_ROOM:
    LD HL,(MM_RUN_FOR_SP)
    LD (MM_STACK_INDEX),HL
    CALL S9D_FOR_SLOT
    PUSH HL
    LD DE,24
    ADD HL,DE
    PUSH HL
    LD HL,(MM_RUN_GOSUB_SP)
    LD (MM_STACK_INDEX),HL
    CALL S9D_GOSUB_SLOT
    POP DE
    OR A
    SBC HL,DE
    POP HL
    RET

; SAVE捕捉本体。EXT_BANK_CALL_CAPTURE経由でのみ入り、main呼び出しはしない。
B3_CAPTURE_IN EQU MM_B3_CAPTURE_IN
B3_CAPTURE_PTR EQU MM_S2_CAPTURE_PTR
B3_CAPTURE_LEN EQU MM_S2_CAPTURE_LEN
    ORG 0x6400
B3_CAPTURE_CHAR_ENTRY:
    LD A,(B3_CAPTURE_IN)
    JP B3_CAPTURE_CHAR
    ORG 0x6410
B3_CAPTURE_NEWLINE_ENTRY:
    LD A,0Dh
    CALL B3_CAPTURE_CHAR
    LD A,0Ah
    JP B3_CAPTURE_CHAR
B3_CAPTURE_CHAR:
    PUSH HL
    PUSH AF
    LD HL,(B3_CAPTURE_PTR)
    PUSH DE
    LD DE,(MM_CAPTURE_END)
    OR A
    SBC HL,DE
    ADD HL,DE
    POP DE
    JR C,_b3_capture_store
    LD A,1
    LD (ERROR_FLAG),A
    LD A,7
    LD (ERROR_KIND),A
    JR _b3_capture_done
_b3_capture_store:
    POP AF
    LD (HL),A
    INC HL
    LD (B3_CAPTURE_PTR),HL
    LD HL,(B3_CAPTURE_LEN)
    INC HL
    LD (B3_CAPTURE_LEN),HL
    POP HL
    RET
_b3_capture_done:
    POP AF
    POP HL
    RET

    ORG 0x64A0
B3_EDITOR_ERROR_ENTRY:
    JP LN_REPORT
