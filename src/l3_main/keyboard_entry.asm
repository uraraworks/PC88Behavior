; main-rom-entry 仕様第9版 1.5.1。定数は仕様 第9版で未確定。
ENTRY_3080_HL_RETURN_VALUE EQU 0F000h ; main-rom-entry.md 1.5.1: 戻り時のHL値
ENTRY_3080:
    PUSH BC
    PUSH DE
    LD A,01h
    LD (MM_GAME_WA_E6C3),A
    OUT (0E4h),A
    LD A,080h
    OUT (51h),A
    LD A,016h
    OUT (50h),A
    LD A,01h
    OUT (50h),A
    LD B,0                   ; 今回の押下の集合
    LD C,0                   ; 前回の押下の集合
    LD A,(MM_GAME_WA_E6D0+11)
    LD (MM_GAME_WA_E6DC+11),A
    OR C
    LD C,A
ENTRY_3080_IN_0B:
    IN A,(0x0B)
    CPL
    LD (MM_GAME_WA_E6D0+11),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0+10)
    LD (MM_GAME_WA_E6DC+10),A
    OR C
    LD C,A
ENTRY_3080_IN_0A:
    IN A,(0x0A)
    CPL
    LD (MM_GAME_WA_E6D0+10),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0+9)
    LD (MM_GAME_WA_E6DC+9),A
    OR C
    LD C,A
ENTRY_3080_IN_09:
    IN A,(0x09)
    CPL
    LD (MM_GAME_WA_E6D0+9),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0+8)
    LD (MM_GAME_WA_E6DC+8),A
    OR C
    LD C,A
ENTRY_3080_IN_08:
    IN A,(0x08)
    CPL
    LD (MM_GAME_WA_E6D0+8),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0+7)
    LD (MM_GAME_WA_E6DC+7),A
    OR C
    LD C,A
ENTRY_3080_IN_07:
    IN A,(0x07)
    CPL
    LD (MM_GAME_WA_E6D0+7),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0+6)
    LD (MM_GAME_WA_E6DC+6),A
    OR C
    LD C,A
ENTRY_3080_IN_06:
    IN A,(0x06)
    CPL
    LD (MM_GAME_WA_E6D0+6),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0+5)
    LD (MM_GAME_WA_E6DC+5),A
    OR C
    LD C,A
ENTRY_3080_IN_05:
    IN A,(0x05)
    CPL
    LD (MM_GAME_WA_E6D0+5),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0+4)
    LD (MM_GAME_WA_E6DC+4),A
    OR C
    LD C,A
ENTRY_3080_IN_04:
    IN A,(0x04)
    CPL
    LD (MM_GAME_WA_E6D0+4),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0+3)
    LD (MM_GAME_WA_E6DC+3),A
    OR C
    LD C,A
ENTRY_3080_IN_03:
    IN A,(0x03)
    CPL
    LD (MM_GAME_WA_E6D0+3),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0+2)
    LD (MM_GAME_WA_E6DC+2),A
    OR C
    LD C,A
ENTRY_3080_IN_02:
    IN A,(0x02)
    CPL
    LD (MM_GAME_WA_E6D0+2),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0+1)
    LD (MM_GAME_WA_E6DC+1),A
    OR C
    LD C,A
ENTRY_3080_IN_01:
    IN A,(0x01)
    CPL
    LD (MM_GAME_WA_E6D0+1),A
    OR B
    LD B,A
    LD A,(MM_GAME_WA_E6D0)
    LD (MM_GAME_WA_E6DC),A
    OR C
    LD C,A
ENTRY_3080_IN_00:
    IN A,(0x00)
    CPL
    LD (MM_GAME_WA_E6D0),A
    OR B
    LD B,A
    XOR A
    LD (MM_GAME_WA_EFFF),A
    LD (MM_GAME_WA_EFF9),A
    LD A,B
    OR A
    JR Z,ENTRY_3080_DONE
    LD A,C
    OR A
    JR NZ,ENTRY_3080_HELD
    LD A,KEY_REPEAT_DELAY
    LD (MM_GAME_WA_E6CF),A
    JR ENTRY_3080_DONE
ENTRY_3080_HELD:
    LD A,(MM_GAME_WA_E6CF)
    DEC A
    LD (MM_GAME_WA_E6CF),A
    JR Z,ENTRY_3080_REPEAT
    LD A,0FFh
    LD (MM_GAME_WA_EFF9),A
    JR ENTRY_3080_DONE
ENTRY_3080_REPEAT:
    LD A,KEY_REPEAT_INTERVAL
    LD (MM_GAME_WA_E6CF),A
    LD (MM_GAME_WA_EFF9),A
ENTRY_3080_DONE:
    LD A,07h
    LD (MM_GAME_WA_E6C3),A
ENTRY_3080_OUT:
    OUT (0E4h),A
    POP DE
    POP BC
    LD HL,0750h
    PUSH HL
    POP AF
    LD HL,ENTRY_3080_HL_RETURN_VALUE
ENTRY_3080_RET:
    EI
    RET
