; main-rom-entry.md 第6版 1.6。未確定のEF89等の分岐は実装しない。
ENTRY_7071:
    LD A,3                     ; カラー、ファンクションキー行なし
    LD (MM_SCR_MODE),A
    LD HL,(25<<8)|80
    LD (MM_FN_AUX),HL
    LD HL,25<<8
    LD (MM_SCR_WTOP),HL
    LD D,1
    CALL SCREEN_MODE_APPLY
    LD HL,07FC0h               ; CONSOLEと共通の窓計算
    XOR A
    CALL EXT_BANK_CALL
    CALL CLS_SCREEN            ; 既存CLSを使い、Okは出さない
    CALL 0xED36                ; RAM上のフック。戻り先は下記の復帰処理
ENTRY_7071_RETURN:
    CALL ENTRY_7071_RESTORE
    CALL ENTRY_7071_RESTORE
    CALL ENTRY_7071_RESTORE
    CALL ENTRY_7071_RESTORE
    RET
; この入口で観測された11DF相当の部分だけを定義する。
; 11DF単独の未確定のスタック契約へ一般化しない。
ENTRY_7071_RESTORE:
    IN A,(0x71)
    OUT (0x71),A
    OUT (0x71),A
    RET
