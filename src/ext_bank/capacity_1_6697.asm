; c1: LIST_RENDER_TEXT。自作mainから移動、規則/処理は維持。
    ORG 0x6697
LIST_RENDER_TEXT:
    LD (PROG_REND_PTR),HL
    LD (PROG_REND_LEN),A
    XOR A
    LD (PROG_REND_MODE),A
    LD (PROG_REND_INNAME),A
    LD (PROG_REND_PREV),A
_lrt_loop:
    LD A,(PROG_REND_LEN)
    OR A
    RET Z
    LD HL,(PROG_REND_PTR)
    LD A,(PROG_REND_MODE)
    LD D,A
    LD A,(HL)
    BIT 1,D
    JR NZ,_lrt_put                  ; 行末まで打鍵どおり
    CP '"'
    JR NZ,_lrt_notq
    LD A,D
    XOR 1
    LD (PROG_REND_MODE),A           ; 引用符の開閉
    XOR A
    LD (PROG_REND_INNAME),A
    LD A,'"'
    JR _lrt_put
_lrt_notq:
    BIT 0,D
    JR NZ,_lrt_put                  ; 引用符の中
    BIT 2,D
    JR Z,_lrt_normal
    CP ':'
    JR NZ,_lrt_put                  ; DATA の中
    LD A,D
    AND 0FBh
    LD (PROG_REND_MODE),A           ; DATA は ':' で終わる
    LD A,':'
    JR _lrt_put
_lrt_put:                           ; A=出す文字。出して1文字進む
    CALL LRT_EMIT
    CALL LRT_ADV1
    JR _lrt_loop
_lrt_normal:
    CP 27h                          ; '
    JR NZ,_lrt_n1
    LD HL,PROG_REND_MODE
    SET 1,(HL)
    LD A,27h
    JR _lrt_put
_lrt_n1:
    CP '?'
    JR Z,_lrt_question
    LD D,A                          ; D=打った文字
    CALL FOLD_UPPER
    CP 'A'
    JR C,_lrt_nonletter
    CP 'Z'+1
    JR NC,_lrt_nonletter
    LD B,A                          ; B=大文字にした英字（以下 PRINT_CHAR を呼ぶまで保つ）
    LD A,(PROG_REND_INNAME)
    OR A
    LD A,B
    JR NZ,_lrt_put                  ; 名前の途中
    ; 名前の連なりの先頭: REM / DATA / GO TO か調べる
    LD HL,LRT_KW
_lrt_kwloop:
    LD A,(HL)
    CP 0FFh
    JR Z,_lrt_namestart
    PUSH AF                         ; 方式ビット
    INC HL
    PUSH HL
    LD DE,(PROG_REND_PTR)
    LD A,(PROG_REND_LEN)
    LD C,A
    CALL LRT_MATCH
    POP HL                          ; 語の先頭（PUSH/POPはフラグを変えない）
    JR Z,_lrt_kwhit
    POP AF
_lrt_kwskip:
    LD A,(HL)
    INC HL
    OR A
    JR NZ,_lrt_kwskip
    JR _lrt_kwloop
_lrt_kwhit:
    LD (PROG_REND_PTR),DE           ; 語の直後へ進める
    LD A,C
    LD (PROG_REND_LEN),A
    CALL LRT_PUTS                   ; 語（大文字）を出す
    POP AF
    LD HL,PROG_REND_MODE
    OR (HL)
    LD (HL),A
    JP _lrt_loop
_lrt_namestart:
    LD A,1
    LD (PROG_REND_INNAME),A
    LD A,B
    JR _lrt_put
_lrt_nonletter:
    LD A,D
    CALL LRT_NAMECH                 ; 英字ではないので、CF=1 は数字か .
    LD A,D
    JR C,_lrt_put                   ; 数字と . は連なりの状態を変えない
    XOR A
    LD (PROG_REND_INNAME),A
    LD A,D
    JR _lrt_put
_lrt_question:
    LD A,(PROG_REND_PREV)
    CALL LRT_NAMECH
    JR NC,_lrt_q1
    LD A,' '
    CALL LRT_EMIT
_lrt_q1:
    LD HL,LRT_W_PRINT
    CALL LRT_PUTS
    XOR A
    LD (PROG_REND_INNAME),A
    LD A,(PROG_REND_LEN)
    CP 2
    JR C,_lrt_q3
    LD HL,(PROG_REND_PTR)
    INC HL
    LD A,(HL)
    CP '&'
    JR Z,_lrt_q2
    CALL LRT_NAMECH
    JR NC,_lrt_q3
_lrt_q2:
    LD A,' '
    CALL LRT_EMIT
_lrt_q3:
    CALL LRT_ADV1
    JP _lrt_loop

; LRT_ADV1 — 1文字進む。
LRT_ADV1:
    LD HL,(PROG_REND_PTR)
    INC HL
    LD (PROG_REND_PTR),HL
    LD HL,PROG_REND_LEN
    DEC (HL)
    RET

; LRT_EMIT — A を出して PROG_REND_PREV に残す。破壊: AF,DE,HL（PRINT_CHAR 準拠）。
LRT_EMIT:
    LD (PROG_REND_PREV),A
    JP PRINT_CHAR

; LRT_PUTS — HL=0終端の語。空白は出さない（"GO TO" -> GOTO）。
LRT_PUTS:
    LD A,(HL)
    OR A
    RET Z
    INC HL
    CP ' '
    JR Z,LRT_PUTS
    PUSH HL
    CALL LRT_EMIT
    POP HL
    JR LRT_PUTS
