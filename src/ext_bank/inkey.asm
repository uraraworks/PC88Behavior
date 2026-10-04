; docs/spec/l4-basic.md 第19節、l3-main.md 第8〜10節。
; 行入力と独立した行列・リピート。32文字FIFO、満杯時は新着を捨てる
; （容量上限・満杯時の動作は未測定のため自作判断）。
; E8D1-E8E8: VRTC/読出し/書込み/件数/行列12B/リピート6B/新着有無/時計。
; E900-E91F: キュー。既存RAM一覧の空きだけを使用する。
IK_VRTC EQU MM_IK_VRTC
IK_HEAD EQU MM_IK_HEAD
IK_TAIL EQU MM_IK_TAIL
IK_COUNT EQU MM_IK_COUNT
IK_OLD EQU MM_IK_OLD
IK_PORT EQU MM_IK_PORT
IK_MASK EQU MM_IK_MASK
IK_CHAR EQU MM_IK_CHAR
IK_TIMER EQU MM_IK_TIMER
IK_MOD EQU MM_IK_MOD
IK_CAPS EQU MM_IK_CAPS
IK_EVENT EQU MM_IK_EVENT
IK_TICK EQU MM_IK_TICK
IK_BUF EQU MM_IK_BUF

    ORG 0x6F00
    JP IK_TRY
    ORG 0x6F10
    JP IK_INIT
    ORG 0x6F20
    JP IK_SCAN

IK_TRY:
    LD HL,MM_IDENT_BUF              ; IDENT_BUF: 接尾辞はIDENT_KINDで判定済み
    LD DE,IK_NAME
    LD B,7
ik_match:
    LD A,(DE)
    CP (HL)
    JR NZ,ik_not_name
    INC HL
    INC DE
    DJNZ ik_match
    XOR A
    LD (S9_TMP_LEN),A
    LD A,(IK_COUNT)
    OR A
    JR Z,ik_read_done
    DEC A
    LD (IK_COUNT),A
    LD A,(IK_HEAD)
    LD L,A
    LD H,0E9h
    LD A,(HL)
    LD (S9_TMP),A
    LD A,L
    INC A
    AND 31
    LD (IK_HEAD),A
    LD A,1
    LD (S9_TMP_LEN),A
ik_read_done:
    CALL S9_OK
    LD A,1
    RET
ik_not_name:
    XOR A
    RET
IK_NAME:
    DB "INKEY",0,0

; RUN開始時点の押下を既読とする。開始RETURNを混入させない。
IK_INIT:
    XOR A
    LD (IK_HEAD),A
    LD (IK_TAIL),A
    LD (IK_COUNT),A
    LD (IK_CHAR),A
    IN A,(040h)
    AND 020h
    LD (IK_VRTC),A
    LD C,0
    LD HL,IK_OLD
ik_init_port:
    IN A,(C)
    LD (HL),A
    INC HL
    INC C
    LD A,C
    CP 12
    JR NZ,ik_init_port
    RET

; 行列変化またはVRTC立ち上がりで呼ぶ。IK_TICK=0なら時計は進めない。
; 時計の立ち上がりの取りこぼしは従来どおり（間隔は第19.4節で未確定）。
; 押下の取りこぼしを時計から分離し、全エッジをポート/ビット順にキューする。
IK_SCAN:
    IN A,(08h)
    LD (IK_MOD),A
    IN A,(0Ah)
    LD (IK_CAPS),A
    XOR A
    LD (IK_EVENT),A
    LD C,0
    LD HL,IK_OLD
ik_scan_port:
    IN A,(C)
    LD E,A
    CPL
    AND (HL)
    LD (HL),E
    LD D,A
    LD B,0
ik_scan_bit:
    SRL D
    JR NC,ik_next_bit
    PUSH BC
    PUSH DE
    PUSH HL
    CALL IK_DECODE
    OR A
    JR Z,ik_decoded
    LD (IK_CHAR),A
    CALL IK_PUSH
    LD A,C
    LD (IK_PORT),A
    LD A,1
    LD (IK_EVENT),A
    PUSH BC
ik_mask_loop:
    DEC B
    JP M,ik_mask_done
    ADD A,A
    JR ik_mask_loop
ik_mask_done:
    LD (IK_MASK),A
    POP BC
    LD A,30
    LD (IK_TIMER),A
ik_decoded:
    POP HL
    POP DE
    POP BC
ik_next_bit:
    INC B
    LD A,B
    CP 8
    JR NZ,ik_scan_bit
    INC HL
    INC C
    LD A,C
    CP 12
    JR NZ,ik_scan_port
    LD A,(IK_EVENT)
    OR A
    RET NZ
    LD A,(IK_CHAR)
    OR A
    RET Z
    LD A,(IK_PORT)
    LD C,A
    IN A,(C)
    LD B,A
    LD A,(IK_MASK)
    AND B
    JR Z,ik_held
    XOR A
    LD (IK_CHAR),A
    RET
ik_held:
    LD A,(IK_TICK)
    OR A
    RET Z
    LD HL,IK_TIMER
    DEC (HL)
    RET NZ
    LD (HL),4
    LD A,(IK_CHAR)
    JP IK_PUSH

IK_PUSH:
    PUSH AF
    LD A,(IK_COUNT)
    CP 32
    JR Z,ik_full
    INC A
    LD (IK_COUNT),A
    LD A,(IK_TAIL)
    LD L,A
    LD H,0E9h
    INC A
    AND 31
    LD (IK_TAIL),A
    POP AF
    LD (HL),A
    RET
ik_full:
    POP AF
    RET

; 既存の生成表と修飾優先順位を共有。編集キーは表の0で無視し画面に触れない。
IK_DECODE:
    LD A,C
    ADD A,A
    ADD A,A
    ADD A,A
    ADD A,B
    CP 15
    JR Z,ik_return
    CP 78
    JR Z,ik_space
    LD E,A
    LD D,0
    LD A,(IK_MOD)
    LD HL,CTRL_CODE_TAB
    BIT 7,A
    JR Z,ik_lookup
    LD HL,GRPH_CODE_TAB
    BIT 4,A
    JR Z,ik_lookup
    LD HL,KANA_CODE_TAB
    BIT 5,A
    JR Z,ik_lookup
    LD HL,SHIFT_CODE_TAB
    BIT 6,A
    JR Z,ik_lookup
    LD A,(IK_CAPS)
    LD HL,CAPS_CODE_TAB
    BIT 7,A
    JR Z,ik_lookup
    LD HL,BASE_CODE_TAB
ik_lookup:
    ADD HL,DE
    LD A,(HL)
    RET
ik_return:
    LD A,13
    RET
ik_space:
    LD A,32
    RET
