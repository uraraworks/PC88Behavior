; docs/spec/l4-basic.md 第17節。新規関数と255文字変数の本体、バンク3。
; C600-C601: 長文字列16スロットの使用ビット、8000-8FFF: 各256B。
; 31文字までは既存レコード内、32文字以上のみ別領域。満杯はOut of memory。
; SAVE捕捉9000-BFFF、MBF/式評価C000-C5FFとは重ならない。
S9_TMP_LEN EQU MM_RUN_STR_TMP_LEN
S9_TMP EQU MM_RUN_STR_TMP_BUF
S9_ARG EQU MM_RUN_STR_ARG1_BUF
S9_CUR_TYPE EQU MM_CUR_TYPE
S9_CUR_DATA EQU MM_CUR_DATA
S9_REC EQU MM_S9_REC
S9_START EQU MM_S9_START
S9_TARGET_LEN EQU MM_S9_TARGET_LEN
S9_NEEDLE_LEN EQU MM_S9_NEEDLE_LEN
S9_POS EQU MM_S9_POS
S9_BASE EQU MM_S9_BASE
S9_DIGITS EQU MM_S9_DIGITS
S9_DIGBUF EQU MM_S9_DIGBUF
S9_RESUME_REC EQU MM_S9_RESUME_REC
S9_RESUME_PTR EQU MM_S9_RESUME_PTR
S9_RESUME_END EQU MM_S9_RESUME_END
RUN_ERROR_ACTIVE EQU MM_RUN_ERROR_ACTIVE

    ORG 0x7300
; 第1引数は評価して無視。省略した上限/スタック量は現在値を保持する。
; 候補を別に持ち、構文/範囲/本文との衝突を確認してから初期化する。
S9B_CLEAR:
    LD HL,(MM_USER_LIMIT)
    LD (MM_CLEAR_LIMIT),HL
    LD HL,(MM_STACK_SIZE)
    LD (MM_CLEAR_STACK),HL
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    OR A
    JP Z,s9b_clear_apply
    CP ':'
    JP Z,s9b_clear_apply
    CP ','
    JR Z,s9b_clear_second
    CALL S9B_CLEAR_EXPR
    CALL S9_BAD
    RET NZ
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP ','
    JP NZ,s9b_clear_apply
s9b_clear_second:
    CALL B3_ADV_PTR
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP ','
    JR Z,s9b_clear_third
    CALL S9B_CLEAR_EXPR
    CALL S9_BAD
    RET NZ
    CALL S9B_ADDRESS_CUR       ; 上限aもPEEK/POKEと同じ番地変換
    CALL S9_BAD
    RET NZ
    LD HL,MM_USER_START
    OR A
    SBC HL,DE
    JR Z,s9b_clear_min_ok
    JP NC,S9_ILLEGAL
s9b_clear_min_ok:
    LD HL,MM_USER_LIMIT_MAX
    OR A
    SBC HL,DE
    JP C,S9_ILLEGAL
    LD (MM_CLEAR_LIMIT),DE
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP ','
    JR NZ,s9b_clear_apply
s9b_clear_third:
    CALL B3_ADV_PTR
    CALL S9B_CLEAR_EXPR
    CALL S9_BAD
    RET NZ
    CALL S9B_ADDRESS_CUR
    CALL S9_BAD
    RET NZ
    LD (MM_CLEAR_STACK),DE
s9b_clear_apply:
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    OR A
    JR Z,s9b_clear_validate
    CP ':'
    JR Z,s9b_clear_validate
    LD A,2
    JP S9_ERROR
s9b_clear_validate:
    LD HL,(MM_CLEAR_STACK)
    LD DE,MM_STACK_RESERVED+7
    OR A
    SBC HL,DE
    JR C,s9b_clear_oom
    LD HL,(MM_CLEAR_LIMIT)
    INC HL
    LD DE,(MM_CLEAR_STACK)
    OR A
    SBC HL,DE
    JR C,s9b_clear_oom
    LD DE,(MM_HEAP_START)       ; 本文＋番兵。既存記号はCLEARで消す。
    OR A
    SBC HL,DE
    JR C,s9b_clear_oom
    LD HL,(MM_CLEAR_LIMIT)
    LD (MM_USER_LIMIT),HL
    LD HL,(MM_CLEAR_STACK)
    LD (MM_STACK_SIZE),HL
    CALL S9B_CLEAR_STATE
    CALL S9D_LAYOUT
    JP S9_OK
s9b_clear_oom:
    LD A,7
    JP S9_ERROR
S9B_CLEAR_EXPR:
    CALL S9_IS_STRING
    OR A
    JP NZ,S9_TYPE
    JP S9B_EXPR

S9B_EXPR_ADDR EQU 0x1787
S9B_EXPR:
    LD IX,S9B_EXPR_ADDR
    JP B3_MAIN_CALL_ADDR
S9B_CLEAR_ADDR EQU 0x1787
S9B_CLEAR_STATE:
    LD IX,S9B_CLEAR_ADDR
    JP B3_MAIN_CALL_ADDR



    ORG 0x7400
    JP S9_CHR
    ORG 0x7410
    JP S9_SPACE
    ORG 0x7420
    JP S9_STRING
    ORG 0x7430
    JP S9_HEX
    ORG 0x7440
    JP S9_OCT
    ORG 0x7450
    JP S9_INSTR
    ORG 0x7460
    JP S9_READ_STRING
    ORG 0x7470
    JP S9_WRITE_STRING
    ORG 0x7480
    JP S9_RESUME
    ORG 0x7490
    JP S9_SAVE_ERROR
    ORG 0x74A0
    JP S9_ERROR_STMT

S9_OK:
    XOR A
    LD (ERROR_FLAG),A
    RET
S9_OVERFLOW:
    LD A,6
    JR S9_ERROR
S9_ILLEGAL:
    LD A,5
    JR S9_ERROR
S9_TYPE:
    LD A,13
S9_ERROR:
    LD (ERROR_KIND),A
    LD A,1
    LD (ERROR_FLAG),A
    RET
S9_BAD:
    LD A,(ERROR_FLAG)
    OR A
    RET
S9_CLOSE:
    LD A,')'
    JP S9_EXPECT
S9_COMMA:
    LD A,','
    JP S9_EXPECT
; 数値引数の型検査は既存LOGIC_OR_EXPR、整数化はCINT相当。
S9_BYTE_ARG:
    CALL S9_IS_STRING
    OR A
    JP NZ,S9_TYPE
    CALL S9_PARSE_INT
    CALL S9_BAD
    RET NZ
    LD A,D
    OR A
    JP NZ,S9_ILLEGAL
    RET
S9_CHR:
    CALL S9_BYTE_ARG
    CALL S9_BAD
    RET NZ
    PUSH DE
    CALL S9_CLOSE
    POP DE
    CALL S9_BAD
    RET NZ
    LD A,E
    LD (S9_TMP),A
    LD A,1
    LD (S9_TMP_LEN),A
    JP S9_OK
S9_SPACE:
    CALL S9_BYTE_ARG
    CALL S9_BAD
    RET NZ
    PUSH DE
    CALL S9_CLOSE
    POP DE
    CALL S9_BAD
    RET NZ
    LD B,E
    LD A,32
    JP S9_REPEAT
S9_STRING:
    CALL S9_BYTE_ARG
    CALL S9_BAD
    RET NZ
    PUSH DE                  ; 第2引数の入れ子評価から長さを守る
    CALL S9_COMMA
    CALL S9_BAD
    JR NZ,s9_string_fail
    CALL S9_IS_STRING
    OR A
    JR Z,s9_string_number
    CALL S9_STRING_EXPR
    CALL S9_BAD
    JR NZ,s9_string_fail
    LD A,(S9_TMP_LEN)
    OR A
    JR Z,s9_string_empty
    LD A,(S9_TMP)
    JR s9_string_char
s9_string_number:
    CALL S9_BYTE_ARG
    CALL S9_BAD
    JR NZ,s9_string_fail
    LD A,E
s9_string_char:
    PUSH AF
    CALL S9_CLOSE
    POP AF
    POP DE
    LD B,E
    PUSH AF
    CALL S9_BAD
    POP DE                   ; D=繰返し文字
    RET NZ
    LD A,D
S9_REPEAT:
    LD HL,S9_TMP
    LD C,A
    LD A,B
    LD (S9_TMP_LEN),A
    OR A
    JP Z,S9_OK
s9_repeat_loop:
    LD (HL),C
    INC HL
    DJNZ s9_repeat_loop
    JP S9_OK
s9_string_empty:
    CALL S9_ILLEGAL
s9_string_fail:
    POP DE
    RET

; 文字列/数値の選択。型の混在した式の検査順序は未測定。
S9_IS_STRING:
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    CP '"'
    JR Z,s9_is_string_yes
    CALL S9_IDENT_PEEK
    CP 3
    JR Z,s9_is_string_yes
    XOR A
    RET
s9_is_string_yes:
    LD A,1
    RET

S9_HEX:
    LD A,16
    JR s9_radix
S9_OCT:
    LD A,8
s9_radix:
    PUSH AF
    CALL S9_IS_STRING
    OR A
    JR Z,s9_radix_number
    CALL S9_TYPE
    JP s9_radix_fail
s9_radix_number:
    CALL S9_NUM_ARG
    CALL S9_BAD
    JP NZ,s9_radix_fail
    ; 拡張正範囲は単精度化後32768以上65536未満を判別し、先に65536を引く。
    LD A,(S9_CUR_TYPE)
    OR A
    JR Z,s9_radix_round
    CALL S9_LOAD_OPA
    LD A,(MM_MBF_OPA+3)            ; MBF exponent、32768以上は144以上
    CP 144
    JR NZ,s9_radix_round
    LD A,(MM_MBF_OPA+2)
    BIT 7,A
    JR NZ,s9_radix_round
    ; 指数144は[32768,65536)。MBF_OPB=65536、既存単精度減算。
    XOR A
    LD (MM_MBF_OPB),A
    LD (MM_MBF_OPB+1),A
    LD (MM_MBF_OPB+2),A
    LD A,145
    LD (MM_MBF_OPB+3),A
    CALL S9_MBF_SUB
    CALL S9_SET_SINGLE
s9_radix_round:
    CALL S9_TO_INT
    OR A
    JP Z,s9_radix_overflow
    EX DE,HL
    POP AF
    LD (S9_BASE),A
    XOR A
    LD (S9_DIGITS),A
s9_radix_divide:
    LD A,(S9_BASE)
    LD E,A
    LD D,0
    LD BC,0
s9_radix_sub:
    OR A
    SBC HL,DE
    JR C,s9_radix_rem
    INC BC
    JR s9_radix_sub
s9_radix_rem:
    ADD HL,DE
    LD A,L
    ADD A,'0'
    CP '9'+1
    JR C,s9_radix_digit
    ADD A,'A'-'0'-10
s9_radix_digit:
    LD HL,S9_DIGITS
    LD E,(HL)
    INC (HL)
    LD D,0
    LD HL,S9_DIGBUF
    ADD HL,DE
    LD (HL),A
    LD H,B
    LD L,C
    LD A,H
    OR L
    JR NZ,s9_radix_divide
    LD A,(S9_DIGITS)
    LD (S9_TMP_LEN),A
    LD B,A
    LD E,A
    LD D,0
    LD HL,S9_DIGBUF
    ADD HL,DE
    LD DE,S9_TMP
s9_radix_emit:
    DEC HL
    LD A,(HL)
    LD (DE),A
    INC DE
    DJNZ s9_radix_emit
    JP S9_OK
s9_radix_overflow:
    CALL S9_OVERFLOW
s9_radix_fail:
    POP AF
    RET

S9_REQUIRE_STRING:
    CALL S9_IS_STRING
    OR A
    JP Z,S9_TYPE
    JP S9_STRING_EXPR

S9_INSTR:
    CALL S9_IS_STRING
    OR A
    JR NZ,s9_instr_default
    CALL S9_BYTE_ARG
    CALL S9_BAD
    RET NZ
    LD A,E
    OR A
    JP Z,S9_ILLEGAL
    PUSH DE
    CALL S9_COMMA
    CALL S9_BAD
    JP NZ,s9_instr_fail
    JR s9_instr_target
s9_instr_default:
    LD DE,1
    PUSH DE
s9_instr_target:
    CALL S9_REQUIRE_STRING
    CALL S9_BAD
    JP NZ,s9_instr_fail
    LD A,(S9_TMP_LEN)
    ; 元文字列をCPUスタックへ退避。検索語内の入れ子関数から独立。
    LD C,A
    LD B,0
    LD HL,S9_TMP
    ADD HL,BC
    LD B,C
    LD C,0
    LD A,B
    OR A
    JR Z,s9_instr_saved
s9_instr_push:
    DEC HL
    LD A,(HL)
    PUSH AF
    INC C
    DJNZ s9_instr_push
s9_instr_saved:
    PUSH BC                  ; C=対象長
    CALL S9_COMMA
    CALL S9_BAD
    JR NZ,s9_instr_pop
    CALL S9_REQUIRE_STRING
    CALL S9_BAD
    JR NZ,s9_instr_pop
    CALL S9_CLOSE
s9_instr_pop:
    POP BC
    LD A,C
    LD (S9_TARGET_LEN),A
    LD B,C
    LD HL,S9_ARG
    OR A
    JR Z,s9_instr_restored
s9_instr_restore:
    POP DE                   ; D=文字
    LD (HL),D
    INC HL
    DJNZ s9_instr_restore
s9_instr_restored:
    POP DE                   ; E=開始
    CALL S9_BAD
    RET NZ
    LD A,E
    LD (S9_START),A
    LD (S9_POS),A
    LD B,A
    LD A,(S9_TARGET_LEN)
    CP B
    JR C,s9_instr_none
    LD A,(S9_TMP_LEN)
    LD (S9_NEEDLE_LEN),A
    OR A
    JR Z,s9_instr_found
s9_instr_search:
    LD A,(S9_POS)
    LD B,A
    LD A,(S9_TARGET_LEN)
    SUB B
    INC A
    LD B,A
    LD A,(S9_NEEDLE_LEN)
    CP B
    JR C,s9_instr_compare
    JR NZ,s9_instr_none
s9_instr_compare:
    LD B,A
    LD A,(S9_POS)
    DEC A
    LD E,A
    LD D,0
    LD HL,S9_ARG
    ADD HL,DE
    LD DE,S9_TMP
s9_instr_chars:
    LD A,(DE)
    CP (HL)
    JR NZ,s9_instr_advance
    INC HL
    INC DE
    DJNZ s9_instr_chars
s9_instr_found:
    LD A,(S9_POS)
    LD L,A
    LD H,0
    JP S9_SET_INT
s9_instr_advance:
    LD HL,S9_POS
    INC (HL)
    JR NZ,s9_instr_search
s9_instr_none:
    LD HL,0
    JP S9_SET_INT
s9_instr_fail:
    POP DE
    RET

; 変数レコードのkind=2は長文字列。value[0]=長さ、value[1..2]=ページ番地。
; 長文字列スロットは割当てた変数に保持（短い値への再代入時に解放）。
S9_READ_STRING:
    CALL S9_VAR_GET
    OR A
    JP Z,S9_OOM
    PUSH HL
    LD DE,9
    ADD HL,DE
    LD C,(HL)
    INC HL
    LD A,(HL)
    LD (S9_TMP_LEN),A
    LD B,A
    INC HL
    LD A,C
    CP 2
    JR NZ,s9_read_copy
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
s9_read_copy:
    LD DE,S9_TMP
    CALL S9_COPY
    POP HL
    JP S9_OK
S9_WRITE_STRING:
    CALL S9_VAR_GET
    OR A
    JP Z,S9_OOM
    LD (S9_REC),HL
    LD DE,9
    ADD HL,DE
    LD A,(HL)
    CP 2
    JR NZ,s9_write_choose
    PUSH HL
    INC HL
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    LD A,(S9_TMP_LEN)
    CP 32
    JR C,s9_write_release
    POP HL
    INC HL
    LD (HL),A
    JR s9_write_copy
s9_write_release:
    CALL S9_SLOT_FREE
    POP HL
s9_write_choose:
    LD A,(S9_TMP_LEN)
    CP 32
    JR NC,s9_write_long
    LD (HL),1
    INC HL
    LD (HL),A
    INC HL
    EX DE,HL
    JR s9_write_copy
s9_write_long:
    PUSH HL
    CALL S9_SLOT_ALLOC
    POP HL
    OR A
    JP Z,S9_OOM
    LD (HL),2
    INC HL
    LD A,(S9_TMP_LEN)
    LD (HL),A
    INC HL
    LD (HL),E
    INC HL
    LD (HL),D
s9_write_copy:
    LD HL,S9_TMP
    LD A,(S9_TMP_LEN)
    LD B,A
    CALL S9_COPY
    LD HL,(S9_REC)
    JP S9_OK
S9_OOM:
    LD A,7
    JP S9_ERROR
S9_SLOT_ALLOC:
    JP B3_PAGE_ALLOC
S9_SLOT_FREE:
    JP B3_PAGE_FREE

; 捕捉直前の実行位置。RESUME NEXTは引用符内のコロンを飛び越して次文へ。
S9_SAVE_ERROR:
    LD HL,(MM_STMT_START)           ; 文頭は捕捉時だけ保存、ハンドラの文頭と分離
    LD (S9_RESUME_PTR),HL
    LD HL,(RUN_CUR_RECORD)
    LD (S9_RESUME_REC),HL
    LD HL,(LINE_END)
    LD (S9_RESUME_END),HL
    RET
S9_SKIP_QUOTED_STMT:
    XOR A
    LD (MM_S9_RESUME_SKIP),A
s9_skip_loop:
    CALL B3_AT_END
    RET Z
    CALL B3_PEEK_CHAR
    CP '"'
    JR NZ,s9_skip_colon
    LD A,(MM_S9_RESUME_SKIP)
    XOR 1
    LD (MM_S9_RESUME_SKIP),A
    JR s9_skip_next
s9_skip_colon:
    CP ':'
    JR NZ,s9_skip_next
    LD A,(MM_S9_RESUME_SKIP)
    OR A
    RET Z
s9_skip_next:
    CALL B3_ADV_PTR
    JR s9_skip_loop

S9_RESUME:
    LD A,(RUN_ERROR_ACTIVE)
    OR A
    JR Z,s9_resume_without
    CALL B3_SKIP_SPACES
    CALL S9_MATCH_NEXT
    OR A
    JR Z,s9_resume_line
    LD HL,(S9_RESUME_REC)
    CALL S9_ENTER_RECORD
    LD HL,(S9_RESUME_PTR)
    LD (CUR_PTR),HL
    LD HL,(S9_RESUME_END)
    LD (LINE_END),HL
    CALL S9_SKIP_QUOTED_STMT
    CALL B3_AT_END
    JR Z,s9_resume_advance
    CALL B3_ADV_PTR
    JR s9_resume_ok
s9_resume_advance:
    CALL S9_ADV_RECORD
    OR A
    JR NZ,s9_resume_ok
    LD A,2
    LD (RUN_CTRL),A
    JR s9_resume_clear
s9_resume_line:
    CALL S9_PARSE_LINE
    JR C,s9_resume_no_target
    CALL S9_FIND_LINE
    JR C,s9_resume_undefined
    CALL S9_ENTER_RECORD
s9_resume_ok:
    LD A,1
    LD (RUN_CTRL),A
s9_resume_clear:
    XOR A
    LD (RUN_ERROR_ACTIVE),A
    JP S9_OK
s9_resume_no_target:
    LD A,19
    JP S9_ERROR
s9_resume_without:
    LD A,20
    JP S9_ERROR
s9_resume_undefined:
    LD A,8
    JP S9_ERROR
S9_ERROR_STMT:
    CALL S9_PARSE_INT
    CALL S9_BAD
    RET NZ
    LD A,D
    OR A
    JP NZ,S9_ILLEGAL
    LD A,E
    OR A
    JP Z,S9_ILLEGAL
    JP S9_ERROR

S9_EXPECT_ADDR EQU 0x1787
S9_EXPECT:
    LD IX,S9_EXPECT_ADDR
    JP B3_MAIN_CALL_ADDR

S9_PARSE_INT_ADDR EQU 0x1787
S9_PARSE_INT:
    LD IX,S9_PARSE_INT_ADDR
    JP B3_MAIN_CALL_ADDR

S9_STRING_EXPR_ADDR EQU 0x1787
S9_STRING_EXPR:
    LD IX,S9_STRING_EXPR_ADDR
    JP B3_MAIN_CALL_ADDR

S9_IDENT_PEEK_ADDR EQU 0x1787
S9_IDENT_PEEK:
    LD IX,S9_IDENT_PEEK_ADDR
    JP B3_MAIN_CALL_ADDR

S9_NUM_ARG_ADDR EQU 0x1787
S9_NUM_ARG:
    LD IX,S9_NUM_ARG_ADDR
    JP B3_MAIN_CALL_ADDR

S9_LOAD_OPA_ADDR EQU 0x1787
S9_LOAD_OPA:
    LD IX,S9_LOAD_OPA_ADDR
    JP B3_MAIN_CALL_ADDR

S9_MBF_SUB_ADDR EQU 0x1787
S9_MBF_SUB:
    LD IX,S9_MBF_SUB_ADDR
    JP B3_MAIN_CALL_ADDR

S9_SET_SINGLE_ADDR EQU 0x1787
S9_SET_SINGLE:
    LD IX,S9_SET_SINGLE_ADDR
    JP B3_MAIN_CALL_ADDR

S9_TO_INT_ADDR EQU 0x1787
S9_TO_INT:
    LD IX,S9_TO_INT_ADDR
    JP B3_MAIN_CALL_ADDR

S9_SET_INT_ADDR EQU 0x1787
S9_SET_INT:
    LD IX,S9_SET_INT_ADDR
    JP B3_MAIN_CALL_ADDR

S9_VAR_GET_ADDR EQU 0x1787
S9_VAR_GET:
    LD IX,S9_VAR_GET_ADDR
    JP B3_MAIN_CALL_ADDR

S9_COPY_ADDR EQU 0x1787
S9_COPY:
    LD IX,S9_COPY_ADDR
    JP B3_MAIN_CALL_ADDR

S9_MATCH_NEXT_ADDR EQU 0x1787
S9_MATCH_NEXT:
    LD IX,S9_MATCH_NEXT_ADDR
    JP B3_MAIN_CALL_ADDR

S9_ENTER_RECORD_ADDR EQU 0x1787
S9_ENTER_RECORD:
    LD IX,S9_ENTER_RECORD_ADDR
    JP B3_MAIN_CALL_ADDR


S9_ADV_RECORD_ADDR EQU 0x1787
S9_ADV_RECORD:
    LD IX,S9_ADV_RECORD_ADDR
    JP B3_MAIN_CALL_ADDR

S9_PARSE_LINE_ADDR EQU 0x1787
S9_PARSE_LINE:
    LD IX,S9_PARSE_LINE_ADDR
    JP B3_MAIN_CALL_ADDR

S9_FIND_LINE_ADDR EQU 0x1787
S9_FIND_LINE:
    LD IX,S9_FIND_LINE_ADDR
    JP B3_MAIN_CALL_ADDR

; ---- 第21節 文字列の比較（l4-s9e）。mainのCOMPARE_EXPR先頭から呼ぶ ----
; 入口 0x7900。出力 A=0: 左辺が文字列式ではない(何もしていない・通常の数値比較へ)。
;   A=1: 処理した(結果は整数-1/0、または誤りはERROR_FLAG)。
; 左辺の複写 CB00(長さ)・CB01〜(最大255B)。他の用途と重ならない空き。
; 演算子の真偽は順序(bit0:左<右 bit1:等しい bit2:左>右)との論理積で決める。
; 比較は符号なしバイトで先頭から、先に尽きた側が小さい。結果の整数はそのまま
; AND/OR/NOT・算術へ渡る。文字列と数値の混在は誤り13(両順)。
S9E_L_LEN EQU MM_S9E_L_LEN
S9E_L_BUF EQU MM_S9E_L_BUF

    ORG 0x7900
    JP S9E_CMP
S9E_CMP:
    ; 左辺が文字列式か(先頭が'"'、または英字で始まる識別子の末尾が'$')を、
    ; CUR_PTRを読むだけで判定する。字句の試し読み(LEX_IDENT_PEEK)は
    ; IDENT_BUFとRUN_TMP16を壊し、数値の比較に副作用を残すので使わない。
    LD HL,(CUR_PTR)
    LD DE,(LINE_END)
s9e_sk:
    CALL s9e_more
    JR NC,s9e_no
    LD A,(HL)
    CP ' '
    JR NZ,s9e_c1
    INC HL
    JR s9e_sk
s9e_c1:
    CP '"'
    JR Z,s9e_is_str
    OR 20h
    CP 'a'
    JR C,s9e_no
    CP 'z'+1
    JR NC,s9e_no
s9e_id:
    INC HL
    CALL s9e_more
    JR NC,s9e_no
    LD A,(HL)
    CP '$'
    JR Z,s9e_is_str
    CP '0'
    JR C,s9e_no
    CP '9'+1
    JR C,s9e_id
    OR 20h
    CP 'a'
    JR C,s9e_no
    CP 'z'+1
    JR C,s9e_id
s9e_no:
    XOR A
    RET
s9e_more:                    ; 文字が残っていればCY=1
    PUSH HL
    OR A
    SBC HL,DE
    POP HL
    RET
s9e_is_str:
    CALL B3_SKIP_SPACES        ; 先頭の空白を読み進める
    CALL S9_STRING_EXPR
    CALL S9_BAD
    JR NZ,s9e_done
    LD A,(S9_TMP_LEN)
    LD (S9E_L_LEN),A
    LD C,A
    LD B,0
    OR A
    JR Z,s9e_lcopied
    LD HL,S9_TMP
    LD DE,S9E_L_BUF
    LDIR
s9e_lcopied:
    CALL B3_SKIP_SPACES
    CALL B3_PEEK_CHAR
    LD D,2                   ; '=' : 等しい
    CP '='
    JR Z,s9e_op1
    LD D,1                   ; '<'
    CP '<'
    JR Z,s9e_lt
    LD D,4                   ; '>'
    CP '>'
    JR Z,s9e_gt
s9e_type:
    CALL S9_TYPE
s9e_done:
    LD A,1
    RET
s9e_lt:
    CALL B3_ADV_PTR
    CALL B3_PEEK_CHAR
    CP '>'
    LD D,5                   ; '<>' : 左<右 または 左>右
    JR Z,s9e_op1
    CP '='
    LD D,3                   ; '<=' : 左<右 または 等しい
    JR Z,s9e_op1
    LD D,1
    JR s9e_rhs
s9e_gt:
    CALL B3_ADV_PTR
    CALL B3_PEEK_CHAR
    CP '='
    LD D,6                   ; '>=' : 等しい または 左>右
    JR Z,s9e_op1
    LD D,4
    JR s9e_rhs
s9e_op1:
    CALL B3_ADV_PTR
s9e_rhs:
    PUSH DE                  ; D=許す順序。右辺の評価(入れ子の比較)から守る
    CALL S9_IS_STRING
    OR A
    JR Z,s9e_rhs_num
    CALL S9_STRING_EXPR
    CALL S9_BAD
    JR NZ,s9e_rhs_fail
    LD A,(S9E_L_LEN)
    LD B,A
    LD A,(S9_TMP_LEN)
    LD C,A
    LD HL,S9E_L_BUF
    LD DE,S9_TMP
s9e_loop:
    LD A,B
    OR A
    JR Z,s9e_lend
    LD A,C
    OR A
    JR Z,s9e_ord_gt              ; 右が尽きた: 左>右
    LD A,(DE)
    CP (HL)                  ; 右 - 左
    JR C,s9e_ord_gt              ; 右の方が小さい
    JR NZ,s9e_ord_lt             ; 右の方が大きい
    INC HL
    INC DE
    DEC B
    DEC C
    JR s9e_loop
s9e_lend:
    LD A,C
    OR A
    LD A,2                   ; 両方尽きた: 等しい
    JR Z,s9e_fin
s9e_ord_lt:
    LD A,1                   ; 左<右
    JR s9e_fin
s9e_ord_gt:
    LD A,4                   ; 左>右
s9e_fin:
    POP DE
    AND D
    LD HL,0
    JR Z,s9e_set
    DEC HL                   ; 真は-1
s9e_set:
    CALL S9_SET_INT
    CALL S9_OK
    LD A,1
    RET
s9e_rhs_num:
    POP DE
    JP s9e_type
s9e_rhs_fail:
    POP DE
    JP s9e_done
