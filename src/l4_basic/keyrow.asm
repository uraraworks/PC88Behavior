; 根拠: docs/spec/l4-program.md 5.7。文字列・装飾は独自設計。
; bank1 FILES本体の後ろ。固定入口を追加し、既存入口は動かさない。
    ORG 0x62A0
    JP ky_init
    ORG 0x62A4
    JP ky_draw
    ORG 0x62A8
    JP ky_init_data
    ORG 0x62AC
    JP ky_snapshot
ky_init:
    LD HL,0
    LD (MM_FKEY_PTR),HL
    LD A,1
    LD (MM_FKEY_ON),A
    JR ky_draw
ky_data:
    LD HL,(MM_FKEY_PTR)
    LD A,H
    OR L
    RET NZ
    LD HL,ky_defaults
    RET
ky_init_data:
    LD HL,ky_defaults
    LD DE,(MM_FKEY_PTR)
    LD BC,120
    LDIR
    RET
ky_snapshot:
    CALL ky_data
    LD DE,MM_RUN_STR_ARG1_BUF
    LD BC,120
    LDIR
    RET
ky_draw:
    LD A,(MM_SCR_P31)
    BIT 5,A
    LD HL,MM_TEXT_BASE+19*120
    JR Z,ky_row
    LD HL,MM_TEXT_BASE+24*120
ky_row:
    PUSH HL
    LD B,80
ky_clear:
    LD (HL),32
    INC HL
    DJNZ ky_clear
    POP DE
    LD A,(MM_SCR_MODE)
    BIT 1,A
    RET NZ                     ; CONSOLE ,,0 は文字行を消す
    LD A,(MM_SCR_COLS)
    CP 80
    JR NZ,ky_narrow
    PUSH DE
    LD HL,75
    ADD HL,DE
    LD (HL),'+'               ; 独自の装飾1セル
    POP DE
    LD IX,ky_pos80
    JR ky_setup
ky_narrow:
    LD IX,ky_pos40
ky_setup:
    CALL ky_data
    LD C,5
ky_slot:
    PUSH DE
    PUSH HL
    LD A,(IX+0)
    LD L,A
    LD H,0
    ADD HL,DE
    EX DE,HL
    POP HL
    LD A,(HL)
    INC HL
    LD B,A
    LD A,(MM_SCR_COLS)
    CP 80
    LD A,11
    JR Z,ky_cap
    LD A,7
ky_cap:
    CP B
    JR NC,ky_len
    LD B,A
ky_len:
    LD A,B
    OR A
    JR Z,ky_next
ky_copy:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    LD A,(MM_SCR_COLS)
    CP 80
    JR Z,ky_step
    INC DE
ky_step:
    DJNZ ky_copy
ky_next:
    POP DE
    CALL ky_data
    LD A,6
    SUB C
    LD B,A
    PUSH DE
    LD DE,12
ky_next_slot:
    ADD HL,DE
    DJNZ ky_next_slot
    POP DE
    INC IX
    DEC C
    JR NZ,ky_slot
    RET
ky_pos80: DB 6,20,34,48,62
ky_pos40: DB 0,16,32,48,64
; 非空白合計20。80桁時は装飾込み21。語は自作、押下には展開しない。
ky_defaults:
    DB 5,"ALPHA",0,0,0,0,0,0
    DB 3,"TWO",0,0,0,0,0,0,0,0
    DB 3,"TRI",0,0,0,0,0,0,0,0
    DB 5,"DELTA",0,0,0,0,0,0
    DB 4,"FIVE",0,0,0,0,0,0,0
    DS 60,0
KY_ROW_END:
