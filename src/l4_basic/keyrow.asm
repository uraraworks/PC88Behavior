; 根拠: docs/spec/l4-program.md 5.7。文字列は独自設計。
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
    LD HL,KY_BOOT_ADDR
    RET
ky_init_data:
    LD DE,(MM_FKEY_PTR)
    LD BC,289
    XOR A
ky_init_clear:
    LD (DE),A
    INC DE
    DEC BC
    LD A,B
    OR C
    JR Z,ky_init_cleared
    XOR A
    JR ky_init_clear
ky_init_cleared:
    LD DE,(MM_FKEY_PTR)
    LD HL,KY_BOOT_ADDR
    LD A,10
ky_init_shift:
    PUSH AF
    LD BC,12
    LDIR
    INC DE
    INC DE
    INC DE
    INC DE
    POP AF
    DEC A
    JR NZ,ky_init_shift
    RET
ky_snapshot:
    LD HL,(MM_FKEY_PTR)
    LD A,H
    OR L
    JR NZ,ky_snapshot_ready
    LD HL,KY_BOOT_ADDR
    LD DE,MM_RUN_STR_ARG1_BUF
    LD A,5
ky_snapshot_loop:
    PUSH AF
    LD BC,12
    LDIR
    XOR A
    LD (DE),A
    INC DE
    LD (DE),A
    INC DE
    LD (DE),A
    INC DE
    LD (DE),A
    INC DE
    POP AF
    DEC A
    JR NZ,ky_snapshot_loop
    RET
ky_snapshot_ready:
    LD DE,MM_RUN_STR_ARG1_BUF
    LD BC,80
    LDIR
    RET
ky_draw:
    LD A,(MM_SCR_P31)
    BIT 5,A
    LD HL,MM_TEXT_BASE+19*120
    JR Z,ky_row
    LD HL,MM_TEXT_BASE+24*120
ky_row:
    LD IX,KY_CLEAR_ADDR
    CALL BANK1_MAIN_CALL_ADDR
    LD A,(MM_SCR_MODE)
    BIT 1,A
    RET NZ
ky_choose_width:
    LD A,(MM_SCR_COLS)
    CP 80
    JR NZ,ky_narrow
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
    PUSH HL                  ; 現在の枠を保ち、次枠へ定長で進む
    LD A,(HL)
    INC HL
    LD B,A
    LD A,(MM_SCR_COLS)
    CP 80
    LD A,11
    JR Z,ky_cap
    LD A,6
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
    CP 13
    JR Z,ky_next
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
    POP HL
    POP DE
    PUSH DE
    LD DE,16
    LD A,(MM_FKEY_PTR+1)
    OR A
    JR NZ,ky_stride
    LD A,(MM_FKEY_PTR)
    OR A
    JR NZ,ky_stride
    LD E,12
ky_stride:
    ADD HL,DE
    POP DE
    INC IX
    DEC C
    JR NZ,ky_slot
    RET
ky_pos40: DB 4,18,32,46,60
KY_BOOT_ADDR EQU 0x1787
KY_CLEAR_ADDR EQU 0x1787
KY_ROW_END:
