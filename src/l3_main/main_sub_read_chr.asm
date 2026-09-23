; main_sub_read_chr.asm — 任意座標の単一セクタREADと上限1回再試行
;
; 要求形の根拠は docs/spec/l3-subrom.md 1.36節（0x02・長さ5・末尾が
; [論理トラック=C*2+H,R]）。再試行1回の根拠は
; docs/notes/m6i-h-drop-the-fixed-wait-results.md、実装条件は
; docs/notes/m6i-i-arbitrary-coordinate-read-preregistration.md に従う。
; b37cad0で既知READ再試行時の入力Aを失いドライブAを読む欠陥があったため、
; 本再試行口は入力Aだけでなく座標D/Eも明示的に保存し、2回目へ渡す。
;
; MAIN_SUB_READ_CHR:
;   入力 A bit0=ドライブ選択、D=論理トラック(C*2+H)、E=R。
;   成功時 MAIN_SUB_MARK_SUCCESS=1。主側AF/BC/DE/HL/IX/IYを保存する。
;   要求送出後は MAIN_SUB_READ_KNOWN と同じスタック配置のまま、同ルーチンの
;   ack受信・256位置受信・後片付けへ合流する。
;
; MAIN_SUB_READ_CHR_RETRY:
;   同じ入力。待ちなし、初回失敗時だけ1回再試行する。
;   成功CY=0、2回とも失敗ならCY=1。

MAIN_SUB_CHR_LOGICAL_TRACK EQU 0E00Eh
MAIN_SUB_CHR_SECTOR        EQU 0E00Fh

MAIN_SUB_READ_CHR:
    PUSH AF
    PUSH BC
    PUSH DE
    PUSH HL
    PUSH IX
    PUSH IY

    AND 001h
    LD (MAIN_SUB_DRIVE_SELECT),A
    LD A,D
    LD (MAIN_SUB_CHR_LOGICAL_TRACK),A
    LD A,E
    LD (MAIN_SUB_CHR_SECTOR),A
    XOR A
    LD (MAIN_SUB_MARK_REQUEST),A
    LD (MAIN_SUB_MARK_RECV256),A
    LD (MAIN_SUB_MARK_SUCCESS),A
    LD (MAIN_SUB_MARK_TIMEOUT),A
    LD (MAIN_SUB_MARK_FAULT_WAIT),A
    LD (MAIN_SUB_MARK_FAULT_CONT),A
    LD (MAIN_SUB_MARK_FAULT_PAIR),A

    LD A,002h
    CALL MAIN_SUB_SEND
    JP C,_ms_read_timeout
    XOR A
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_ms_read_timeout
    LD A,(MAIN_SUB_DRIVE_SELECT)
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_ms_read_timeout
    LD A,(MAIN_SUB_CHR_LOGICAL_TRACK)
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_ms_read_timeout
    LD A,(MAIN_SUB_CHR_SECTOR)
    CALL MAIN_SUB_SEND_REQUEST_CONT
    JP C,_ms_read_timeout
    JP MAIN_SUB_READ_AFTER_REQUEST
MAIN_SUB_READ_CHR_END:

MAIN_SUB_READ_CHR_RETRY:
    PUSH AF
    PUSH DE
    CALL MAIN_SUB_READ_CHR
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A
    JR NZ,_ms_chr_retry_first_success
    POP DE                       ; 入口D/Eを2回目へ戻す
    POP AF                       ; 入口Aとフラグを2回目へ戻す
    CALL MAIN_SUB_READ_CHR
    LD A,(MAIN_SUB_MARK_SUCCESS)
    OR A                         ; 成功時CY=0を明示
    RET NZ
    SCF
    RET
_ms_chr_retry_first_success:
    POP DE
    POP AF
    OR A                         ; 保存されていたCYに依存せず成功CY=0
    RET
MAIN_SUB_READ_CHR_RETRY_END:
