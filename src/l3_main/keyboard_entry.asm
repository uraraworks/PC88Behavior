; main-rom-entry 仕様 第12版 1.5.1・1.5.2。
ENTRY_3080_HL_RETURN_VALUE EQU 0F000h ; キーがない道筋だけの戻りHL
ENTRY_3080:
    PUSH BC
    PUSH DE
    LD A,01h
    LD (MM_GAME_WA_E6C3),A
    OUT (0E4h),A
ENTRY_3080_INHIBIT:
    LD A,(MM_GAME_WA_E6CD)
    OR A
    JP NZ,ENTRY_3080_IDLE
    LD A,080h
    OUT (51h),A
    LD A,016h
    OUT (50h),A
    LD A,01h
    OUT (50h),A
    XOR A
    LD (MM_GAME_WA_EFF9),A
    LD HL,MM_GAME_WA_E6D0+11
    LD DE,MM_GAME_WA_E6DC+11
    LD C,11
ENTRY_3080_SCAN:
    LD A,(HL)
    LD (DE),A
    LD B,A
ENTRY_3080_IN:
    IN A,(C)
    CPL
    LD (HL),A
    XOR B
    AND (HL)                    ; 前回0・今回1だけを押し始めとする
    JR Z,ENTRY_3080_NEXT
    LD B,A
    XOR A
    SUB B
    AND B                       ; 同時押しの優先順は未確定。最下位ビットを選ぶ
    LD B,A
    LD A,1                      ; 仕様 第11版で未確定。既存のイベント有りの値
    LD (MM_GAME_WA_EFF9),A
    LD (MM_GAME_WA_EFFB),DE
    LD A,B
    LD (MM_GAME_WA_EFFA),A
    LD B,0
ENTRY_3080_BIT:
    RRCA
    JR C,ENTRY_3080_NUMBER
    INC B
    JR ENTRY_3080_BIT
ENTRY_3080_NUMBER:
    LD A,C
    ADD A,A
    ADD A,A
    ADD A,A
    ADD A,B
    LD (MM_GAME_WA_EFFD),A
ENTRY_3080_NEXT:
    DEC HL
    DEC DE
    DEC C
    JP P,ENTRY_3080_SCAN
    XOR A
    LD (MM_GAME_WA_EFFF),A
    LD A,(MM_GAME_WA_EFF9)
    OR A
    JR NZ,ENTRY_3080_NEW
    LD HL,MM_GAME_WA_E6D0
    LD B,12
ENTRY_3080_ANY:
    OR (HL)
    INC HL
    DJNZ ENTRY_3080_ANY
    JR Z,ENTRY_3080_IDLE
    LD A,0FFh
    LD (MM_GAME_WA_EFF9),A
    LD HL,MM_GAME_WA_E6CF
    DEC (HL)
    JR NZ,ENTRY_3080_DONE
    LD (HL),KEY_REPEAT_INTERVAL
    JR ENTRY_3080_PUSH
ENTRY_3080_NEW:
    LD HL,(MM_GAME_WA_EFFB)
    PUSH HL
    LD BC,-12
    ADD HL,BC
    LD A,(HL)
    POP HL
    LD (HL),A
ENTRY_3080_DELAY:
    LD A,28                     ; 押し始めを0回目とした呼出し回数
    LD (MM_GAME_WA_E6CF),A
    LD A,(MM_GAME_WA_EFFD)
    PUSH BC
    PUSH DE
    EI
ENTRY_3080_HOOK:
    CALL MM_GAME_WA_ECDF         ; フック入口SP=3080入口SP-10、A=番号、HL=前回行
    POP DE
    POP BC
    LD A,(MM_GAME_WA_EFFD)
    LD C,A
    AND 7
    LD B,A
    LD A,C
    RRCA
    RRCA
    RRCA
    AND 15
    LD C,A
    CALL IK_DECODE_MAIN          ; INKEY$と同じ既存変換
    LD (MM_GAME_WA_EFFE),A
ENTRY_3080_PUSH:
    LD HL,0                     ; 仕様 第11版で未確定。既存の空の値0を代用
    LD (MM_GAME_WA_EFC6),HL
    LD HL,(MM_GAME_WA_E6CB)
    LD A,(HL)
    INC A
    LD C,A
    INC HL
    LD B,(HL)                   ; 読み索引
    INC HL
    INC HL
    LD A,(HL)
    AND C
    CP B
ENTRY_3080_FULL:
    JR Z,ENTRY_3080_DONE
    LD E,A
    LD D,0
    INC HL
    LD C,(HL)
    INC HL
    LD B,(HL)
    LD H,B
    LD L,C
    ADD HL,DE
    LD A,(MM_GAME_WA_EFFE)
ENTRY_3080_STORE:
    LD (HL),A
    LD HL,(MM_GAME_WA_E6CB)
    LD (HL),E                   ; 文字を先に書き、最後に書き索引を公開する
    JR ENTRY_3080_DONE
ENTRY_3080_IDLE:
    LD HL,0750h
    PUSH HL
    POP AF
    LD HL,ENTRY_3080_HL_RETURN_VALUE
ENTRY_3080_DONE:
    LD A,07h
    LD (MM_GAME_WA_E6C3),A
ENTRY_3080_OUT:
    OUT (0E4h),A
    POP DE
    POP BC
ENTRY_3080_RET:
    EI
    RET

ENTRY_35CE:
    PUSH BC
    PUSH HL
    LD C,A                      ; 空のとき入口のAを返す
    LD HL,(MM_GAME_WA_E6CB)
    INC HL
    INC HL
    LD A,(HL)
    OR A
    JR NZ,ENTRY_35CE_LOOKAHEAD
    DEC HL
    LD B,(HL)
    DEC HL
    LD A,(HL)
    CP B
ENTRY_35CE_EMPTY_CHECK:
    JR Z,ENTRY_35CE_EMPTY
    LD A,B
    INC A
    INC HL
    INC HL
    INC HL
    AND (HL)
    LD C,A
    LD B,0
    INC HL
    LD A,(HL)
    INC HL
    LD H,(HL)
    LD L,A
    ADD HL,BC
    LD B,(HL)
    LD HL,(MM_GAME_WA_E6CB)
    INC HL
    LD (HL),C
ENTRY_35CE_ADVANCE:
    INC HL
    LD (HL),0
    LD A,B
    JR ENTRY_35CE_RETURN
ENTRY_35CE_LOOKAHEAD:
    LD (HL),0
    JR ENTRY_35CE_RETURN
ENTRY_35CE_EMPTY:
    LD A,C
    CP A
    POP HL
    POP BC
    RET
ENTRY_35CE_RETURN:
    OR A                        ; 文字の符号・ゼロ・パリティを返す
    POP HL
    POP BC
    RET
