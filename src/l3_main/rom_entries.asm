; docs/spec/main-rom-entry.md 第2版。戻りレジスタ規約は未確定。
; 37D2は継続送信へ直結。15の返送だけは既存subの2位置PAIRを
; 1バイトずつ返す。09など他の要求は既存の単発受信を使う。
; 状態は構造化セクタ操作と排他のDISK_STATEを共用する。
ENTRY_RX_PAIR EQU MM_ENTRY_RX_PAIR
ENTRY_RX_PENDING EQU MM_ENTRY_RX_PENDING
ENTRY_RX_BUFFER EQU MM_ENTRY_RX_BUFFER
; 呼び出し時のHLへ制御を渡し、呼び出し元への戻り番地を維持する。
ENTRY_3391:
    JP (HL)
ENTRY_37D2 EQU MAIN_SUB_SEND_CONT
ENTRY_37C9:
    PUSH AF
    XOR A
    LD (ENTRY_RX_PENDING),A
    LD (ENTRY_RX_PAIR),A
    POP AF
    CP 0x15
    JR NZ,_entry_send
    PUSH AF
    LD A,1
    LD (ENTRY_RX_PAIR),A
    POP AF
_entry_send:
    JP MAIN_SUB_SEND
ENTRY_3847:
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
    PUSH HL
    LD HL,ENTRY_RX_BUFFER
    CALL MAIN_SUB_RECV_PAIR
    POP HL
    RET C
    LD A,1
    LD (ENTRY_RX_PENDING),A
    LD A,(ENTRY_RX_BUFFER)
    RET

; B=論理トラック、C=1始まりセクタ、HL=256B、CY=書き。
; 自作の戻り規約: 読みCY=失敗、書きCY=通信失敗・A=sub状態。
; ドライブ1(bit0=0)。
ENTRY_369A:
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
    PUSH AF
    LD A,2
    LD IX,0x6663              ; 既存s2_write（入力A=drive, DE=座標, HL=本体）
    CALL CAPACITY_BANK_CALL
    RET C
    LD A,6                   ; 書込み完了を待って応答を消費する
    CALL MAIN_SUB_SEND
    RET C
    JP MAIN_SUB_RECV
