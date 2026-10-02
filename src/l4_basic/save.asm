; SAVE ,A の常駐入口。媒体管理・捕捉本体は拡張バンク2/3。
SAVE_CAPTURE_ACTIVE EQU 0E240h
SAVE_CAPTURE_IN EQU 0E24Dh
SAVE_DONE_FLAG EQU 0E24Bh

SAVE_STMT:
    LD A,2
    LD HL,06080h
    JP EXT_BANK_CALL

; LIST_RENDER_ALLはmainにある。バンク2からの汎用中継中に呼ばれるため、
; 捕捉時だけ限定的な入れ子中継でバンク3のRAM専用ルーチンへ渡す。
SAVE_CAPTURE_CHAR:
    LD (SAVE_CAPTURE_IN),A
    PUSH HL
    LD HL,06400h
    JR _save_capture_call
SAVE_CAPTURE_NEWLINE:
    PUSH HL
    LD HL,06410h
_save_capture_call:
    PUSH BC
    PUSH DE
    LD A,3
    CALL EXT_BANK_CALL_CAPTURE
    POP DE
    POP BC
    POP HL
    RET

; KILL/NAMEもSAVEと同じ通信完了フラグを使う。常駐部は入口だけ。
KILL_STMT:
    LD A,2
    LD HL,07100h
    JP EXT_BANK_CALL
NAME_STMT:
    LD A,2
    LD HL,07110h
    JP EXT_BANK_CALL
