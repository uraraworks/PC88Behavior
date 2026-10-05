; PRINT USING — docs/spec/l4-basic.md 第5・23節だけから実装。
; bank1の0x6D00以降。mainの式評価・MBF・画面出力は窓外中継で呼ぶ。
; 書式は式評価の文字列作業域から退避し、次の値で上書きされない。
; 空書式は出力しないERR 5。公式の不定出力は再現しない。
; main側入口への返値: A=0はUSING不一致、A=1は実行済み（誤り含む）。
    ORG 0x6D00
PU_ENTRY:
    CALL pu_skip
    LD HL,(MM_CUR_PTR)
    LD DE,(MM_LINE_END)
    EX DE,HL
    OR A
    SBC HL,DE
    LD A,H
    OR A
    JR NZ,pu_match_begin
    LD A,L
    CP 5
    JR C,pu_no_match
pu_match_begin:
    LD HL,(MM_CUR_PTR)
    LD DE,pu_using
    LD B,5
pu_match_loop:
    LD A,(HL)
    CALL pu_upper
    LD C,A
    LD A,(DE)
    CP C
    JR NZ,pu_no_match
    INC HL
    INC DE
    DJNZ pu_match_loop
    LD DE,(MM_LINE_END)
    PUSH HL
    OR A
    SBC HL,DE
    POP HL
    JR Z,pu_match_ok
    LD A,(HL)
    CALL pu_upper
    CP 'A'
    JR C,pu_match_digit
    CP 'Z'+1
    JR C,pu_no_match
pu_match_digit:
    CP '0'
    JR C,pu_match_suffix
    CP '9'+1
    JR C,pu_no_match
pu_match_suffix:
    CP '$'
    JR Z,pu_no_match
    CP '%'
    JR Z,pu_no_match
    CP '#'
    JR Z,pu_no_match
pu_match_ok:
    LD (MM_CUR_PTR),HL
    CALL pu_statement
    LD A,1
    RET
pu_no_match:
    XOR A
    RET
pu_upper:
    CP 'a'
    RET C
    CP 'z'+1
    RET NC
    SUB 32
    RET
pu_using:
    DB "USING"

pu_statement:
    CALL pu_value
    CALL pu_bad
    RET NZ
    LD A,(MM_PU_VTYPE)
    OR A
    JP Z,pu_type
    LD A,(MM_RUN_STR_TMP_LEN)
    OR A
    JP Z,pu_illegal
    LD C,A
    LD B,0
    LD HL,MM_RUN_STR_TMP_BUF
    LD DE,MM_PU_FORMAT
    LDIR
    XOR A
    LD (DE),A
    LD (MM_SUPPRESS_NL),A
    LD (MM_PU_SEEN),A
    LD HL,MM_PU_FORMAT
    LD (MM_PU_PTR),HL
    CALL pu_skip
    CALL pu_peek
    CP ';'
    JP NZ,pu_syntax
    CALL pu_adv
    LD A,1
    LD (MM_PU_HASVAL),A
pu_scan:
    LD HL,(MM_PU_PTR)
    LD A,(HL)
    OR A
    JP Z,pu_format_end
    CP '_'
    JR NZ,pu_scan_field
    INC HL
    LD A,(HL)
    OR A
    JR NZ,pu_literal
    DEC HL
    LD A,'_'
    JR pu_literal
pu_scan_field:
    CALL pu_field
    OR A
    JR NZ,pu_have_field
    LD HL,(MM_PU_PTR)
    LD A,(HL)
pu_literal:
    INC HL
    LD (MM_PU_PTR),HL
    CALL pu_print
    JP pu_scan
pu_have_field:
    LD (MM_PU_PTR),HL
    LD B,A
    LD A,1
    LD (MM_PU_SEEN),A
    LD A,(MM_PU_HASVAL)
    OR A
    JP Z,pu_done
    PUSH BC
    CALL pu_value
    POP BC
    CALL pu_bad
    RET NZ
    LD A,B
    CP 2
    JR Z,pu_string_field
    LD A,(MM_PU_VTYPE)
    OR A
    JP NZ,pu_type
    CALL pu_number
    JR pu_after_field
pu_string_field:
    LD A,(MM_PU_VTYPE)
    OR A
    JP Z,pu_type
    CALL pu_string_out
pu_after_field:
    CALL pu_bad
    RET NZ
    XOR A
    LD (MM_SUPPRESS_NL),A
    CALL pu_skip
    CALL pu_peek
    CP ';'
    JR Z,pu_separator
    CP ','
    JR Z,pu_separator
    XOR A
    LD (MM_PU_HASVAL),A
    JP pu_scan
pu_separator:
    CALL pu_adv
    LD A,1
    LD (MM_SUPPRESS_NL),A
    CALL pu_skip
    CALL pu_peek
    OR A
    JR Z,pu_no_value
    CP ':'
    JR Z,pu_no_value
    XOR A
    LD (MM_SUPPRESS_NL),A
    INC A
    LD (MM_PU_HASVAL),A
    JP pu_scan
pu_no_value:
    XOR A
    LD (MM_PU_HASVAL),A
    JP pu_scan
pu_format_end:
    LD A,(MM_PU_SEEN)
    OR A
    JP Z,pu_illegal
    LD A,(MM_PU_HASVAL)
    OR A
    JR Z,pu_done
    XOR A
    LD (MM_PU_SEEN),A
    LD HL,MM_PU_FORMAT
    LD (MM_PU_PTR),HL
    JP pu_scan
pu_done:
    LD A,(MM_SUPPRESS_NL)
    OR A
    RET NZ
    LD IX,PU_NEWLINE_ADDR
    JP PU_MAIN_CALL_ADDR

; 数値/文字列の通常の式評価を共用。書式の型違いもERR 13へ揃える。
pu_value:
    CALL pu_skip
    CALL pu_peek
    CP '"'
    JR Z,pu_value_string
    LD IX,PU_IDENT_ADDR
    CALL PU_MAIN_CALL_ADDR
    CP 3
    JR Z,pu_value_string
    XOR A
    LD (MM_PU_VTYPE),A
    LD IX,PU_EXPR_ADDR
    JP PU_MAIN_CALL_ADDR
pu_value_string:
    LD A,1
    LD (MM_PU_VTYPE),A
    LD IX,PU_STRING_ADDR
    JP PU_MAIN_CALL_ADDR
pu_bad:
    LD A,(MM_ERROR_FLAG)
    OR A
    RET
pu_type:
    LD A,13
    JR pu_error
pu_illegal:
    LD A,5
    JR pu_error
pu_syntax:
    LD A,2
pu_error:
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
    RET

; HL=書式位置。A=0リテラル、1数値欄、2文字欄、HL=次の位置。
; 欄幅は符号・星・円・カンマも含む。小数後のカンマはリテラル。
pu_field:
    PUSH HL
    LD HL,MM_PU_LEFT
    LD DE,MM_PU_LEFT+1
    LD BC,10
    LD (HL),0
    LDIR
    POP HL
    LD A,(HL)
    CP '!'
    JR Z,pu_bang
    CP '@'
    JR Z,pu_at
    CP '&'
    JR NZ,pu_numeric_field
    PUSH HL
    INC HL
    LD B,2
pu_amp_spaces:
    LD A,(HL)
    CP ' '
    JR NZ,pu_amp_end
    INC HL
    INC B
    JR pu_amp_spaces
pu_amp_end:
    CP '&'
    JR NZ,pu_amp_literal
    POP DE
    INC HL
    LD A,B
    LD (MM_PU_SWIDTH),A
    LD A,2
    RET
pu_amp_literal:
    POP HL
    XOR A
    RET
pu_bang:
    LD A,1
    LD (MM_PU_SWIDTH),A
pu_at:
    INC HL
    LD A,2
    RET
pu_numeric_field:
    LD A,(HL)
    CP '+'
    JR NZ,pu_prefix
    LD A,1
    LD (MM_PU_LEAD),A
    INC HL
pu_prefix:
    LD A,(HL)
    CP '*'
    JR NZ,pu_yen_prefix
    INC HL
    LD A,(HL)
    CP '*'
    JP NZ,pu_not_field
    INC HL
    LD A,1
    LD (MM_PU_STAR),A
    LD A,2
    LD (MM_PU_LEFT),A
    LD A,(HL)
    CP 92
    JR NZ,pu_left_loop
    INC HL
    LD A,1
    LD (MM_PU_YEN),A
    LD A,3
    LD (MM_PU_LEFT),A
    JR pu_left_loop
pu_yen_prefix:
    CP 92
    JR NZ,pu_left_loop
    INC HL
    LD A,(HL)
    CP 92
    JP NZ,pu_not_field
    INC HL
    LD A,1
    LD (MM_PU_YEN),A
    LD A,2
    LD (MM_PU_LEFT),A
pu_left_loop:
    LD A,(HL)
    CP '#'
    JR Z,pu_left_add
    CP ','
    JR NZ,pu_dot
    LD A,(MM_PU_LEFT)
    OR A
    JR Z,pu_dot
    LD A,1
    LD (MM_PU_COMMA),A
pu_left_add:
    LD A,(MM_PU_LEFT)
    INC A
    LD (MM_PU_LEFT),A
    INC HL
    JR pu_left_loop
pu_dot:
    LD A,(HL)
    CP '.'
    JR NZ,pu_digits_end
    LD A,(MM_PU_LEFT)
    OR A
    JR NZ,pu_dot_yes
    INC HL
    LD A,(HL)
    CP '#'
    DEC HL
    JP NZ,pu_not_field
pu_dot_yes:
    INC HL
    LD A,1
    LD (MM_PU_DOT),A
pu_dec_loop:
    LD A,(HL)
    CP '#'
    JR NZ,pu_digits_end
    LD A,(MM_PU_DEC)
    INC A
    LD (MM_PU_DEC),A
    INC HL
    JR pu_dec_loop
pu_digits_end:
    LD A,(MM_PU_LEFT)
    LD B,A
    LD A,(MM_PU_DEC)
    OR B
    JR Z,pu_not_field
    LD A,(MM_PU_LEAD)
    ADD A,B
    LD (MM_PU_LEFT),A
    LD B,4
    PUSH HL
pu_caret_loop:
    LD A,(HL)
    CP '^'
    JR NZ,pu_caret_no
    INC HL
    DJNZ pu_caret_loop
    POP DE
    LD A,1
    LD (MM_PU_SCI),A
    JR pu_trail
pu_caret_no:
    POP HL
pu_trail:
    LD A,(MM_PU_LEAD)
    OR A
    JR NZ,pu_field_yes
    LD A,(HL)
    CP '+'
    JR Z,pu_trail_yes
    CP '-'
    JR NZ,pu_field_yes
pu_trail_yes:
    LD (MM_PU_TRAIL),A
    INC HL
pu_field_yes:
    LD A,1
    RET
pu_not_field:
    XOR A
    RET

pu_string_out:
    LD A,(MM_RUN_STR_TMP_LEN)
    LD C,A
    LD A,(MM_PU_SWIDTH)
    OR A
    JR NZ,pu_string_fixed
    LD B,C
    JR pu_string_start
pu_string_fixed:
    LD B,A
pu_string_start:
    LD A,B
    OR A
    RET Z
    LD HL,MM_RUN_STR_TMP_BUF
pu_string_loop:
    LD A,C
    OR A
    LD A,' '
    JR Z,pu_string_char
    LD A,(HL)
    INC HL
    DEC C
pu_string_char:
    CALL pu_print
    DJNZ pu_string_loop
    RET

; MBF_DFOUTの16桁と十進桁位置を使用。整数/単精度を厳密に倍精度へ
; 広げるので、PRINTの6桁表示を再丸めすることなく欄精度で半端を丸める。
; 十進ガード桁>=5で絶対値側へ。指数書式の繰り上がりはS_KEEP。
pu_number:
    LD A,(MM_PU_LEFT)
    LD B,A
    LD A,(MM_PU_DEC)
    ADD A,B
    LD B,A
    LD A,(MM_PU_DOT)
    ADD A,B
    CP 25
    JP NC,pu_illegal
    LD B,A
    LD A,(MM_PU_SCI)
    OR A
    LD A,B
    JR Z,pu_width_done
    ADD A,4
pu_width_done:
    LD (MM_PU_WIDTH),A
    LD A,(MM_CUR_TYPE)
    CP 2
    LD A,'E'
    JR NZ,pu_letter_done
    LD A,'D'
pu_letter_done:
    LD (MM_PU_LETTER),A
    LD IX,PU_LOAD_D_ADDR
    CALL PU_MAIN_CALL_ADDR
    LD IX,PU_DFOUT_ADDR
    CALL PU_MAIN_CALL_ADDR
    LD HL,MM_PU_DIGITS
    LD DE,MM_PU_DIGITS+1
    LD BC,79
    LD (HL),'0'
    LDIR
    XOR A
    LD (MM_PU_EXP),A
    LD (MM_PU_SIGN),A
    ; MBF_DFOUTのゼロ入口はDIGITS/E/SIGNを更新しない。packed MBFの
    ; 指数は最後のバイト（+7）なので、下位仮数でゼロ判定しない。
    LD A,(MM_MBF_DOUBLE_RAM_BASE+7)
    OR A
    JR Z,pu_zero
    LD A,(MM_DFOUT_SIGN)
    OR A
    JR Z,pu_positive
    LD A,'-'
    LD (MM_PU_SIGN),A
pu_positive:
    LD HL,MM_DFOUT_DIGITS
    LD DE,MM_PU_DIGITS+1
    LD BC,16
    LDIR
    LD A,(MM_DFOUT_E)
    JR pu_e_ready
pu_zero:
    LD A,1
pu_e_ready:
    LD (MM_PU_E),A
    LD A,(MM_PU_SCI)
    OR A
    JR Z,pu_round_setup
    LD A,(MM_PU_LEFT)
    LD B,A
    LD A,(MM_PU_TRAIL)
    OR A
    JR NZ,pu_sci_digits
    LD A,B
    OR A
    JR Z,pu_sci_digits
    DEC B
pu_sci_digits:
    LD A,(MM_MBF_DOUBLE_RAM_BASE+7)
    OR A
    JR Z,pu_sci_zero
    LD A,(MM_PU_E)
    SUB B
    LD (MM_PU_EXP),A
pu_sci_zero:
    LD A,B
    LD (MM_PU_E),A
pu_round_setup:
    LD A,(MM_PU_E)
    LD B,A
    LD A,(MM_PU_DEC)
    ADD A,B
    LD (MM_PU_KEEP),A
    JP M,pu_round_clear_all
    ; KEEP個の有効桁の次がガード桁。KEEP=0も先頭へ繰り上がる。
    LD E,A
    LD D,0
    LD HL,MM_PU_DIGITS+1
    ADD HL,DE
    LD A,(HL)
    CP '5'
    PUSH AF
    LD B,80
    LD A,(MM_PU_KEEP)
    INC A
    LD C,A
    LD A,B
    SUB C
    LD B,A
    LD A,'0'
pu_clear_tail:
    LD (HL),A
    INC HL
    DJNZ pu_clear_tail
    POP AF
    JR C,pu_build
    LD A,(MM_PU_KEEP)
    LD E,A
    LD D,0
    LD HL,MM_PU_DIGITS
    ADD HL,DE
pu_round_carry:
    INC (HL)
    LD A,(HL)
    CP '9'+1
    JR C,pu_round_carry_done
    LD (HL),'0'
    DEC HL
    JR pu_round_carry
pu_round_carry_done:
    LD A,(MM_PU_DIGITS)
    CP '0'
    JR Z,pu_build
    ; 符号セルまで伸びる仮数。指数は更新しない。
    LD HL,MM_PU_DIGITS+63
    LD DE,MM_PU_DIGITS+64
    LD BC,64
    LDDR
    LD A,'0'
    LD (MM_PU_DIGITS),A
    LD A,(MM_PU_E)
    INC A
    LD (MM_PU_E),A
    JR pu_build
pu_round_clear_all:
    LD HL,MM_PU_DIGITS
    LD DE,MM_PU_DIGITS+1
    LD BC,79
    LD (HL),'0'
    LDIR
pu_build:
    XOR A
    LD (MM_PU_BODYLEN),A
    LD HL,MM_PU_BODY
    LD (MM_PU_OUT_PTR),HL
    LD A,(MM_PU_SIGN)
    OR A
    JR NZ,pu_sign_ready
    LD A,(MM_PU_LEAD)
    OR A
    JR Z,pu_sign_ready
    LD A,'+'
    LD (MM_PU_SIGN),A
pu_sign_ready:
    LD A,(MM_PU_TRAIL)
    OR A
    JR NZ,pu_build_yen
    LD A,(MM_PU_SIGN)
    OR A
    CALL NZ,pu_append
pu_build_yen:
    LD A,(MM_PU_YEN)
    OR A
    LD A,92
    CALL NZ,pu_append
    LD A,(MM_PU_E)
    OR A
    JR Z,pu_integer_zero
    JP M,pu_integer_zero
    LD (MM_PU_REMAIN),A
    LD A,1
    LD (MM_PU_INDEX),A
pu_integer_loop:
    LD A,(MM_PU_INDEX)
    CALL pu_digit
    CALL pu_append
    LD A,(MM_PU_REMAIN)
    DEC A
    LD (MM_PU_REMAIN),A
    JR Z,pu_fraction
    LD B,A
    LD A,(MM_PU_INDEX)
    INC A
    LD (MM_PU_INDEX),A
    LD A,(MM_PU_SCI)
    OR A
    JR NZ,pu_integer_loop
    LD A,(MM_PU_COMMA)
    OR A
    JR Z,pu_integer_loop
    LD A,B
pu_mod_three:
    SUB 3
    JR Z,pu_insert_comma
    JR NC,pu_mod_three
    JR pu_integer_loop
pu_insert_comma:
    LD A,','
    CALL pu_append
    JR pu_integer_loop
pu_integer_zero:
    LD A,'0'
    CALL pu_append
pu_fraction:
    LD A,(MM_PU_DOT)
    OR A
    JR Z,pu_exponent
    LD A,'.'
    CALL pu_append
    LD A,(MM_PU_DEC)
    OR A
    JR Z,pu_exponent
    LD B,A
    LD A,(MM_PU_E)
    INC A
    LD (MM_PU_INDEX),A
pu_fraction_loop:
    LD A,(MM_PU_INDEX)
    CALL pu_digit
    CALL pu_append
    LD A,(MM_PU_INDEX)
    INC A
    LD (MM_PU_INDEX),A
    DJNZ pu_fraction_loop
pu_exponent:
    LD A,(MM_PU_SCI)
    OR A
    JR Z,pu_emit
    LD A,(MM_PU_LETTER)
    CALL pu_append
    LD A,(MM_PU_EXP)
    OR A
    LD C,A
    LD A,'+'
    JP P,pu_exp_sign
    LD A,C
    NEG
    LD C,A
    LD A,'-'
pu_exp_sign:
    CALL pu_append
    LD A,C
    LD C,0
pu_exp_tens:
    CP 10
    JR C,pu_exp_units
    SUB 10
    INC C
    JR pu_exp_tens
pu_exp_units:
    LD B,A
    LD A,C
    ADD A,'0'
    CALL pu_append
    LD A,B
    ADD A,'0'
    CALL pu_append
pu_emit:
    LD A,(MM_PU_WIDTH)
    LD B,A
    LD A,(MM_PU_BODYLEN)
    CP B
    JR C,pu_pad
    JR Z,pu_emit_body
    ; 1未満で幅に収まらない場合は小数点前の0を省く。
    LD HL,MM_PU_BODY
    LD A,(MM_PU_TRAIL)
    OR A
    JR NZ,pu_omit_yen
    LD A,(MM_PU_SIGN)
    OR A
    JR Z,pu_omit_yen
    INC HL
pu_omit_yen:
    LD A,(MM_PU_YEN)
    OR A
    JR Z,pu_omit_zero
    INC HL
pu_omit_zero:
    LD A,(HL)
    CP '0'
    JR NZ,pu_overflow
    INC HL
    LD A,(HL)
    CP '.'
    JR NZ,pu_overflow
    PUSH HL
    POP DE
    DEC DE
    LD A,(MM_PU_BODYLEN)
    LD C,A
    LD B,0
    LDIR
    LD A,(MM_PU_BODYLEN)
    DEC A
    LD (MM_PU_BODYLEN),A
    LD B,A
    LD A,(MM_PU_WIDTH)
    CP B
    JR C,pu_overflow
    JR Z,pu_emit_body
    ; 省略後に余白がある場合も同じ埋め規則。
    JR pu_pad_reversed
pu_overflow:
    LD A,'%'
    CALL pu_print
    JR pu_emit_body
pu_pad:
    LD A,B
    LD B,A
    LD A,(MM_PU_BODYLEN)
    LD C,A
    LD A,B
    SUB C
    JR pu_pad_count
pu_pad_reversed:
    SUB B
pu_pad_count:
    LD B,A
    LD A,(MM_PU_STAR)
    OR A
    LD A,' '
    JR Z,pu_pad_loop
    LD A,'*'
pu_pad_loop:
    CALL pu_print
    DJNZ pu_pad_loop
pu_emit_body:
    LD A,(MM_PU_BODYLEN)
    LD B,A
    LD HL,MM_PU_BODY
pu_emit_loop:
    LD A,(HL)
    INC HL
    CALL pu_print
    DJNZ pu_emit_loop
    LD A,(MM_PU_TRAIL)
    OR A
    RET Z
    CP '+'
    JR NZ,pu_trailing_minus
    LD A,(MM_PU_SIGN)
    OR A
    JR NZ,pu_trailing_print
    LD A,'+'
    JR pu_trailing_print
pu_trailing_minus:
    LD A,(MM_PU_SIGN)
    OR A
    JR NZ,pu_trailing_print
    LD A,' '
pu_trailing_print:
    JP pu_print

; A=正規化桁の添字（1始まり）。小数前の負添字・桁外は0。
pu_digit:
    OR A
    JR Z,pu_digit_zero
    JP M,pu_digit_zero
    CP 80
    JR NC,pu_digit_zero
    PUSH HL
    PUSH DE
    LD E,A
    LD D,0
    LD HL,MM_PU_DIGITS
    ADD HL,DE
    LD A,(HL)
    POP DE
    POP HL
    RET
pu_digit_zero:
    LD A,'0'
    RET
pu_append:
    PUSH HL
    LD HL,(MM_PU_OUT_PTR)
    LD (HL),A
    INC HL
    LD (MM_PU_OUT_PTR),HL
    LD A,(MM_PU_BODYLEN)
    INC A
    LD (MM_PU_BODYLEN),A
    POP HL
    RET

; PRINT_CHARはHLを破壊するので、欄走査・字数のレジスタを保存する。
pu_print:
    PUSH BC
    PUSH DE
    PUSH HL
    PUSH AF
    LD IX,PU_PRINT_ADDR
    CALL PU_MAIN_CALL_ADDR
    POP AF
    POP HL
    POP DE
    POP BC
    RET
pu_skip:
    LD IX,PU_SKIP_ADDR
    JP PU_MAIN_CALL_ADDR
pu_peek:
    LD IX,PU_PEEK_ADDR
    JP PU_MAIN_CALL_ADDR
pu_adv:
    LD IX,PU_ADV_ADDR
    JP PU_MAIN_CALL_ADDR
PU_MAIN_CALL_ADDR EQU 0x1787
PU_SKIP_ADDR EQU 0x1787
PU_PEEK_ADDR EQU 0x1787
PU_ADV_ADDR EQU 0x1787
PU_IDENT_ADDR EQU 0x1787
PU_STRING_ADDR EQU 0x1787
PU_EXPR_ADDR EQU 0x1787
PU_LOAD_D_ADDR EQU 0x1787
PU_DFOUT_ADDR EQU 0x1787
PU_PRINT_ADDR EQU 0x1787
PU_NEWLINE_ADDR EQU 0x1787
