; l4-basic 14.1規則4・14.5: 保存前のGO SUB詰めと数値のFIN/FOUT書き直し。
; バンク3。共有処理は既存の窓外中継を通す（main窓内の呼び先も可）。
; C500-C5CFは専用スクラッチ。実行変数・保存済み行とは重ならない。
    ORG 0x64C0
; 直接モードは整数の入力拒否だけを検査し、本文とPRINTの値は変更しない。
LISTNUM_CHECK_ENTRY:
    LD A,1
    LD (LN_CHECKONLY),A
    JP LISTNUM_START
    ORG 0x6500
LN_CHECKONLY EQU 0C5CFh
LN_INPUT EQU 0C500h             ; 入力行80文字 + NUL
LN_OUTPUT EQU 0C560h            ; 書き換え行80文字
LN_SRC EQU 0C5B0h
LN_DST EQU 0C5B2h
LN_PREFIX EQU 0C5B4h            ; 最後に採った行番号数字の直後（途中の空白を含む）
LN_MODE EQU 0C5B5h             ; 1=引用符 2=行末コメント 4=DATA
LN_NAME EQU 0C5B6h
LN_KIND EQU 0C5B7h             ; 0=自動 1=単精度 2=倍精度 3=整数
LN_DOT EQU 0C5B8h
LN_EXP EQU 0C5B9h
LN_VALUE EQU 0C5BAh
LN_BIG EQU 0C5BCh
LN_BASE EQU 0C5BDh
LN_ERR EQU 0C5BEh
LN_NDIG EQU 0C5BFh
LN_DIGBUF EQU 0C5C0h            ; 6文字（整数書き出し用）
LN_FIN_BUF EQU 0C080h
LN_FIN_LEN EQU 0C098h
LN_STATUS EQU 0C00Ch
LN_RES EQU 0C008h
LN_OPA EQU 0C000h
LN_DRES EQU 0C210h
LN_DOPA EQU 0C200h
LN_FOUT_BUF EQU 0C0D0h
LN_FOUT_LEN EQU 0C0E0h
LN_DFOUT_BUF EQU 0C285h
LN_DFOUT_LEN EQU 0C29Dh
LN_LINE_BUF EQU 0E82Bh
LN_LINE_LEN EQU 0E82Ah

; LN_PREFIX=行番号部分の文字数。CF=1なら拒否、CF=0ならLINE_BUFを書き換え済み。
LISTNUM_ENTRY:
    XOR A
    LD (LN_CHECKONLY),A
LISTNUM_START:
    XOR A
    LD (LN_MODE),A
    LD (LN_NAME),A
    LD (LN_ERR),A
    LD (ERROR_FLAG),A
    LD A,(LN_LINE_LEN)
    OR A
    RET Z
    LD C,A
    LD B,0
    LD HL,LN_LINE_BUF
    LD DE,LN_INPUT
    LDIR
    XOR A
    LD (DE),A
    LD A,(LN_PREFIX)
    LD C,A
    LD B,0
    LD HL,LN_INPUT
    LD DE,LN_OUTPUT
    LD A,C
    OR A
    JR Z,_ln_prefix_done
    LDIR
_ln_prefix_done:
    LD (LN_SRC),HL
    LD (LN_DST),DE
_ln_scan:
    LD HL,(LN_SRC)
    LD A,(HL)
    OR A
    JP Z,_ln_finish
    LD C,A
    LD A,(LN_MODE)
    BIT 1,A
    JP NZ,_ln_copy
    LD A,C
    CP '"'
    JR NZ,_ln_noquote
    LD A,(LN_MODE)
    XOR 1
    LD (LN_MODE),A
    XOR A
    LD (LN_NAME),A
    JP _ln_copy
_ln_noquote:
    LD A,(LN_MODE)
    BIT 0,A
    JP NZ,_ln_copy
    BIT 2,A
    JR Z,_ln_normal
    LD A,C
    CP ':'
    JP NZ,_ln_copy
    XOR A
    LD (LN_MODE),A
    LD (LN_NAME),A
    JP _ln_copy
_ln_normal:
    LD A,C
    CP 27h
    JR NZ,_ln_noapostrophe
    LD A,2
    LD (LN_MODE),A
    JP _ln_copy
_ln_noapostrophe:
    LD A,(LN_NAME)
    OR A
    JR Z,_ln_start
    LD A,C
    CALL LN_NAMECHAR
    JP NC,_ln_copy
    XOR A
    LD (LN_NAME),A
_ln_start:
    LD A,C
    CALL LN_FOLD
    CP 'A'
    JR C,_ln_numeric_start
    CP 'Z'+1
    JR NC,_ln_numeric_start
    CALL LN_GOSUB
    JP Z,_ln_scan
    LD DE,LN_REM
    CALL LN_WORD
    JR NZ,_ln_trydata
    LD A,2
    LD (LN_MODE),A
    JP _ln_copy
_ln_trydata:
    LD DE,LN_DATA
    CALL LN_WORD
    JR NZ,_ln_namestart
    LD A,4
    LD (LN_MODE),A
_ln_namestart:
    LD A,1
    LD (LN_NAME),A
    JP _ln_copy
_ln_numeric_start:
    LD A,C
    CP '&'
    JR Z,_ln_number
    CP '.'
    JR NZ,_ln_numeric_digit
    ; 単独の点や「..5」の最初の点は数にしない。
    LD HL,(LN_SRC)
    INC HL
    LD A,(HL)
    CALL LN_DIGIT
    JP C,_ln_copy
    JR _ln_number
_ln_numeric_digit:
    CALL LN_DIGIT
    JP C,_ln_copy
_ln_number:
    CALL LN_NUMBER
    LD A,(LN_ERR)
    OR A
    JP NZ,_ln_reject
    ; 直結したREMだけに空白を挿入。remabc等は名前。
    LD DE,LN_REM
    CALL LN_WORD
    JP NZ,_ln_scan
    LD A,' '
    CALL LN_PUT
    JP _ln_scan
_ln_copy:
    LD HL,(LN_SRC)
    LD A,(HL)
    CALL LN_PUT
    LD HL,(LN_SRC)
    INC HL
    LD (LN_SRC),HL
    JP _ln_scan
_ln_finish:
    LD A,(LN_ERR)
    OR A
    JP NZ,_ln_reject
    LD A,(LN_CHECKONLY)
    OR A
    JR Z,_ln_finish_store
    OR A
    RET
_ln_finish_store:
    LD HL,(LN_DST)
    LD DE,LN_OUTPUT
    OR A
    SBC HL,DE
    LD A,L
    LD (LN_LINE_LEN),A
    LD C,A
    LD B,0
    LD HL,LN_OUTPUT
    LD DE,LN_LINE_BUF
    LD A,C
    OR A
    RET Z
    LDIR
    OR A
    RET
_ln_reject:
    CALL LN_REPORT
    SCF
    RET

; 書き出しが80文字を超えた場合も、部分的な行を保存しない。
LN_PUT:
    PUSH HL
    PUSH DE
    PUSH AF
    LD HL,(LN_DST)
    LD DE,LN_OUTPUT+80
    OR A
    SBC HL,DE
    JR C,_ln_put_ok
    LD A,2
    LD (LN_ERR),A
    POP AF
    POP DE
    POP HL
    RET
_ln_put_ok:
    POP AF
    LD HL,(LN_DST)
    LD (HL),A
    INC HL
    LD (LN_DST),HL
    POP DE
    POP HL
    RET
LN_FOLD:
    CP 'a'
    RET C
    CP 'z'+1
    RET NC
    SUB 32
    RET
; CF=0: ASCII名前の文字、CF=1: 境界。
LN_NAMECHAR:
    CALL LN_FOLD
    CP '.'
    JR Z,_ln_name_yes
    CP 'A'
    JR C,LN_DIGIT
    CP 'Z'+1
    JR C,_ln_name_yes
    SCF
    RET
_ln_name_yes:
    OR A
    RET
LN_DIGIT:
    CP '0'
    RET C
    CP '9'+1
    CCF
    RET
; DE=大文字のNUL終端語。LN_SRCの名前の連なりがちょうどその語ならZ。
LN_WORD:
    PUSH BC
    LD HL,(LN_SRC)
_ln_word_loop:
    LD A,(DE)
    OR A
    JR Z,_ln_word_end
    LD B,A
    LD A,(HL)
    CALL LN_FOLD
    CP B
    JR NZ,_ln_word_done
    INC HL
    INC DE
    JR _ln_word_loop
_ln_word_end:
    LD A,(HL)
    CALL LN_NAMECHAR
    LD A,1
    JR NC,_ln_word_no
    XOR A
_ln_word_no:
    OR A
_ln_word_done:
    POP BC
    RET
LN_REM: DB "REM",0
LN_DATA: DB "DATA",0

; 第14.1節規則4 G_H。保護された文脈・名前内部では呼ばれない。
; "GO SUB"の直後を1文字消費し、残りを通常の数値書き換えへ戻す。
; 直接モードでは書き換えず、検査対象の数値範囲も変えない。
; Z=詰めた、NZ=不一致。BCは呼び出し元の走査文字を保持する。
LN_GOSUB:
    LD A,(LN_CHECKONLY)
    OR A
    RET NZ
    PUSH BC
    LD HL,(LN_SRC)
    LD DE,LN_GO_SUB
_ln_go_match:
    LD A,(DE)
    OR A
    JR Z,_ln_go_hit
    LD B,A
    LD A,(HL)
    CALL LN_FOLD
    CP B
    JR NZ,_ln_go_done
    INC HL
    INC DE
    JR _ln_go_match
_ln_go_hit:
    LD A,(HL)
    OR A
    JR Z,_ln_go_tail
    INC HL                         ; sub直後は文字種にかかわらず1文字だけ消費
_ln_go_tail:
    LD (LN_SRC),HL
    LD DE,LN_GOSUB_TEXT
_ln_go_put:
    LD A,(DE)
    OR A
    JR Z,_ln_go_space
    CALL LN_PUT
    INC DE
    JR _ln_go_put
_ln_go_space:
    LD A,(HL)
    CP '&'
    JR Z,_ln_go_addspace
    CALL LN_NAMECHAR
    JR C,_ln_go_success
_ln_go_addspace:
    LD A,' '
    CALL LN_PUT
_ln_go_success:
    XOR A
    LD (LN_NAME),A
_ln_go_done:
    POP BC
    RET
LN_GO_SUB: DB "GO SUB",0
LN_GOSUB_TEXT: DB "gosub",0

; 空白を先読みするだけ。次の文字を受理して初めてLN_SRCを進める。
LN_NEXT:
    LD HL,(LN_SRC)
_ln_next_loop:
    LD A,(HL)
    CP ' '
    RET NZ
    INC HL
    JR _ln_next_loop
LN_ACCEPT:
    INC HL
    LD (LN_SRC),HL
    RET
LN_FIN_PUT:
    PUSH HL
    PUSH BC
    LD HL,LN_FIN_LEN
    LD C,(HL)
    LD B,A
    LD A,C
    CP 24
    JR C,_ln_fin_put_ok
    LD A,2
    LD (LN_ERR),A
    POP BC
    POP HL
    RET
_ln_fin_put_ok:
    LD A,B
    LD B,0
    LD HL,LN_FIN_BUF
    ADD HL,BC
    LD (HL),A
    LD HL,LN_FIN_LEN
    INC (HL)
    POP BC
    POP HL
    RET
LN_NUMBER:
    XOR A
    LD (LN_FIN_LEN),A
    LD (LN_KIND),A
    LD (LN_DOT),A
    LD (LN_EXP),A
    LD (LN_BIG),A
    LD (LN_VALUE),A
    LD (LN_VALUE+1),A
    LD HL,(LN_SRC)
    LD A,(HL)
    CP '&'
    JP Z,LN_RADIX
_ln_mantissa:
    CALL LN_NEXT
    LD C,A
    CALL LN_DIGIT
    JR NC,_ln_mant_digit
    LD A,C
    CP '.'
    JR NZ,_ln_after_mantissa
    LD A,(LN_DOT)
    OR A
    JR NZ,_ln_after_mantissa
    LD A,1
    LD (LN_DOT),A
    LD A,'.'
    JR _ln_mant_accept
_ln_mant_digit:
    LD A,C
_ln_mant_accept:
    ; FINの24文字域を越える字句は入力拒否。隣接作業域を壊さない。
    LD B,A
    LD A,(LN_FIN_LEN)
    CP 23
    JP NC,_ln_token_long
    LD A,B
    CALL LN_FIN_PUT
    CALL LN_ACCEPT
    JR _ln_mantissa
_ln_after_mantissa:
    LD A,C
    CALL LN_FOLD
    CP 'D'
    JR Z,_ln_exponent_double
    CP 'E'
    JR NZ,_ln_suffix
    PUSH HL
    INC HL
_ln_el_spaces:
    LD A,(HL)
    CP ' '
    JR NZ,_ln_el_char
    INC HL
    JR _ln_el_spaces
_ln_el_char:
    CALL LN_FOLD
    CP 'L'
    POP HL
    JR Z,_ln_suffix
    LD A,1
    JR _ln_exponent
_ln_exponent_double:
    LD A,2
_ln_exponent:
    LD (LN_KIND),A
    LD (LN_EXP),A
    LD A,C
    CALL LN_FIN_PUT
    CALL LN_ACCEPT
    CALL LN_NEXT
    CP '+'
    JR Z,_ln_exp_sign
    CP '-'
    JR NZ,_ln_exp_digits
_ln_exp_sign:
    CALL LN_FIN_PUT
    CALL LN_ACCEPT
_ln_exp_digits:
    CALL LN_NEXT
    CALL LN_DIGIT
    JR C,_ln_convert
    LD B,A
    LD A,(LN_FIN_LEN)
    CP 23
    JP NC,_ln_token_long
    LD A,B
    CALL LN_FIN_PUT
    CALL LN_ACCEPT
    JR _ln_exp_digits
_ln_suffix:
    CALL LN_NEXT
    LD C,A
    LD A,3
    LD B,A
    LD A,C
    CP '%'
    JR Z,_ln_set_kind
    LD B,1
    CP '!'
    JR Z,_ln_set_kind
    LD B,2
    CP '#'
    JR NZ,_ln_convert
_ln_set_kind:
    LD A,B
    LD (LN_KIND),A
    CALL LN_ACCEPT
_ln_convert:
    LD A,(LN_ERR)
    OR A
    RET NZ
    LD A,(LN_KIND)
    CP 3
    JP Z,LN_DECIMAL_INTEGER
    LD A,(LN_CHECKONLY)
    OR A
    RET NZ
    LD A,(LN_KIND)
    OR A
    JR NZ,_ln_force_kind
    LD A,(LN_DOT)
    OR A
    JR NZ,_ln_fin
    ; 純整数か判定する。32767超ならFINの単/倍精度判定へ。
    LD HL,LN_FIN_BUF
    LD A,(LN_FIN_LEN)
    LD B,A
_ln_int_loop:
    LD A,(HL)
    SUB '0'
    PUSH HL
    PUSH BC
    LD B,10
    CALL LN_ACCUM
    POP BC
    POP HL
    INC HL
    DJNZ _ln_int_loop
    LD A,(LN_BIG)
    OR A
    JR NZ,_ln_fin
    LD HL,(LN_VALUE)
    BIT 7,H
    JR NZ,_ln_fin
    LD A,10
    JP LN_FORMAT_INT
_ln_force_kind:
    CP 2
    LD A,'#'
    JR Z,_ln_force_append
    LD A,'!'
_ln_force_append:
    CALL LN_FIN_PUT
_ln_fin:
    CALL LN_FIN
    LD A,(LN_STATUS)
    CP 3
    JP Z,_ln_double
    LD A,1
    LD (LN_KIND),A
    LD A,(LN_STATUS)
    OR A
    JR Z,_ln_single_output
    CALL LN_OVERFLOW
    LD HL,LN_MAX_SINGLE
    LD DE,LN_RES
    LD BC,4
    LDIR
_ln_single_output:
    LD HL,LN_RES
    LD DE,LN_OPA
    LD BC,4
    LDIR
    CALL LN_FOUT
    LD HL,LN_FOUT_BUF
    LD A,(LN_FOUT_LEN)
    JR _ln_float_output
_ln_double:
    LD A,2
    LD (LN_KIND),A
    CALL LN_DFIN
    LD A,(LN_STATUS)
    OR A
    JR Z,_ln_double_output
    CALL LN_OVERFLOW
    LD HL,LN_MAX_DOUBLE
    LD DE,LN_DRES
    LD BC,8
    LDIR
_ln_double_output:
    LD HL,LN_DRES
    LD DE,LN_DOPA
    LD BC,8
    LDIR
    CALL LN_DFOUT
    LD HL,LN_DFOUT_BUF
    LD A,(LN_DFOUT_LEN)
_ln_float_output:
    LD B,A
    LD C,0                   ; bit0=小数点 bit1=指数
_ln_float_loop:
    LD A,(HL)
    CP '.'
    JR NZ,_ln_float_exp
    SET 0,C
_ln_float_exp:
    CP 'E'
    JR Z,_ln_float_exp_yes
    CP 'D'
    JR NZ,_ln_float_put
_ln_float_exp_yes:
    SET 1,C
_ln_float_put:
    CALL LN_PUT
    INC HL
    DJNZ _ln_float_loop
    BIT 1,C
    RET NZ
    LD A,(LN_KIND)
    CP 2
    LD A,'#'
    JP Z,LN_PUT
    BIT 0,C
    RET NZ
    LD A,'!'
    JP LN_PUT
LN_DECIMAL_INTEGER:
    LD HL,LN_FIN_BUF
    LD A,(LN_FIN_LEN)
    LD B,A
_ln_decimal_integer_loop:
    LD A,(HL)
    CP '.'
    JR Z,_ln_decimal_fraction
    SUB '0'
    PUSH HL
    PUSH BC
    LD B,10
    CALL LN_ACCUM
    POP BC
    POP HL
    INC HL
    DJNZ _ln_decimal_integer_loop
    JR _ln_decimal_integer_done
_ln_decimal_fraction:
    DEC B
    JR Z,_ln_decimal_integer_done
    INC HL
    LD A,(HL)
    CP '5'
    JR C,_ln_decimal_integer_done
    LD HL,(LN_VALUE)
    INC HL
    LD (LN_VALUE),HL
    LD A,H
    OR L
    JR NZ,_ln_decimal_integer_done
    LD A,1
    LD (LN_BIG),A
_ln_decimal_integer_done:
    LD A,(LN_BIG)
    OR A
    JR NZ,_ln_integer_overflow
    LD HL,(LN_VALUE)
    BIT 7,H
    JR NZ,_ln_integer_overflow
    LD A,(LN_CHECKONLY)
    OR A
    RET NZ
    LD A,10
    JP LN_FORMAT_INT
_ln_token_long:
    LD A,2
    LD (LN_ERR),A
    RET
_ln_integer_overflow:
    LD A,6
    LD (LN_ERR),A
    RET
LN_OVERFLOW:
    LD A,6
    LD (ERROR_KIND),A
    JP LN_MESSAGE
LN_REPORT:
    LD A,(LN_ERR)
    LD (ERROR_KIND),A
LN_MESSAGE:
    LD A,1
    LD (ERROR_FLAG),A
    CALL LN_ERROR_MESSAGE
    XOR A
    LD (ERROR_FLAG),A
    RET
LN_MAX_SINGLE: DB 0FFh,0FFh,07Fh,0FFh
LN_MAX_DOUBLE: DB 0FFh,0FFh,0FFh,0FFh,0FFh,0FFh,07Fh,0FFh

; 非負整数の蓄積。B=基数 A=桁。16bitを越えたことを記憶する。
LN_ACCUM:
    LD C,A
    LD DE,(LN_VALUE)
    LD HL,0
_ln_accum_loop:
    ADD HL,DE
    JR NC,_ln_accum_next
    LD A,1
    LD (LN_BIG),A
_ln_accum_next:
    DJNZ _ln_accum_loop
    LD E,C
    LD D,0
    ADD HL,DE
    JR NC,_ln_accum_done
    LD A,1
    LD (LN_BIG),A
_ln_accum_done:
    LD (LN_VALUE),HL
    RET
LN_RADIX:
    CALL LN_ACCEPT
    LD A,8
    LD (LN_BASE),A
    CALL LN_NEXT
    CALL LN_FOLD
    CP 'H'
    JR NZ,_ln_octal_prefix
    LD A,16
    LD (LN_BASE),A
    CALL LN_ACCEPT
    JR _ln_radix_loop
_ln_octal_prefix:
    CP 'O'
    CALL Z,LN_ACCEPT
_ln_radix_loop:
    LD A,(LN_BASE)
    CP 16
    JR NZ,_ln_octal_next
    LD HL,(LN_SRC)
    LD A,(HL)
    JR _ln_radix_digit
_ln_octal_next:
    CALL LN_NEXT
_ln_radix_digit:
    CALL LN_FOLD
    CP '0'
    JR C,_ln_radix_done
    CP '9'+1
    JR C,_ln_radix_decimal
    LD C,A
    LD A,(LN_BASE)
    CP 16
    JR NZ,_ln_radix_done
    LD A,C
    CP 'A'
    JR C,_ln_radix_done
    CP 'F'+1
    JR NC,_ln_radix_done
    SUB 'A'-10
    JR _ln_radix_accept
_ln_radix_decimal:
    SUB '0'
    LD C,A
    LD A,(LN_BASE)
    CP 8
    LD A,C
    JR NZ,_ln_radix_accept
    CP 8
    JR C,_ln_radix_accept
    LD A,2
    LD (LN_ERR),A
    RET
_ln_radix_accept:
    PUSH HL
    LD C,A
    LD A,(LN_BASE)
    LD B,A
    LD A,C
    CALL LN_ACCUM
    POP HL
    CALL LN_ACCEPT
    JR _ln_radix_loop
_ln_radix_done:
    LD A,(LN_BIG)
    OR A
    JP NZ,_ln_integer_overflow
    LD A,'&'
    CALL LN_PUT
    LD A,(LN_BASE)
    CP 16
    LD A,'O'
    JR NZ,_ln_radix_prefix_out
    LD A,'H'
_ln_radix_prefix_out:
    CALL LN_PUT
    LD HL,(LN_VALUE)
    LD A,(LN_BASE)
LN_FORMAT_INT:
    LD (LN_BASE),A
    XOR A
    LD (LN_NDIG),A
_ln_format_divide:
    LD A,(LN_BASE)
    LD E,A
    LD D,0
    LD BC,0
_ln_format_sub:
    OR A
    SBC HL,DE
    JR C,_ln_format_remainder
    INC BC
    JR _ln_format_sub
_ln_format_remainder:
    ADD HL,DE
    LD A,L
    ADD A,'0'
    CP '9'+1
    JR C,_ln_format_digit
    ADD A,'A'-'0'-10
_ln_format_digit:
    LD HL,LN_NDIG
    LD E,(HL)
    INC (HL)
    LD D,0
    LD HL,LN_DIGBUF
    ADD HL,DE
    LD (HL),A
    LD H,B
    LD L,C
    LD A,H
    OR L
    JR NZ,_ln_format_divide
    LD A,(LN_NDIG)
    LD B,A
    LD E,A
    LD D,0
    LD HL,LN_DIGBUF
    ADD HL,DE
_ln_format_emit:
    DEC HL
    LD A,(HL)
    CALL LN_PUT
    DJNZ _ln_format_emit
    RET

; ビルド時にmainの実番地を渡す。中継はIX先を1回CALLして戻る。
LN_FIN_ADDR EQU 0x1787
LN_DFIN_ADDR EQU 0x1787
LN_FOUT_ADDR EQU 0x1787
LN_DFOUT_ADDR EQU 0x1787
LN_ERROR_MESSAGE_ADDR EQU 0x1787
LN_FIN:
    LD IX,LN_FIN_ADDR
    JP B3_MAIN_CALL_ADDR
LN_DFIN:
    LD IX,LN_DFIN_ADDR
    JP B3_MAIN_CALL_ADDR
LN_FOUT:
    LD IX,LN_FOUT_ADDR
    JP B3_MAIN_CALL_ADDR
LN_DFOUT:
    LD IX,LN_DFOUT_ADDR
    JP B3_MAIN_CALL_ADDR
LN_ERROR_MESSAGE:
    LD IX,LN_ERROR_MESSAGE_ADDR
    JP B3_MAIN_CALL_ADDR
