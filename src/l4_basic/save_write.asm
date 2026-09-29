; SAVE書き込み通信。main/sub通信を含む構成でのみ組み込む。
; A=drive、D=論理トラック、E=R、HL=256バイト。
; 現行送信は自作subとの暫定形。l3-subrom.md 1.35節の6バイト制御
; レコードの先頭4バイトは未確定であり、この5位置を公式mainの制御
; レコードと同一とは主張できない。1.36節のsub視点受信runとmain視点
; SEND runも1対1ではない（同節・1.53節）。1.38節の受信位相だけを
; 根拠に送信値や確認応答の位置を補うことはできない。
SAVE_WRITE_DRIVE EQU 0E246h
SAVE_WRITE_TRACK EQU 0E247h
SAVE_WRITE_SECTOR EQU 0E248h
SAVE_WRITE_SOURCE EQU 0E249h
MAIN_SUB_WRITE_CHR:
    AND 1
    LD (SAVE_WRITE_DRIVE),A
    LD A,D
    LD (SAVE_WRITE_TRACK),A
    LD A,E
    LD (SAVE_WRITE_SECTOR),A
    LD (SAVE_WRITE_SOURCE),HL
    LD A,011h
    CALL MAIN_SUB_SEND
    RET C
    XOR A
    CALL MAIN_SUB_SEND_REQUEST_CONT
    RET C
    LD A,(SAVE_WRITE_DRIVE)
    CALL MAIN_SUB_SEND_REQUEST_CONT
    RET C
    LD A,(SAVE_WRITE_TRACK)
    CALL MAIN_SUB_SEND_REQUEST_CONT
    RET C
    LD A,(SAVE_WRITE_SECTOR)
    CALL MAIN_SUB_SEND_REQUEST_CONT
    RET C
    LD HL,(SAVE_WRITE_SOURCE)
    LD B,128
_swc_data:
    CALL MAIN_SUB_SEND_PAIR
    RET C
    DJNZ _swc_data
    LD A,7
    CALL MAIN_SUB_SEND
    RET C
    CALL MAIN_SUB_RECV
    RET
