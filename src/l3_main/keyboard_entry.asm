; main-rom-entry 仕様第9版 1.5.1。定数は仕様 第9版で未確定。
ENTRY_3080:
    PUSH BC
    PUSH DE
    LD A,01h
    LD (0E6C3h),A
    OUT (0E4h),A
    LD A,080h
    OUT (51h),A
    LD A,016h
    OUT (50h),A
    LD A,01h
    OUT (50h),A
    LD B,0                   ; 今回の押下の集合
    LD C,0                   ; 前回の押下の集合
    LD A,(0xE6DB)
    LD (0xE6E7),A
    OR C
    LD C,A
ENTRY_3080_IN_0B:
    IN A,(0x0B)
    CPL
    LD (0xE6DB),A
    OR B
    LD B,A
    LD A,(0xE6DA)
    LD (0xE6E6),A
    OR C
    LD C,A
ENTRY_3080_IN_0A:
    IN A,(0x0A)
    CPL
    LD (0xE6DA),A
    OR B
    LD B,A
    LD A,(0xE6D9)
    LD (0xE6E5),A
    OR C
    LD C,A
ENTRY_3080_IN_09:
    IN A,(0x09)
    CPL
    LD (0xE6D9),A
    OR B
    LD B,A
    LD A,(0xE6D8)
    LD (0xE6E4),A
    OR C
    LD C,A
ENTRY_3080_IN_08:
    IN A,(0x08)
    CPL
    LD (0xE6D8),A
    OR B
    LD B,A
    LD A,(0xE6D7)
    LD (0xE6E3),A
    OR C
    LD C,A
ENTRY_3080_IN_07:
    IN A,(0x07)
    CPL
    LD (0xE6D7),A
    OR B
    LD B,A
    LD A,(0xE6D6)
    LD (0xE6E2),A
    OR C
    LD C,A
ENTRY_3080_IN_06:
    IN A,(0x06)
    CPL
    LD (0xE6D6),A
    OR B
    LD B,A
    LD A,(0xE6D5)
    LD (0xE6E1),A
    OR C
    LD C,A
ENTRY_3080_IN_05:
    IN A,(0x05)
    CPL
    LD (0xE6D5),A
    OR B
    LD B,A
    LD A,(0xE6D4)
    LD (0xE6E0),A
    OR C
    LD C,A
ENTRY_3080_IN_04:
    IN A,(0x04)
    CPL
    LD (0xE6D4),A
    OR B
    LD B,A
    LD A,(0xE6D3)
    LD (0xE6DF),A
    OR C
    LD C,A
ENTRY_3080_IN_03:
    IN A,(0x03)
    CPL
    LD (0xE6D3),A
    OR B
    LD B,A
    LD A,(0xE6D2)
    LD (0xE6DE),A
    OR C
    LD C,A
ENTRY_3080_IN_02:
    IN A,(0x02)
    CPL
    LD (0xE6D2),A
    OR B
    LD B,A
    LD A,(0xE6D1)
    LD (0xE6DD),A
    OR C
    LD C,A
ENTRY_3080_IN_01:
    IN A,(0x01)
    CPL
    LD (0xE6D1),A
    OR B
    LD B,A
    LD A,(0xE6D0)
    LD (0xE6DC),A
    OR C
    LD C,A
ENTRY_3080_IN_00:
    IN A,(0x00)
    CPL
    LD (0xE6D0),A
    OR B
    LD B,A
    XOR A
    LD (0EFFFh),A
    LD (0EFF9h),A
    LD A,B
    OR A
    JR Z,ENTRY_3080_DONE
    LD A,C
    OR A
    JR NZ,ENTRY_3080_HELD
    LD A,KEY_REPEAT_DELAY
    LD (0E6CFh),A
    JR ENTRY_3080_DONE
ENTRY_3080_HELD:
    LD A,(0E6CFh)
    DEC A
    LD (0E6CFh),A
    JR Z,ENTRY_3080_REPEAT
    LD A,0FFh
    LD (0EFF9h),A
    JR ENTRY_3080_DONE
ENTRY_3080_REPEAT:
    LD A,KEY_REPEAT_INTERVAL
    LD (0E6CFh),A
    LD (0EFF9h),A
ENTRY_3080_DONE:
    LD A,07h
    LD (0E6C3h),A
ENTRY_3080_OUT:
    OUT (0E4h),A
    POP DE
    POP BC
    LD HL,0750h
    PUSH HL
    POP AF
    LD HL,0F000h
ENTRY_3080_RET:
    EI
    RET
