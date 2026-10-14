; 第5.7.1節。起動既定80桁20行。バンク切替・CRTC/DMA出力をしない。
; 各12Bの独自既定値は実行時のKEY表示と同じ。起動時だけ使う。
KEY_BOOT_ROW:
    LD HL,0
    LD (MM_FKEY_PTR),HL
    LD A,1
    LD (MM_FKEY_ON),A
    LD DE,MM_TEXT_BASE+19*120+6
    LD HL,KEY_BOOT_DEFAULTS
_kbr_slot:
    PUSH DE
    PUSH HL
    LD B,(HL)
    INC HL
_kbr_copy:
    LD A,(HL)
    LD (DE),A
    INC HL
    INC DE
    DJNZ _kbr_copy
    POP HL
    LD DE,12
    ADD HL,DE
    POP DE
    EX DE,HL
    LD BC,14
    ADD HL,BC
    EX DE,HL
    ; 5組の終端は既定値の終端で判定し、追加RAMを使わない。
    LD A,L
    CP (KEY_BOOT_DEFAULTS_END & 255)
    JR NZ,_kbr_slot
    LD A,'+'
    LD (MM_TEXT_BASE+19*120+75),A
    RET
KEY_BOOT_DEFAULTS:
    DB 5,"ALPHA",0,0,0,0,0,0
    DB 3,"TWO",0,0,0,0,0,0,0,0
    DB 3,"TRI",0,0,0,0,0,0,0,0
    DB 5,"DELTA",0,0,0,0,0,0
    DB 4,"FIVE",0,0,0,0,0,0,0
KEY_BOOT_DEFAULTS_END:
KEY_BOOT_ROW_END:

