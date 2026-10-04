; docs/spec/l4-basic.md 第17節。新規関数と255文字変数の本体、バンク3。
; C600-C601: 長文字列16スロットの使用ビット、8000-8FFF: 各256B。
; 31文字までは既存レコード内、32文字以上のみ別領域。満杯はOut of memory。
; SAVE捕捉9000-BFFF、MBF/式評価C000-C5FFとは重ならない。
S9_TMP_LEN EQU 0D031h
S9_TMP EQU 0C700h
S9_ARG EQU 0C800h
S9_CUR_TYPE EQU 0E8A2h
S9_CUR_DATA EQU 0E8A3h
S9_REC EQU 0CA00h
S9_START EQU 0CA02h
S9_TARGET_LEN EQU 0CA03h
S9_NEEDLE_LEN EQU 0CA04h
S9_POS EQU 0CA05h
S9_BASE EQU 0CA06h
S9_DIGITS EQU 0CA07h
S9_DIGBUF EQU 0CA08h
S9_RESUME_REC EQU 0D979h
S9_RESUME_PTR EQU 0D97Bh
S9_RESUME_END EQU 0D97Dh
RUN_ERROR_ACTIVE EQU 0D977h

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
    LD A,(0C003h)            ; MBF exponent、32768以上は144以上
    CP 144
    JR NZ,s9_radix_round
    LD A,(0C002h)
    BIT 7,A
    JR NZ,s9_radix_round
    ; 指数144は[32768,65536)。MBF_OPB=65536、既存単精度減算。
    XOR A
    LD (0C004h),A
    LD (0C005h),A
    LD (0C006h),A
    LD A,145
    LD (0C007h),A
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
    INC HL
    LD A,(HL)               ; 長文字列ページ上位
    SUB 080h
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
    LD DE,08000h
    LD HL,0C600h
    LD C,1
    LD B,16
s9_slot_loop:
    LD A,(HL)
    AND C
    JR Z,s9_slot_found
    INC D
    RLC C
    JR NC,s9_slot_next
    INC HL
s9_slot_next:
    DJNZ s9_slot_loop
    XOR A
    RET
s9_slot_found:
    LD A,(HL)
    OR C
    LD (HL),A
    LD A,1
    RET
S9_SLOT_FREE:
    LD HL,0C600h
    CP 8
    JR C,s9_slot_low
    SUB 8
    INC HL
s9_slot_low:
    LD C,1
    OR A
    JR Z,s9_slot_mask
    LD B,A
s9_slot_rotate:
    RLC C
    DJNZ s9_slot_rotate
s9_slot_mask:
    LD A,C
    CPL
    AND (HL)
    LD (HL),A
    RET

; 捕捉直前の実行位置。RESUME NEXTは引用符内のコロンを飛び越して次文へ。
S9_SAVE_ERROR:
    LD HL,(0CA10h)           ; 文頭は捕捉時だけ保存、ハンドラの文頭と分離
    LD (S9_RESUME_PTR),HL
    LD HL,(RUN_CUR_RECORD)
    LD (S9_RESUME_REC),HL
    LD HL,(LINE_END)
    LD (S9_RESUME_END),HL
    RET
S9_SKIP_QUOTED_STMT:
    XOR A
    LD (0CA0Fh),A
s9_skip_loop:
    CALL B3_AT_END
    RET Z
    CALL B3_PEEK_CHAR
    CP '"'
    JR NZ,s9_skip_colon
    LD A,(0CA0Fh)
    XOR 1
    LD (0CA0Fh),A
    JR s9_skip_next
s9_skip_colon:
    CP ':'
    JR NZ,s9_skip_next
    LD A,(0CA0Fh)
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
