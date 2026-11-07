; INPUTだけの桁検査。既存の数値器が大きな指数を循環させる場合でも、
; 非ゼロの十進仮数の桁位置+指数が38を超えればERR6。境界38は既存変換へ。
; 旧INPUT予約域を一時カウンタに使い、現在の受け皿表を壊さない。
IR_INTEGER EQU MM_RUN_INPUT_COUNT
IR_ZERO EQU MM_RUN_INPUT_VARS
    ORG 0x6A40
ir_range:
    XOR A
    LD (MM_ERROR_FLAG),A
    LD (IR_INTEGER),A
    LD (IR_ZERO),A
    LD (IR_ZERO+1),A
    LD (IR_ZERO+2),A
    LD (IR_ZERO+5),A
    LD HL,MM_RUN_STR_TMP_BUF
    LD A,(MM_RUN_STR_TMP_LEN)
    LD B,A
    OR A
    RET Z
    LD A,(HL)
    CP '+'
    JR Z,ir_sign
    CP '-'
    JR NZ,ir_mantissa
ir_sign:
    INC HL
    DEC B
    RET Z
ir_mantissa:
    LD A,(HL)
    CP '.'
    JR NZ,ir_digit
    LD A,1
    LD (IR_ZERO+2),A
    JR ir_next
ir_digit:
    CP '0'
    JR C,ir_other
    CP '9'+1
    JR NC,ir_other
    LD C,A
    LD A,(IR_ZERO+2)
    OR A
    JR NZ,ir_leading
    LD A,(IR_INTEGER)
    INC A
    LD (IR_INTEGER),A
ir_leading:
    LD A,(IR_ZERO+1)
    OR A
    JR NZ,ir_next
    LD A,C
    CP '0'
    JR NZ,ir_nonzero
    LD A,(IR_ZERO)
    INC A
    LD (IR_ZERO),A
    JR ir_next
ir_nonzero:
    LD A,1
    LD (IR_ZERO+1),A
ir_next:
    INC HL
    DJNZ ir_mantissa
    LD DE,0
    JR ir_combine
ir_other:
    AND 0DFh
    CP 'E'
    JR Z,ir_exponent
    CP 'D'
    RET NZ                    ; 基数・任意式・接尾辞は既存解析に委ねる
ir_exponent:
    INC HL
    DEC B
    RET Z
    LD A,(HL)
    CP '-'
    JR NZ,ir_plus
    LD A,1
    LD (IR_ZERO+5),A
    JR ir_exp_sign
ir_plus:
    CP '+'
    JR NZ,ir_exp_begin
ir_exp_sign:
    INC HL
    DEC B
    RET Z
ir_exp_begin:
    LD DE,0
ir_exp_digit:
    LD A,(HL)
    SUB '0'
    CP 10
    RET NC
    LD C,A
    LD A,D
    CP 4
    JR NC,ir_exp_next         ; 大きな指数は十分大きい値で飽和
    PUSH HL
    LD H,D
    LD L,E
    ADD HL,HL
    ADD HL,HL
    ADD HL,DE
    ADD HL,HL
    LD D,0
    LD E,C
    ADD HL,DE
    EX DE,HL
    POP HL
ir_exp_next:
    INC HL
    DJNZ ir_exp_digit
ir_combine:
    LD A,(IR_ZERO+1)
    OR A
    RET Z                    ; 0に大きな指数を掛けても0
    PUSH DE
    LD A,(IR_INTEGER)
    LD L,A
    LD H,0
    LD A,(IR_ZERO)
    LD E,A
    LD D,0
    OR A
    SBC HL,DE
    DEC HL
    POP DE
    LD A,(IR_ZERO+5)
    OR A
    JR Z,ir_exp_positive
    OR A
    SBC HL,DE
    JR ir_check
ir_exp_positive:
    ADD HL,DE
ir_check:
    BIT 7,H
    RET NZ
    LD A,H
    OR A
    JR NZ,ir_overflow
    LD A,L
    CP 39
    RET C
ir_overflow:
    LD A,6
    LD (MM_ERROR_KIND),A
    LD A,1
    LD (MM_ERROR_FLAG),A
    LD (MM_ERROR_IS_RUNTIME),A
    RET
ir_code_end:
