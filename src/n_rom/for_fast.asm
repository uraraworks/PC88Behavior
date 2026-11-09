; l4-program.md 4.2・5.7.6: 単位刻みの非負整数FORを同じ16bit演算で短縮する。
; 条件外は従来処理へ戻す。捕捉中は毎文、空ループでは最大4回ごとにキーを走査する。
    ORG 0x4100
for_fast_step:
    LD HL,(MM_RUN_FOR_FRAME_PTR)
    INC HL
    INC HL
    LD A,(HL)
    OR A
    JP NZ,for_fast_fallback
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    BIT 7,D
    JP NZ,for_fast_fallback
    PUSH DE
    LD HL,(MM_RUN_FOR_FRAME_PTR)
    LD DE,7
    ADD HL,DE
    LD A,(HL)
    OR A
    JP NZ,for_fast_pop
    INC HL
    LD A,(HL)
    CP 1
    JP NZ,for_fast_pop
    INC HL
    LD A,(HL)
    OR A
    JP NZ,for_fast_pop
    ; 本体が空で捕捉キーが無いときだけ、同じNEXTを最大4回まとめる。
    ; キー走査は外側の文境界で続け、捕捉中は常に1回ずつ進む。
    LD HL,(MM_RUN_FOR_FRAME_PTR)
    LD DE,14
    ADD HL,DE
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
    LD A,(HL)
    CP ':'
    JR NZ,for_fast_single
    INC HL
for_fast_space:
    LD A,(HL)
    CP ' '
    JR NZ,for_fast_body
    INC HL
    JR for_fast_space
for_fast_body:
    LD DE,(MM_STMT_START)
    OR A
    SBC HL,DE
    JR NZ,for_fast_single
    LD A,(MM_FKEY_ON)
    BIT 3,A
    JR NZ,for_fast_single
for_fast_batch:
    LD B,3
    JR for_fast_var
for_fast_single:
    LD B,1
for_fast_var:
    LD HL,(MM_RUN_FOR_FRAME_PTR)
    LD E,(HL)
    INC HL
    LD D,(HL)
    EX DE,HL
    LD DE,10
    ADD HL,DE
    LD A,(HL)
    OR A
    JP NZ,for_fast_pop
    INC HL
    LD E,(HL)
    INC HL
    LD D,(HL)
    BIT 7,D
    JP NZ,for_fast_pop
    LD A,D
    CP 07Fh
    JR NZ,for_fast_increment
    LD A,E
    CP 0FFh
    JP Z,for_fast_pop
for_fast_increment:
    ; 空ループでは3回と4回の小さな塊を使い、走査点が同じ位相に偏らないようにする。
    LD A,B
    CP 3
    JR NZ,for_fast_batch_ready
    BIT 2,E
    JR Z,for_fast_batch_ready
    BIT 3,E
    JR Z,for_fast_batch_ready
    INC B
for_fast_batch_ready:
    ; DE=current、HL=変数の上位バイト、スタック先頭=上限。
    POP IX
for_fast_batch_loop:
    INC DE
    PUSH HL
    PUSH IX
    POP HL
    OR A
    SBC HL,DE
    POP HL
    JR C,for_fast_finish
    LD A,D
    CP 07Fh
    JR NZ,for_fast_batch_next
    LD A,E
    CP 0FFh
    JR Z,for_fast_continue
for_fast_batch_next:
    DJNZ for_fast_batch_loop
for_fast_continue:
    LD (HL),D
    DEC HL
    LD (HL),E
    LD A,1
    OR A
    RET
for_fast_finish:
    LD (HL),D
    DEC HL
    LD (HL),E
    XOR A
    RET
for_fast_pop:
    POP DE
for_fast_fallback:
    SCF
    RET
