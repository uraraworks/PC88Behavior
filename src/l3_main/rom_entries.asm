; docs/spec/main-rom-entry.md 第5版の固定入口。
ENTRY_RX_PAIR EQU MM_ENTRY_RX_PAIR
ENTRY_RX_PENDING EQU MM_ENTRY_RX_PENDING
ENTRY_RX_BUFFER EQU MM_ENTRY_RX_BUFFER
ENTRY_3391:
    JP (HL)
ENTRY_37D2:
    PUSH AF
    PUSH BC
    PUSH DE
    CALL MAIN_SUB_SEND_CONT
    POP DE
    POP BC
    POP AF
    RET
ENTRY_37C9:
    PUSH AF
    PUSH BC
    PUSH DE
    PUSH HL
    XOR A
    LD (ENTRY_RX_PENDING),A
    LD (ENTRY_RX_PAIR),A
    LD HL,6
    ADD HL,SP
    INC HL
    LD A,(HL)
    CP 0x15
    JR NZ,_entry_send
    LD A,1
    LD (ENTRY_RX_PAIR),A
    LD A,0x15
_entry_send:
    CALL MAIN_SUB_SEND
    POP HL
    POP DE
    POP BC
    POP AF
    PUSH HL
    PUSH AF
    POP HL
    LD A,L
    AND 0x80
    OR 0x02
    LD L,A
    PUSH HL
    POP AF
    POP HL
    RET
ENTRY_3847:
    PUSH BC
    PUSH DE
    PUSH HL
    PUSH AF
    CALL _entry_recv
    PUSH AF
    POP HL
    POP AF
    LD A,H
    POP HL
    POP DE
    POP BC
    RET
_entry_recv:
    LD A,(ENTRY_RX_PAIR)
    OR A
    JP Z,MAIN_SUB_RECV
    LD A,(ENTRY_RX_PENDING)
    OR A
    JR Z,_entry_recv_pair
    XOR A
    LD (ENTRY_RX_PENDING),A
    LD A,(ENTRY_RX_BUFFER+1)
    RET
_entry_recv_pair:
    LD HL,ENTRY_RX_BUFFER
    CALL MAIN_SUB_RECV_PAIR
    RET C
    LD A,1
    LD (ENTRY_RX_PENDING),A
    LD A,(ENTRY_RX_BUFFER)
    RET

; B=論理トラック、C=1始まりセクタ、HL=256B、CY=書き。
ENTRY_369A:
    PUSH AF
    LD A,C
    OR A
    JR NZ,_entry_valid
    BIT 7,B
    JR NZ,_entry_bad
_entry_valid:
    POP AF
    PUSH BC
    PUSH HL
    PUSH IX
    PUSH IY
    CALL _entry_sector
    DI
    POP IY
    POP IX
    POP HL
    POP BC
    LD D,H
    LD E,L
ENTRY_369A_ADVANCE:
    INC D
    PUSH HL
    LD HL,0x0100
    PUSH HL
    POP AF
    POP HL
    RET
_entry_bad:
    POP AF
    DI
    LD D,H
    LD E,L
    LD HL,0x0193
    PUSH HL
    POP AF
    LD HL,0xEF60
    RET
_entry_sector:
    LD D,B
    LD E,C
    JR C,_entry_write
    PUSH HL
    XOR A
    CALL MAIN_SUB_READ_CHR_RETRY
    POP DE
    RET C
    LD HL,MM_MAIN_SUB_SECTOR_BUF
    LD BC,256
    LDIR
    OR A
    RET
_entry_write:
    XOR A
    LD (MM_S2_WRITE_COUNT),A
    LD BC,_entry_after_bank
    PUSH BC
    PUSH AF
    LD A,2
    LD IX,0x6663
    JP CAPACITY_BANK_CALL
_entry_after_bank:
    RET C
    LD A,6
    CALL MAIN_SUB_SEND
    RET C
    JP MAIN_SUB_RECV
