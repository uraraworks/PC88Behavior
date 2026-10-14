; c1: LIST_STMT。自作mainから移動、規則/処理は維持。
    ORG 0x7FA3
LIST_STMT:
    CALL SKIP_SPACES
    CALL PEEK_CHAR
    OR A
    JR Z,_l4list_ok
    CP ':'
    JR Z,_l4list_ok
    LD A,1
    LD (ERROR_FLAG),A
    RET
_l4list_ok:
    JP LIST_RENDER_ALL

; ---------------------------------------------------------------------
; LIST_RENDER_ALL — 保存済みの全行を、行番号順に
;   「行番号(前ゼロなし) + 変換済み本文」の形で1行ずつ出す（第2節）。
;   破壊: AF,BC,DE,HL。
; ---------------------------------------------------------------------
LIST_RENDER_ALL:
    LD HL,PROGRAM_AREA
_lra_loop:
    LD E,(HL)
    INC HL
    LD D,(HL)
    DEC HL
    LD A,D
    CP 0FFh
    JR NZ,_lra_have
    LD A,E
    CP 0FFh
    JR Z,_lra_done
_lra_have:
    PUSH HL
    EX DE,HL
    CALL PRINT_UDEC                 ; 行番号(前ゼロ抑制、既存ルーチン流用)
    POP HL
    PUSH HL
    INC HL
    INC HL
    LD A,(HL)                       ; 本文長
    INC HL                          ; HL=本文の先頭
    LD C,A                          ; C=本文の残り長さ
    PUSH HL                         ; PRINT_CHARはHLを作業用に破壊する
                                     ; (screen.asmヘッダ注記)ので退避する
    LD A,' '
    CALL PRINT_CHAR                 ; 保存時に区切りの空白1個だけ除去済み
    POP HL
    LD A,C
    CALL LIST_RENDER_TEXT
    CALL NEWLINE
    POP HL
    PUSH HL
    INC HL
    INC HL
    LD A,(HL)
    POP HL
    LD C,A
    LD B,0
    INC BC
    INC BC
    INC BC
    ADD HL,BC
    JR _lra_loop
_lra_done:
    RET
